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
                select i.item_name, i.stock_uom, 
                min(conv.conversion_factor) as conversion_factor,
                min(conv.uom) as bulk_uom
                sum(i.stock_qty) as qty from `tabSales Invoice Item` as i
                left join `tabUOM Conversion Detail` as conv
                on conv.parent = i.item_code
                where i.parent in %(sales_invoices)s and conv.conversion_factor > 1
                group by i.item_name 
                """,values=values ,as_dict=True)
    return res