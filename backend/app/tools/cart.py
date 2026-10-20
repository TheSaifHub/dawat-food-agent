"""Cart tools (D-025): add_to_cart, remove_from_cart, set_delivery, view_cart. Plain-JSON results.

Safety rules, in code (the database re-checks them: cart_items_guard, carts_delivery_guard, D-020/D-025):
  · user_id comes only from the verified token (app.auth). A user has at most ONE active cart (open or
    confirmed), always looked up BY user_id, so no tool can reach another user's cart.
  · Prices are never stored in the cart or taken from the caller: view_cart reads them live from menu_items
    and app.pricing computes every total. The agent quotes grand_total from here, never its own sum.
  · An item that has become unavailable (or whose branch closed) is listed under `unavailable` and left out of
    the totals, and the cart can't be confirmed until it is removed.
  · Delivery range (Saif, D-025): nothing is added from a branch more than MAX_DELIVERY_KM (8 km) from the
    delivery point ("too_far"); items that end up too far after a delivery change are flagged in
    `unavailable` with reason "too_far", exactly like unavailable items.
  · Changing a CONFIRMED cart (items or delivery point) re-opens it and clears the confirmation: the user must
    say "yes" again to the new total (confirmation_cleared: true tells the agent to ask).
Every change returns the whole cart, so the chat and the website always show the same server-computed total.
"""

import hashlib
import json
import re
import uuid

from psycopg import Connection

from app.pricing import MAX_DELIVERY_KM, MAX_QTY, quote, within_delivery_range
from app.tools.areas import resolve_area
from app.tools.menu import BRANCH_ID
from app.tools.reference import get_reference, km

ITEM_ID = re.compile(r"^r-[a-z0-9-]{1,80}__[a-z0-9]+(-[a-z0-9]+)*$")


def _invalid(message: str, **extra) -> dict:
    return {"status": "invalid_input", "message": message, **extra}


def _qty_ok(qty) -> bool:
    return not isinstance(qty, bool) and isinstance(qty, int) and 1 <= qty <= MAX_QTY


def _active_cart(conn: Connection, user_id: uuid.UUID, create: bool = False) -> dict | None:
    """The user's open or confirmed cart, locked for this transaction; created on first use if asked.
    A new cart is delivered to the user's default address, else their saved default area, else nowhere yet."""
    sql = ("select cart_id, status, delivery_area_id, address_id from public.carts "
           "where user_id = %s and status in ('open', 'confirmed') order by status = 'open' desc, created_at desc "
           "limit 1 for update")
    cart = conn.execute(sql, (user_id,)).fetchone()
    if cart or not create:
        return cart
    if not conn.execute("select 1 from public.users where user_id = %s", (user_id,)).fetchone():
        raise LookupError("no such user")
    addr = conn.execute("select address_id, area_id from public.addresses where user_id = %s and is_default",
                        (user_id,)).fetchone()
    area_id = addr["area_id"] if addr else None
    if area_id is None:
        pref = conn.execute("select value #>> '{}' as v from public.user_preferences "
                            "where user_id = %s and key = 'default_area'", (user_id,)).fetchone()
        if pref and pref["v"] in get_reference(conn).areas:
            area_id = pref["v"]
    conn.execute("""insert into public.carts (user_id, delivery_area_id, address_id) values (%s, %s, %s)
                    on conflict (user_id) where status = 'open' do nothing""",
                 (user_id, area_id, addr["address_id"] if addr else None))
    return conn.execute(sql, (user_id,)).fetchone()


def _delivery_point(conn: Connection, cart: dict) -> tuple[float, float] | None:
    """The saved address's coordinates, else the delivery area's centre, else None (not chosen yet)."""
    if cart["address_id"]:
        a = conn.execute("select lat, lon from public.addresses where address_id = %s", (cart["address_id"],)).fetchone()
        if a and a["lat"] is not None:
            return a["lat"], a["lon"]
    area = get_reference(conn).areas.get(cart["delivery_area_id"]) if cart["delivery_area_id"] else None
    return (area["lat"], area["lon"]) if area else None


def reopen(conn: Connection, cart_id) -> None:
    """Back to open: the confirmation and what was confirmed are cleared together (carts_confirmation_recorded)."""
    conn.execute("update public.carts set status = 'open', confirmed_at = null, confirmed_total = null, "
                 "confirmed_quote = null where cart_id = %s and status = 'confirmed'", (cart_id,))


def quote_fingerprint(cart_id: str, delivery: dict, bills: list[dict], grand_total: int) -> str:
    """A short fingerprint of exactly what the user is shown: every line with its price, each restaurant's fee and
    GST, the delivery point and the total. confirm_cart confirms THIS; place_order refuses if it has changed."""
    canon = {"cart": cart_id, "to": [delivery["area_id"], delivery["address_id"], delivery["lat"], delivery["lon"]],
             "b": [[b["branch_id"], [[i["item_id"], i["qty"], i["price"]] for i in b["items"]], b["delivery_fee"],
                    b["gst_food"], b["gst_delivery"], b["total"]] for b in bills], "t": grand_total}
    return hashlib.sha256(json.dumps(canon, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:20]


def _reopen_if_confirmed(conn: Connection, cart: dict) -> bool:
    if cart["status"] != "confirmed":
        return False
    reopen(conn, cart["cart_id"])
    cart["status"] = "open"
    return True


def _with_cart(conn: Connection, user_id: uuid.UUID, result: dict, cleared: bool) -> dict:
    out = {**result, "cart": view_cart(conn, user_id)}
    if cleared:
        out["confirmation_cleared"] = True
        out["message"] = ("The cart had been confirmed; this change re-opened it. Show the new total and ask the "
                          "user for a clear yes again before ordering.")
    return out


def add_to_cart(conn: Connection, user_id: uuid.UUID, item_id: str, branch_id: str, qty: int = 1) -> dict:
    if not isinstance(item_id, str) or not ITEM_ID.match(item_id):
        return _invalid("item_id must be an item id from get_menu or search_dishes")
    if not isinstance(branch_id, str) or not BRANCH_ID.match(branch_id):
        return _invalid("branch_id must be a branch id from search_restaurants or search_dishes")
    if not _qty_ok(qty):
        return _invalid(f"qty must be a whole number from 1 to {MAX_QTY}")

    item = conn.execute("""select m.item_id, m.restaurant_id, m.is_available, m.price, d.name
                           from public.menu_items m join public.dishes d using (dish_id) where m.item_id = %s""",
                        (item_id,)).fetchone()
    branch = conn.execute("select branch_id, restaurant_id, open_for_demo, lat, lon from public.branches where branch_id = %s",
                          (branch_id,)).fetchone()
    if item is None:
        return {"status": "unknown_item", "item_id": item_id, "message": "No such item. Use get_menu or search_dishes."}
    if branch is None or not branch["open_for_demo"]:
        return {"status": "branch_unavailable", "branch_id": branch_id,
                "message": "This branch is not taking Dawat orders. Find another branch with search_restaurants."}
    if item["restaurant_id"] != branch["restaurant_id"]:
        return {"status": "not_on_this_menu", "item_id": item_id, "branch_id": branch_id,
                "message": "This item is not on that branch's menu. Use the branch_id that came with the item."}
    if not item["is_available"]:
        return {"status": "item_unavailable", "item_id": item_id, "name": item["name"],
                "message": f"{item['name']} is not available right now. Say so; do not add a substitute silently."}

    try:
        cart = _active_cart(conn, user_id, create=True)
    except LookupError:
        return {"status": "unknown_user", "message": "Sign in again: this account has no Dawat profile."}
    point = _delivery_point(conn, cart)
    if point is not None:
        dist = km(branch["lat"], branch["lon"], *point)
        if not within_delivery_range(dist):
            return {"status": "too_far", "item_id": item_id, "branch_id": branch_id, "distance_km": round(dist, 1),
                    "max_km": MAX_DELIVERY_KM,
                    "message": f"This place is {dist:.1f} km from the delivery point, beyond our {MAX_DELIVERY_KM} km "
                               "delivery range. Tell the user it is too far to deliver; nothing was added."}
    have = conn.execute("select qty from public.cart_items where cart_id = %s and item_id = %s and branch_id = %s",
                        (cart["cart_id"], item_id, branch_id)).fetchone()
    new_qty = (have["qty"] if have else 0) + qty
    if new_qty > MAX_QTY:
        return {"status": "qty_limit", "max_qty": MAX_QTY, "in_cart": have["qty"] if have else 0,
                "message": f"At most {MAX_QTY} of one item per order."}
    cleared = _reopen_if_confirmed(conn, cart)
    conn.execute("""insert into public.cart_items (cart_id, item_id, branch_id, qty) values (%s, %s, %s, %s)
                    on conflict (cart_id, item_id, branch_id) do update set qty = excluded.qty""",
                 (cart["cart_id"], item_id, branch_id, new_qty))
    return _with_cart(conn, user_id, {"status": "ok", "added": {"item_id": item_id, "name": item["name"], "qty": qty,
                                                                 "now_in_cart": new_qty}}, cleared)


def remove_from_cart(conn: Connection, user_id: uuid.UUID, item_id: str, branch_id: str | None = None,
                     qty: int | None = None) -> dict:
    """Remove `qty` of an item (all of it if qty is omitted). branch_id is needed only if the same item is in
    the cart from two branches."""
    if not isinstance(item_id, str) or not ITEM_ID.match(item_id):
        return _invalid("item_id must be an item id from the cart")
    if branch_id is not None and (not isinstance(branch_id, str) or not BRANCH_ID.match(branch_id)):
        return _invalid("branch_id must be a branch id from the cart")
    if qty is not None and not _qty_ok(qty):
        return _invalid(f"qty must be a whole number from 1 to {MAX_QTY}, or omitted to remove the item")

    cart = _active_cart(conn, user_id)
    lines = [] if cart is None else conn.execute(
        "select branch_id, qty from public.cart_items where cart_id = %s and item_id = %s"
        + (" and branch_id = %s" if branch_id else ""),
        (cart["cart_id"], item_id, *([branch_id] if branch_id else []))).fetchall()
    if not lines:
        return {"status": "not_in_cart", "item_id": item_id, "message": "That item is not in the cart.",
                "cart": view_cart(conn, user_id)}
    if len(lines) > 1:
        return {"status": "needs_branch", "item_id": item_id, "branches": [ln["branch_id"] for ln in lines],
                "message": "This item is in the cart from more than one branch. Ask which one."}
    line = lines[0]
    cleared = _reopen_if_confirmed(conn, cart)
    if qty is None or qty >= line["qty"]:
        conn.execute("delete from public.cart_items where cart_id = %s and item_id = %s and branch_id = %s",
                     (cart["cart_id"], item_id, line["branch_id"]))
        left = 0
    else:
        left = line["qty"] - qty
        conn.execute("update public.cart_items set qty = %s where cart_id = %s and item_id = %s and branch_id = %s",
                     (left, cart["cart_id"], item_id, line["branch_id"]))
    return _with_cart(conn, user_id, {"status": "ok", "removed": {"item_id": item_id, "now_in_cart": left}}, cleared)


def set_delivery(conn: Connection, user_id: uuid.UUID, area: str | None = None, address_id: str | None = None) -> dict:
    """Deliver to one of the user's saved addresses, or to an area (its centre is used for distances)."""
    if (area is None) == (address_id is None):
        return _invalid("give exactly one of area or address_id")
    if area is not None:
        if not isinstance(area, str) or not area.strip():
            return _invalid("area must be text, e.g. 'Madhapur'")
        resolved = resolve_area(get_reference(conn), area)
        if resolved["status"] != "ok":
            return {"status": resolved["status"], "area_resolution": resolved, "message": resolved["message"]}
        area_id, addr_id = resolved["area"]["area_id"], None
    else:
        try:
            addr_uuid = uuid.UUID(str(address_id))
        except ValueError:
            return _invalid("address_id must be one of the user's address ids")
        addr = conn.execute("select address_id, area_id from public.addresses where address_id = %s and user_id = %s",
                            (addr_uuid, user_id)).fetchone()
        if addr is None:                                  # someone else's address looks exactly like a missing one
            return {"status": "unknown_address", "message": "No saved address with that id for this user."}
        area_id, addr_id = addr["area_id"], addr["address_id"]
    try:
        cart = _active_cart(conn, user_id, create=True)
    except LookupError:
        return {"status": "unknown_user", "message": "Sign in again: this account has no Dawat profile."}
    changed = (cart["delivery_area_id"], cart["address_id"]) != (area_id, addr_id)
    cleared = changed and _reopen_if_confirmed(conn, cart)
    if changed:
        conn.execute("update public.carts set delivery_area_id = %s, address_id = %s where cart_id = %s",
                     (area_id, addr_id, cart["cart_id"]))
    return _with_cart(conn, user_id, {"status": "ok"}, cleared)


def view_cart(conn: Connection, user_id: uuid.UUID) -> dict:
    cart = conn.execute("""select c.cart_id, c.status, c.delivery_area_id, c.address_id, c.confirmed_total,
                                  c.confirmed_quote, a.label
                           from public.carts c left join public.addresses a on a.address_id = c.address_id
                           where c.user_id = %s and c.status in ('open', 'confirmed')
                           order by c.status = 'open' desc, c.created_at desc limit 1""", (user_id,)).fetchone()
    if cart is None:
        return {"status": "empty", "cart_id": None, "branches": [], "grand_total": 0,
                "message": "The cart is empty."}
    ref = get_reference(conn)
    rows = conn.execute("""
        select ci.item_id, ci.branch_id, ci.qty, m.price, m.is_available, d.name, d.is_veg, d.spice_level, d.serves,
               b.restaurant_id, b.label as branch_label, b.area_id as branch_area, b.lat, b.lon, b.open_for_demo,
               r.name as restaurant_name
        from public.cart_items ci join public.menu_items m using (item_id) join public.dishes d using (dish_id)
             join public.branches b on b.branch_id = ci.branch_id join public.restaurants r on r.restaurant_id = b.restaurant_id
        where ci.cart_id = %s order by r.name, b.label, d.name""", (cart["cart_id"],)).fetchall()

    area = ref.areas.get(cart["delivery_area_id"]) if cart["delivery_area_id"] else None
    point = _delivery_point(conn, cart)
    delivery = None if area is None else {"area_id": area["area_id"], "area": area["name"],
                                          "address_id": str(cart["address_id"]) if cart["address_id"] else None,
                                          "address_label": cart["label"],
                                          "lat": round(point[0], 6), "lon": round(point[1], 6)}
    unavailable, groups = [], {}
    for r in rows:
        line = {"item_id": r["item_id"], "name": r["name"], "price": r["price"], "qty": r["qty"],
                "line_total": r["price"] * r["qty"], "is_veg": r["is_veg"], "spice_level": r["spice_level"],
                "serves": r["serves"]}
        dist = km(r["lat"], r["lon"], *point) if point else 0.0
        reason = ("branch_closed" if not r["open_for_demo"] else "unavailable" if not r["is_available"]
                  else "too_far" if point and not within_delivery_range(dist) else None)
        if reason:
            unavailable.append({**line, "branch_id": r["branch_id"], "restaurant": r["restaurant_name"], "reason": reason,
                                **({"distance_km": round(dist, 1), "max_km": MAX_DELIVERY_KM} if reason == "too_far" else {})})
            continue
        g = groups.setdefault(r["branch_id"], {
            "branch_id": r["branch_id"], "restaurant_id": r["restaurant_id"], "restaurant": r["restaurant_name"],
            "branch_label": r["branch_label"], "branch_area": ref.areas[r["branch_area"]]["name"],
            "distance_km": dist, "items": []})
        g["items"].append(line)

    base = {"cart_id": str(cart["cart_id"]), "cart_status": cart["status"], "delivery": delivery,
            **({"confirmed_total": cart["confirmed_total"]} if cart["status"] == "confirmed" else {}),
            "unavailable": unavailable}
    if not groups:
        return {"status": "empty", **base, "branches": [], "grand_total": 0,
                "can_confirm": False, "message": "The cart is empty." + (" Some items are no longer available."
                                                                         if unavailable else "")}
    if point is None:
        branches = [{k: v for k, v in g.items() if k != "distance_km"} |
                    {"items_total": sum(i["line_total"] for i in g["items"])} for g in groups.values()]
        return {"status": "needs_delivery_area", **base, "branches": branches,
                "items_total": sum(b["items_total"] for b in branches), "grand_total": None, "can_confirm": False,
                "message": "Ask where to deliver (an area or a saved address) and call set_delivery; delivery fees "
                           "and the total depend on it. Do not state a total yet."}

    q = quote([{**g, "lines": g["items"]} for g in groups.values()])
    issues = (["Some items can't be delivered now (unavailable, closed, or too far for this delivery point): "
               "remove them, or change the delivery point, before confirming."] if unavailable else [])
    can_confirm = not unavailable
    fingerprint = ({"quote_id": quote_fingerprint(base["cart_id"], delivery, q["branches"], q["grand_total"])}
                   if can_confirm else {})
    return {"status": "ok", **base, **q, "can_confirm": can_confirm, **fingerprint,
            **({"issues": issues} if issues else {}),
            "message": "Quote grand_total and the per-restaurant delivery fees exactly as given; never add them up "
                       "yourself. To order: show this summary, get a clear yes, then confirm_cart with this quote_id."}
