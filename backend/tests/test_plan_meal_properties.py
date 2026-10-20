"""5g · Property-based test of the meal planner on the REAL data (D-029): random budgets, groups, meal types and
areas, and no plan the planner returns may ever break a hard rule, judged by the independent oracle in
test_plan_meal.py (its own SQL, its own fee/GST maths, brute-force matching of people to portions).

Fixed seed (derandomize) so a failure reproduces; the database work is always rolled back.
The synthetic-menu property test (thousands of random menus, no database) is in test_planner_rules.py.
"""

import pytest
from hypothesis import HealthCheck, event, given, settings, strategies as st

from app.tools.planner import plan_meal
from tests.test_plan_meal import oracle, point_of

pytestmark = pytest.mark.db

AREAS = ["Madhapur", "Charminar", "Gachibowli", "Secunderabad", "Kukatpally", "Tolichowki", "Amberpet", "Attapur",
         "Banjara Hills", "Begumpet", "Malakpet", "Uppal", "Alwal", "Budvel", "Mehdipatnam", "Ameerpet"]


@st.composite
def meal_request(draw):
    people = draw(st.integers(1, 10))
    veg = draw(st.integers(0, people))
    ns = draw(st.integers(0, people))
    req = {"budget": draw(st.one_of(st.integers(50, 600), st.integers(600, 6000))), "people": people,
           "veg_count": veg, "non_spicy_count": ns,
           "spice_preference": draw(st.sampled_from([None, "mild", "medium", "spicy"])),
           "meal_type": draw(st.sampled_from(["dinner", "lunch", "meal", "snack", "breakfast"])),
           "area": draw(st.sampled_from(AREAS))}
    if draw(st.booleans()) and min(veg, ns) >= max(0, veg + ns - people):
        req["non_spicy_veg_count"] = draw(st.integers(max(0, veg + ns - people), min(veg, ns)))
    return req


@pytest.fixture(scope="module")
def module_db(db_conn):
    with db_conn.transaction(force_rollback=True):
        yield db_conn


@given(meal_request())
@settings(max_examples=120, deadline=None, derandomize=True,
          suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow])
def test_no_returned_plan_ever_breaks_a_hard_rule(module_db, request_):
    out = plan_meal(module_db, request_)
    event(f"status: {out['status']}")
    centre = module_db.execute("select a.lat, a.lon from public.areas a where a.name = %s", (request_["area"],)).fetchone()
    assert (out["delivery"]["lat"], out["delivery"]["lon"]) == (centre["lat"], centre["lon"])   # anonymous: area centre
    assert out["status"] in ("ok", "over_budget", "no_valid_plan"), out
    if out["status"] == "ok":
        event(f"plans: {len(out['plans'])}, radius {out['radius_km']}")
        assert out["planner"]["refused_by_checker"] == 0
        for p in out["plans"]:
            oracle(module_db, request_, p, point_of(out), out["radius_km"])
        x = out["plans"][0]["grand_total"]                                     # best value: the cheapest shown
        assert out["plans"][0]["role"] == "best_value" and all(p["grand_total"] >= x for p in out["plans"])
        if x > 1:              # one rupee less: no cheaper plan turns up, and the quote is never below best value
            below = plan_meal(module_db, {**request_, "budget": x - 1})
            assert below["status"] == "over_budget" and below["cheapest_total"] >= x
            event(f"quote at X-1 equals X: {below['cheapest_total'] == x}")
    elif out["status"] == "over_budget":
        total = oracle(module_db, request_, out["cheapest_plan"], point_of(out), 5.0, budget=10 ** 9)
        assert total == out["cheapest_total"] > request_["budget"]
        at_x = plan_meal(module_db, {**request_, "budget": total})            # the quoted price is honest
        assert at_x["status"] == "ok" and min(p["grand_total"] for p in at_x["plans"]) == total
        assert plan_meal(module_db, {**request_, "budget": total - 1})["status"] == "over_budget"
        smaller = out["largest_group_within_budget"]
        assert smaller is None or (smaller["people"] < request_["people"] and smaller["cheapest_total"] <= request_["budget"])
        if smaller:
            group = {k: smaller[k] for k in ("people", "veg_count", "non_spicy_count")}
            shown = plan_meal(module_db, {**request_, **group, "non_spicy_veg_count": None})
            assert min(p["grand_total"] for p in shown["plans"]) == smaller["cheapest_total"]
    else:
        assert out["reasons"] and "plans" not in out and "cheapest_plan" not in out
