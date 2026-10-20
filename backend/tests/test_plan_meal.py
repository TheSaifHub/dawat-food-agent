"""5d–5f · plan_meal and add_plan_to_cart against the real database, inside a rolled-back transaction.

Every plan returned is re-judged by an ORACLE written for this file: its own SQL for prices, flags and distances
(SQL haversine), its own fee and GST maths (Decimal), and a brute-force matching of people to portions for every
possible overlap (not the builder's greedy count, not the checker's Hall condition).
"""

import math
import uuid
from decimal import ROUND_HALF_UP, Decimal

import pytest

from app.tools.cart import add_to_cart, view_cart
from app.tools.planner import PlanCartMismatch, add_plan_to_cart, plan_meal

HAVERSINE = """6371 * 2 * asin(sqrt(power(sin(radians(b.lat - %(lat)s) / 2), 2)
               + cos(radians(%(lat)s)) * cos(radians(b.lat)) * power(sin(radians(b.lon - %(lon)s) / 2), 2)))"""
DINNER = {"budget": 1000, "people": 4, "veg_count": 2, "non_spicy_count": 1, "meal_type": "dinner", "area": "Madhapur"}
# The oracle's own idea of a proper lunch/dinner/meal main (Saif, Session 12), written out here, not imported.
ORACLE_MEAL_MAINS = ("biryani", "mandi", "meals", "curry", "rice", "noodles", "kebab", "pizza", "pasta",
                     "fried_chicken", "continental", "mexican", "tiffin")


def gst(amount: int, pct: int) -> int:
    return int((Decimal(amount) * pct / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def can_feed(people: list[tuple[bool, bool]], portions: list[tuple[bool, bool]]) -> bool:
    """Brute-force bipartite matching (Kuhn): each (needs_veg, needs_mild) person to a distinct (veg, mild) portion."""
    owner = [-1] * len(portions)

    def ok(p, q):
        return (portions[q][0] or not people[p][0]) and (portions[q][1] or not people[p][1])

    def try_person(p, seen):
        for q in range(len(portions)):
            if ok(p, q) and q not in seen:
                seen.add(q)
                if owner[q] == -1 or try_person(owner[q], seen):
                    owner[q] = p
                    return True
        return False
    return all(try_person(p, set()) for p in range(len(people)))


def oracle(db, request: dict, plan: dict, point: tuple[float, float], radius: float, budget: int | None = None):
    """Asserts every hard rule independently; returns the oracle's own total."""
    budget = request["budget"] if budget is None else budget
    people, veg, ns = request["people"], request.get("veg_count", 0), request.get("non_spicy_count", 0)
    meal = request.get("meal_type", "meal")
    total, portions, restaurants, all_lines = 0, [], set(), []
    for r in plan["restaurants"]:
        rows = {row["item_id"]: row for row in db.execute(f"""
            select m.item_id, m.price, m.is_available, m.restaurant_id = b.restaurant_id as on_menu, b.open_for_demo,
                   b.restaurant_id, d.is_veg, d.spice_level, d.serves, d.course, d.category, {HAVERSINE} as km
            from public.menu_items m join public.dishes d using (dish_id) join public.branches b on b.branch_id = %(b)s
            where m.item_id = any(%(ids)s)""", {"lat": point[0], "lon": point[1], "b": r["branch_id"],
                                               "ids": [i["item_id"] for i in r["items"]]})}
        items = 0
        for it in r["items"]:
            row = rows[it["item_id"]]
            assert row["is_available"] and row["on_menu"] and row["open_for_demo"]
            assert row["km"] <= radius + 0.0005
            assert it["price"] == row["price"] and it["is_veg"] == row["is_veg"]
            assert it["spice_level"] == row["spice_level"] and 1 <= it["qty"] <= 20
            assert row["course"] not in ("dessert", "drink")
            items += row["price"] * it["qty"]
            restaurants.add(row["restaurant_id"])
            all_lines.append(row)
            if meal in ("lunch", "dinner", "meal") and row["course"] == "main":
                assert row["category"] in ORACLE_MEAL_MAINS, f"{row['category']} is not a proper {meal} main"
            if row["course"] == "main" or (meal == "snack" and row["category"] in
                                           ("snack", "bakery", "starter", "fried_chicken", "kebab")):
                portions += [(row["is_veg"], row["spice_level"] <= 1)] * (row["serves"] * it["qty"])
        fee = 0 if items >= 499 else 25 + 10 * max(0, math.ceil(round(next(iter(rows.values()))["km"] - 2, 3)))
        branch_total = items + fee + gst(items, 5) + gst(fee, 18)
        assert r["total"] == branch_total
        total += branch_total
    assert plan["grand_total"] == total and total <= budget
    assert len(restaurants) <= 2
    assert len(portions) >= people
    lo, hi = max(0, veg + ns - people), min(veg, ns)
    if request.get("non_spicy_veg_count") is not None:          # the user said who: only that case
        lo = hi = request["non_spicy_veg_count"]
    for k in range(lo, hi + 1):
        group = ([(True, True)] * k + [(True, False)] * (veg - k) + [(False, True)] * (ns - k)
                 + [(False, False)] * (people - veg - ns + k))
        assert can_feed(group, portions), (k, group, portions)
    if veg == people:
        assert all(row["is_veg"] for row in all_lines)
    if ns == people:
        assert all(row["spice_level"] <= 1 for row in all_lines)
    if meal in ("lunch", "dinner", "meal"):
        mains = [row for row in all_lines if row["course"] == "main"]
        assert any(row["category"] in ("biryani", "mandi", "meals") for row in mains) or \
            any(row["course"] == "side" for row in all_lines)
        if any(row["category"] == "curry" for row in mains):
            assert any(row["category"] in ("bread", "rice") for row in all_lines)
    return total


def point_of(out):
    return out["delivery"]["lat"], out["delivery"]["lon"]


# ─── answers before planning ─────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("request_, missing", [
    ({}, ["people", "budget", "area"]),
    ({"people": 2}, ["budget", "area"]),
    ({"people": 2, "budget": 500}, ["area"]),
])
def test_missing_information_is_asked_for_in_order(db, request_, missing):
    out = plan_meal(db, request_)
    assert out["status"] == "needs_info" and out["missing"] == missing
    assert "plans" not in out and "grand_total" not in str(out)


@pytest.mark.parametrize("area, status", [("madhapoor", "confirm_area"), ("Hyderabad", "needs_area"),
                                          ("Manikonda", "outside_coverage"), ("Zzyzx", "unknown_area")])
def test_an_unresolved_area_stops_the_planner(db, area, status):
    out = plan_meal(db, {**DINNER, "area": area})
    assert out["status"] == status and "plans" not in out


def test_text_numbers_are_refused(db):
    out = plan_meal(db, {**DINNER, "budget": "1000"})
    assert out["status"] == "invalid_input" and any(p.startswith("budget") for p in out["problems"])


# ─── plans ───────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("request_", [
    DINNER,
    {"budget": 500, "people": 2, "veg_count": 1, "spice_preference": "spicy", "meal_type": "meal", "area": "Madhapur"},
    {"budget": 700, "people": 3, "veg_count": 3, "meal_type": "lunch", "area": "Charminar"},
    {"budget": 900, "people": 3, "non_spicy_count": 3, "meal_type": "dinner", "area": "Kukatpally"},
    {"budget": 400, "people": 2, "meal_type": "snack", "area": "Gachibowli"},
    {"budget": 250, "people": 1, "veg_count": 1, "non_spicy_count": 1, "meal_type": "breakfast", "area": "Secunderabad"},
    {"budget": 3000, "people": 10, "veg_count": 3, "non_spicy_count": 4, "non_spicy_veg_count": 2,
     "meal_type": "dinner", "area": "Tolichowki"},
])
def test_every_plan_passes_the_oracle(db, request_):
    out = plan_meal(db, request_)
    assert out["status"] == "ok", out.get("message")
    assert out["planner"]["refused_by_checker"] == 0
    assert 1 <= len(out["plans"]) <= 3
    assert [p["role"] for p in out["plans"]] == ["best_value", "best_match", "variety"][:len(out["plans"])]
    for p in out["plans"]:
        oracle(db, request_, p, point_of(out), out["radius_km"])
        assert p["budget_left"] == request_["budget"] - p["grand_total"]
    ids = [p["plan_id"] for p in out["plans"]]
    assert len(set(ids)) == len(ids)
    # three genuinely different plans
    for i, a in enumerate(out["plans"]):
        for b in out["plans"][i + 1:]:
            ra, rb = {r["restaurant_id"] for r in a["restaurants"]}, {r["restaurant_id"] for r in b["restaurants"]}
            ia = {it["item_id"] for r in a["restaurants"] for it in r["items"]}
            ib = {it["item_id"] for r in b["restaurants"] for it in r["items"]}
            assert ra != rb or len(ia & ib) <= max(len(ia), len(ib)) / 2


def items_of(plan) -> list:
    return sorted((r["branch_id"], it["item_id"], it["qty"]) for r in plan["restaurants"] for it in r["items"])


def test_best_value_is_the_cheapest_at_every_budget(db):
    """Saif, Session 12: best value is the cheapest plan found within 5 km. Here (a fixed case) it is the same plan
    at every budget it fits, and one rupee less is over budget with exactly that price quoted."""
    out = plan_meal(db, DINNER)
    best = out["plans"][0]
    x = best["grand_total"]
    assert best["role"] == "best_value" and x == min(p["grand_total"] for p in out["plans"])
    for budget in (x, x + 1, (x + DINNER["budget"]) // 2, 5000):
        again = plan_meal(db, {**DINNER, "budget": budget})
        assert again["status"] == "ok" and items_of(again["plans"][0]) == items_of(best)
        assert all(p["grand_total"] >= x for p in again["plans"])
    below = plan_meal(db, {**DINNER, "budget": x - 1})
    assert below["status"] == "over_budget" and below["cheapest_total"] == x
    assert items_of(below["cheapest_plan"]) == items_of(best)


def test_best_value_looks_past_3_km(db):
    """The weak spot Session 11 left open: with 3 plans inside 3 km the search stopped there, so 'best value' was
    ₹277 at a ₹297 budget while a ₹276 budget (forcing the 5 km search) showed ₹205. Now best value always comes
    from the whole 5 km and doesn't depend on the budget."""
    request_ = {"people": 1, "meal_type": "meal", "area": "Chanchalguda"}
    a, b = plan_meal(db, {**request_, "budget": 297}), plan_meal(db, {**request_, "budget": 276})
    assert a["status"] == b["status"] == "ok"
    assert items_of(a["plans"][0]) == items_of(b["plans"][0])
    assert a["plans"][0]["grand_total"] == b["plans"][0]["grand_total"] < 205
    assert any(r["distance_km"] > 3.0 for r in a["plans"][0]["restaurants"]) and a["radius_km"] == 5.0
    for p in a["plans"]:
        oracle(db, {**request_, "budget": 297}, p, point_of(a), a["radius_km"])


@pytest.mark.parametrize("request_, independent", [
    ({"people": 1, "area": "Barkatpura"}, 125),                                       # Rasam cheaper than Sambar
    ({"people": 2, "veg_count": 1, "non_spicy_count": 1, "area": "Katedan"}, 525),    # was found, then hidden
    ({"people": 6, "non_spicy_count": 6, "meal_type": "dinner", "area": "Moghalpura"}, 530),   # ₹499 free delivery
    ({"people": 3, "non_spicy_count": 1, "area": "Jeedimetla"}, 536),                 # one side per plate counted
    ({"people": 3, "non_spicy_count": 1, "area": "Hayathnagar"}, 536),
])
def test_rule_breaker_cheaper_plans_are_found(db, request_, independent):
    """Session 12 rule-breaker, Break A: its own search found these valid plans cheaper than our best value, and at
    their price we said "no plan fits". Best value must now be at most that, and that budget must plan."""
    out = plan_meal(db, {**request_, "budget": 20000})
    assert out["status"] == "ok" and out["plans"][0]["grand_total"] <= independent
    at = plan_meal(db, {**request_, "budget": independent})
    assert at["status"] == "ok" and at["plans"][0]["grand_total"] <= independent
    for p in at["plans"]:
        oracle(db, {**request_, "budget": independent}, p, point_of(at), at["radius_km"])


def test_meal_main_lists_cover_every_category(db):
    """The builder's deny-list and the checker's allow-list split the database's main categories exactly, so no
    category is quietly a portion for one and not the other."""
    from app.planner.candidates import NOT_MEAL_MAINS
    from app.planner.rules import PROPER_MEAL_MAINS
    cats = {r["category"] for r in db.execute("select distinct category from public.dishes where course = 'main'")}
    assert not NOT_MEAL_MAINS & PROPER_MEAL_MAINS
    assert cats <= NOT_MEAL_MAINS | PROPER_MEAL_MAINS
    assert PROPER_MEAL_MAINS <= cats and set(ORACLE_MEAL_MAINS) == PROPER_MEAL_MAINS


@pytest.mark.parametrize("area", ["Gachibowli", "Madhapur", "Ameerpet", "Kukatpally"])
def test_no_burger_or_sandwich_dinner(db, area):
    """Session 11 showed 'Veg Burger ×10 + Samosa ×5' as a dinner's best value."""
    request_ = {"budget": 3000, "people": 10, "meal_type": "dinner", "area": area}
    out = plan_meal(db, request_)
    assert out["status"] == "ok"
    for p in out["plans"]:
        oracle(db, request_, p, point_of(out), out["radius_km"])
        assert not {it["category"] for r in p["restaurants"] for it in r["items"]} & \
            {"burger", "sandwich", "roll", "shawarma", "snack", "bakery"}


def test_plans_are_deterministic(db):
    a, b = plan_meal(db, DINNER), plan_meal(db, {**DINNER, "area": "madhapur"})
    assert [p["plan_id"] for p in a["plans"]] == [p["plan_id"] for p in b["plans"]]
    assert a["plans"] == b["plans"]


def test_the_unclear_overlap_note(db):
    out = plan_meal(db, DINNER)
    assert all("whoever the non-spicy person is" in p["diet_note"] for p in out["plans"])
    known = plan_meal(db, {**DINNER, "non_spicy_veg_count": 1})
    assert all("whoever" not in p["diet_note"] for p in known["plans"])


BREAKFAST_VEG_MILD = {"budget": 2000, "people": 2, "veg_count": 2, "non_spicy_count": 2, "meal_type": "breakfast"}


def test_fewer_than_three_plans_widens_to_5_km(db):
    out = plan_meal(db, {**BREAKFAST_VEG_MILD, "area": "Alwal"})
    assert out["status"] == "ok" and out["radius_km"] == 5.0
    assert any(r["distance_km"] > 3.0 for p in out["plans"] for r in p["restaurants"])
    for p in out["plans"]:
        oracle(db, BREAKFAST_VEG_MILD, p, point_of(out), 5.0)


def test_fewer_than_three_genuinely_different_plans_are_said_plainly(db):
    out = plan_meal(db, {**BREAKFAST_VEG_MILD, "area": "Budvel"})
    assert out["status"] == "ok" and out["radius_km"] == 5.0 and len(out["plans"]) < 3
    assert f"Only {len(out['plans'])} genuinely different plan" in out["message"]


# ─── impossible requests ─────────────────────────────────────────────────────────────────────────────────────
def test_over_budget_gives_the_real_cheapest_valid_plan(db):
    request_ = {"budget": 150, "people": 4, "meal_type": "dinner", "area": "Gachibowli"}
    out = plan_meal(db, request_)
    assert out["status"] == "over_budget" and "plans" not in out
    cheapest = out["cheapest_plan"]
    assert "plan_id" not in cheapest                          # can't be added as a plan for a ₹150 request
    total = oracle(db, request_, cheapest, point_of(out), 5.0, budget=10 ** 9)
    assert total == out["cheapest_total"] > 150 and out["short_by"] == total - 150
    smaller = out["largest_group_within_budget"]
    assert smaller and smaller["people"] < 4 and smaller["cheapest_total"] <= 150
    assert f"₹{total}" in out["message"]


def test_no_valid_plan_names_the_blocking_rule(db):
    out = plan_meal(db, {"budget": 2000, "people": 2, "veg_count": 2, "non_spicy_count": 2, "meal_type": "breakfast",
                         "area": "Hayathnagar"})
    assert out["status"] == "no_valid_plan" and out["reasons"][0]["rule"] == "places"
    assert "plans" not in out and "cheapest_plan" not in out


# ─── the user's delivery point; plan → cart ──────────────────────────────────────────────────────────────────
@pytest.fixture
def priya(demo_users, db):
    uid = next(u for u in demo_users if "Priya" in db.execute(
        "select display_name from public.users where user_id = %s", (u,)).fetchone()["display_name"])
    assert view_cart(db, uid)["status"] == "empty"            # demo users start with no cart (D-021)
    return uid


def test_a_signed_in_user_is_planned_from_their_address(db, priya):
    addr = db.execute("""insert into public.addresses (user_id, label, line1, area_id, lat, lon, is_default)
                         values (%s, 'Test', 'Test line (fictional)', 'madhapur', 17.4480, 78.3800, false)
                         returning address_id""", (priya,)).fetchone()["address_id"]
    db.execute("update public.addresses set is_default = (address_id = %s) where user_id = %s", (addr, priya))
    out = plan_meal(db, DINNER, priya)
    assert out["delivery"]["address_id"] == str(addr) and (out["delivery"]["lat"], out["delivery"]["lon"]) == (17.448, 78.38)
    for p in out["plans"]:
        oracle(db, DINNER, p, (17.448, 78.38), out["radius_km"])
    added = add_plan_to_cart(db, priya, DINNER, out["plans"][1]["plan_id"], source="website")
    assert added["status"] == "ok" and added["cart"]["delivery"]["address_id"] == str(addr)
    assert added["cart"]["grand_total"] == out["plans"][1]["grand_total"]


def test_add_plan_fills_the_cart_with_exactly_the_plan(db, priya):
    out = plan_meal(db, DINNER, priya)
    plan = out["plans"][0]
    added = add_plan_to_cart(db, priya, DINNER, plan["plan_id"], source="website")
    assert added["status"] == "ok"
    cart = view_cart(db, priya)
    assert cart["cart_status"] == "open"                      # NOT confirmed: the user still says yes
    assert cart["grand_total"] == plan["grand_total"]
    in_cart = sorted((it["item_id"], b["branch_id"], it["qty"]) for b in cart["branches"] for it in b["items"])
    planned = sorted((it["item_id"], r["branch_id"], it["qty"]) for r in plan["restaurants"] for it in r["items"])
    assert in_cart == planned


def test_a_cart_with_items_is_not_overwritten_without_a_yes(db, priya):
    out = plan_meal(db, DINNER, priya)
    add_plan_to_cart(db, priya, DINNER, out["plans"][0]["plan_id"], source="website")
    before = view_cart(db, priya)
    again = add_plan_to_cart(db, priya, DINNER, out["plans"][1]["plan_id"], source="website")
    assert again["status"] == "cart_not_empty"
    assert view_cart(db, priya)["quote_id"] == before["quote_id"]
    replaced = add_plan_to_cart(db, priya, DINNER, out["plans"][1]["plan_id"], replace=True, source="website")
    assert replaced["status"] == "ok" and replaced["cart"]["grand_total"] == out["plans"][1]["grand_total"]


@pytest.fixture
def full_cart(db, priya):
    """Priya's cart holds plan 0; plan 1 is the one offered as a replacement."""
    out = plan_meal(db, DINNER, priya)
    assert add_plan_to_cart(db, priya, DINNER, out["plans"][0]["plan_id"], source="website")["status"] == "ok"
    return out, view_cart(db, priya)


# A handful per answer: the full language coverage is in test_consent.py (pure and fast); each case here runs the
# planner three times.
@pytest.mark.parametrize("message", ["yes", "haan, replace kar do", "అవును"])
def test_from_chat_a_clear_yes_replaces_the_cart(db, priya, full_cart, message):
    out, _ = full_cart
    r = add_plan_to_cart(db, priya, DINNER, out["plans"][1]["plan_id"], replace=True, source="chat",
                         user_message=message)
    assert r["status"] == "ok" and r["cart"]["grand_total"] == out["plans"][1]["grand_total"], message


@pytest.mark.parametrize("message, said", [
    ("no", "no"), ("haan par ruko", "no"), ("vaddu", "no"),
    ("replace?", "unclear"), ("ok thanks", "unclear"), ("ha ha", "unclear"), ("show me plan 2", "unclear"),
])
def test_from_chat_anything_but_a_clear_yes_leaves_the_cart_alone(db, priya, full_cart, message, said):
    out, before = full_cart
    r = add_plan_to_cart(db, priya, DINNER, out["plans"][1]["plan_id"], replace=True, source="chat",
                         user_message=message)
    assert r["status"] == "no_clear_yes" and r["consent"]["consent"] == said, message
    after = view_cart(db, priya)
    assert after["quote_id"] == before["quote_id"] and after["cart_status"] == before["cart_status"]


def test_from_chat_a_missing_message_never_replaces(db, priya, full_cart):
    out, before = full_cart
    r = add_plan_to_cart(db, priya, DINNER, out["plans"][1]["plan_id"], replace=True, source="chat")
    assert r["status"] == "no_clear_yes" and view_cart(db, priya)["quote_id"] == before["quote_id"]


def test_the_yes_check_only_guards_what_would_be_removed(db, priya):
    # An empty cart loses nothing, so a plan goes in from chat without a yes; replace=true changes nothing there.
    out = plan_meal(db, DINNER, priya)
    r = add_plan_to_cart(db, priya, DINNER, out["plans"][0]["plan_id"], replace=True, source="chat",
                         user_message="plan 1 please")
    assert r["status"] == "ok"
    # And without replace, a full cart is never touched whatever the message says.
    r = add_plan_to_cart(db, priya, DINNER, out["plans"][1]["plan_id"], source="chat", user_message="yes")
    assert r["status"] == "cart_not_empty"


def test_the_source_has_no_default_and_must_be_known(db, priya, full_cart):
    out, before = full_cart
    with pytest.raises(TypeError):
        add_plan_to_cart(db, priya, DINNER, out["plans"][1]["plan_id"], replace=True)
    for source in ("", "Chat", "agent", "llm", None):
        r = add_plan_to_cart(db, priya, DINNER, out["plans"][1]["plan_id"], replace=True, source=source,
                             user_message="yes")
        assert r["status"] == "invalid_input", source
    assert view_cart(db, priya)["quote_id"] == before["quote_id"]


def test_a_made_up_or_edited_plan_is_refused(db, priya):
    out = plan_meal(db, DINNER, priya)
    for request_, pid in [(DINNER, "0" * 20), ({**DINNER, "budget": 2000}, out["plans"][0]["plan_id"]),
                          ({**DINNER, "veg_count": 0}, out["plans"][0]["plan_id"])]:
        r = add_plan_to_cart(db, priya, request_, pid, source="website")
        assert r["status"] == "plan_changed", request_
    assert view_cart(db, priya)["status"] == "empty"


def test_a_price_change_after_planning_means_plan_changed(db, priya):
    out = plan_meal(db, DINNER, priya)
    plan = out["plans"][1]
    it = plan["restaurants"][0]["items"][0]
    rng = db.execute("select d.price_low, d.price_high from public.menu_items m join public.dishes d using (dish_id) "
                     "where m.item_id = %s", (it["item_id"],)).fetchone()
    new = it["price"] - 1 if it["price"] > rng["price_low"] else it["price"] + 1
    db.execute("update public.menu_items set price = %s where item_id = %s", (new, it["item_id"]))
    r = add_plan_to_cart(db, priya, DINNER, plan["plan_id"], source="website")
    assert r["status"] == "plan_changed" and view_cart(db, priya)["status"] == "empty"


def test_a_cart_total_mismatch_raises_and_leaves_nothing(db, priya, monkeypatch):
    import app.tools.planner as planner_tools
    out = plan_meal(db, DINNER, priya)
    real = planner_tools.cart_tools.view_cart
    calls = {"n": 0}

    def off_by_one(conn, user_id):
        cart = real(conn, user_id)
        calls["n"] += 1
        if calls["n"] > 1 and cart.get("grand_total"):
            cart = {**cart, "grand_total": cart["grand_total"] + 1}
        return cart
    monkeypatch.setattr(planner_tools.cart_tools, "view_cart", off_by_one)
    with pytest.raises(PlanCartMismatch):
        with db.transaction():                                     # the route's get_conn rolls back the same way
            add_plan_to_cart(db, priya, DINNER, out["plans"][0]["plan_id"], source="website")
    monkeypatch.undo()
    assert view_cart(db, priya)["status"] == "empty"


def test_plan_cart_then_checkout_needs_the_usual_yes(db, priya):
    from app.tools.orders import confirm_cart, place_order
    out = plan_meal(db, DINNER, priya)
    cart = add_plan_to_cart(db, priya, DINNER, out["plans"][0]["plan_id"], source="website")["cart"]
    assert place_order(db, priya, cart["cart_id"])["status"] == "not_confirmed"
    assert confirm_cart(db, priya, cart["cart_id"], cart["quote_id"], source="website")["status"] == "ok"
    placed = place_order(db, priya, cart["cart_id"])
    assert placed["status"] == "ok" and placed["grand_total"] == out["plans"][0]["grand_total"]


def test_unknown_user_cannot_add_a_plan(db):
    out = plan_meal(db, DINNER)
    r = add_plan_to_cart(db, uuid.uuid4(), DINNER, out["plans"][0]["plan_id"], source="website")
    assert r["status"] == "unknown_user"


def test_a_branch_closed_after_the_cache_loaded_is_never_planned(db):
    before = plan_meal(db, DINNER)                         # warms the reference cache
    used = {r["branch_id"] for p in before["plans"] for r in p["restaurants"]}
    db.execute("update public.branches set open_for_demo = false where branch_id = any(%s)", (list(used),))
    after = plan_meal(db, DINNER)                          # the cache still lists them as open
    assert after["status"] == "ok" and after["planner"]["refused_by_checker"] == 0
    assert not used & {r["branch_id"] for p in after["plans"] for r in p["restaurants"]}


def test_a_plan_the_checker_refuses_is_never_shown(db, monkeypatch):
    """Simulate a builder bug: every built plan gets a chicken dish swapped in for the vegetarians' mains. plan_meal
    must show none of them, must not call the request impossible, and must stop after MAX_REFUSALS checks."""
    import app.planner.plan as plan_module
    from app.planner.build import Plan
    real = plan_module.build_plans

    def buggy(req, pool, budget, **kw):
        plans = real(req, pool, budget, **kw)
        bad = []
        for p in plans:
            b = p.lines[0][0]
            nonveg = next((i for i in b.mains if not i.is_veg), None)
            if nonveg:
                bad.append(Plan([(bb, nonveg if it.is_veg and it in bb.mains else it, q) for bb, it, q in p.lines],
                                "value"))
        return bad
    monkeypatch.setattr(plan_module, "build_plans", buggy)
    request_ = {"budget": 2000, "people": 2, "veg_count": 2, "meal_type": "dinner", "area": "Madhapur"}
    out = plan_meal(db, request_)
    assert out["status"] == "planner_error"                         # honest: our fault, not "impossible"
    assert "plans" not in out and "cheapest_plan" not in out
    assert out["planner"]["refused_by_checker"] == plan_module.MAX_REFUSALS      # it gave up checking, logged


@pytest.mark.parametrize("request_", [
    {"budget": 150, "people": 4, "meal_type": "dinner", "area": "Gachibowli"},
    {"budget": 200, "people": 3, "veg_count": 1, "non_spicy_count": 1, "meal_type": "dinner", "area": "Charminar"},
    {"budget": 100, "people": 2, "veg_count": 2, "meal_type": "lunch", "area": "Kukatpally"},
    {"budget": 300, "people": 6, "non_spicy_count": 6, "meal_type": "meal", "area": "Madhapur"},
    # the rule-breaker's breaks (Session 11): ₹903 was quoted while ₹882 existed; the 3-person price was ₹851, not ₹840
    {"budget": 100, "people": 4, "veg_count": 1, "meal_type": "meal", "area": "Rajendra Nagar"},
    {"budget": 100, "people": 6, "veg_count": 2, "meal_type": "meal", "area": "Rajendra Nagar"},
    {"budget": 900, "people": 8, "veg_count": 1, "non_spicy_count": 7, "meal_type": "lunch", "area": "Gagan Pahad"},
    # one rupee under the 4-person best value (₹324): the answer must be "plan for 3", the next size down
    # (regression: a planted bug that skipped a size went unnoticed until this case)
    {"budget": 323, "people": 4, "meal_type": "dinner", "area": "Gachibowli"},
])
def test_the_quoted_cheapest_price_is_honest(db, request_):
    """'The cheapest valid plan costs ₹X' must be true of the planner itself: at ₹X it plans, at ₹X − 1 it can't.
    And 'or plan for p people (from ₹Y)' must be exactly what planning for p people at this budget shows."""
    out = plan_meal(db, request_)
    assert out["status"] == "over_budget"
    x = out["cheapest_total"]
    at_x = plan_meal(db, {**request_, "budget": x})
    assert at_x["status"] == "ok" and min(p["grand_total"] for p in at_x["plans"]) == x
    assert plan_meal(db, {**request_, "budget": x - 1})["status"] == "over_budget"
    smaller = out["largest_group_within_budget"]
    if smaller:
        group = {k: smaller[k] for k in ("people", "veg_count", "non_spicy_count")}
        shown = plan_meal(db, {**request_, **group, "non_spicy_veg_count": None})
        assert shown["status"] == "ok" and min(p["grand_total"] for p in shown["plans"]) == smaller["cheapest_total"]
        for size in range(smaller["people"] + 1, request_["people"]):    # it really is the LARGEST group that fits
            bigger = {**request_, "people": size, "veg_count": min(request_.get("veg_count", 0), size),
                      "non_spicy_count": min(request_.get("non_spicy_count", 0), size), "non_spicy_veg_count": None}
            assert plan_meal(db, bigger)["status"] == "over_budget", size


def test_best_value_counts_the_bread_a_curry_needs(db):
    """Regression (5g honesty check): Dal ₹170 + Veg Biryani ₹210 looks cheaper than 2 × Veg Biryani ₹420 until
    the dal's rotis are added (₹492 vs ₹471). Best value must be the real cheapest."""
    out = plan_meal(db, {"budget": 600, "people": 2, "veg_count": 1, "meal_type": "dinner", "area": "Budvel"})
    assert out["status"] == "ok"
    assert out["plans"][0]["role"] == "best_value" and out["plans"][0]["grand_total"] == 471


# ─── the ₹500 demo: a stated spice preference holds in every plan (Saif, Session 15, D-036) ────────────────
DEMO = {"budget": 500, "people": 2, "veg_count": 1, "spice_preference": "spicy", "area": "Madhapur"}


def test_the_500_demo_is_spicy_in_every_plan_and_best_value_is_the_cheapest_spicy_one(db):
    out = plan_meal(db, DEMO)
    assert out["status"] == "ok" and len(out["plans"]) == 3
    for p in out["plans"]:
        mains = [it["item_id"] for r in p["restaurants"] for it in r["items"] if it["role"] == "main"]
        rows = db.execute("select d.spice_level, d.is_veg from public.menu_items m join public.dishes d "   # own SQL
                          "using (dish_id) where m.item_id = any(%s)", (mains,)).fetchall()
        assert len(rows) == len(mains) and all(r["spice_level"] >= 2 for r in rows), p["label"]
        assert any(r["is_veg"] for r in rows), p["label"]                       # the vegetarian's main is spicy too
        assert p["grand_total"] <= 500
        assert "spicy (spice 2–3) for everyone, as asked" in p["diet_note"]
    value = next(p for p in out["plans"] if p["role"] == "best_value")
    assert value["grand_total"] == min(p["grand_total"] for p in out["plans"])
    # Without the preference a cheaper, non-spicy plan exists: the preference really binds "best value".
    plain = plan_meal(db, {k: v for k, v in DEMO.items() if k != "spice_preference"})
    plain_value = next(p for p in plain["plans"] if p["role"] == "best_value")
    assert plain_value["grand_total"] <= value["grand_total"]
