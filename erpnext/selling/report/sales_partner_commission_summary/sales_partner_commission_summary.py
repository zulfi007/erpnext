# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


import json
import frappe
from frappe import _, msgprint, whitelist
from frappe.query_builder import DocType
from frappe.utils import today




def execute(filters=None):
	if not filters:
		filters = {}

	columns = get_columns(filters)
	data = get_entries(filters)

	return columns, data


def get_columns(filters):
	if not filters.get("doctype"):
		msgprint(_("Please select the document type first"), raise_exception=1)

	columns = [
		{
			"label": _(filters["doctype"]),
			"options": filters["doctype"],
			"fieldname": "name",
			"fieldtype": "Link",
			"width": 140,
		},
		{
			"label": _("Customer"),
			"options": "Customer",
			"fieldname": "customer",
			"fieldtype": "Link",
			"width": 140,
		},
		{
			"label": _("Territory"),
			"options": "Territory",
			"fieldname": "territory",
			"fieldtype": "Link",
			"width": 100,
		},
		{
			"label": _("Posting Date"), 
			"fieldname": "posting_date", 
			"fieldtype": "Date", 
			"width": 100
		},
		{
			"label": _("Amount"), 
			"fieldname": "amount", 
			"fieldtype": "Currency", 
			"width": 120
		},
		{
			"label": _("Sales Partner"),
			"options": "Sales Partner",
			"fieldname": "sales_partner",
			"fieldtype": "Link",
			"width": 140,
		},
		{
			"label": _("%age Paid"),
			"fieldname": "paid_percentage",
			"fieldtype": "Percent",
			"non_negative": 1,
			"width": 120,

		},	
		{
			"label": _("Total Commission"),
			"fieldname": "total_commission",
			"fieldtype": "Currency",
			"non_negative": 1,
			"width": 120,
		},

		{
			"label": _("PaidOut Commission"),
			"fieldname": "dispersed_commission",
			"fieldtype": "Currency",
			"width": 120,
		},
		{
			"label": _("Outstanding Commission"),
			"fieldname": "commission_outstanding",
			"fieldtype": "Currency",
			"width": 120,		
		},


	]

	return columns


def get_entries(filters):
	date_field = "transaction_date" if filters.get("doctype") == "Sales Order" else "posting_date"

	conditions = get_conditions(filters, date_field)
	entries = frappe.db.sql(
		"""
		SELECT
			name, customer, territory, {0} as posting_date, base_net_total as amount,
			sales_partner, commission_rate, total_commission, dispersed_commission,  CEILING((1-outstanding_amount/base_net_total)*100) as paid_percentage,
			(total_commission - dispersed_commission) as commission_outstanding
		FROM
			`tab{1}`
		WHERE
			{2} and docstatus = 1 and sales_partner is not null
			and sales_partner != '' order by name desc, sales_partner
		""".format(
			date_field, filters.get("doctype"), conditions
		),
		filters,
		as_dict=1,
	)
	return entries


def get_conditions(filters, date_field):
	conditions = "1=1"

	for field in ["company", "customer", "territory"]:
		if filters.get(field):
			conditions += " and {0} = %({1})s".format(field, field)

	if filters.get("sales_partner"):
		conditions += " and sales_partner = %(sales_partner)s"

	if filters.get("from_date"):
		conditions += " and {0} >= %(from_date)s".format(date_field)

	if filters.get("to_date"):
		conditions += " and {0} <= %(to_date)s".format(date_field)

	return conditions

@whitelist()
def allocate_sales_partner_commission(params):
	# update the sales order and sales invoice 
	# create salary incentive with reference

	sales_invoice = DocType("Sales Invoice") 
	sales_partner = DocType("Sales Partner")
	employee_incentive = DocType("Employee Incentive")  
	query =frappe.qb.update(sales_invoice)
	items=json.loads(params)
	total_incentive_amount = 0
	
	sales_partner=items[0]['sales_partner']

	company =frappe.db.get_default("Company")
	currency = frappe.db.get_value("Company", company, "default_currency", cache=True)
	salary_component = frappe.db.get_value('Sales Partner',sales_partner,'commission_account')
	employee=items[0]["employee"]
	employee_name, department = frappe.db.get_value('Employee',employee,['employee_name','department'])
	refs= {}

	for item in items:
		total_incentive_amount +=item['commission_outstanding']
		refs.update({item['name']:item['commission_outstanding']})

		query=	query.set(sales_invoice.dispersed_commission, item['commission_outstanding']) \
				.where(sales_invoice.name == item['name'])
		
	query.run()
	frappe.get_doc({
		"doctype": "Employee Incentive",
		"docstatus":0,
		"company":company,
		"currency":currency,
		"employee":employee,
		"employee_name": employee_name,
		"department": department,
		"salary_component":salary_component,
		"payroll_date":today(),
		"incentive_amount":total_incentive_amount,
		"reference":json.dumps(refs)
	}).insert()
	frappe.msgprint(salary_component +" of "+currency+" "+ str(total_incentive_amount) +" has been Created for "+employee_name)