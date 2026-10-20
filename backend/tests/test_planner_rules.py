"""5c/5d · The checker, the builder and the scenario picker on synthetic menus (pure, no database).

- Every checker rule is broken on purpose once and must be caught; the boundary cases must pass.
- The builder's greedy diet count and the checker's Hall condition are two different algorithms for the same
  question: Hypothesis checks they always agree.
- The builder's property: on random menus and random groups, every plan it builds passes every non-budget rule
  of the independent checker, and select() only ever picks checked, mutually different plans.
"""

from dataclasses import replace
from itertools import count

import pytest
from hypothesis import HealthCheck, event, given, settings, strategies as st

from app.planner.build import build_plans, feeds_everyone, portion_mixes
from app.planner.candidates import Branch, Item, is_base, is_main, is_side
from app.planner.request import MealRequest
from app.planner.rules import LineFacts, check_plan, everyone_fed
from app.planner.score import different, price, score, select

_ids = count()


def item(category="curry", course="main", is_veg=True, spice=1, serves=1, price=200, name=None) -> Item:
    n = next(_ids)
    return Item(f"r-x__d{n}", f"d{n}", name or f"Dish {n}", price, is_veg, spice, serves, category, course)


def branch(items, bid="b-n1", rid="r-1", km=1.0, meal_type="dinner") -> Branch:
    return Branch(bid, rid, f"Restaurant {rid}", "Area", "Area", km, False,
                  mains=[i for i in items if is_main(i, meal_type)], bases=[i for i in items if is_base(i)],
                  sides=[i for i in items if is_side(i)])


def facts(lines, **override) -> list[LineFacts]:
    """LineFacts for [(Branch, Item, qty)], all valid unless overridden."""
    return [LineFacts(it.item_id, b.branch_id, q, it.price, it.is_veg, it.spice_level, it.serves, it.category,
                      it.course, True, True, True, b.restaurant_id, b.distance_km) for b, it, q in lines] \
        if not override else [replace(f, **override) for f in facts(lines)]


def req(**kw) -> MealRequest:
    return MealRequest(**{"budget": 10_000, "people": 2, "meal_type": "dinner", "area": "Madhapur", **kw})


def rules_broken(r, lines, radius=3.0) -> set[str]:
    return {v["rule"] for v in check_plan(r, lines, radius)["violations"]}


# ─── the checker, rule by rule ───────────────────────────────────────────────────────────────────────────────
B = branch([])
BIRYANI_V = item("biryani", is_veg=True, spice=2, price=200)
BIRYANI_N = item("biryani", is_veg=False, spice=2, price=250)
DAL = item("curry", is_veg=True, spice=1, price=150)
CHICKEN_CURRY = item("curry", is_veg=False, spice=2, price=250)
ROTI = item("bread", course="side", spice=0, price=30)
RAITA = item("curry", course="side", spice=0, price=60)
LASSI = item("drink", course="drink", spice=0, price=80)
FULL = item("biryani", is_veg=False, spice=2, serves=2, price=450)


def test_valid_plan_passes():
    r = req(people=2, veg_count=1)
    result = check_plan(r, facts([(B, BIRYANI_V, 1), (B, BIRYANI_N, 1)]), 3.0)
    assert result["ok"], result["violations"]
    # items 450 < 499: ₹25 fee; GST 5% of 450 = 22.5 → 23, 18% of 25 = 4.5 → 5
    assert result["bill"]["grand_total"] == 450 + 25 + 23 + 5 == 503


def test_budget_boundary():
    lines = facts([(B, BIRYANI_V, 1), (B, BIRYANI_N, 1)])
    assert "budget" not in rules_broken(req(veg_count=1, budget=503), lines)
    assert "budget" in rules_broken(req(veg_count=1, budget=502), lines)


def test_not_enough_food():
    assert "food" in rules_broken(req(people=3), facts([(B, BIRYANI_N, 2)]))
    assert rules_broken(req(people=3), facts([(B, FULL, 1), (B, BIRYANI_N, 1)])) == set()   # serves 2 + 1


def test_vegetarian_needs_veg_main():
    assert "diet" in rules_broken(req(people=2, veg_count=1), facts([(B, BIRYANI_N, 2)]))


def test_non_spicy_needs_mild_main():
    assert "diet" in rules_broken(req(people=2, non_spicy_count=1), facts([(B, BIRYANI_N, 1), (B, BIRYANI_V, 1)]))


def test_unknown_overlap_checked_for_every_case():
    """D-028 #1 example: 2 veg + 1 non-spicy in 4, with 1 mild veg, 1 spicy veg, 2 spicy non-veg portions.
    Fine if the non-spicy person is vegetarian, but if not, one vegetarian goes without."""
    mild_veg = item("rice", is_veg=True, spice=1, price=150)
    lines = facts([(B, mild_veg, 1), (B, BIRYANI_V, 1), (B, BIRYANI_N, 2)])
    assert "diet" in rules_broken(req(people=4, veg_count=2, non_spicy_count=1), lines)
    assert rules_broken(req(people=4, veg_count=2, non_spicy_count=1, non_spicy_veg_count=1), lines) == set()
    assert "diet" in rules_broken(req(people=4, veg_count=2, non_spicy_count=1, non_spicy_veg_count=0), lines)


def test_whole_veg_group_gets_no_non_veg_at_all():
    chicken_side = item("starter", course="side", is_veg=False, spice=1, price=200)
    assert "group" in rules_broken(req(people=2, veg_count=2), facts([(B, BIRYANI_V, 2), (B, chicken_side, 1)]))
    assert rules_broken(req(people=2, veg_count=1), facts([(B, BIRYANI_V, 1), (B, BIRYANI_N, 1),
                                                           (B, chicken_side, 1)])) == set()


def test_whole_non_spicy_group_gets_nothing_spicy():
    hot_side = item("curry", course="side", spice=2, price=50)
    lines = facts([(B, DAL, 2), (B, ROTI, 4), (B, hot_side, 1)])
    assert "group" in rules_broken(req(people=2, non_spicy_count=2), lines)


def test_meal_needs_side_and_curry_needs_base():
    assert "meal" in rules_broken(req(people=1), facts([(B, DAL, 1)]))                     # curry, nothing else
    assert "meal" in rules_broken(req(people=1), facts([(B, DAL, 1), (B, RAITA, 1)]))      # a side, but no bread/rice
    assert rules_broken(req(people=1), facts([(B, DAL, 1), (B, ROTI, 2)])) == set()
    assert rules_broken(req(people=1), facts([(B, BIRYANI_V, 1)])) == set()                 # biryani = main + rice
    pizza = item("pizza", price=300)
    assert "meal" in rules_broken(req(people=1), facts([(B, pizza, 1)]))
    assert rules_broken(req(people=1, meal_type="snack"), facts([(B, pizza, 1)])) == set()


@pytest.mark.parametrize("category", ["burger", "sandwich", "roll", "shawarma", "snack", "bread", "bakery",
                                      "breakfast"])
@pytest.mark.parametrize("meal_type", ["lunch", "dinner", "meal"])
def test_a_full_meal_needs_a_proper_meal_main(category, meal_type):
    """Saif, Session 12: burgers, sandwiches, rolls, shawarma, snack, bakery and bread mains are not a lunch or
    dinner, even with a side. They don't count as portions either, so the food rule breaks too."""
    light = item(category, is_veg=True, spice=1, price=150)
    fries = item("snack", course="side", spice=0, price=80, name="French Fries")
    broken = rules_broken(req(people=1, meal_type=meal_type), facts([(B, light, 1), (B, fries, 1)]))
    assert {"meal", "food"} <= broken
    assert rules_broken(req(people=1, meal_type="snack"), facts([(B, light, 1)])) == set()


@pytest.mark.parametrize("category", ["biryani", "mandi", "meals", "rice", "noodles", "kebab", "pizza", "pasta",
                                      "fried_chicken", "continental", "mexican", "tiffin"])
def test_every_proper_meal_main_is_accepted(category):
    main = item(category, is_veg=True, spice=1, price=150)
    side = item("salad", course="side", spice=0, price=80)
    assert rules_broken(req(people=1), facts([(B, main, 1), (B, side, 1)])) == set()


def test_a_curry_needs_bread_from_its_own_restaurant():
    b1, b2 = branch([], "b-n1", "r-1"), branch([], "b-n2", "r-2")
    r = req(people=2, veg_count=1)
    lines = facts([(b1, DAL, 1), (b2, BIRYANI_N, 1), (b2, ROTI, 2)])
    assert "meal" in rules_broken(r, lines)
    assert rules_broken(r, facts([(b1, DAL, 1), (b1, ROTI, 2), (b2, BIRYANI_N, 1)])) == set()


def test_padding_refused():
    assert "padding" in rules_broken(req(people=2), facts([(B, BIRYANI_N, 3)]))
    assert "padding" in rules_broken(req(people=2), facts([(B, FULL, 1), (B, BIRYANI_N, 1)]))
    assert rules_broken(req(people=3), facts([(B, FULL, 2)])) == set()                    # 4 portions, but 2 is too few


def test_desserts_and_drinks_never_added():
    assert "extras" in rules_broken(req(people=1), facts([(B, BIRYANI_N, 1), (B, LASSI, 1)]))


@pytest.mark.parametrize("override", [
    {"available": False}, {"on_menu": False}, {"branch_open": False}, {"distance_km": 3.0006}, {"qty": 0},
    {"qty": 21}, {"qty": True},
])
def test_places_and_quantities(override):
    lines = facts([(B, BIRYANI_N, 1)], **override)
    assert "places" in rules_broken(req(people=1), lines)


def test_radius_boundary_and_restaurant_limit():
    assert rules_broken(req(people=1), facts([(B, BIRYANI_N, 1)], distance_km=3.0004)) == set()
    three = [(branch([], f"b-n{i}", f"r-{i}"), item("biryani", is_veg=False, spice=2), 1) for i in range(3)]
    assert "places" in rules_broken(req(people=3), facts(three))
    same_restaurant = [(branch([], "b-n1", "r-1"), BIRYANI_N, 1), (branch([], "b-n2", "r-1"), BIRYANI_V, 1)]
    assert "places" in rules_broken(req(people=2), facts(same_restaurant))
    assert "places" in rules_broken(req(people=2), facts([(B, BIRYANI_N, 1), (B, BIRYANI_N, 1)]))


# ─── two algorithms, one answer ──────────────────────────────────────────────────────────────────────────────
@st.composite
def group(draw, max_people=8):
    people = draw(st.integers(1, max_people))
    veg = draw(st.integers(0, people))
    ns = draw(st.integers(0, people))
    known = draw(st.booleans())
    k = None
    if known:
        k = draw(st.integers(max(0, veg + ns - people), min(veg, ns)))
    meal = draw(st.sampled_from(["dinner", "lunch", "meal", "snack", "breakfast"]))
    pref = draw(st.sampled_from([None, "mild", "medium", "spicy"]))
    return MealRequest(budget=draw(st.integers(100, 5000)), people=people, veg_count=veg, non_spicy_count=ns,
                       non_spicy_veg_count=k, spice_preference=pref, meal_type=meal, area="Madhapur")


@given(group(), st.lists(st.integers(0, 6), min_size=4, max_size=4))
@settings(max_examples=3000, deadline=None)
def test_greedy_and_hall_agree(r, counts):
    mix = dict(zip(("veg_mild", "veg_spicy", "nonveg_mild", "nonveg_spicy"), counts))
    hall = sum(counts) >= r.people and everyone_fed(r, mix)
    assert feeds_everyone(r, mix) == hall


def test_portion_mixes_all_feed_everyone():
    r = req(people=4, veg_count=2, non_spicy_count=1)
    mixes = portion_mixes(r)
    assert mixes and all(sum(m.values()) == 4 and everyone_fed(r, m) for m in mixes)
    assert {"veg_mild": 1, "veg_spicy": 1, "nonveg_mild": 0, "nonveg_spicy": 2} not in mixes   # the D-028 #1 trap


# ─── the builder's property on random menus ──────────────────────────────────────────────────────────────────
CATEGORY_COURSES = [("biryani", "main"), ("curry", "main"), ("rice", "main"), ("noodles", "main"), ("pizza", "main"),
                    ("burger", "main"), ("tiffin", "main"), ("breakfast", "main"), ("mandi", "main"),
                    ("sandwich", "main"), ("roll", "main"), ("shawarma", "main"), ("snack", "main"), ("bread", "main"),
                    ("kebab", "main"), ("fried_chicken", "main"), ("pasta", "main"), ("mexican", "main"),
                    ("bread", "side"), ("rice", "side"), ("curry", "side"), ("starter", "side"), ("snack", "side"),
                    ("salad", "side"), ("bread", "side"), ("dessert", "dessert"), ("drink", "drink")]


@st.composite
def menu_item(draw):
    category, course = draw(st.sampled_from(CATEGORY_COURSES))
    name = draw(st.sampled_from(["Garlic Bread", "Plain Dish", "Sambar"])) if course == "side" else None
    return item(category, course, is_veg=draw(st.booleans()), spice=draw(st.integers(0, 3)),
                serves=draw(st.sampled_from([1, 1, 1, 2])) if course == "main" else 1,
                price=draw(st.integers(20, 600)), name=name)


@st.composite
def pool(draw, meal_type):
    n = draw(st.integers(1, 4))
    return [branch(draw(st.lists(menu_item(), min_size=1, max_size=14)), f"b-n{i}", f"r-{i}",
                   km=draw(st.floats(0, 3.0)), meal_type=meal_type) for i in range(n)]


def facts_of(plan) -> list[LineFacts]:
    return facts(plan.lines)


@given(st.data())
@settings(max_examples=1000, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
def test_every_built_plan_passes_the_checker(data):
    r = data.draw(group(max_people=6))
    branches = [b for b in data.draw(pool(r.meal_type)) if b.mains]
    unlimited = r.model_copy(update={"budget": 10 ** 9})
    plans = build_plans(r, branches, budget=None)
    for p in plans:
        result = check_plan(unlimited, facts_of(p), 3.0)
        assert result["ok"], (r, [(b.branch_id, i, q) for b, i, q in p.lines], result["violations"])

    within = [score(r, p, price(p)) for p in plans if price(p)["grand_total"] <= r.budget]
    picked, refused = select(within, lambda s: check_plan(r, facts_of(s.plan), 3.0)["ok"])
    event(f"plans built: {'0' if not plans else '1-9' if len(plans) < 10 else '10+'}; picked: {len(picked)}")
    assert refused == 0
    for _, s in picked:
        assert s.total <= r.budget and check_plan(r, facts_of(s.plan), 3.0)["ok"]
    for i, (_, a) in enumerate(picked):
        for _, b in picked[i + 1:]:
            assert different(a, b)
    roles = [role for role, _ in picked]
    assert roles == ["best_value", "best_match", "variety"][:len(roles)]
    if picked:                                        # best value = the cheapest of all, one restaurant or two
        assert picked[0][1].total == min(s.total for s in within)


# ─── scoring and picking ─────────────────────────────────────────────────────────────────────────────────────
def test_different_means_other_restaurant_or_half_the_items():
    from app.planner.build import Plan
    b1, b2 = branch([], "b-n1", "r-1"), branch([], "b-n2", "r-2")
    a, b_, c, d = (item("biryani", is_veg=False) for _ in range(4))
    r = req(people=2)

    def s(lines):
        p = Plan(lines, "value")
        return score(r, p, price(p))
    base = s([(b1, a, 1), (b1, b_, 1)])
    assert different(base, s([(b2, a, 1), (b2, b_, 1)]))                      # other restaurant
    assert different(base, s([(b1, a, 1), (b1, c, 1)]))                       # half the items differ (1 of 2)
    assert not different(base, s([(b1, a, 2), (b1, b_, 1)]))                  # same items, other quantity
    assert not different(s([(b1, a, 1), (b1, b_, 1), (b1, c, 1)]), s([(b1, a, 1), (b1, b_, 1), (b1, d, 1)]))


def test_select_keeps_the_given_best_value_and_picks_the_rest_around_it():
    from app.planner.build import Plan
    b1, b2 = branch([], "b-n1", "r-1"), branch([], "b-n2", "r-2")
    cheap, dear = item("biryani", is_veg=False, price=150), item("biryani", is_veg=False, price=400)
    r = req(people=1, budget=1000)

    def s(lines):
        p = Plan(lines, "value")
        return score(r, p, price(p))
    value = s([(b2, cheap, 1)])
    others = [s([(b1, cheap, 1)]), s([(b1, dear, 1)]), value]
    picked, refused = select(others, lambda x: True, value=value)
    assert refused == 0 and picked[0] == ("best_value", value)
    assert all(different(value, p) for _, p in picked[1:])
    assert value not in [p for _, p in picked[1:]]


def test_budget_part_prefers_75_to_100_percent():
    from app.planner.build import Plan
    p = Plan([(B, BIRYANI_N, 1)], "value")
    bill = price(p)
    total = bill["grand_total"]
    assert score(req(people=1, budget=total), p, bill).parts["budget"] == 1.0
    assert score(req(people=1, budget=int(total / 0.75)), p, bill).parts["budget"] == 1.0
    assert score(req(people=1, budget=total * 2), p, bill).parts["budget"] == pytest.approx(0.5 / 0.75, abs=0.01)


def test_a_build_cache_is_never_shared_between_groups():
    """Regression (planted bug, Session 12): one cache for a mixed group and an all-veg group would price the
    all-veg group's sides as if a chicken side were allowed. The cache records its group and refuses another."""
    b = branch([DAL, ROTI, BIRYANI_N])
    cache: dict = {}
    build_plans(req(people=2, veg_count=1), [b], budget=None, cache=cache)
    build_plans(req(people=2, veg_count=1, budget=50), [b], budget=50, cache=cache)       # same group: fine
    with pytest.raises(ValueError):
        build_plans(req(people=2, veg_count=2), [b], budget=None, cache=cache)


def test_side_cost_is_per_kind_of_main():
    """Regression (planted bug, Session 12): the cached side cost must be per (branch, main category). A curry
    needs 2 rotis (₹60); idli needs half a sambar (₹20); asking about one must not answer for the other."""
    from app.planner.build import accompaniment_cost
    roti = item("bread", course="side", spice=0, price=30)
    sambar = item("curry", course="side", spice=0, price=40, name="Sambar")
    curry, idli = item("curry", price=150), item("tiffin", price=60)
    b = branch([roti, sambar, curry, idli])
    cache: dict = {}
    r = req(people=1)
    assert accompaniment_cost(r, b, curry, cache) == 60
    assert accompaniment_cost(r, b, idli, cache) == 20
    assert accompaniment_cost(r, b, curry, cache) == 60


def test_one_bread_as_curry_base_and_kebab_side_is_one_line():
    """Regression (found by the property test): the same garlic naan is the curry's base AND the kebab's side."""
    naan = item("bread", course="side", spice=0, price=50, name="Garlic Naan")
    curry = item("curry", is_veg=False, spice=2, price=200)
    kebab = item("kebab", is_veg=False, spice=2, price=200)
    b = branch([naan, curry, kebab])
    r = req(people=2)
    plans = build_plans(r, [b], budget=None)
    both = [p for p in plans if {curry.item_id, kebab.item_id} <= {i.item_id for _, i, _ in p.lines}]
    assert both, "expected a variety plan with the curry and the kebab"
    for p in both:
        naans = [q for _, i, q in p.lines if i.item_id == naan.item_id]
        assert naans == [3]                                     # 2 for the curry + 1 for the kebab, one line
        assert check_plan(r.model_copy(update={"budget": 10 ** 9}), facts(p.lines), 3.0)["ok"]


# ─── a stated spice preference is a rule (Saif, Session 15, D-036) ───────────────────────────────────────────
MILD_BIRYANI_V = item("biryani", is_veg=True, spice=1, price=190)
MILD_BIRYANI_N = item("biryani", is_veg=False, spice=1, price=240)
HOT_BIRYANI_N = item("biryani", is_veg=False, spice=3, price=260)


def test_spicy_gives_every_spice_eater_spice_2_or_more():
    r = req(people=2, veg_count=1, spice_preference="spicy")
    assert not rules_broken(r, facts([(B, BIRYANI_V, 1), (B, BIRYANI_N, 1)]))
    assert "diet" in rules_broken(r, facts([(B, MILD_BIRYANI_V, 1), (B, BIRYANI_N, 1)]))   # the vegetarian got spice 1
    assert "diet" in rules_broken(r, facts([(B, BIRYANI_V, 1), (B, MILD_BIRYANI_N, 1)]))
    assert not rules_broken(req(people=2, veg_count=1), facts([(B, MILD_BIRYANI_V, 1), (B, BIRYANI_N, 1)]))


def test_spicy_still_gives_the_non_spicy_people_a_mild_main():
    r = req(people=2, non_spicy_count=1, spice_preference="spicy")
    assert not rules_broken(r, facts([(B, MILD_BIRYANI_N, 1), (B, BIRYANI_N, 1)]))
    assert "diet" in rules_broken(r, facts([(B, MILD_BIRYANI_N, 2)]))                 # the spice eater got mild
    assert "diet" in rules_broken(r, facts([(B, BIRYANI_N, 2)]))                      # the non-spicy one got spicy


def test_medium_is_spice_2_and_nothing_very_spicy():
    r = req(people=2, spice_preference="medium")
    assert not rules_broken(r, facts([(B, BIRYANI_N, 2)]))
    assert "spice" in rules_broken(r, facts([(B, HOT_BIRYANI_N, 1), (B, BIRYANI_N, 1)]))
    assert "diet" in rules_broken(r, facts([(B, MILD_BIRYANI_N, 2)]))
    assert not rules_broken(req(people=2, spice_preference="spicy"), facts([(B, HOT_BIRYANI_N, 1), (B, BIRYANI_N, 1)]))


def test_mild_means_nothing_above_spice_1_for_anyone():
    r = req(people=2, spice_preference="mild")
    assert not rules_broken(r, facts([(B, MILD_BIRYANI_N, 2)]))
    assert {"spice", "diet"} <= rules_broken(r, facts([(B, BIRYANI_N, 2)]))
    hot_side = item("starter", course="side", is_veg=True, spice=2, price=120)
    assert "spice" in rules_broken(r, facts([(B, MILD_BIRYANI_N, 2), (B, hot_side, 1)]))


@pytest.mark.parametrize("pref", ["spicy", "medium", "mild"])
def test_the_builder_only_builds_plans_inside_the_preference(pref):
    menu = [BIRYANI_V, BIRYANI_N, MILD_BIRYANI_V, MILD_BIRYANI_N, HOT_BIRYANI_N, DAL, CHICKEN_CURRY, ROTI, RAITA]
    r = req(people=3, veg_count=1, non_spicy_count=1, spice_preference=pref)
    plans = build_plans(r, [branch(menu)], None)
    assert plans
    for p in plans:
        assert check_plan(r, facts(p.lines), 3.0)["violations"] == [], (pref, p.lines)
