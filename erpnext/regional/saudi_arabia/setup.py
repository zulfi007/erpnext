# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
from frappe.permissions import add_permission, update_permission_property
from erpnext.regional.united_arab_emirates.setup import make_custom_fields as uae_custom_fields, add_print_formats
from erpnext.regional.saudi_arabia.wizard.operations.setup_ksa_vat_setting import create_ksa_vat_setting
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def setup(company=None, patch=True):
	uae_custom_fields()
	add_print_formats()
	add_permissions()
	make_custom_fields()

def add_permissions():
	"""Add Permissions for KSA VAT Setting."""
	add_permission('KSA VAT Setting', 'All', 0)
	for role in ('Accounts Manager', 'Accounts User', 'System Manager'):
		add_permission('KSA VAT Setting', role, 0)
		update_permission_property('KSA VAT Setting', role, 0, 'write', 1)
		update_permission_property('KSA VAT Setting', role, 0, 'create', 1)

	"""Enable KSA VAT Report"""
	frappe.db.set_value('Report', 'KSA VAT', 'disabled', 0)

def make_custom_fields():
	"""Create Custom fields
	- QR code Image file
	- Company Name in Arabic
	- Address in Arabic
	"""
	custom_fields = {
		'Sales Invoice': [
			dict(
				fieldname='qr_code',
				label='QR Code',
				fieldtype='Attach Image',
				read_only=1, no_copy=1, hidden=1
			)
		],
		'Address': [
			dict(
				fieldname='address_in_arabic',
				label='Address in Arabic',
				fieldtype='Data',
				insert_after='address_line2'
			)
		],
		'Company': [
			dict(
				fieldname='company_name_in_arabic',
				label='Company Name In Arabic',
				fieldtype='Data',
				insert_after='company_name'
			)
		]
	}

	create_custom_fields(custom_fields, update=True)

def update_regional_tax_settings(country, company):
	create_ksa_vat_setting(company)
