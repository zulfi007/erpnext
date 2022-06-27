// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Sales Partner Commission Summary"] = {
	"filters": [

		{
			fieldname: "sales_partner",
			label: __("Sales Partner"),
			fieldtype: "Link",
			options: "Sales Partner"
		},
		{
			fieldname: "doctype",
			label: __("Document Type"),
			fieldtype: "Select",
			options: "Sales Order\nDelivery Note\nSales Invoice",
			default: "Sales Invoice"
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today()
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company")
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "territory",
			label: __("Territory"),
			fieldtype: "Link",
			options: "Territory",
		},
	],
	onload: function (report) {
		report.page.add_inner_button(__("Pay-out Commission"), function () {
			let indexes = []
			$('.dt-scrollable').find(":input[type=checkbox]").each((idx, row) => {
				if (row.checked) {
					indexes.push($(row.closest(".dt-cell")).data("row-index"))
				}
			});

			const rows = frappe.query_report.data.filter((x, idx) => indexes.indexOf(idx) >= 0);
			const rows_eligable_for_commisssion = rows.filter(r => r.paid_percentage > 90)

			const commission_total = rows_eligable_for_commisssion.map(r => r.commission_outstanding).reduce((t, v) => t + v, 0)

			frappe.prompt([
				{
					label: 'Employee Name',
					fieldname: 'employee',
					fieldtype: 'Link',
					options: 'Employee'
				},
				{
					label: 'Commission',
					fieldname: 'commission',
					fieldtype: 'Data',
					readonly: 1,
					default: commission_total
				},
			], (values) => {
				frappe.call({
					"method": "erpnext.selling.report.sales_partner_commission_summary.sales_partner_commission_summary.allocate_sales_partner_commission",
					"args": {
						'params': rows_eligable_for_commisssion.map(r => ({
							'name': r.name,
							'commission_outstanding': r.commission_outstanding,
							'sales_partner': r.sales_partner,
							'employee': values.employee
						}))

					}
				});

			})
		}).css("font-weight", "bold").css("color", "red");


	},
	get_datatable_options(options) {
		return Object.assign(options, {
			checkboxColumn: true
		});
	}
}
