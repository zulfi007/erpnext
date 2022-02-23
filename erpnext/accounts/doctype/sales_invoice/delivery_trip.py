import frappe
from frappe import _
from frappe.contacts.doctype.address.address import get_company_address
from frappe.model.mapper import get_mapped_doc
from frappe.utils import cint, flt

from erpnext.controllers.accounts_controller import get_taxes_and_charges
from erpnext.controllers.selling_controller import SellingController

@frappe.whitelist()
def make_delivery_trip(source_name, target_doc=None):
	def update_stop_details(source_doc, target_doc, source_parent):
		target_doc.customer = source_parent.customer
		target_doc.address = source_parent.customer_address
		target_doc.customer_address = source_parent.address_display
		target_doc.contact = source_parent.contact_person
		target_doc.customer_contact = source_parent.contact_display
		target_doc.grand_total = source_parent.grand_total

		# Append unique Sales Invoices in Delivery Trip
		sales_invoices.append(target_doc.sales_invoice)

	sales_invoices = []

	doclist = get_mapped_doc("Sales Invoice", source_name, {
		"Sales Invoice": {
			"doctype": "Delivery Trip",
			"validation": {
				"docstatus": ["=", 1]
			}
		},
		"Sales Invoice Item": {
			"doctype": "Delivery Stop",
			"field_map": {
				"parent": "sales_invoice"
			},
			"condition": lambda item: item.parent not in sales_invoices,
			"postprocess": update_stop_details
		}
	}, target_doc)

	return doclist

@frappe.whitelist()
def update_sales_order_delivery_status(source,status,is_delete=False):
	ilist=frappe.db.get_list('Sales Invoice Item',
		filters={
			'parent': source
		},
		fields=['sales_order', 'so_detail','item_code','stock_qty'],
	)
	
	for i in ilist:
		so_details=frappe.db.get_value('Sales Order Item', i.so_detail,['item_code', 'stock_qty','parent'] ,as_dict=True )
		if so_details is not None and (so_details.stock_qty - i.stock_qty)>0 and status =='Delivered':
			status='Partly Delivered'
		elif so_details is not None and (so_details.stock_qty - i.stock_qty)==0 and status =='Delivered':
			status='Fully Delivered'
	
	m_status='To Deliver'

	if "Not Delivered" in status:
		m_status='To Deliver'
	elif "In Transit" in status:
		m_status='To Deliver'
	elif 'Partly Delivered' in status:
		m_status='Completed'
	elif 'Fully Delivered' in status:
		m_status='Completed'
	
	
	if ilist is not None :
		frappe.db.set_value('Sales Order', ilist[0].sales_order, {
				'delivery_status': status,
				'status': m_status
			})    
