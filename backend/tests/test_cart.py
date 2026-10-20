"""Cart tools (D-025) against the real database, inside a rolled-back transaction.

Totals are re-derived independently: prices summed in SQL, distance computed in SQL (haversine), and the fee
and GST rules re-implemented here with Decimal (not app.pricing). Cross-user tests prove one user can never
see or change another user's cart."""

import math
import uuid
from decimal import ROUND_HALF_UP, Decimal

import pytest
from psycopg import errors

from app.tools.cart import add_to_cart, remove_from_cart, set_delivery, view_cart

HAVERSINE = """6371 * 2 * asin(sqrt(power(sin(radians(b.lat - p.lat) / 2), 2)
               + cos(radians(p.lat)) * cos(radians(b.lat)) * power(sin(radians(b.lon - p.lon) / 2), 2)))"""


def item(db, restaurant, dish, area_id=None):
    """(item_id, branch_id) of a dish at a restaurant: the branch in area_id if given, else the first branch."""
    row = db.execute("""
        select m.item_id, b.branch_id from public.menu_items m join public.dishes d using (dish_id)
        join public.restaurants r using (restaurant_id) join public.branches b on b.restaurant_id = r.restaurant_id
        where r.name = %s and d.name = %s and b.open_for_demo and (%s::text is null or b.area_id = %s)
        order by b.branch_id limit 1""", (restaurant, dish, area_id, area_id)).fetchone()
    assert row, (restaurant, dish, area_id)
    return row["item_id"], row["branch_id"]


def gst(amount: int, pct: int) -> int:
    return int((Decimal(amount) * pct / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def expected(db, user_id) -> dict:
    """branch_id → total, computed without app.pricing."""
    rows = db.execute(f"""
        with p as (select c.cart_id, coalesce(ad.lat, a.lat) as lat, coalesce(ad.lon, a.lon) as lon
                   from public.carts c join public.areas a on a.area_id = c.delivery_area_id
                   left join public.addresses ad on ad.address_id = c.address_id
                   where c.user_id = %s and c.status in ('open', 'confirmed'))
        select ci.branch_id, sum(m.price * ci.qty)::int as items, min({HAVERSINE}) as km
        from p join public.cart_items ci on ci.cart_id = p.cart_id join public.menu_items m using (item_id)
        join public.branches b on b.branch_id = ci.branch_id
        where m.is_available and b.open_for_demo group by ci.branch_id""", (user_id,)).fetchall()
    out = {}
    for r in rows:
        if r["km"] > 8.0005:                                     # beyond the 8 km delivery range: not billed
            continue
        fee = 0 if r["items"] >= 499 else 25 + 10 * max(0, math.ceil(round(r["km"] - 2, 3)))
        out[r["branch_id"]] = r["items"] + fee + gst(r["items"], 5) + gst(fee, 18)
    return out


def check_totals(db, user_id, cart):
    exp = expected(db, user_id)
    assert {b["branch_id"]: b["total"] for b in cart["branches"]} == exp
    assert cart["grand_total"] == sum(exp.values())


@pytest.fixture
def users(demo_users):
    arjun, family, priya = demo_users          # ordered by display name; default areas gachibowli, kukatpally, madhapur
    return {"arjun": arjun, "family": family, "priya": priya}


@pytest.fixture
def biryani(db):
    return item(db, "Hi-Tech Bawarchi", "Chicken Dum Biryani", "madhapur")


# ── totals ───────────────────────────────────────────────────────────────
def test_approved_example_total(db, users, biryani):
    """Saif's approved example: 1 × Chicken Dum Biryani ₹370, Hi-Tech Bawarchi → Madhapur = ₹419."""
    cart = add_to_cart(db, users["priya"], *biryani, 1)["cart"]
    assert cart["status"] == "ok" and cart["grand_total"] == 419
    check_totals(db, users["priya"], cart)


def test_two_restaurants_two_fees_and_free_delivery_from_499(db, users, biryani):
    sandwich = item(db, "Chick King", "Paneer Tikka Sandwich", "madhapur")
    add_to_cart(db, users["priya"], *biryani, 1)
    cart = add_to_cart(db, users["priya"], *sandwich, 1)["cart"]
    assert [b["delivery_fee"] for b in cart["branches"]] == [25, 25]
    check_totals(db, users["priya"], cart)
    cart = add_to_cart(db, users["priya"], *biryani, 1)["cart"]          # Hi-Tech now ₹740 ≥ ₹499
    fees = {b["restaurant"]: b["delivery_fee"] for b in cart["branches"]}
    assert fees == {"Hi-Tech Bawarchi": 0, "Chick King": 25}
    check_totals(db, users["priya"], cart)


def test_distance_changes_the_fee(db, users):
    sandwich = item(db, "Chick King", "Paneer Tikka Sandwich", "madhapur")
    add_to_cart(db, users["priya"], *sandwich, 1)
    cart = set_delivery(db, users["priya"], area="Kukatpally")["cart"]
    assert cart["branches"][0]["delivery_fee"] > 25
    check_totals(db, users["priya"], cart)


def test_distance_is_measured_from_the_address_not_the_area_centre(db, users, biryani):
    """Found by a planted bug (D-025): the demo addresses sit exactly on their area centres, so ignoring the
    address changed nothing. Moved ~3.3 km north here (rolled back), the fee must follow the address."""
    db.execute("update public.addresses set lat = lat + 0.03 where user_id = %s", (users["priya"],))
    cart = add_to_cart(db, users["priya"], *biryani, 1)["cart"]
    assert cart["delivery"]["address_label"] == "Home"
    assert cart["branches"][0]["distance_km"] > 3 and cart["branches"][0]["delivery_fee"] == 45
    check_totals(db, users["priya"], cart)


def test_prices_are_read_live_never_stored(db, users, biryani):
    add_to_cart(db, users["priya"], *biryani, 1)
    db.execute("update public.menu_items set price = 380 where item_id = %s", (biryani[0],))   # rolled back
    cart = view_cart(db, users["priya"])
    assert cart["branches"][0]["items"][0]["price"] == 380
    check_totals(db, users["priya"], cart)


def test_unavailable_items_are_flagged_left_out_and_block_confirming(db, users, biryani):
    sandwich = item(db, "Chick King", "Paneer Tikka Sandwich", "madhapur")
    add_to_cart(db, users["priya"], *biryani, 1)
    add_to_cart(db, users["priya"], *sandwich, 1)
    db.execute("update public.menu_items set is_available = false where item_id = %s", (sandwich[0],))
    cart = view_cart(db, users["priya"])
    assert [u["item_id"] for u in cart["unavailable"]] == [sandwich[0]] and cart["can_confirm"] is False
    assert [b["restaurant"] for b in cart["branches"]] == ["Hi-Tech Bawarchi"] and cart["grand_total"] == 419
    check_totals(db, users["priya"], cart)


def test_a_closed_branch_counts_as_unavailable(db, users, biryani):
    add_to_cart(db, users["priya"], *biryani, 1)
    db.execute("update public.branches set open_for_demo = false where branch_id = %s", (biryani[1],))
    cart = view_cart(db, users["priya"])
    assert cart["status"] == "empty" and cart["unavailable"] and cart["can_confirm"] is False


# ── quantities and lines ─────────────────────────────────────────────────
def test_quantities_add_up_and_stop_at_20(db, users, biryani):
    add_to_cart(db, users["priya"], *biryani, 19)
    res = add_to_cart(db, users["priya"], *biryani, 2)
    assert res["status"] == "qty_limit" and res["in_cart"] == 19
    assert view_cart(db, users["priya"])["branches"][0]["items"][0]["qty"] == 19
    assert add_to_cart(db, users["priya"], *biryani, 1)["cart"]["branches"][0]["items"][0]["qty"] == 20


@pytest.mark.parametrize("qty", [0, -1, 21, 1.5, "2", True, None])
def test_bad_quantities_are_refused(db, users, biryani, qty):
    assert add_to_cart(db, users["priya"], *biryani, qty)["status"] == "invalid_input"


def test_remove_some_then_all(db, users, biryani):
    add_to_cart(db, users["priya"], *biryani, 3)
    assert remove_from_cart(db, users["priya"], biryani[0], qty=2)["removed"]["now_in_cart"] == 1
    res = remove_from_cart(db, users["priya"], biryani[0])
    assert res["removed"]["now_in_cart"] == 0 and res["cart"]["status"] == "empty"
    assert remove_from_cart(db, users["priya"], biryani[0])["status"] == "not_in_cart"


def test_same_item_from_two_branches_asks_which(db, users):
    rows = db.execute(f"""select m.item_id, b.branch_id from public.menu_items m join public.dishes d using (dish_id)
                          join public.branches b using (restaurant_id), public.areas p
                          where m.restaurant_id = 'r-paradise' and d.name = 'Chicken Dum Biryani' and b.open_for_demo
                            and p.area_id = 'madhapur' and {HAVERSINE} <= 8
                          order by b.branch_id limit 2""").fetchall()
    assert len(rows) == 2                                   # two Paradise branches within delivery range
    for r in rows:
        add_to_cart(db, users["priya"], r["item_id"], r["branch_id"], 1)
    res = remove_from_cart(db, users["priya"], rows[0]["item_id"])
    assert res["status"] == "needs_branch" and len(res["branches"]) == 2
    assert remove_from_cart(db, users["priya"], rows[0]["item_id"], branch_id=rows[0]["branch_id"])["status"] == "ok"


def test_wrong_ids_are_refused(db, users, biryani):
    other_branch = item(db, "Chick King", "Paneer Tikka Sandwich", "madhapur")[1]
    assert add_to_cart(db, users["priya"], biryani[0], other_branch)["status"] == "not_on_this_menu"
    assert add_to_cart(db, users["priya"], "r-nope__chicken-dum-biryani", biryani[1])["status"] == "unknown_item"
    assert add_to_cart(db, users["priya"], biryani[0], "b-n1")["status"] == "branch_unavailable"
    for bad in ("'; drop table carts; --", "", None, 5):
        assert add_to_cart(db, users["priya"], bad, biryani[1])["status"] == "invalid_input"
        assert add_to_cart(db, users["priya"], biryani[0], bad)["status"] == "invalid_input"


def test_unavailable_item_cannot_be_added(db, users, biryani):
    db.execute("update public.menu_items set is_available = false where item_id = %s", (biryani[0],))
    assert add_to_cart(db, users["priya"], *biryani)["status"] == "item_unavailable"
    assert view_cart(db, users["priya"])["status"] == "empty"


# ── where it is delivered ────────────────────────────────────────────────
def test_new_cart_uses_the_default_address(db, users, biryani):
    cart = add_to_cart(db, users["priya"], *biryani)["cart"]
    assert cart["delivery"]["area_id"] == "madhapur" and cart["delivery"]["address_label"] == "Home"


def test_without_an_address_the_saved_default_area_is_used(db, users, biryani):
    db.execute("delete from public.addresses where user_id = %s", (users["priya"],))           # rolled back
    cart = add_to_cart(db, users["priya"], *biryani)["cart"]
    d = cart["delivery"]
    assert (d["area_id"], d["address_id"], d["address_label"]) == ("madhapur", None, None)
    centre = db.execute("select lat, lon from public.areas where area_id = 'madhapur'").fetchone()
    assert (d["lat"], d["lon"]) == (round(centre["lat"], 6), round(centre["lon"], 6))      # the area's centre


def test_with_no_delivery_point_there_is_no_total_yet(db, users, biryani):
    db.execute("delete from public.addresses where user_id = %s", (users["priya"],))
    db.execute("delete from public.user_preferences where user_id = %s and key = 'default_area'", (users["priya"],))
    cart = add_to_cart(db, users["priya"], *biryani)["cart"]
    assert cart["status"] == "needs_delivery_area" and cart["grand_total"] is None and cart["can_confirm"] is False
    cart = set_delivery(db, users["priya"], area="madhapur")["cart"]
    assert cart["grand_total"] == 419


@pytest.mark.parametrize("area, status", [("madhapoor", "confirm_area"), ("Manikonda", "outside_coverage"),
                                          ("hyderabad", "needs_area"), ("xyzabad", "unknown_area")])
def test_unresolved_delivery_areas_change_nothing(db, users, biryani, area, status):
    add_to_cart(db, users["priya"], *biryani)
    assert set_delivery(db, users["priya"], area=area)["status"] == status
    assert view_cart(db, users["priya"])["delivery"]["area_id"] == "madhapur"


@pytest.mark.parametrize("kwargs", [{}, {"area": "Madhapur", "address_id": str(uuid.uuid4())}, {"area": ""},
                                    {"address_id": "not-a-uuid"}])
def test_set_delivery_needs_exactly_one_valid_target(db, users, kwargs):
    assert set_delivery(db, users["priya"], **kwargs)["status"] == "invalid_input"


# ── the confirmation is cleared by any change ────────────────────────────
def confirm(db, user_id):
    from app.tools.orders import confirm_cart
    cart = view_cart(db, user_id)
    assert confirm_cart(db, user_id, cart["cart_id"], cart["quote_id"], source="website")["status"] == "ok"


@pytest.mark.parametrize("change", ["add", "remove", "deliver"])
def test_changing_a_confirmed_cart_reopens_it(db, users, biryani, change):
    add_to_cart(db, users["priya"], *biryani, 2)
    confirm(db, users["priya"])
    res = {"add": lambda: add_to_cart(db, users["priya"], *biryani),
           "remove": lambda: remove_from_cart(db, users["priya"], biryani[0], qty=1),
           "deliver": lambda: set_delivery(db, users["priya"], area="Kondapur")}[change]()
    assert res["confirmation_cleared"] is True and res["cart"]["cart_status"] == "open"


def test_setting_the_same_delivery_point_keeps_the_confirmation(db, users, biryani):
    add_to_cart(db, users["priya"], *biryani)
    addr = view_cart(db, users["priya"])["delivery"]["address_id"]
    confirm(db, users["priya"])
    res = set_delivery(db, users["priya"], address_id=addr)
    assert "confirmation_cleared" not in res and res["cart"]["cart_status"] == "confirmed"


# ── one user can never reach another user's cart ─────────────────────────
def test_each_user_sees_only_their_own_cart(db, users, biryani):
    sandwich = item(db, "Chick King", "Paneer Tikka Sandwich", "madhapur")
    add_to_cart(db, users["priya"], *biryani, 2)
    add_to_cart(db, users["arjun"], *sandwich, 1)
    p, a = view_cart(db, users["priya"]), view_cart(db, users["arjun"])
    assert p["cart_id"] != a["cart_id"]
    assert [i["item_id"] for b in p["branches"] for i in b["items"]] == [biryani[0]]
    assert [i["item_id"] for b in a["branches"] for i in b["items"]] == [sandwich[0]]


def test_removing_never_touches_another_users_cart(db, users, biryani):
    add_to_cart(db, users["priya"], *biryani, 2)
    assert remove_from_cart(db, users["arjun"], biryani[0])["status"] == "not_in_cart"
    assert view_cart(db, users["priya"])["branches"][0]["items"][0]["qty"] == 2


def test_another_users_address_is_unknown(db, users, biryani):
    add_to_cart(db, users["priya"], *biryani)
    priya_addr = view_cart(db, users["priya"])["delivery"]["address_id"]
    assert set_delivery(db, users["arjun"], address_id=priya_addr)["status"] == "unknown_address"


def test_unknown_user_gets_no_cart(db, biryani):
    assert add_to_cart(db, uuid.uuid4(), *biryani)["status"] == "unknown_user"
    assert view_cart(db, uuid.uuid4())["status"] == "empty"


def test_only_one_active_cart_per_user(db, users, biryani):
    add_to_cart(db, users["priya"], *biryani)
    set_delivery(db, users["priya"], area="Kondapur")
    remove_from_cart(db, users["priya"], biryani[0])
    add_to_cart(db, users["priya"], *biryani)
    n = db.execute("select count(*) as n from public.carts where user_id = %s and status in ('open', 'confirmed')",
                   (users["priya"],)).fetchone()["n"]
    assert n == 1


# ── the database guards (second layer) ───────────────────────────────────
def test_db_refuses_moving_a_confirmed_carts_delivery(db, users, biryani):
    add_to_cart(db, users["priya"], *biryani)
    confirm(db, users["priya"])
    with pytest.raises(errors.CheckViolation), db.transaction():
        db.execute("update public.carts set delivery_area_id = 'kondapur', address_id = null "
                   "where user_id = %s and status = 'confirmed'", (users["priya"],))


def test_db_refuses_another_users_address_or_one_in_another_area(db, users, biryani):
    add_to_cart(db, users["priya"], *biryani)
    arjun_addr = db.execute("select address_id from public.addresses where user_id = %s",
                            (users["arjun"],)).fetchone()["address_id"]
    with pytest.raises(errors.CheckViolation), db.transaction():
        db.execute("update public.carts set delivery_area_id = 'gachibowli', address_id = %s where user_id = %s",
                   (arjun_addr, users["priya"]))
    with pytest.raises(errors.CheckViolation), db.transaction():
        db.execute("update public.carts set delivery_area_id = 'kondapur' where user_id = %s and address_id is not null",
                   (users["priya"],))


# ── delivery range: 8 km (Saif, D-025) ───────────────────────────────────
def far_item(db, area_id, min_km=8.5):
    """A Chicken Dum Biryani at an open branch more than min_km from the area's centre."""
    row = db.execute(f"""
        select m.item_id, b.branch_id, {HAVERSINE} as km from public.menu_items m join public.dishes d using (dish_id)
        join public.branches b using (restaurant_id), public.areas p
        where d.name = 'Chicken Dum Biryani' and m.is_available and b.open_for_demo and p.area_id = %s
          and {HAVERSINE} > %s order by km limit 1""", (area_id, min_km)).fetchone()
    assert row
    return row["item_id"], row["branch_id"]


def test_a_place_beyond_8_km_is_too_far_and_nothing_is_added(db, users, biryani):
    add_to_cart(db, users["priya"], *biryani)
    far = far_item(db, "madhapur")
    res = add_to_cart(db, users["priya"], *far)
    assert res["status"] == "too_far" and res["distance_km"] > 8 and res["max_km"] == 8
    cart = view_cart(db, users["priya"])
    assert [i["item_id"] for b in cart["branches"] for i in b["items"]] == [biryani[0]]


def test_items_too_far_after_a_delivery_change_are_flagged_like_unavailable(db, users, biryani):
    add_to_cart(db, users["priya"], *biryani, 2)
    far_area = db.execute(f"""select p.area_id from public.areas p, public.branches b where b.branch_id = %s
                              and {HAVERSINE} > 9 order by p.area_id limit 1""", (biryani[1],)).fetchone()["area_id"]
    cart = set_delivery(db, users["priya"], area=far_area)["cart"]
    assert cart["status"] == "empty" and cart["can_confirm"] is False and cart["grand_total"] == 0
    assert [(u["item_id"], u["reason"]) for u in cart["unavailable"]] == [(biryani[0], "too_far")]
    cart = set_delivery(db, users["priya"], area="Madhapur")["cart"]          # back in range: counted again
    assert cart["unavailable"] == [] and cart["grand_total"] > 0 and cart["can_confirm"] is True
    check_totals(db, users["priya"], cart)


def test_a_far_item_beside_a_near_one_is_left_out_of_the_total(db, users, biryani):
    """Two restaurants; after the delivery point moves, one is beyond 8 km and one is near: only the near one
    is billed, the far one is flagged, and the cart can't be confirmed until it is removed."""
    add_to_cart(db, users["priya"], *biryani)
    far_area = db.execute(f"""select p.area_id from public.areas p, public.branches b where b.branch_id = %s
                              and {HAVERSINE} > 9 order by p.area_id limit 1""", (biryani[1],)).fetchone()["area_id"]
    near = far_item(db, far_area, min_km=-1)                       # the nearest Chicken Dum Biryani to far_area
    set_delivery(db, users["priya"], area=far_area)
    assert add_to_cart(db, users["priya"], *near)["status"] == "ok"
    cart = view_cart(db, users["priya"])
    assert [(u["item_id"], u["reason"]) for u in cart["unavailable"]] == [(biryani[0], "too_far")]
    assert [b["branch_id"] for b in cart["branches"]] == [near[1]] and cart["can_confirm"] is False
    check_totals(db, users["priya"], cart)
    remove_from_cart(db, users["priya"], biryani[0])
    assert view_cart(db, users["priya"])["can_confirm"] is True


def test_unavailable_reasons_are_named(db, users, biryani):
    sandwich = item(db, "Chick King", "Paneer Tikka Sandwich", "madhapur")
    add_to_cart(db, users["priya"], *biryani)
    add_to_cart(db, users["priya"], *sandwich)
    db.execute("update public.menu_items set is_available = false where item_id = %s", (sandwich[0],))
    db.execute("update public.branches set open_for_demo = false where branch_id = %s", (biryani[1],))
    reasons = {u["item_id"]: u["reason"] for u in view_cart(db, users["priya"])["unavailable"]}
    assert reasons == {sandwich[0]: "unavailable", biryani[0]: "branch_closed"}
