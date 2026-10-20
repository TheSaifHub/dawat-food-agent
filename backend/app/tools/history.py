"""get_user_history (D-027): the user's past checkouts, newest first. Plain-JSON results.

A checkout is what the user placed in one go; it holds one order per restaurant (D-026). Everything comes from the
order snapshot (order_items), so a past order shows what was charged then, even if the menu price changed since.
Only the token's user's orders are read: there is no parameter that could name another user.
"""

import uuid

from psycopg import Connection

from app.tools import tracking
from app.tools.orders import order_number

DEFAULT_LIMIT, MAX_LIMIT = 10, 20


def get_user_history(conn: Connection, user_id: uuid.UUID, limit: int = DEFAULT_LIMIT) -> dict:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        return {"status": "invalid_input", "message": f"limit must be a whole number from 1 to {MAX_LIMIT}"}
    tracking.advance(conn, user_id)                  # simulated progress that is due (D-061); the user's own orders only
    heads = conn.execute("""select checkout_id, min(created_at) as placed_at from public.orders where user_id = %s
                            group by checkout_id order by placed_at desc, checkout_id limit %s""",
                         (user_id, limit + 1)).fetchall()
    has_more, heads = len(heads) > limit, heads[:limit]
    if not heads:
        return {"status": "empty", "checkouts": [], "has_more": False, "message": "The user has no past orders."}
    ids = [h["checkout_id"] for h in heads]
    orders = conn.execute("""
        select o.order_id, o.order_no, o.is_sample, o.checkout_id, o.branch_id, o.status, o.payment_status, o.items_total,
               o.delivery_fee, o.taxes, o.grand_total, r.restaurant_id, r.name as restaurant, b.label as branch_label,
               a.name as delivery_area
        from public.orders o join public.branches b using (branch_id) join public.restaurants r using (restaurant_id)
             join public.areas a on a.area_id = o.delivery_area_id
        where o.user_id = %s and o.checkout_id = any(%s) order by r.name, b.label""", (user_id, ids)).fetchall()
    items = conn.execute("""select order_id, item_id, dish_name, unit_price, qty, is_veg from public.order_items
                            where order_id = any(%s) order by dish_name""", ([o["order_id"] for o in orders],)).fetchall()
    by_order: dict = {}
    for i in items:
        by_order.setdefault(i["order_id"], []).append(
            {"item_id": i["item_id"], "name": i["dish_name"], "price_paid": i["unit_price"], "qty": i["qty"],
             "line_total": i["unit_price"] * i["qty"], "is_veg": i["is_veg"]})
    by_checkout: dict = {}
    for o in orders:
        by_checkout.setdefault(o["checkout_id"], []).append(
            {"order_id": str(o["order_id"]), "order_number": order_number(o["order_no"]), "is_sample": o["is_sample"],
             "restaurant_id": o["restaurant_id"], "restaurant": o["restaurant"],
             "branch_id": o["branch_id"], "branch_label": o["branch_label"], "order_status": o["status"],
             "payment_status": o["payment_status"], "items": by_order.get(o["order_id"], []),
             "items_total": o["items_total"], "delivery_fee": o["delivery_fee"], "taxes": o["taxes"],
             "total": o["grand_total"], "delivery_area": o["delivery_area"]})
    checkouts = [{"checkout_id": str(h["checkout_id"]), "placed_at": h["placed_at"].isoformat(),
                  "orders": by_checkout[h["checkout_id"]],
                  "grand_total": sum(o["total"] for o in by_checkout[h["checkout_id"]])} for h in heads]
    return {"status": "ok", "checkouts": checkouts, "has_more": has_more,
            "message": "Past orders with the prices paid then. Today's prices may differ: to reorder, add the items to "
                       "the cart and quote view_cart's total, never these old totals."}
