# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import frappe
from frappe.model.document import Document
from frappe.utils import flt


class Bin(Document):
	def before_save(self):
		if self.get("__islocal") or not self.stock_uom:
			self.stock_uom = frappe.get_cached_value('Item', self.item_code, 'stock_uom')
		self.set_projected_qty()

	def set_projected_qty(self):
		self.projected_qty = (flt(self.actual_qty) + flt(self.ordered_qty)
			+ flt(self.indented_qty) + flt(self.planned_qty) - flt(self.reserved_qty)
			- flt(self.reserved_qty_for_production) - flt(self.reserved_qty_for_sub_contract))

	def get_first_sle(self):
		sle = frappe.db.sql("""
			select * from `tabStock Ledger Entry`
			where item_code = %s
			and warehouse = %s
			order by timestamp(posting_date, posting_time) asc, creation asc
			limit 1
		""", (self.item_code, self.warehouse), as_dict=1)
		return sle and sle[0] or None

	def update_reserved_qty_for_production(self):
		'''Update qty reserved for production from Production Item tables
			in open work orders'''
		self.reserved_qty_for_production = frappe.db.sql('''
			SELECT
				SUM(CASE WHEN ifnull(skip_transfer, 0) = 0 THEN
					item.required_qty - item.transferred_qty
				ELSE
					item.required_qty - item.consumed_qty END)
				END
			FROM `tabWork Order` pro, `tabWork Order Item` item
			WHERE
				item.item_code = %s
				and item.parent = pro.name
				and pro.docstatus = 1
				and item.source_warehouse = %s
				and pro.status not in ("Stopped", "Completed")
				and (item.required_qty > item.transferred_qty or item.required_qty > item.consumed_qty)
		''', (self.item_code, self.warehouse))[0][0]

		self.set_projected_qty()

		self.db_set('reserved_qty_for_production', flt(self.reserved_qty_for_production))
		self.db_set('projected_qty', self.projected_qty)

	def update_reserved_qty_for_sub_contracting(self):
		#reserved qty
		reserved_qty_for_sub_contract = frappe.db.sql('''
			select ifnull(sum(itemsup.required_qty),0)
			from `tabPurchase Order` po, `tabPurchase Order Item Supplied` itemsup
			where
				itemsup.rm_item_code = %s
				and itemsup.parent = po.name
				and po.docstatus = 1
				and po.is_subcontracted = 'Yes'
				and po.status != 'Closed'
				and po.per_received < 100
				and itemsup.reserve_warehouse = %s''', (self.item_code, self.warehouse))[0][0]

		#Get Transferred Entries
		materials_transferred = frappe.db.sql("""
			select
				ifnull(sum(CASE WHEN se.is_return = 1 THEN (transfer_qty * -1) ELSE transfer_qty END),0)
			from
				`tabStock Entry` se, `tabStock Entry Detail` sed, `tabPurchase Order` po
			where
				se.docstatus=1
				and se.purpose='Send to Subcontractor'
				and ifnull(se.purchase_order, '') !=''
				and (sed.item_code = %(item)s or sed.original_item = %(item)s)
				and se.name = sed.parent
				and se.purchase_order = po.name
				and po.docstatus = 1
				and po.is_subcontracted = 'Yes'
				and po.status != 'Closed'
				and po.per_received < 100
		""", {'item': self.item_code})[0][0]

		if reserved_qty_for_sub_contract > materials_transferred:
			reserved_qty_for_sub_contract = reserved_qty_for_sub_contract - materials_transferred
		else:
			reserved_qty_for_sub_contract = 0

		self.db_set('reserved_qty_for_sub_contract', reserved_qty_for_sub_contract)
		self.set_projected_qty()
		self.db_set('projected_qty', self.projected_qty)

def on_doctype_update():
	frappe.db.add_index("Bin", ["item_code", "warehouse"])


def update_stock(bin_name, args, allow_negative_stock=False, via_landed_cost_voucher=False):
	"""WARNING: This function is deprecated. Inline this function instead of using it."""
	from erpnext.stock.stock_ledger import repost_current_voucher

	repost_current_voucher(args, allow_negative_stock, via_landed_cost_voucher)
	update_qty(bin_name, args)

def get_bin_details(bin_name):
	return frappe.db.get_value('Bin', bin_name, ['actual_qty', 'ordered_qty',
	'reserved_qty', 'indented_qty', 'planned_qty', 'reserved_qty_for_production',
	'reserved_qty_for_sub_contract'], as_dict=1)

def update_qty(bin_name, args):
	from erpnext.controllers.stock_controller import future_sle_exists

	bin_details = get_bin_details(bin_name)
	# actual qty is already updated by processing current voucher
	actual_qty = bin_details.actual_qty

	# actual qty is not up to date in case of backdated transaction
	if future_sle_exists(args):
		actual_qty = frappe.db.get_value("Stock Ledger Entry",
				filters={
					"item_code": args.get("item_code"),
					"warehouse": args.get("warehouse"),
					"is_cancelled": 0
				},
				fieldname="qty_after_transaction",
				order_by="posting_date desc, posting_time desc, creation desc",
			) or 0.0

	ordered_qty = flt(bin_details.ordered_qty) + flt(args.get("ordered_qty"))
	reserved_qty = flt(bin_details.reserved_qty) + flt(args.get("reserved_qty"))
	indented_qty = flt(bin_details.indented_qty) + flt(args.get("indented_qty"))
	planned_qty = flt(bin_details.planned_qty) + flt(args.get("planned_qty"))


	# compute projected qty
	projected_qty = (flt(actual_qty) + flt(ordered_qty)
		+ flt(indented_qty) + flt(planned_qty) - flt(reserved_qty)
		- flt(bin_details.reserved_qty_for_production) - flt(bin_details.reserved_qty_for_sub_contract))

	frappe.db.set_value('Bin', bin_name, {
		'actual_qty': actual_qty,
		'ordered_qty': ordered_qty,
		'reserved_qty': reserved_qty,
		'indented_qty': indented_qty,
		'planned_qty': planned_qty,
		'projected_qty': projected_qty
	})
