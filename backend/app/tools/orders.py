"""confirm_cart, place_order, track_order (D-026). Plain-JSON results.

THE CONFIRMATION GATE, in code (the database re-checks it: orders_require_confirmed_cart, D-020; and
carts_confirmation_recorded, 0007):
  1. view_cart shows a quote with a quote_id (a fingerprint of every line, price, fee, GST and the delivery point).
  2. The agent shows that summary and gets a clear "yes". Only then: confirm_cart(cart_id, quote_id). It confirms
     THAT quote; if the cart changed in between, it refuses (stale_quote) so the user is never confirmed into
     something they weren't shown. From chat, code also checks the yes itself (Saif, Session 12; D-030): the
     user's latest message, passed by the agent runtime and never written by the LLM, must be a clear yes in
     English, Hinglish or Telugu (app.tools.consent), or nothing is confirmed (no_clear_yes). From the website
     the Confirm button is the yes.
  3. place_order(cart_id) recomputes the quote. If anything differs from what was confirmed (a price, an item now
     unavailable, a fee), the cart is re-opened and the new total returned: the user must say yes again (Saif,
     Session 10). Otherwise one order per restaurant is created, sharing one checkout_id, with a snapshot of the
     items at the price charged and of the delivery point.
Every lookup is by (id AND user_id from the verified token): another user's cart or order is answered exactly like
one that doesn't exist. Orders are created only after a verified Razorpay test payment (Phase 8, D-061; see
app/tools/payments.py); place_order is the internal step that creates them.
"""

import re
import uuid

from psycopg import Connection

from app.tools import tracking
from app.tools.cart import reopen, view_cart
from app.tools.consent import consent

SOURCES = ("chat", "website")

NOT_FOUND = {"status": "not_found", "message": "No such cart or order for this user."}


ORDER_NUMBER = re.compile(r"^\s*#?\s*(?:dw\s*-?\s*)?(\d{1,12})\s*$", re.IGNORECASE)


def order_number(order_no: int) -> str:
    """The short label people see and say (Saif, Session 15): DW1042. Migration 0013 numbers orders from 1001."""
    return f"DW{order_no}"


def _uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _invalid(message: str) -> dict:
    return {"status": "invalid_input", "message": message}


def confirm_cart(conn: Connection, user_id: uuid.UUID, cart_id: str, quote_id: str, *, source: str,
                 user_message: str | None = None) -> dict:
    """Call ONLY after the user clearly said yes to the summary that carried this quote_id.
    `source` has no default on purpose: a chat call can't skip the yes check by leaving it out."""
    if source not in SOURCES:
        return _invalid(f"source must be one of {', '.join(SOURCES)}")
    if source == "chat":
        said = consent(user_message)
        if said["consent"] != "yes":
            return {"status": "no_clear_yes", "consent": said,
                    "message": ("The user said no or asked to wait. Nothing was ordered and nothing was cancelled: "
                                "the cart still has all its items. Tell the user plainly that the order was NOT "
                                "placed and their items are still in the cart, and ask what they'd like to do "
                                "(change something, remove items, or order later). Never say it was cancelled."
                                if said["consent"] == "no" else
                                "The user's latest message isn't a clear yes. Nothing was confirmed. Show the cart "
                                "summary again and ask them to say yes to place the order.")}
    cid = _uuid(cart_id)
    if cid is None:
        return _invalid("cart_id must be the cart_id from view_cart")
    if not isinstance(quote_id, str) or not quote_id:
        return _invalid("quote_id must be the quote_id from the view_cart summary the user said yes to")
    cart = conn.execute("select cart_id, status, confirmed_quote from public.carts where cart_id = %s and user_id = %s "
                        "for update", (cid, user_id)).fetchone()
    if cart is None or cart["status"] not in ("open", "confirmed"):
        return {**NOT_FOUND, "message": "No open cart with this id for this user (it may already be ordered)."}
    current = view_cart(conn, user_id)
    if current.get("cart_id") != str(cid):
        return NOT_FOUND
    if cart["status"] == "confirmed" and cart["confirmed_quote"] == quote_id == current.get("quote_id"):
        return {"status": "ok", "already_confirmed": True, "cart": current,
                "message": "Already confirmed. place_order can be called."}
    if current["status"] != "ok" or not current.get("can_confirm"):
        return {"status": "cannot_confirm", "cart": current,
                "message": "This cart can't be confirmed yet: " + current.get("message", "") +
                           (" " + " ".join(current["issues"]) if current.get("issues") else "")}
    if current["quote_id"] != quote_id:
        return {"status": "stale_quote", "cart": current,
                "message": "The cart changed since that summary was shown. Show this new summary and ask again."}
    conn.execute("""update public.carts set status = 'confirmed', confirmed_at = now(), confirmed_total = %s,
                    confirmed_quote = %s where cart_id = %s""", (current["grand_total"], quote_id, cid))
    return {"status": "ok", "cart": view_cart(conn, user_id),
            "message": f"Confirmed: ₹{current['grand_total']}. Now call place_order with this cart_id."}


def confirmed_cart_gate(conn: Connection, user_id: uuid.UUID, cart_id: str) -> tuple[dict | None, dict | None, dict | None]:
    """The checks every way of ordering shares: (answer, cart_row, current_view). If `answer` is not None, that is
    the reply and nothing may be created. Otherwise the cart (locked FOR UPDATE) is the user's, confirmed, and its
    quote is exactly what the user confirmed. A changed quote re-opens the cart (the user must say yes again)."""
    cid = _uuid(cart_id)
    if cid is None:
        return _invalid("cart_id must be the cart_id from view_cart"), None, None
    cart = conn.execute("""select cart_id, status, confirmed_quote, confirmed_total, delivery_area_id, address_id
                           from public.carts where cart_id = %s and user_id = %s for update""", (cid, user_id)).fetchone()
    if cart is None:
        return NOT_FOUND, None, None
    if cart["status"] == "ordered":
        return {"status": "already_placed", **_checkout_of_cart(conn, user_id, cid),
                "message": "This cart was already ordered; nothing new was placed."}, None, None
    if cart["status"] != "confirmed":
        return {"status": "not_confirmed", "cart": view_cart(conn, user_id) if cart["status"] == "open" else None,
                "message": "Not confirmed. Show the cart summary, get a clear yes, then confirm_cart. Nothing was ordered."}, None, None

    current = view_cart(conn, user_id)
    if current.get("quote_id") != cart["confirmed_quote"]:
        reopen(conn, cid)
        return {"status": "quote_changed", "confirmed_total": cart["confirmed_total"],
                "new_total": current.get("grand_total"), "cart": view_cart(conn, user_id),
                "message": "Something changed since the user said yes (a price, an item's availability or a fee). "
                           "Nothing was ordered and the cart is open again. Show the new summary and ask for a yes "
                           "again."}, None, None
    return None, cart, current


def payment_required(conn: Connection, user_id: uuid.UUID, cart_id: str) -> dict:
    """What ordering means now (Phase 8, D-061): an order exists only after a verified Razorpay test payment. This is
    the answer the website's POST /orders and the chat's place_order give. It runs the same checks as before (so a
    cart that isn't confirmed, or whose quote changed, is refused exactly as before) and creates NOTHING; the user
    pays for the confirmed total through POST /payments/start and /payments/verify (app.tools.payments)."""
    answer, cart, current = confirmed_cart_gate(conn, user_id, cart_id)
    if answer is not None:
        return answer
    return {"status": "payment_required", "cart_id": str(cart["cart_id"]), "quote_id": cart["confirmed_quote"],
            "grand_total": current["grand_total"],
            "message": f"The order is NOT placed yet. The app now shows the user a Pay ₹{current['grand_total']} button "
                       "(test payment). The order is created only after they pay. Tell them to tap Pay to finish; "
                       "never say the order is placed, confirmed or on its way."}


def place_order(conn: Connection, user_id: uuid.UUID, cart_id: str, *, payment: dict | None = None) -> dict:
    """CREATES the orders of a confirmed cart. Fails unless the cart is confirmed and its quote is unchanged.

    Not reachable from the website or the chat any more (they answer payment_required): only app.tools.payments
    (after a verified payment, `payment` = {"order_id", "payment_id"}) and the demo accounts' sample orders call it.
    tests/test_payments.py scans the source to keep it that way."""
    answer, cart, current = confirmed_cart_gate(conn, user_id, cart_id)
    if answer is not None:
        return answer
    cid = cart["cart_id"]
    paid = (payment["order_id"], payment["payment_id"]) if payment else (None, None)

    checkout_id = uuid.uuid4()
    d = current["delivery"]
    orders = []
    for b in current["branches"]:
        oid = conn.execute("""
            insert into public.orders (checkout_id, user_id, cart_id, branch_id, address_id, items_total, delivery_fee,
                                       taxes, grand_total, delivery_area_id, delivery_lat, delivery_lon,
                                       payment_status, razorpay_order_id, razorpay_payment_id)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning order_id""",
            (checkout_id, user_id, cid, b["branch_id"], d["address_id"], b["items_total"], b["delivery_fee"], b["taxes"],
             b["total"], d["area_id"], d["lat"], d["lon"], "paid" if payment else "pending", *paid)).fetchone()["order_id"]
        with conn.cursor() as cur:
            cur.executemany("""insert into public.order_items (order_id, item_id, dish_name, unit_price, qty, is_veg)
                               values (%s, %s, %s, %s, %s, %s)""",
                            [(oid, i["item_id"], i["name"], i["price"], i["qty"], i["is_veg"]) for i in b["items"]])
        conn.execute("insert into public.order_status_events (order_id, status) values (%s, 'placed')", (oid,))
        orders.append(oid)
    conn.execute("update public.carts set status = 'ordered' where cart_id = %s", (cid,))
    return {"status": "ok", **_checkout(conn, user_id, checkout_id),
            "message": "Order placed" + (" and paid (test payment)" if payment else "; payment is pending") +
                       ". Share the order numbers (DW…) and totals exactly as given; do not invent an ETA."}


def _checkout(conn: Connection, user_id: uuid.UUID, checkout_id) -> dict:
    rows = conn.execute("""
        select o.order_id, o.order_no, o.branch_id, o.status, o.payment_status, o.items_total, o.delivery_fee, o.taxes,
               o.grand_total, o.created_at, r.name as restaurant, b.label as branch_label
        from public.orders o join public.branches b using (branch_id) join public.restaurants r using (restaurant_id)
        where o.checkout_id = %s and o.user_id = %s order by r.name, b.label""", (checkout_id, user_id)).fetchall()
    return {"checkout_id": str(checkout_id),
            "orders": [{"order_id": str(r["order_id"]), "order_number": order_number(r["order_no"]),
                        "restaurant": r["restaurant"], "branch_label": r["branch_label"],
                        "status": r["status"], "payment_status": r["payment_status"], "items_total": r["items_total"],
                        "delivery_fee": r["delivery_fee"], "taxes": r["taxes"], "total": r["grand_total"]} for r in rows],
            "grand_total": sum(r["grand_total"] for r in rows)}


def _checkout_of_cart(conn: Connection, user_id: uuid.UUID, cart_id) -> dict:
    row = conn.execute("select checkout_id from public.orders where cart_id = %s and user_id = %s limit 1",
                       (cart_id, user_id)).fetchone()
    return _checkout(conn, user_id, row["checkout_id"]) if row else {}


def track_order(conn: Connection, user_id: uuid.UUID, order_id: str) -> dict:
    oid = _uuid(order_id)
    number = ORDER_NUMBER.match(order_id) if oid is None and isinstance(order_id, str) else None
    if oid is None and number is None:
        return _invalid("order_id must be an order number like DW1042, or an order id from place_order or the history")
    o = conn.execute(f"""
        select o.order_id, o.order_no, o.checkout_id, o.status, o.payment_status, o.items_total, o.delivery_fee, o.taxes,
               o.grand_total, o.created_at, o.delivery_area_id, o.is_sample, o.branch_id, r.name as restaurant, b.label as branch_label,
               a.name as delivery_area, o.delivery_lat, o.delivery_lon, b.lat as b_lat, b.lon as b_lon,
               extract(epoch from now() - o.created_at)::float as age
        from public.orders o join public.branches b using (branch_id) join public.restaurants r using (restaurant_id)
             join public.areas a on a.area_id = o.delivery_area_id
        where {"o.order_id" if oid else "o.order_no"} = %s and o.user_id = %s""",
                     (oid if oid else int(number.group(1)), user_id)).fetchone()
    if o is None:
        return NOT_FOUND
    oid = o["order_id"]
    simulated = o["payment_status"] == "paid" and not o["is_sample"]
    if simulated:                                     # D-061: write the progress events that are due, then read them
        tracking.advance(conn, user_id, oid)
        o = {**o, "status": conn.execute("select status from public.orders where order_id = %s", (oid,)).fetchone()["status"]}
    start, end = (o["b_lat"], o["b_lon"]), (o["delivery_lat"], o["delivery_lon"])
    items = conn.execute("select item_id, dish_name, unit_price, qty, is_veg from public.order_items "
                         "where order_id = %s order by dish_name", (oid,)).fetchall()
    events = conn.execute("select status, created_at from public.order_status_events where order_id = %s "
                          "order by created_at, event_id", (oid,)).fetchall()
    return {"status": "ok", "order_id": str(o["order_id"]), "order_number": order_number(o["order_no"]),
            "checkout_id": str(o["checkout_id"]),
            "order_status": o["status"], "payment_status": o["payment_status"],
            "restaurant": o["restaurant"], "branch_id": o["branch_id"], "branch_label": o["branch_label"],
            "delivery_area": o["delivery_area"], "is_sample": o["is_sample"],
            "items": [dict(i) for i in items], "items_total": o["items_total"], "delivery_fee": o["delivery_fee"],
            "taxes": o["taxes"], "total": o["grand_total"], "placed_at": o["created_at"].isoformat(),
            "timeline": [{"status": e["status"], "at": e["created_at"].isoformat()} for e in events],
            "simulated_tracking": simulated,
            "route": {"from": {"lat": start[0], "lon": start[1]}, "to": {"lat": end[0], "lon": end[1]}},
            "rider": tracking.rider_position(o["age"], start, end) if simulated else None,
            "next_update_in_s": tracking.next_update_in(o["age"]) if simulated and o["status"] not in tracking.FINAL else None,
            "message": "Report the status and timeline exactly as given. Progress is simulated for this demo. There is no ETA: do not invent one."}
