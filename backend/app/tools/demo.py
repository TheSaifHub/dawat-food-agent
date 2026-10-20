"""Per-visitor demo accounts (Phase 7b, D-048): "Try as Priya / Arjun".

The browser signs the visitor in anonymously (a fresh, private Supabase account), then POST /demo/start seeds that
account ONCE as a persona:
  · the persona's name and saved preferences (source = 'seed', like load_db.py's demo users);
  · one fictional default address in the persona's area;
  · 3 past orders made through the REAL tools (add_to_cart → view_cart → confirm_cart as website → place_order), so
    the confirmation-gate trigger, the server totals and the item snapshots all apply. Only afterwards are their
    dates moved back, their status set to delivered, and is_sample set, so the site can label them "sample orders".

Rules:
  · Only an anonymous account can become a persona, so an email account's real preferences are never overwritten.
  · The persona is claimed atomically (`demo_persona is null`), once per account. The same persona again is
    `already_started`; the other one is `persona_locked` (sign out for a new account to switch).
  · Everything happens in the request's one transaction: if anything fails, nothing is kept, claim included.
  · Sample dishes are found with the same search the agent uses, filtered by the persona's diet and spice, so a
    vegetarian persona can never get a meat sample. A dish that can't be found or added is skipped, never invented.
"""

import uuid

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.tools.cart import add_to_cart, view_cart
from app.tools.dishes import search_dishes
from app.tools.menu import get_menu
from app.tools.orders import confirm_cart, place_order

# The visitor personas mirror two of load_db.py's fixed demo users (D-021), with the same preferences.
PERSONAS = {
    "priya": {
        "display_name": "Priya (demo)",
        "prefs": {"diet": "vegetarian", "max_spice": 1, "default_area": "madhapur", "language": "en"},
        "address": {"label": "Home", "line1": "Flat 101, Demo Residency (fictional)", "area_id": "madhapur"},
        "is_veg": True,
        # (days ago, first dish searched in the area, qty, [(another dish at the same branch, qty)])
        "orders": [(13, "masala dosa", 2, [("Filter Coffee", 2)]),
                   (7, "paneer butter masala", 1, [("Butter Naan", 2)]),
                   (2, "south indian meals", 1, [("Masala Chaas", 1)])],
    },
    "arjun": {
        "display_name": "Arjun (demo)",
        "prefs": {"diet": "non_vegetarian", "max_spice": 3, "default_area": "gachibowli", "language": "hinglish"},
        "address": {"label": "Office", "line1": "Tower 2, Demo Tech Park (fictional)", "area_id": "gachibowli"},
        "is_veg": None,
        "orders": [(12, "chicken dum biryani", 1, [("Chicken 65", 1)]),
                   (6, "apollo fish", 1, [("Butter Naan", 2)]),
                   (2, "mutton biryani", 1, [("Double ka Meetha", 1)])],
    },
}

# The simulated timeline of a delivered sample order, in minutes after it was placed.
TIMELINE = [("confirmed", 2), ("preparing", 5), ("picked_up", 24), ("on_the_way", 27), ("delivered", 48)]
ORDER_HOUR_IST = {13: 20, 12: 13, 7: 21, 6: 20, 2: 13}       # dinner / lunch, so the history looks lived-in


def _fits(item: dict, persona: dict) -> bool:
    if persona["is_veg"] and not item["is_veg"]:
        return False
    return item["spice_level"] <= persona["prefs"]["max_spice"]


def _sample_lines(conn: Connection, persona: dict, query: str, qty: int, extras: list) -> list[tuple[str, str, int]]:
    """(item_id, branch_id, qty) lines for one sample order, all at one branch; [] if the first dish isn't found."""
    found = search_dishes(conn, query, area=persona["address"]["area_id"], is_veg=persona["is_veg"],
                          max_spice=persona["prefs"]["max_spice"])
    first = next((r for r in found.get("results") or [] if _fits(r, persona)), None)
    if first is None:
        return []
    branch_id = first["branch"]["branch_id"]
    lines = [(first["item_id"], branch_id, qty)]
    menu = get_menu(conn, branch_id).get("items") or []
    for name, extra_qty in extras:
        item = next((i for i in menu if i["name"] == name and _fits(i, persona)), None)
        if item is not None:
            lines.append((item["item_id"], branch_id, extra_qty))
    return lines


class _Skip(Exception):
    """A sample order that couldn't be made: its savepoint is rolled back, so no half-filled cart is left behind."""


def _place_sample(conn: Connection, user_id: uuid.UUID, lines: list, days_ago: int) -> str | None:
    """Through the real tools; then backdated. Returns the order id, or None (nothing kept) if it couldn't be ordered."""
    try:
        with conn.transaction():
            return _place_sample_or_skip(conn, user_id, lines, days_ago)
    except _Skip:
        return None


def _place_sample_or_skip(conn: Connection, user_id: uuid.UUID, lines: list, days_ago: int) -> str:
    for item_id, branch_id, qty in lines:
        if add_to_cart(conn, user_id, item_id, branch_id, qty).get("status") != "ok":
            raise _Skip
    cart = view_cart(conn, user_id)
    if cart.get("status") != "ok" or not cart.get("can_confirm"):
        raise _Skip
    if confirm_cart(conn, user_id, cart["cart_id"], cart["quote_id"], source="website")["status"] != "ok":
        raise _Skip
    placed = place_order(conn, user_id, cart["cart_id"])
    if placed["status"] != "ok" or len(placed["orders"]) != 1:
        raise _Skip
    order_id = placed["orders"][0]["order_id"]
    at = conn.execute("""select (date_trunc('day', now() at time zone 'Asia/Kolkata') - make_interval(days => %s)
                                 + make_interval(hours => %s)) at time zone 'Asia/Kolkata' as t""",
                      (days_ago, ORDER_HOUR_IST.get(days_ago, 13))).fetchone()["t"]
    conn.execute("update public.orders set created_at = %s, status = 'delivered', is_sample = true where order_id = %s",
                 (at, order_id))
    conn.execute("update public.order_status_events set created_at = %s where order_id = %s and status = 'placed'",
                 (at, order_id))
    for status, minutes in TIMELINE:
        conn.execute("""insert into public.order_status_events (order_id, status, created_at)
                        values (%s, %s, %s + make_interval(mins => %s))""", (order_id, status, at, minutes))
    conn.execute("update public.carts set created_at = %s, confirmed_at = %s where cart_id = %s",
                 (at, at, cart["cart_id"]))
    return order_id


def start_demo(conn: Connection, user_id: uuid.UUID, persona: str, *, is_anonymous: bool) -> dict:
    """Seed this (anonymous) account as a persona, once. The user id and is_anonymous come from the verified token."""
    p = PERSONAS.get(persona) if isinstance(persona, str) else None
    if p is None:
        return {"status": "invalid_input", "message": f"persona must be one of {', '.join(PERSONAS)}"}
    if not is_anonymous:
        return {"status": "not_anonymous",
                "message": "Demo personas are only for the 'Try as' accounts. Your own account is left as it is."}
    claimed = conn.execute("""update public.users set demo_persona = %s, display_name = %s
                              where user_id = %s and demo_persona is null returning user_id""",
                           (persona, p["display_name"], user_id)).fetchone()
    if claimed is None:
        current = conn.execute("select demo_persona from public.users where user_id = %s", (user_id,)).fetchone()
        if current is None:
            return {"status": "unknown_user", "message": "This account no longer exists. Please sign in again."}
        if current["demo_persona"] == persona:
            return {"status": "already_started", "persona": persona, "display_name": p["display_name"],
                    "message": "This demo account is already set up."}
        return {"status": "persona_locked", "persona": current["demo_persona"],
                "message": "This demo account already plays another persona. Sign out to start a fresh one."}

    for key, value in p["prefs"].items():
        conn.execute("""insert into public.user_preferences (user_id, key, value, source) values (%s, %s, %s, 'seed')
                        on conflict (user_id, key) do update set value = excluded.value, source = 'seed'""",
                     (user_id, key, Jsonb(value)))
    a = p["address"]
    conn.execute("update public.addresses set is_default = false where user_id = %s and is_default", (user_id,))
    conn.execute("""insert into public.addresses (user_id, label, line1, area_id, lat, lon, is_default)
                    select %s, %s, %s, area_id, lat, lon, true from public.areas where area_id = %s""",
                 (user_id, a["label"], a["line1"], a["area_id"]))

    order_ids = []
    for days_ago, query, qty, extras in p["orders"]:
        lines = _sample_lines(conn, p, query, qty, extras)
        if lines and (oid := _place_sample(conn, user_id, lines, days_ago)):
            order_ids.append(oid)
    return {"status": "ok", "persona": persona, "display_name": p["display_name"], "preferences": p["prefs"],
            "sample_orders": len(order_ids),
            "message": f"Welcome, {p['display_name']}. Your saved preferences and {len(order_ids)} sample orders are ready."}
