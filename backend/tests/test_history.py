"""get_user_history (D-027) against the real database, rolled back: newest first, grouped by checkout, prices as paid,
limited, and only ever the token's user's orders."""

import uuid

import pytest

from app.tools.cart import add_to_cart, view_cart
from app.tools.history import get_user_history
from app.tools.orders import confirm_cart, place_order
from tests.test_orders import item


@pytest.fixture
def users(demo_users):
    arjun, family, priya = demo_users
    return {"arjun": arjun, "family": family, "priya": priya}


def order(db, user_id, *picks, qty=1):
    for p in picks:
        add_to_cart(db, user_id, *p, qty=qty)
    cart = view_cart(db, user_id)
    assert confirm_cart(db, user_id, cart["cart_id"], cart["quote_id"], source="website")["status"] == "ok"
    res = place_order(db, user_id, cart["cart_id"])
    assert res["status"] == "ok", res
    return res


def test_no_orders_yet(db, users):
    res = get_user_history(db, users["family"])
    if res["status"] == "ok":                       # the demo users have no committed orders (D-021)
        pytest.skip("this demo user has committed orders now")
    assert res == {"status": "empty", "checkouts": [], "has_more": False, "message": "The user has no past orders."}


def test_history_groups_a_checkout_and_shows_what_was_paid(db, users):
    biryani = item(db, "Hi-Tech Bawarchi", "Chicken Dum Biryani", "madhapur")
    sandwich = item(db, "Chick King", "Paneer Tikka Sandwich", "madhapur")
    placed = order(db, users["priya"], biryani, sandwich, qty=2)
    res = get_user_history(db, users["priya"])
    assert res["status"] == "ok" and not res["has_more"]
    c = res["checkouts"][0]
    assert c["checkout_id"] == placed["checkout_id"] and c["grand_total"] == placed["grand_total"]
    assert {o["order_id"] for o in c["orders"]} == {o["order_id"] for o in placed["orders"]}
    lines = {i["item_id"]: i for o in c["orders"] for i in o["items"]}
    assert set(lines) == {biryani[0], sandwich[0]} and {i["qty"] for i in lines.values()} == {2}
    assert lines[sandwich[0]]["is_veg"] is True and lines[biryani[0]]["is_veg"] is False
    for o in c["orders"]:
        assert o["items_total"] == sum(i["line_total"] for i in o["items"])
        assert o["total"] == o["items_total"] + o["delivery_fee"] + o["taxes"]
        assert o["delivery_area"] == "Madhapur" and o["order_status"] == "placed"


def test_history_keeps_the_price_paid_after_the_menu_price_changes(db, users):
    biryani = item(db, "Hi-Tech Bawarchi", "Chicken Dum Biryani", "madhapur")
    paid = order(db, users["priya"], biryani)
    price = db.execute("select price from public.menu_items where item_id = %s", (biryani[0],)).fetchone()["price"]
    db.execute("update public.menu_items set price = price + 50 where item_id = %s", (biryani[0],))
    c = get_user_history(db, users["priya"])["checkouts"][0]
    assert c["orders"][0]["items"][0]["price_paid"] == price and c["grand_total"] == paid["grand_total"]
    assert "Today's prices may differ" in get_user_history(db, users["priya"])["message"]


def test_newest_first_and_limited(db, users):
    biryani = item(db, "Hi-Tech Bawarchi", "Chicken Dum Biryani", "madhapur")
    ids = []
    for _ in range(3):
        ids.append(order(db, users["priya"], biryani)["checkout_id"])
        db.execute("update public.orders set created_at = created_at - interval '1 hour' where user_id = %s",
                   (users["priya"],))                  # one transaction shares now(); spread them out in time
    res = get_user_history(db, users["priya"], limit=2)
    assert [c["checkout_id"] for c in res["checkouts"]] == ids[::-1][:2] and res["has_more"] is True
    assert [c["checkout_id"] for c in get_user_history(db, users["priya"], limit=3)["checkouts"]] == ids[::-1]


@pytest.mark.parametrize("limit", [0, 21, -1, True, 2.0, "5", None])
def test_bad_limits(db, users, limit):
    assert get_user_history(db, users["priya"], limit=limit)["status"] == "invalid_input"


def test_users_only_see_their_own_history(db, users):
    placed = order(db, users["priya"], item(db, "Hi-Tech Bawarchi", "Chicken Dum Biryani", "madhapur"))
    mine = {c["checkout_id"] for c in get_user_history(db, users["priya"])["checkouts"]}
    assert placed["checkout_id"] in mine
    for other in ("arjun", "family"):
        res = get_user_history(db, users[other])
        assert placed["checkout_id"] not in {c["checkout_id"] for c in res["checkouts"]}
    assert get_user_history(db, uuid.uuid4())["status"] == "empty"
