import frappe
import math
from frappe.utils import cint, cstr, flt, getdate, add_days
from erpnext.accounts.doctype.loyalty_program.loyalty_program import get_loyalty_program_details_with_points


def get_carton_conversion_factor(item_code, carton_uom='Carton'):
    return frappe.db.get_value(
        "UOM Conversion Detail",
        {"parent": item_code,"parenttype": 'Item' ,"uom": carton_uom},
        "conversion_factor",
    )

def calculate_loyalty_points_by_item(items, loyalty_program):
    lp = frappe.get_doc("Loyalty Program", loyalty_program)
    lp_rules = {rule.item_code: rule for rule in lp.custom_item_reward_rules} 

    total_points = 0
    for item in items:
        item_code = item.get("item_code")
        rule = lp_rules.get(item_code)  # Use dictionary lookup for efficiency
        
        if not rule:
            continue
        
        collection_factor = rule.get("collection_factor") or 0
    
        carton_qty = get_carton_conversion_factor(item_code)
        adjusted_qty = math.ceil(item.get("stock_qty") / carton_qty) if carton_qty else 0
        points_earned_per_item = collection_factor * adjusted_qty
        total_points += points_earned_per_item

    return total_points

def update_loyalty_point(docc):
    returned_amount = docc.get_returned_amount()
    current_amount = flt(docc.grand_total) - cint(docc.loyalty_amount)
    eligible_amount = current_amount - returned_amount
    lp_details = get_loyalty_program_details_with_points(
        docc.customer,
        company=docc.company,
        current_transaction_amount=current_amount,
        loyalty_program=docc.loyalty_program,
        expiry_date=docc.posting_date,
        include_expired_entry=True,
    )
    if (
        lp_details
        and getdate(lp_details.from_date) <= getdate(docc.posting_date)
        and (not lp_details.to_date or getdate(lp_details.to_date) >= getdate(docc.posting_date))
        and lp_details.custom_collection_rule_type == 'Item'
    ):
        
        points_earned = cint(calculate_loyalty_points_by_item(docc.items, docc.loyalty_program))

        filters = {
            "company": docc.company,
            "loyalty_program": lp_details.loyalty_program,
            "invoice_type": docc.doctype,
            "invoice": docc.name,
        }

        # Try to find existing loyalty point entry for this invoice
        lp= frappe.get_value("Loyalty Point Entry", filters,'name')

        if lp:
            loyalty_point_entry= frappe.get_doc("Loyalty Point Entry", lp)

            loyalty_point_entry.purchase_amount = eligible_amount
            loyalty_point_entry.loyalty_points = points_earned
        else:
                # Fallback to creating a new entry if none exists (for future compatibility)
            loyalty_point_entry = frappe.get_doc(
                {
                    "doctype": "Loyalty Point Entry",
                    "company": docc.company,
                    "loyalty_program": lp_details.loyalty_program,
                    "loyalty_program_tier": lp_details.tier_name,
                    "customer": docc.customer,
                    "invoice_type": docc.doctype,
                    "invoice": docc.name,
                    "loyalty_points" : points_earned,
                    "purchase_amount": eligible_amount,
					"expiry_date": add_days(docc.posting_date, lp_details.expiry_duration),
					"posting_date": docc.posting_date,
                }
            )

        loyalty_point_entry.flags.ignore_permissions = 1
        loyalty_point_entry.save()
      
def update_against_si_doc_items(si, against_si_doc):
    """
    Updates the quantities of items in the against_si_doc by subtracting
    the quantities from the corresponding items in the current sales invoice (si).

    Args:
        si (Sales Invoice): The current sales invoice.
        against_si_doc (Sales Invoice): The sales invoice being returned against.

    Raises:
        ValueError: If an item code mismatch is found.
    """

    if not against_si_doc.items:
        return against_si_doc  # No items to update, return original doc

    return_items = {item.item_code: item for item in against_si_doc.items}
    items=[]

    for si_item in si.items:
        item = return_items.get(si_item.get("item_code"))
        if not item:
            frappe.throw(
                message="Item code '{}' not found in return against invoice.".format(
                    si_item.get("item_code")
                ),
                title="Item Code Mismatch",
            )

        # Handle potential zero or negative stock situations gracefully
        returned_qty = min(si_item.get("stock_qty"), item.get("stock_qty"))
        item.stock_qty += returned_qty
        items.append(item)

    against_si_doc.items=items

    return against_si_doc

@frappe.whitelist()
def make_loyalty_point_entry(si, method=None):
    if (
        not si.is_return
        and not si.is_consolidated
        and si.loyalty_program
        and not si.dont_create_loyalty_points
    ):
        update_loyalty_point(si)
    elif si.is_return and si.return_against and not si.is_consolidated and si.loyalty_program:
        against_si_doc = frappe.get_doc("Sales Invoice", si.return_against)
        against_si_doc.delete_loyalty_point_entry()

        against_si_doc =     update_against_si_doc_items(si , against_si_doc)

        update_loyalty_point(against_si_doc)

def on_cancel(doc, method=None):
    if not doc.is_return and not doc.is_consolidated and doc.loyalty_program:
        doc.delete_loyalty_point_entry()
    elif doc.is_return and doc.return_against and not doc.is_consolidated and doc.loyalty_program:
        against_si_doc = frappe.get_doc("Sales Invoice", doc.return_against)
        against_si_doc.delete_loyalty_point_entry()
        update_loyalty_point(against_si_doc)