"""confirm_cart, place_order, track_order (D-026) against the real database, inside a rolled-back transaction.

Orders are checked independently: item totals summed from order_items in SQL, fees and GST re-derived here with
Decimal from the order's own delivery point (distance in SQL), and the deferred database totals triggers are
forced to run (SET CONSTRAINTS ALL IMMEDIATE) instead of waiting for a commit that never comes in tests."""

import math
import uuid
from decimal import ROUND_HALF_UP, Decimal

import pytest
from psycopg import errors

from app.tools.cart import add_to_cart, set_delivery, view_cart
from app.tools.orders import confirm_cart, place_order, track_order

HAVERSINE = """6371 * 2 * asin(sqrt(power(sin(radians(b.lat - o.delivery_lat) / 2), 2)
               + cos(radians(o.delivery_lat)) * cos(radians(b.lat)) * power(sin(radians(b.lon - o.delivery_lon) / 2), 2)))"""


def item(db, restaurant, dish, area_id):
    row = db.execute("""
        select m.item_id, b.branch_id from public.menu_items m join public.dishes d using (dish_id)
        join public.restaurants r using (restaurant_id) join public.branches b on b.restaurant_id = r.restaurant_id
        where r.name = %s and d.name = %s and b.open_for_demo and b.area_id = %s order by b.branch_id limit 1""",
                     (restaurant, dish, area_id)).fetchone()
    assert row
    return row["item_id"], row["branch_id"]


def gst(amount, pct):
    return int((Decimal(amount) * pct / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


@pytest.fixture
def users(demo_users):
    arjun, family, priya = demo_users
    return {"arjun": arjun, "family": family, "priya": priya}


@pytest.fixture
def two_restaurant_cart(db, users):
    """Priya: 1 × Chicken Dum Biryani (Hi-Tech Bawarchi) + 1 × Paneer Tikka Sandwich (Chick King), Madhapur."""
    biryani = item(db, "Hi-Tech Bawarchi", "Chicken Dum Biryani", "madhapur")
    sandwich = item(db, "Chick King", "Paneer Tikka Sandwich", "madhapur")
    add_to_cart(db, users["priya"], *biryani)
    add_to_cart(db, users["priya"], *sandwich)
    return {"biryani": biryani, "sandwich": sandwich, "cart": view_cart(db, users["priya"])}


def confirm(db, user_id):
    cart = view_cart(db, user_id)
    res = confirm_cart(db, user_id, cart["cart_id"], cart["quote_id"], source="website")
    assert res["status"] == "ok", res
    return cart


def order_count(db, user_id):
    return db.execute("select count(*) as n from public.orders where user_id = %s", (user_id,)).fetchone()["n"]


# ── the happy path ───────────────────────────────────────────────────────
def test_confirm_then_place_creates_one_order_per_restaurant(db, users, two_restaurant_cart):
    shown = confirm(db, users["priya"])
    res = place_order(db, users["priya"], shown["cart_id"])
    assert res["status"] == "ok" and len(res["orders"]) == 2
    assert res["grand_total"] == shown["grand_total"]
    assert {o["payment_status"] for o in res["orders"]} == {"pending"} and {o["status"] for o in res["orders"]} == {"placed"}
    rows = db.execute("select distinct checkout_id from public.orders where cart_id = %s", (shown["cart_id"],)).fetchall()
    assert len(rows) == 1 and str(rows[0]["checkout_id"]) == res["checkout_id"]
    assert db.execute("select status from public.carts where cart_id = %s", (shown["cart_id"],)).fetchone()["status"] == "ordered"
    db.execute("set constraints all immediate")          # run the deferred totals triggers now (they pass)


def test_orders_are_checked_independently(db, users, two_restaurant_cart):
    shown = confirm(db, users["priya"])
    res = place_order(db, users["priya"], shown["cart_id"])
    rows = db.execute(f"""
        select o.order_id, o.items_total, o.delivery_fee, o.taxes, o.grand_total, {HAVERSINE} as km,
               (select sum(unit_price * qty) from public.order_items i where i.order_id = o.order_id)::int as summed
        from public.orders o join public.branches b using (branch_id) where o.checkout_id = %s""",
                      (res["checkout_id"],)).fetchall()
    for r in rows:
        assert r["summed"] == r["items_total"]
        fee = 0 if r["items_total"] >= 499 else 25 + 10 * max(0, math.ceil(round(r["km"] - 2, 3)))
        assert r["delivery_fee"] == fee
        assert r["taxes"] == gst(r["items_total"], 5) + gst(fee, 18)
        assert r["grand_total"] == r["items_total"] + r["delivery_fee"] + r["taxes"]
    assert sum(r["grand_total"] for r in rows) == shown["grand_total"]


def test_order_items_are_a_snapshot_of_the_confirmed_cart(db, users, two_restaurant_cart):
    shown = confirm(db, users["priya"])
    res = place_order(db, users["priya"], shown["cart_id"])
    snap = db.execute("""select i.item_id, i.dish_name, i.unit_price, i.qty, i.is_veg from public.order_items i
                         join public.orders o using (order_id) where o.checkout_id = %s order by i.item_id""",
                      (res["checkout_id"],)).fetchall()
    cart_lines = sorted(((i["item_id"], i["name"], i["price"], i["qty"], i["is_veg"]) for b in shown["branches"]
                         for i in b["items"]))
    assert [tuple(r.values()) for r in snap] == cart_lines
    # a later price change does not touch what was ordered
    db.execute("update public.menu_items set price = price + 10 where item_id = %s", (two_restaurant_cart["biryani"][0],))
    again = db.execute("select unit_price from public.order_items where item_id = %s", (two_restaurant_cart["biryani"][0],)).fetchone()
    assert again["unit_price"] == next(c[2] for c in cart_lines if c[0] == two_restaurant_cart["biryani"][0])


def test_the_delivery_point_is_snapshotted(db, users, two_restaurant_cart):
    shown = confirm(db, users["priya"])
    res = place_order(db, users["priya"], shown["cart_id"])
    o = db.execute("select address_id, delivery_area_id, delivery_lat, delivery_lon from public.orders where checkout_id = %s "
                   "limit 1", (res["checkout_id"],)).fetchone()
    d = shown["delivery"]
    assert (str(o["address_id"]), o["delivery_area_id"], o["delivery_lat"], o["delivery_lon"]) == \
           (d["address_id"], d["area_id"], d["lat"], d["lon"])


def test_the_order_goes_to_the_address_not_the_area_centre(db, users, two_restaurant_cart):
    """Demo addresses sit on their area centres (the Session 9 blind spot), so move it first (rolled back)."""
    db.execute("update public.addresses set lat = lat + 0.01 where user_id = %s", (users["priya"],))
    shown = confirm(db, users["priya"])
    res = place_order(db, users["priya"], shown["cart_id"])
    o = db.execute("select delivery_lat from public.orders where checkout_id = %s limit 1", (res["checkout_id"],)).fetchone()
    centre = db.execute("select lat from public.areas where area_id = 'madhapur'").fetchone()["lat"]
    assert abs(o["delivery_lat"] - (centre + 0.01)) < 1e-6


def test_an_address_moved_after_yes_counts_as_a_change(db, users, two_restaurant_cart):
    """The address row itself can be edited while the cart is confirmed; the fee then changes (~3.3 km: ₹25 → ₹45),
    so the order must not go through at the old total."""
    shown = confirm(db, users["priya"])
    db.execute("update public.addresses set lat = lat + 0.03 where user_id = %s", (users["priya"],))
    res = place_order(db, users["priya"], shown["cart_id"])
    assert res["status"] == "quote_changed" and res["new_total"] > shown["grand_total"]
    assert order_count(db, users["priya"]) == 0


def test_after_ordering_the_next_add_starts_a_new_cart(db, users, two_restaurant_cart):
    shown = confirm(db, users["priya"])
    place_order(db, users["priya"], shown["cart_id"])
    assert view_cart(db, users["priya"])["status"] == "empty"
    new = add_to_cart(db, users["priya"], *two_restaurant_cart["biryani"])["cart"]
    assert new["cart_id"] != shown["cart_id"] and new["grand_total"] == 419


def test_tracking_shows_the_order_and_its_timeline(db, users, two_restaurant_cart):
    shown = confirm(db, users["priya"])
    res = place_order(db, users["priya"], shown["cart_id"])
    for o in res["orders"]:
        t = track_order(db, users["priya"], o["order_id"])
        assert t["status"] == "ok" and t["order_status"] == "placed" and [e["status"] for e in t["timeline"]] == ["placed"]
        assert t["total"] == o["total"] and t["delivery_area"] == "Madhapur" and t["items"]


# ── the gate ─────────────────────────────────────────────────────────────
def test_nothing_is_ordered_without_confirmation(db, users, two_restaurant_cart):
    res = place_order(db, users["priya"], two_restaurant_cart["cart"]["cart_id"])
    assert res["status"] == "not_confirmed" and order_count(db, users["priya"]) == 0


def test_confirm_needs_the_quote_that_was_shown(db, users, two_restaurant_cart):
    cart = two_restaurant_cart["cart"]
    assert confirm_cart(db, users["priya"], cart["cart_id"], "0" * 20, source="website")["status"] == "stale_quote"
    add_to_cart(db, users["priya"], *two_restaurant_cart["biryani"])          # cart changes after it was shown
    res = confirm_cart(db, users["priya"], cart["cart_id"], cart["quote_id"], source="website")
    assert res["status"] == "stale_quote" and res["cart"]["quote_id"] != cart["quote_id"]
    assert view_cart(db, users["priya"])["cart_status"] == "open"


def test_confirming_twice_is_harmless(db, users, two_restaurant_cart):
    shown = confirm(db, users["priya"])
    res = confirm_cart(db, users["priya"], shown["cart_id"], shown["quote_id"], source="website")
    assert res["status"] == "ok" and res["already_confirmed"] is True


@pytest.mark.parametrize("problem", ["no_delivery_point", "unavailable_item", "empty"])
def test_carts_that_cannot_be_confirmed(db, users, problem):
    biryani = item(db, "Hi-Tech Bawarchi", "Chicken Dum Biryani", "madhapur")
    if problem == "no_delivery_point":
        db.execute("delete from public.addresses where user_id = %s", (users["priya"],))
        db.execute("delete from public.user_preferences where user_id = %s and key = 'default_area'", (users["priya"],))
    add_to_cart(db, users["priya"], *biryani)
    if problem == "unavailable_item":
        sandwich = item(db, "Chick King", "Paneer Tikka Sandwich", "madhapur")
        add_to_cart(db, users["priya"], *sandwich)
        db.execute("update public.menu_items set is_available = false where item_id = %s", (sandwich[0],))
    if problem == "empty":
        from app.tools.cart import remove_from_cart
        remove_from_cart(db, users["priya"], biryani[0])
    cart = view_cart(db, users["priya"])
    assert "quote_id" not in cart
    res = confirm_cart(db, users["priya"], cart["cart_id"], "0" * 20, source="website")
    assert res["status"] == "cannot_confirm"


# ── a change after the "yes" (Saif, Session 10: ask again) ───────────────
@pytest.mark.parametrize("change", ["price_up", "item_unavailable", "branch_closed"])
def test_a_change_after_yes_reopens_and_orders_nothing(db, users, two_restaurant_cart, change):
    shown = confirm(db, users["priya"])
    biryani = two_restaurant_cart["biryani"]
    {"price_up": lambda: db.execute("update public.menu_items set price = price + 10 where item_id = %s", (biryani[0],)),
     "item_unavailable": lambda: db.execute("update public.menu_items set is_available = false where item_id = %s", (biryani[0],)),
     "branch_closed": lambda: db.execute("update public.branches set open_for_demo = false where branch_id = %s", (biryani[1],)),
     }[change]()
    res = place_order(db, users["priya"], shown["cart_id"])
    assert res["status"] == "quote_changed" and res["confirmed_total"] == shown["grand_total"]
    assert res["new_total"] != shown["grand_total"] and res["cart"]["cart_status"] == "open"
    assert order_count(db, users["priya"]) == 0


def test_a_change_that_keeps_the_same_total_still_needs_a_new_yes(db, users):
    """Found by planted bugs (D-026): one item +₹10 and another −₹10 at the same restaurant leaves every total equal,
    but the line prices the user agreed to have changed. The fingerprint covers each line's price."""
    chicken = item(db, "Hi-Tech Bawarchi", "Chicken Dum Biryani", "madhapur")
    mutton = item(db, "Hi-Tech Bawarchi", "Mutton Dum Biryani", "madhapur")
    add_to_cart(db, users["priya"], *chicken)
    add_to_cart(db, users["priya"], *mutton)
    shown = confirm(db, users["priya"])
    db.execute("update public.menu_items set price = price + 10 where item_id = %s", (chicken[0],))
    db.execute("update public.menu_items set price = price - 10 where item_id = %s", (mutton[0],))
    assert view_cart(db, users["priya"])["grand_total"] == shown["grand_total"]
    res = place_order(db, users["priya"], shown["cart_id"])
    assert res["status"] == "quote_changed" and order_count(db, users["priya"]) == 0


def test_an_address_moved_a_little_after_yes_still_needs_a_new_yes(db, users, two_restaurant_cart):
    """~50 m keeps every fee and total the same, but the order would go somewhere the user didn't confirm."""
    shown = confirm(db, users["priya"])
    db.execute("update public.addresses set lat = lat + 0.0005 where user_id = %s", (users["priya"],))
    assert view_cart(db, users["priya"])["grand_total"] == shown["grand_total"]
    assert place_order(db, users["priya"], shown["cart_id"])["status"] == "quote_changed"


def test_after_a_price_change_a_new_yes_places_the_new_price(db, users, two_restaurant_cart):
    shown = confirm(db, users["priya"])
    db.execute("update public.menu_items set price = price + 10 where item_id = %s", (two_restaurant_cart["biryani"][0],))
    changed = place_order(db, users["priya"], shown["cart_id"])
    again = confirm(db, users["priya"])
    res = place_order(db, users["priya"], again["cart_id"])
    assert res["status"] == "ok" and res["grand_total"] == changed["new_total"] == again["grand_total"]


def test_placing_twice_orders_once(db, users, two_restaurant_cart):
    shown = confirm(db, users["priya"])
    first = place_order(db, users["priya"], shown["cart_id"])
    second = place_order(db, users["priya"], shown["cart_id"])
    assert second["status"] == "already_placed" and second["checkout_id"] == first["checkout_id"]
    assert order_count(db, users["priya"]) == 2


# ── one user can never reach another user's cart or order ────────────────
def test_another_user_cannot_confirm_place_or_track(db, users, two_restaurant_cart):
    cart = two_restaurant_cart["cart"]
    assert confirm_cart(db, users["arjun"], cart["cart_id"], cart["quote_id"], source="website")["status"] == "not_found"
    assert view_cart(db, users["priya"])["cart_status"] == "open"
    confirm(db, users["priya"])
    assert place_order(db, users["arjun"], cart["cart_id"])["status"] == "not_found"
    assert order_count(db, users["arjun"]) == 0 and order_count(db, users["priya"]) == 0
    res = place_order(db, users["priya"], cart["cart_id"])
    for o in res["orders"]:
        assert track_order(db, users["arjun"], o["order_id"])["status"] == "not_found"


def test_unknown_and_malformed_ids(db, users):
    for fn, args, kw in ((confirm_cart, ("x" * 20,), {"source": "website"}), (place_order, (), {}),
                         (track_order, (), {})):
        assert fn(db, users["priya"], str(uuid.uuid4()), *args, **kw)["status"] == "not_found"
        for bad in ("abc", None, 5, "'; drop table orders; --"):
            assert fn(db, users["priya"], bad, *args, **kw)["status"] == "invalid_input"
    assert confirm_cart(db, users["priya"], str(uuid.uuid4()), "", source="website")["status"] == "invalid_input"


# ── the database gate holds even if the code is bypassed ─────────────────
def insert_order(db, user_id, cart_id, branch_id, total=100):
    db.execute("""insert into public.orders (checkout_id, user_id, cart_id, branch_id, items_total, delivery_fee, taxes,
                  grand_total, delivery_area_id, delivery_lat, delivery_lon)
                  values (gen_random_uuid(), %s, %s, %s, %s, 0, 0, %s, 'madhapur', 17.44, 78.39)""",
               (user_id, cart_id, branch_id, total, total))


def test_db_refuses_an_order_from_an_unconfirmed_cart(db, users, two_restaurant_cart):
    cart = two_restaurant_cart["cart"]
    with pytest.raises(errors.CheckViolation), db.transaction():
        insert_order(db, users["priya"], cart["cart_id"], two_restaurant_cart["biryani"][1])


def test_db_refuses_an_order_on_someone_elses_cart(db, users, two_restaurant_cart):
    shown = confirm(db, users["priya"])
    with pytest.raises(errors.CheckViolation), db.transaction():
        insert_order(db, users["arjun"], shown["cart_id"], two_restaurant_cart["biryani"][1])


def test_db_refuses_a_confirmation_without_its_quote(db, users, two_restaurant_cart):
    with pytest.raises(errors.CheckViolation), db.transaction():
        db.execute("update public.carts set status = 'confirmed', confirmed_at = now() where cart_id = %s",
                   (two_restaurant_cart["cart"]["cart_id"],))


def test_db_refuses_tampered_order_totals(db, users, two_restaurant_cart):
    shown = confirm(db, users["priya"])
    res = place_order(db, users["priya"], shown["cart_id"])
    oid = res["orders"][0]["order_id"]
    with pytest.raises(errors.CheckViolation), db.transaction():
        db.execute("update public.orders set items_total = items_total + 1, grand_total = grand_total + 1 "
                   "where order_id = %s", (oid,))
        db.execute("set constraints all immediate")


# ── from chat, code checks the yes itself (Saif, Session 12; D-030) ─────────────
def cart_status(db, cart_id):
    return db.execute("select status from public.carts where cart_id = %s", (cart_id,)).fetchone()["status"]


@pytest.mark.parametrize("message", ["yes, place it", "haan bhai kar do", "theek hai", "avunu, order pettu",
                                     "sare andi", "సరే", "हाँ जी", "haan order palce kardo"])   # typo repaired (D-040)
def test_chat_confirms_on_a_clear_yes_in_any_language(db, users, two_restaurant_cart, message):
    cart = two_restaurant_cart["cart"]
    res = confirm_cart(db, users["priya"], cart["cart_id"], cart["quote_id"], source="chat", user_message=message)
    assert res["status"] == "ok", res
    assert cart_status(db, cart["cart_id"]) == "confirmed"


@pytest.mark.parametrize("message, said", [
    ("no", "no"), ("wait", "no"), ("nahi", "no"), ("vaddu", "no"), ("ok wait", "no"), ("haan par ruko", "no"),
    ("ఆగండి", "no"), ("yes?", "unclear"), ("yes but add a coke", "unclear"), ("kar do na", "unclear"),
    ("", "unclear"), (None, "unclear"),
    ("haan order kar do aur ek coke add karo", "unclear"), ("haan order cancle karo", "no"),   # D-040
    ("haan saudi arebian rest wala order palce kardo.", "unclear"),   # D-045: names make it unclear (LLM asks)
])
def test_chat_without_a_clear_yes_confirms_nothing(db, users, two_restaurant_cart, message, said):
    cart = two_restaurant_cart["cart"]
    res = confirm_cart(db, users["priya"], cart["cart_id"], cart["quote_id"], source="chat", user_message=message)
    assert res["status"] == "no_clear_yes" and res["consent"]["consent"] == said
    assert cart_status(db, cart["cart_id"]) == "open"
    assert place_order(db, users["priya"], cart["cart_id"])["status"] == "not_confirmed"
    assert order_count(db, users["priya"]) == 0


def test_chat_message_is_required_and_source_is_never_guessed(db, users, two_restaurant_cart):
    cart = two_restaurant_cart["cart"]
    assert confirm_cart(db, users["priya"], cart["cart_id"], cart["quote_id"], source="chat")["status"] == "no_clear_yes"
    for source in ("agent", "", None, "Website", "chat "):
        res = confirm_cart(db, users["priya"], cart["cart_id"], cart["quote_id"], source=source, user_message="yes")
        assert res["status"] == "invalid_input"
    with pytest.raises(TypeError):                       # no default: forgetting the source can't skip the check
        confirm_cart(db, users["priya"], cart["cart_id"], cart["quote_id"])
    assert cart_status(db, cart["cart_id"]) == "open"


def test_a_clear_yes_still_needs_the_right_quote(db, users, two_restaurant_cart):
    """The yes check is a second lock, not a replacement: a yes to an old summary is still refused."""
    cart = two_restaurant_cart["cart"]
    res = confirm_cart(db, users["priya"], cart["cart_id"], "0" * 20, source="chat", user_message="yes")
    assert res["status"] == "stale_quote" and cart_status(db, cart["cart_id"]) == "open"


def test_a_no_tells_the_model_the_cart_is_kept_not_cancelled(db, users, two_restaurant_cart):
    # Saif, Session 15: after "no", Dawat AI said "Order cancel kardiya hai" with the items still in the cart (D-041).
    cart = two_restaurant_cart["cart"]
    res = confirm_cart(db, users["priya"], cart["cart_id"], cart["quote_id"], source="chat", user_message="no")
    assert res["status"] == "no_clear_yes" and "NOT placed" in res["message"] and "still in the cart" in res["message"]
    assert "Never say it was cancelled" in res["message"]
    assert cart_status(db, cart["cart_id"]) == "open"
    assert view_cart(db, users["priya"])["grand_total"] == cart["grand_total"]       # every item still there
