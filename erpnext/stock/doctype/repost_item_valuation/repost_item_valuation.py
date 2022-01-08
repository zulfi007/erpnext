# Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, get_link_to_form, get_weekday, now, nowtime, today
from frappe.utils.user import get_users_with_role
from rq.timeouts import JobTimeoutException

import erpnext
from erpnext.accounts.utils import (
	check_if_stock_and_account_balance_synced,
	update_gl_entries_after,
)
from erpnext.stock.stock_ledger import repost_future_sle


class RepostItemValuation(Document):
	def validate(self):
		self.set_status(write=False)
		self.reset_field_values()
		self.set_company()

	def reset_field_values(self):
		if self.based_on == 'Transaction':
			self.item_code = None
			self.warehouse = None

		self.allow_negative_stock = self.allow_negative_stock or \
				cint(frappe.db.get_single_value("Stock Settings", "allow_negative_stock"))

	def set_company(self):
		if self.based_on == "Transaction":
			self.company = frappe.get_cached_value(self.voucher_type, self.voucher_no, "company")
		elif self.warehouse:
			self.company = frappe.get_cached_value("Warehouse", self.warehouse, "company")

	def set_status(self, status=None, write=True):
		status = status or self.status
		if not status:
			self.status = 'Queued'
		else:
			self.status = status
		if write:
			self.db_set('status', self.status)

	def on_submit(self):
		if not frappe.flags.in_test or self.flags.dont_run_in_test or frappe.flags.dont_execute_stock_reposts:
			return

		frappe.enqueue(repost, timeout=1800, queue='long',
			job_name='repost_sle', now=frappe.flags.in_test, doc=self)

	@frappe.whitelist()
	def restart_reposting(self):
		self.set_status('Queued', write=False)
		self.current_index = 0
		self.distinct_item_and_warehouse = None
		self.items_to_be_repost = None
		self.db_update()

	def deduplicate_similar_repost(self):
		""" Deduplicate similar reposts based on item-warehouse-posting combination."""
		if self.based_on != "Item and Warehouse":
			return

		filters = {
			"item_code": self.item_code,
			"warehouse": self.warehouse,
			"name": self.name,
			"posting_date": self.posting_date,
			"posting_time": self.posting_time,
		}

		frappe.db.sql("""
			update `tabRepost Item Valuation`
			set status = 'Skipped'
			WHERE item_code = %(item_code)s
				and warehouse = %(warehouse)s
				and name != %(name)s
				and TIMESTAMP(posting_date, posting_time) > TIMESTAMP(%(posting_date)s, %(posting_time)s)
				and docstatus = 1
				and status = 'Queued'
				and based_on = 'Item and Warehouse'
				""",
			filters
		)

def on_doctype_update():
	frappe.db.add_index("Repost Item Valuation", ["warehouse", "item_code"], "item_warehouse")


def repost(doc):
	try:
		if not frappe.db.exists("Repost Item Valuation", doc.name):
			return

		doc.set_status('In Progress')
		if not frappe.flags.in_test:
			frappe.db.commit()

		repost_sl_entries(doc)
		repost_gl_entries(doc)

		doc.set_status('Completed')

	except (Exception, JobTimeoutException):
		frappe.db.rollback()
		traceback = frappe.get_traceback()
		frappe.log_error(traceback)

		message = frappe.message_log.pop()
		if traceback:
			message += "<br>" + "Traceback: <br>" + traceback
		frappe.db.set_value(doc.doctype, doc.name, 'error_log', message)

		notify_error_to_stock_managers(doc, message)
		doc.set_status('Failed')
		raise
	finally:
		frappe.db.commit()

def repost_sl_entries(doc):
	if doc.based_on == 'Transaction':
		repost_future_sle(doc=doc, voucher_type=doc.voucher_type, voucher_no=doc.voucher_no,
			allow_negative_stock=doc.allow_negative_stock, via_landed_cost_voucher=doc.via_landed_cost_voucher)
	else:
		repost_future_sle(args=[frappe._dict({
			"item_code": doc.item_code,
			"warehouse": doc.warehouse,
			"posting_date": doc.posting_date,
			"posting_time": doc.posting_time
		})], allow_negative_stock=doc.allow_negative_stock, via_landed_cost_voucher=doc.via_landed_cost_voucher)

def repost_gl_entries(doc):
	if not cint(erpnext.is_perpetual_inventory_enabled(doc.company)):
		return

	if doc.based_on == 'Transaction':
		ref_doc = frappe.get_doc(doc.voucher_type, doc.voucher_no)
		items, warehouses = ref_doc.get_items_and_warehouses()
	else:
		items = [doc.item_code]
		warehouses = [doc.warehouse]

	update_gl_entries_after(doc.posting_date, doc.posting_time,
		warehouses, items, company=doc.company)

def notify_error_to_stock_managers(doc, traceback):
	recipients = get_users_with_role("Stock Manager")
	if not recipients:
		get_users_with_role("System Manager")

	subject = _("Error while reposting item valuation")
	message = (_("Hi,") + "<br>"
		+ _("An error has been appeared while reposting item valuation via {0}")
			.format(get_link_to_form(doc.doctype, doc.name)) + "<br>"
		+ _("Please check the error message and take necessary actions to fix the error and then restart the reposting again.")
	)
	frappe.sendmail(recipients=recipients, subject=subject, message=message)

def repost_entries():
	if not in_configured_timeslot():
		return

	riv_entries = get_repost_item_valuation_entries()

	for row in riv_entries:
		doc = frappe.get_doc('Repost Item Valuation', row.name)
		if doc.status in ('Queued', 'In Progress'):
			repost(doc)
			doc.deduplicate_similar_repost()

	riv_entries = get_repost_item_valuation_entries()
	if riv_entries:
		return

	for d in frappe.get_all('Company', filters= {'enable_perpetual_inventory': 1}):
		check_if_stock_and_account_balance_synced(today(), d.name)

def get_repost_item_valuation_entries():
	return frappe.db.sql(""" SELECT name from `tabRepost Item Valuation`
		WHERE status in ('Queued', 'In Progress') and creation <= %s and docstatus = 1
		ORDER BY timestamp(posting_date, posting_time) asc, creation asc
	""", now(), as_dict=1)


def in_configured_timeslot(repost_settings=None, current_time=None):
	"""Check if current time is in configured timeslot for reposting."""

	if repost_settings is None:
		repost_settings = frappe.get_cached_doc("Stock Reposting Settings")

	if not repost_settings.limit_reposting_timeslot:
		return True

	if get_weekday() == repost_settings.limits_dont_apply_on:
		return True

	start_time = repost_settings.start_time
	end_time = repost_settings.end_time

	now_time = current_time or nowtime()

	if start_time < end_time:
		return end_time >= now_time >= start_time
	else:
		return now_time >= start_time or now_time <= end_time
