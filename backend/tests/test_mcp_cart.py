"""MCP cart tools, module M2 (D-067): what an additive-only caller may put in a cart, and what it may never do.

Full rigour: these rules stand in for the yes a model can't give. A model in another app has no user message and no
confirmation card, so code decides from the database and the token alone:
  · it never touches a confirmed cart (the website's yes) · it never replaces or removes · it never adds meat for a
  saved vegetarian · quantity and cart size are capped · it sees no cart_id/quote_id to confirm with.
"""

import json

import pytest

from app import mcp_cart
from app.mcp_cart import MAX_CART_UNITS, MAX_ITEM_QTY
from app.tools import cart, orders, preferences
from tests.test_mcp_server import call, handler_for, refused_handler


def cart_rows(db, user):
    return db.execute("""select ci.item_id, ci.branch_id, ci.qty, c.status from public.cart_items ci
                         join public.carts c using (cart_id) where c.user_id = %s and c.status in ('open', 'confirmed')
                         order by ci.item_id""", (user,)).fetchall()


def units(db, user):
    return sum(r["qty"] for r in cart_rows(db, user))


def items(db, veg: bool, n: int):
    """n available items of one open Madhapur branch (veg or non-veg), the same ones every run."""
    rows = db.execute("""select m.item_id, b.branch_id, d.name from public.menu_items m
                         join public.branches b using (restaurant_id) join public.dishes d using (dish_id)
                         where b.area_id = 'madhapur' and m.is_available and b.open_for_demo and d.is_veg = %s
                         order by b.branch_id, m.item_id""", (veg,)).fetchall()
    by_branch: dict = {}
    for r in rows:
        by_branch.setdefault(r["branch_id"], []).append(r)
    branch = next(b for b, v in by_branch.items() if len(v) >= n)
    return by_branch[branch][:n]


@pytest.fixture
def people(db, demo_users):
    """(vegetarian user, user with no vegetarian diet) among the seeded demo users."""
    diets = {r["user_id"]: r["v"] for r in db.execute(
        "select user_id, value #>> '{}' as v from public.user_preferences where key = 'diet'")}
    veg = next(u for u in demo_users if diets.get(u) in preferences.VEG_DIETS)
    other = next(u for u in demo_users if diets.get(u) not in preferences.VEG_DIETS)
    return veg, other


def add(handler, it, qty=None):
    args = {"item_id": it["item_id"], "branch_id": it["branch_id"], **({"qty": qty} if qty is not None else {})}
    return call(handler, "add_to_cart", args)


# ─── adding ──────────────────────────────────────────────────────────────────────────────────────────────

def test_adding_an_item_puts_it_in_that_users_cart_only(db, verifier, make_token, people):
    veg, other = people
    it = items(db, True, 1)[0]
    err, reply = add(handler_for(db, verifier, make_token(veg)), it, 2)
    assert not err and reply["status"] == "ok" and reply["added"]["qty"] == 2
    assert [(r["item_id"], r["qty"]) for r in cart_rows(db, veg)] == [(it["item_id"], 2)]
    assert cart_rows(db, other) == []
    text = json.dumps(reply)
    assert "quote_id" not in text and "cart_id" not in text and "confirm_card" not in text
    assert "website" in reply["message"] and reply["cart"]["grand_total"] > 0


def test_a_non_veg_item_is_refused_for_a_saved_vegetarian_and_allowed_otherwise(db, verifier, make_token, people):
    veg, other = people
    meat = items(db, False, 1)[0]
    err, reply = add(handler_for(db, verifier, make_token(veg)), meat)
    assert err is False and reply["status"] == "diet_blocked" and reply["items"] == [meat["name"]]
    assert cart_rows(db, veg) == []
    _, ok = add(handler_for(db, verifier, make_token(other)), meat)
    assert ok["status"] == "ok" and len(cart_rows(db, other)) == 1


@pytest.mark.parametrize("diet", ["vegetarian", "eggetarian"])
def test_the_diet_is_read_when_the_call_is_made(db, verifier, make_token, people, diet):
    """Saved a moment ago counts (there is no 'diet at the start of the turn' over MCP)."""
    _, other = people
    meat = items(db, False, 1)[0]
    handler = handler_for(db, verifier, make_token(other))
    preferences.save_preference(db, other, "diet", diet, "settings")
    _, reply = add(handler, meat)
    assert reply["status"] == "diet_blocked" and cart_rows(db, other) == []


def test_a_diet_that_is_not_vegetarian_blocks_nothing(db, verifier, make_token, people):
    _, other = people
    preferences.save_preference(db, other, "diet", "non_vegetarian", "settings")
    _, reply = add(handler_for(db, verifier, make_token(other)), items(db, False, 1)[0])
    assert reply["status"] == "ok"


# ─── the limits ──────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("qty", [0, -1, MAX_ITEM_QTY + 1, 20, 1.5, "3", True, "ten"])
def test_a_quantity_outside_the_limit_is_refused_before_anything_runs(db, verifier, make_token, people, qty):
    veg, _ = people
    it = items(db, True, 1)[0]
    err, reply = call(handler_for(db, verifier, make_token(veg)), "add_to_cart",
                      {"item_id": it["item_id"], "branch_id": it["branch_id"], "qty": qty})
    assert err and reply["status"] == "invalid_arguments"
    assert cart_rows(db, veg) == []


def test_the_limit_is_per_item_across_calls(db, verifier, make_token, people):
    veg, _ = people
    it = items(db, True, 1)[0]
    handler = handler_for(db, verifier, make_token(veg))
    assert add(handler, it, MAX_ITEM_QTY)[1]["status"] == "ok"
    err, reply = add(handler, it, 1)
    assert reply["status"] == "qty_limit" and reply["in_cart"] == MAX_ITEM_QTY
    assert units(db, veg) == MAX_ITEM_QTY


def test_the_limit_counts_what_the_website_already_put_in_the_cart(db, verifier, make_token, people):
    veg, _ = people
    it = items(db, True, 1)[0]
    assert cart.add_to_cart(db, veg, it["item_id"], it["branch_id"], 15)["status"] == "ok"      # the site allows 20
    _, reply = add(handler_for(db, verifier, make_token(veg)), it, 1)
    assert reply["status"] == "qty_limit" and units(db, veg) == 15


def test_the_cart_as_a_whole_is_capped(db, verifier, make_token, people):
    veg, _ = people
    a, b, c, d = items(db, True, 4)
    handler = handler_for(db, verifier, make_token(veg))
    for it in (a, b, c):
        assert add(handler, it, MAX_ITEM_QTY)[1]["status"] == "ok"
    assert units(db, veg) == MAX_CART_UNITS
    _, reply = add(handler, d, 1)
    assert reply["status"] == "cart_limit" and reply["in_cart"] == MAX_CART_UNITS
    assert units(db, veg) == MAX_CART_UNITS


def test_the_total_cap_counts_the_website_items_too(db, verifier, make_token, people):
    veg, _ = people
    a, b, c, d = items(db, True, 4)
    for it in (a, b):
        cart.add_to_cart(db, veg, it["item_id"], it["branch_id"], 15)
    _, reply = add(handler_for(db, verifier, make_token(veg)), c, 1)
    assert reply["status"] == "cart_limit"        # 30 already (15 + 15), though each line was within the site's 20


# ─── a confirmed cart is the website's yes ───────────────────────────────────────────────────────────────

def test_a_confirmed_cart_is_never_touched(db, verifier, make_token, people):
    veg, _ = people
    first, second = items(db, True, 2)
    cart.add_to_cart(db, veg, first["item_id"], first["branch_id"], 1)
    view = cart.view_cart(db, veg)
    done = orders.confirm_cart(db, veg, view["cart_id"], view["quote_id"], source="website")
    assert done["status"] == "ok", done
    before = cart_rows(db, veg)
    err, reply = add(handler_for(db, verifier, make_token(veg)), second)
    assert reply["status"] == "cart_confirmed"
    after = cart_rows(db, veg)
    assert after == before and all(r["status"] == "confirmed" for r in after)       # still confirmed, nothing added
    _, again = add(handler_for(db, verifier, make_token(veg)), first)               # even more of the same item
    assert again["status"] == "cart_confirmed" and cart_rows(db, veg) == before


# ─── plans ───────────────────────────────────────────────────────────────────────────────────────────────

REQUEST = {"budget": 700, "people": 2, "area": "Madhapur"}


def first_plan(handler):
    _, planned = call(handler, "plan_meal", REQUEST)
    assert planned["status"] == "ok", planned
    return planned["plans"][0]


def test_a_plan_goes_into_an_empty_cart_with_the_planners_own_total(db, verifier, make_token, people):
    veg, _ = people
    handler = handler_for(db, verifier, make_token(veg))
    plan = first_plan(handler)
    err, reply = call(handler, "add_plan_to_cart", {"request": REQUEST, "plan_id": plan["plan_id"]})
    assert not err and reply["status"] == "ok" and reply["cart"]["grand_total"] == plan["grand_total"]
    text = json.dumps(reply)
    assert "quote_id" not in text and "cart_id" not in text and "confirm_card" not in text
    assert units(db, veg) == sum(it["qty"] for r in plan["restaurants"] for it in r["items"])


def test_a_plan_never_replaces_a_cart_that_has_items(db, verifier, make_token, people):
    veg, _ = people
    handler = handler_for(db, verifier, make_token(veg))
    plan = first_plan(handler)
    it = items(db, True, 1)[0]
    cart.add_to_cart(db, veg, it["item_id"], it["branch_id"], 1)
    before = cart_rows(db, veg)
    err, reply = call(handler, "add_plan_to_cart", {"request": REQUEST, "plan_id": plan["plan_id"]})
    assert reply["status"] == "cart_not_empty" and cart_rows(db, veg) == before


def test_there_is_no_way_to_ask_for_a_replacement(db, verifier, make_token, people):
    veg, _ = people
    handler = handler_for(db, verifier, make_token(veg))
    plan = first_plan(handler)
    it = items(db, True, 1)[0]
    cart.add_to_cart(db, veg, it["item_id"], it["branch_id"], 1)
    before = cart_rows(db, veg)
    err, reply = call(handler, "add_plan_to_cart", {"request": REQUEST, "plan_id": plan["plan_id"], "replace": True})
    assert err and reply["status"] == "invalid_arguments" and cart_rows(db, veg) == before


def test_a_plan_is_not_added_to_a_confirmed_cart(db, verifier, make_token, people):
    veg, _ = people
    handler = handler_for(db, verifier, make_token(veg))
    plan = first_plan(handler)
    it = items(db, True, 1)[0]
    cart.add_to_cart(db, veg, it["item_id"], it["branch_id"], 1)
    view = cart.view_cart(db, veg)
    orders.confirm_cart(db, veg, view["cart_id"], view["quote_id"], source="website")
    before = cart_rows(db, veg)
    _, reply = call(handler, "add_plan_to_cart", {"request": REQUEST, "plan_id": plan["plan_id"]})
    assert reply["status"] == "cart_confirmed" and cart_rows(db, veg) == before


def test_an_unknown_plan_adds_nothing(db, verifier, make_token, people):
    veg, _ = people
    _, reply = call(handler_for(db, verifier, make_token(veg)), "add_plan_to_cart",
                    {"request": REQUEST, "plan_id": "not-a-plan"})
    assert reply["status"] == "plan_changed" and cart_rows(db, veg) == []


def fake_plan(units_each, veg=True):
    return {"plan_id": "p1", "label": "Fake", "grand_total": 100,
            "restaurants": [{"branch_id": "b-fake", "items": [
                {"item_id": f"i-{i}", "qty": q, "name": f"Dish {i}", "is_veg": veg} for i, q in enumerate(units_each)]}]}


def test_a_plan_with_meat_is_refused_for_a_saved_vegetarian(db, verifier, make_token, people, monkeypatch):
    """The planner already plans vegetarian for a saved vegetarian; this is the second lock, shown by feeding it a
    plan it would never make."""
    veg, other = people
    monkeypatch.setattr(mcp_cart.planner, "plan_meal", lambda *a, **k: {"status": "ok", "plans": [fake_plan([1, 1], veg=False)]})
    _, reply = call(handler_for(db, verifier, make_token(veg)), "add_plan_to_cart",
                    {"request": REQUEST, "plan_id": "p1"})
    assert reply["status"] == "diet_blocked" and cart_rows(db, veg) == []


def test_a_plan_over_the_item_or_cart_limits_is_refused(db, verifier, make_token, people, monkeypatch):
    veg, _ = people
    for sizes, status in (([MAX_ITEM_QTY + 1], "qty_limit"), ([10, 10, 10, 1], "cart_limit")):
        monkeypatch.setattr(mcp_cart.planner, "plan_meal", lambda *a, _s=sizes, **k: {"status": "ok", "plans": [fake_plan(_s)]})
        _, reply = call(handler_for(db, verifier, make_token(veg)), "add_plan_to_cart",
                        {"request": REQUEST, "plan_id": "p1"})
        assert reply["status"] == status and cart_rows(db, veg) == []


# ─── identity and absence of the unsafe tools ────────────────────────────────────────────────────────────

def test_no_token_means_no_cart_change_and_no_database(verifier):
    handler = refused_handler(verifier, None)
    for name, args in (("add_to_cart", {"item_id": "i-1", "branch_id": "b-n1"}),
                       ("add_plan_to_cart", {"request": REQUEST, "plan_id": "p"})):
        err, reply = call(handler, name, args)
        assert err and reply["status"] == "sign_in_required"


def test_one_users_additions_are_invisible_to_another(db, verifier, make_token, people):
    veg, other = people
    it = items(db, True, 1)[0]
    add(handler_for(db, verifier, make_token(veg)), it, 3)
    _, theirs = call(handler_for(db, verifier, make_token(other)), "view_cart")
    assert not theirs.get("branches") and cart_rows(db, other) == []


def test_the_cart_can_only_grow_from_here(db, verifier, make_token, people):
    """The removal, replacement and delivery tools are not here; asking for them changes nothing."""
    veg, _ = people
    it = items(db, True, 1)[0]
    handler = handler_for(db, verifier, make_token(veg))
    add(handler, it, 2)
    before = cart_rows(db, veg)
    for name in ("remove_from_cart", "set_delivery", "confirm_cart", "place_order", "save_preference"):
        err, reply = call(handler, name, {"item_id": it["item_id"], "area": "Kondapur", "key": "diet"})
        assert err and reply["status"] == "unknown_tool"
    assert cart_rows(db, veg) == before
