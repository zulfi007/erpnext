import frappe

jenvs = {
    "methods": [
        "trip_items:erpnext.jinja.trip_items",
    ],
    # "filters": [
    #     "app.jinja.filters",
    #     "app.utils.format_currency"
    # ]
}

# METHODS
@frappe.whitelist()
def trip_items(doc=None):
    values = {'sales_invoices': doc}
    res=frappe.db.sql("""
                select item_name, stock_uom, sum(stock_qty) as qty from `tabSales Invoice Item`
                where parent in %(sales_invoices)s 
                group by item_name 
                """,values=values ,as_dict=True)
    return res