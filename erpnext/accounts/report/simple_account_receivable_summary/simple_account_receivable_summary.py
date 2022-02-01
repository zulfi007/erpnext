# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _, scrub
from frappe.utils import flt, cint,getdate
from six import iteritems
from frappe.query_builder.functions import Sum,Max
from pypika import AliasedQuery
from functools import reduce
from itertools import accumulate, groupby

from soupsieve import select


def execute(filters=None):
	return ReceivableSummaryReport().run(filters)

class ReceivableSummaryReport():
	def run(self, filters):
		self.get_columns()
		self.get_data(filters)
		message=""
		chart=[]
		self.get_summary(filters)
		return self.columns, self.data

	def get_data(self, filters):
		self.data=[]
		gl	= 	frappe.qb.DocType('GL Entry')
		customerTable	= 	frappe.qb.DocType('Customer')
		invoiceTable = frappe.qb.DocType('Sales Invoice')
		kpi	= frappe.qb.DocType('Customer KPI')
		debit = 	Sum(gl.debit).as_("debit")
		credit = 	Sum(gl.credit).as_("credit")
		customer = (frappe.qb.from_(customerTable)
					.left_join(kpi)
					.on(customerTable.name == kpi.parent)
					.select(customerTable.star,kpi.last_payment_amount,kpi.last_payment_date,
							kpi.last_invoice_date,kpi.last_invoice_amount)
					.groupby(customerTable.name)
		)

		# invoices = (frappe.qb.from_(invoiceTable)
		# 			.select(invoiceTable.customer_name,Sum(invoiceTable.outstanding_amount).as_("outstanding_amount"))
		# 			.where(invoiceTable.docstatus==1)
		# 			.where(invoiceTable.status=='Overdue')
		# 			.where(invoiceTable.due_date < getdate())
		# 			.groupby(invoiceTable.customer_name)
		# 			)

		query = (frappe.qb.from_(gl)

			.select(gl.party,(debit-credit).as_("balance"))
			.where(gl.party_type=='Customer')
			.where(gl.docstatus==1)
			.where(gl.is_cancelled==0)
			.groupby(gl.party)
			.orderby(gl.party)
		)

		cust=AliasedQuery("Cust")
		query=(query.with_(customer,'Cust')
			.left_join(cust)
			.on(gl.party==AliasedQuery("Cust").customer_name)
			.select(cust.customer_name,cust.primary_address,cust.sales_person,cust.last_payment_amount, cust.last_payment_date,cust.last_invoice_amount,cust.last_invoice_date)
			)
		
		# Inv=AliasedQuery('Inv')

		# query=(query.with_(invoices,'Inv')		
		# 	.left_join(Inv)
		# 	.on(gl.party==Inv.customer_name)
		# 	.select(Inv.outstanding_amount))
		
		if filters.customer_name is not None :
			query=query.where(gl.party==filters.customer_name)
		if filters.territory is not None :
			query=query.where(AliasedQuery("Cust").territory==filters.territory)
		if filters.sales_person is not None :
			query=query.where(AliasedQuery("Cust").sales_person==filters.sales_person)
		if filters.address is not None :
			query=query.where(AliasedQuery("Cust").primary_address.like('%'+str(filters.address)+'%'))
		if filters.min_balance is not None :
			query=query.having((debit-credit)>filters.min_balance)

		data=query.run(as_dict=True)

		self.total_balance=0
		self.total_count=0	

		if data is not None:
			balance_list=list(map(lambda value: value.balance,data))
			self.total_count=len(balance_list)
			self.total_balance=reduce(lambda total,value: total+value,balance_list,0)
		
		self.data=data
	

	def get_summary(self,filters):
		self.summary = [{	
				"value": self.total_count,
				"label": _("Total Customers"),
				"fieldtype": "Data",
			},
			{
				"value": '',
				"label": _("Total OverDue"),
				"fieldtype": "Data",
			},
			{
				"value": round(self.total_balance,2),
				"label": _("Total Balance"),
				"fieldtype": "Currency",
				'options': 'currency',
			},
			
			]

	def get_columns(self):
		self.columns =  [
			{
				'fieldname': 'party',
				'label': _('NAME'),
				'fieldtype': 'Link',
				'options': 'Customer',
				'align': 'left',
				'width': 250
			},
			{
				'fieldname': 'primary_address',
				'label': _('Address'),
				'fieldtype': 'Data',
				'width': 150,
				'align': 'left'
			},
				{
				'fieldname': 'last_payment_date',
				'label': _('Last Payment Date'),
				'fieldtype': 'Data',
				'width': 59,

			},
			{
				'fieldname': 'last_payment_amount',
				'label': _('Last Payment Amout'),
				'fieldtype': 'Data',
				'align': 'right',
				'width': 59
			},
			{
				'fieldname': 'last_invoice_date',
				'label': _('Last Invoice Date'),
				'fieldtype': 'Data',
				'align': 'right',
				'width': 59
			},
			{
				'fieldname': 'last_invoice_amount',
				'label': _('Last Invoice Amount'),
				'fieldtype': 'Data',
				'align': 'right',
				'width': 59
			},
			{
				'fieldname': 'balance',
				'label': _('Balance'),
				'fieldtype': 'Float',
				'align': 'right',
				'width': 150
			},
		]
