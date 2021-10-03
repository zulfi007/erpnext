# Copyright (c) 2021, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt
import frappe
from frappe import _dict
from frappe.utils import floor


class ProductFiltersBuilder:
	def __init__(self, item_group=None):
		if not item_group:
			self.doc = frappe.get_doc("E Commerce Settings")
		else:
			self.doc = frappe.get_doc("Item Group", item_group)

		self.item_group = item_group

	def get_field_filters(self):
		if not self.item_group and not self.doc.enable_field_filters:
			return

		fields, filter_data = [], []
		filter_fields = [row.fieldname for row in self.doc.filter_fields] # fields in settings

		# filter valid field filters i.e. those that exist in Item
		item_meta = frappe.get_meta('Item', cached=True)
		fields = [item_meta.get_field(field) for field in filter_fields if item_meta.has_field(field)]

		for df in fields:
			item_filters, item_or_filters = {}, []
			link_doctype_values = self.get_filtered_link_doctype_records(df)

			if df.fieldtype == "Link":
				if self.item_group:
					item_or_filters.extend([
						["item_group", "=", self.item_group],
						["Website Item Group", "item_group", "=", self.item_group] # consider website item groups
					])

				# Get link field values attached to published items
				item_filters['published_in_website'] = 1
				item_values = frappe.get_all(
					"Item",
					fields=[df.fieldname],
					filters=item_filters,
					or_filters=item_or_filters,
					distinct="True",
					pluck=df.fieldname
				)

				values = list(set(item_values) & link_doctype_values) # intersection of both
			else:
				# table multiselect
				values = list(link_doctype_values)

			# Remove None
			if None in values:
				values.remove(None)

			if values:
				filter_data.append([df, values])

		return filter_data

	def get_filtered_link_doctype_records(self, field):
		"""
			Get valid link doctype records depending on filters.
			Apply enable/disable/show_in_website filter.
			Returns:
				set: A set containing valid record names
		"""
		link_doctype = field.get_link_doctype()
		meta = frappe.get_meta(link_doctype, cached=True) if link_doctype else None
		if meta:
			filters = self.get_link_doctype_filters(meta)
			link_doctype_values = set(d.name for d in frappe.get_all(link_doctype, filters))

		return link_doctype_values if meta else set()

	def get_link_doctype_filters(self, meta):
		"Filters for Link Doctype eg. 'show_in_website'."
		filters = {}
		if not meta:
			return filters

		if meta.has_field('enabled'):
			filters['enabled'] = 1
		if meta.has_field('disabled'):
			filters['disabled'] = 0
		if meta.has_field('show_in_website'):
			filters['show_in_website'] = 1

		return filters

	def get_attribute_filters(self):
		if not self.item_group and not self.doc.enable_attribute_filters:
			return

		attributes = [row.attribute for row in self.doc.filter_attributes]
		attribute_docs = [
			frappe.get_doc('Item Attribute', attribute) for attribute in attributes
		]

		valid_attributes = []

		for attr_doc in attribute_docs:
			selected_attributes = []
			for attr in attr_doc.item_attribute_values:
				or_filters = []
				filters= [
					["Item Variant Attribute", "attribute", "=", attr.parent],
					["Item Variant Attribute", "attribute_value", "=", attr.attribute_value]
				]
				if self.item_group:
					or_filters.extend([
						["item_group", "=", self.item_group],
						["Website Item Group", "item_group", "=", self.item_group]
					])

				if frappe.db.get_all("Item", filters, or_filters=or_filters, limit=1):
					selected_attributes.append(attr)

			if selected_attributes:
				valid_attributes.append(
					_dict(
						item_attribute_values=selected_attributes,
						name=attr_doc.name
					)
				)

		return valid_attributes

	def get_discount_filters(self, discounts):
		discount_filters = []

		# [25.89, 60.5] min max
		min_discount, max_discount = discounts[0], discounts[1]
		# [25, 60] rounded min max
		min_range_absolute, max_range_absolute = floor(min_discount), floor(max_discount)

		min_range = int(min_discount - (min_range_absolute % 10)) # 20
		max_range = int(max_discount - (max_range_absolute % 10)) # 60

		min_range = (min_range + 10) if min_range != min_range_absolute else min_range # 30 (upper limit of 25.89 in range of 10)
		max_range = (max_range + 10) if max_range != max_range_absolute else max_range # 60

		for discount in range(min_range, (max_range + 1), 10):
			label = f"{discount}% and below"
			discount_filters.append([discount, label])

		return discount_filters