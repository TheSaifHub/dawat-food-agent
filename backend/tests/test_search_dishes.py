"""search_dishes (D-024) on the real seeded data, inside a rolled-back transaction.

Results are checked against the database, never against the tool's own output: every item exists at that
price with those flags, its branch belongs to its restaurant, is open and really is near the area (distance
recomputed in SQL), and a random cross-check compares the full matching set with an independent SQL query."""

import random

import pytest

from app.tools.areas import resolve_area
from app.tools.dish_query import understand
from app.tools.dishes import PER_RESTAURANT, search_dishes
from app.tools.reference import get_reference
from app.tools.restaurants import NEAR_KM

HAVERSINE = """6371 * 2 * asin(sqrt(power(sin(radians(b.lat - a.lat) / 2), 2)
               + cos(radians(a.lat)) * cos(radians(b.lat)) * power(sin(radians(b.lon - a.lon) / 2), 2)))"""


def check_results(db, res):
    """Every returned item, re-read from the database."""
    assert res["status"] == "ok" and res["results"]
    area_id = res["area"]["area_id"]
    f = res["filters"]
    per = {}
    for r in res["results"]:
        row = db.execute(f"""
            select m.price, m.restaurant_id, m.is_available, d.dish_id, d.name, d.is_veg, d.spice_level, d.category,
                   b.restaurant_id as branch_restaurant, b.open_for_demo, b.area_id, {HAVERSINE} as km
            from public.menu_items m join public.dishes d using (dish_id), public.branches b, public.areas a
            where m.item_id = %s and b.branch_id = %s and a.area_id = %s""",
                         (r["item_id"], r["branch"]["branch_id"], area_id)).fetchone()
        assert row, r
        assert (row["price"], row["dish_id"], row["name"], row["is_veg"], row["spice_level"]) == \
               (r["price"], r["dish_id"], r["name"], r["is_veg"], r["spice_level"])
        assert row["is_available"] and row["open_for_demo"]
        assert row["restaurant_id"] == row["branch_restaurant"] == r["restaurant"]["restaurant_id"]
        assert row["area_id"] == area_id or row["km"] <= NEAR_KM
        assert f["is_veg"] is None or row["is_veg"] == f["is_veg"]
        assert f["max_spice"] is None or row["spice_level"] <= f["max_spice"]
        assert f["min_spice"] is None or row["spice_level"] >= f["min_spice"]
        assert f["max_price"] is None or row["price"] <= f["max_price"]
        assert f["category"] is None or row["category"] == f["category"]
        per[row["restaurant_id"]] = per.get(row["restaurant_id"], 0) + 1
    assert max(per.values()) <= PER_RESTAURANT


# ── Saif's nine ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("q, area, top", [
    ("ek mutton biryani", "Madhapur", "Mutton Dum Biryani"), ("rendu kodi biryani", "Kukatpally", "Chicken Dum Biryani"),
    ("బిర్యానీ", "Madhapur", "Chicken Dum Biryani"), ("biriyani", "Gachibowli", "Chicken Dum Biryani"),
    ("chiken 65", "Kondapur", "Chicken 65"), ("paneer under 200", "Madhapur", None),
    ("karam kam", "Madhapur", None), ("karam lekunda", "Ameerpet", None),
    ("something veg not spicy in Madhapur", None, None)])
def test_saif_queries(db, q, area, top):
    res = search_dishes(db, q, area=area)
    check_results(db, res)
    if top:
        assert res["results"][0]["name"] == top


def test_quantity_and_filters_are_reported(db):
    res = search_dishes(db, "rendu kodi biryani", area="Kukatpally")
    assert res["understood"]["quantity"] == 2 and "quantity" in res["message"]
    res = search_dishes(db, "something veg not spicy in Madhapur")
    assert res["filters"]["is_veg"] is True and res["filters"]["max_spice"] == 1 and res["area"]["area_id"] == "madhapur"
    res = search_dishes(db, "paneer under 200", area="Madhapur")
    assert res["filters"]["max_price"] == 200 and all(r["price"] <= 200 for r in res["results"])


# ── vegetarian safety ────────────────────────────────────────────────────
@pytest.mark.parametrize("q, kwargs", [("veg thali", {}), ("vegg biryani", {}), ("veg starters", {}),
                                       ("pure veg biryani", {}), ("shakahari biryani", {}), ("శాకాహారం biryani", {}),
                                       ("biryani", {"is_veg": True}), ("veg biryani", {"is_veg": False}),
                                       ("chicken", {"is_veg": True})])
def test_vegetarian_requests_never_return_non_veg(db, q, kwargs):
    res = search_dishes(db, q, area="Ameerpet", **kwargs)
    assert res["filters"]["is_veg"] is True
    assert all(r["is_veg"] for r in res.get("results", []))
    if res["status"] == "ok":
        check_results(db, res)


def test_conflicting_veg_filters_choose_veg_and_say_so(db):
    res = search_dishes(db, "veg biryani", area="Ameerpet", is_veg=False)
    assert res["filters"]["is_veg"] is True and any("vegetarian only" in n for n in res["understood"]["notes"])


def test_filters_only_get_stricter(db):
    res = search_dishes(db, "chicken karam kam under 300", area="Madhapur", max_spice=3, max_price=500)
    assert res["filters"]["max_spice"] == 1 and res["filters"]["max_price"] == 300
    res = search_dishes(db, "chicken under 300", area="Madhapur", max_price=150)
    assert res["filters"]["max_price"] == 150


def test_spicy_and_not_spicy_together_keep_only_the_safe_limit(db):
    res = search_dishes(db, "spicy chicken", area="Madhapur", max_spice=1)
    assert res["filters"]["max_spice"] == 1 and res["filters"]["min_spice"] is None


# ── the area rule: required, and an unresolved area stops the search ────
def test_no_area_asks_for_one_and_shows_no_prices(db):
    res = search_dishes(db, "biriyani")
    assert res["status"] == "needs_area" and "results" not in res and "price" not in str(res.get("dishes_understood"))
    assert res["dishes_understood"]


@pytest.mark.parametrize("q, area, status", [("biryani in manikonda", None, "outside_coverage"),
                                             ("biryani", "Bowenpally", "outside_coverage"),
                                             ("biryani in xyzabad", None, "unknown_area"),
                                             ("biryani", "madhapoor", "confirm_area"),
                                             ("biryani in hyderabad", None, "needs_area")])
def test_unresolved_areas_stop_the_search(db, q, area, status):
    res = search_dishes(db, q, area=area)
    assert res["status"] == status and not res.get("results")


def test_close_area_typo_resolves_with_a_note(db):
    res = search_dishes(db, "biryani", area="gachibouli")
    assert res["status"] == "ok" and res["area"]["area_id"] == "gachibowli" and "area_note" in res


def test_two_different_areas_are_a_question(db):
    res = search_dishes(db, "biryani in Madhapur", area="Kondapur")
    assert res["status"] == "area_conflict" and not res.get("results")


# ── honest "no" answers ──────────────────────────────────────────────────
def test_borderline_dish_typo_asks(db):
    res = search_dishes(db, "muttun biryani", area="Madhapur")
    assert res["status"] == "confirm_dish" and res["confirm"]["candidate"] == "mutton" and not res.get("results")


def test_unknown_dish_is_said_not_invented(db):
    res = search_dishes(db, "xqzt", area="Madhapur")
    assert res["status"] == "no_dish_match" and not res.get("results")


def test_unknown_word_is_flagged_in_the_answer(db):
    res = search_dishes(db, "pork biryani", area="Madhapur")
    assert res["understood"]["unmatched_words"] == ["pork"] and "pork" in res["message"]
    assert all("pork" not in r["name"].lower() for r in res["results"])


def test_dish_not_served_nearby_points_to_the_nearest_places(db):
    res = search_dishes(db, "sushi", area="Charminar")
    assert res["status"] == "none_near_area" and res["results"] == [] and res["nearest_elsewhere"]
    for p in res["nearest_elsewhere"]:
        assert p["distance_km"] > NEAR_KM
        assert db.execute("""select 1 from public.menu_items m join public.branches b using (restaurant_id)
                             where b.branch_id = %s and m.dish_id in ('veg-sushi', 'salmon-sushi') and m.is_available""",
                          (p["branch_id"],)).fetchone()


def test_filters_that_rule_everything_out_are_explained(db):
    res = search_dishes(db, "chicken 65 karam lekunda", area="Kondapur")
    assert res["status"] == "no_match_with_filters" and res["results"] == []
    assert res["nearby_without_filters"]["mildest_spice"] > 1


def test_category_filter_param(db):
    res = search_dishes(db, "paneer", area="Madhapur", category="starters")
    check_results(db, res)
    assert {r["category"] for r in res["results"]} == {"starter"}


# ── what is offered: available items, open branches, a spread of restaurants ──
def test_unavailable_items_and_closed_branches_are_never_offered(db):
    first = search_dishes(db, "chicken biryani", area="Madhapur")["results"][0]
    db.execute("update public.menu_items set is_available = false where item_id = %s", (first["item_id"],))  # rolled back
    again = search_dishes(db, "chicken biryani", area="Madhapur")
    assert first["item_id"] not in {r["item_id"] for r in again["results"]}
    branch = again["results"][0]["branch"]["branch_id"]
    rid = again["results"][0]["restaurant"]["restaurant_id"]
    db.execute("update public.branches set open_for_demo = false where restaurant_id = %s", (rid,))   # rolled back
    from app.tools.reference import clear_reference_cache
    clear_reference_cache()
    try:
        after = search_dishes(db, "chicken biryani", area="Madhapur")
        assert rid not in {r["restaurant"]["restaurant_id"] for r in after["results"]}
        assert branch not in {r["branch"]["branch_id"] for r in after["results"]}
    finally:
        clear_reference_cache()             # the next test reloads the real (rolled-back) state


def test_limit_and_spread(db):
    res = search_dishes(db, "biryani", area="Madhapur", limit=7)
    assert len(res["results"]) == 7
    assert len({r["restaurant"]["restaurant_id"] for r in res["results"]}) >= 4


@pytest.mark.parametrize("kwargs", [{"query": ""}, {"query": "x" * 201}, {"query": None}, {"query": 5},
                                    {"is_veg": "yes"}, {"is_veg": 1}, {"max_spice": 4}, {"max_spice": True},
                                    {"max_price": 0}, {"max_price": 99.5}, {"category": "sushi"}, {"limit": 0},
                                    {"limit": 21}, {"limit": True}, {"area": 7}])
def test_bad_inputs_are_refused(db, kwargs):
    args = {"query": "biryani", "area": "Madhapur", **kwargs}
    assert search_dishes(db, **args)["status"] == "invalid_input"


# ── random cross-check against independent SQL ──────────────────────────
def test_random_queries_match_independent_sql(db):
    """40 random requests (fixed seed): dish names/aliases, category words and "something", random areas and
    filters. The set of matching items must equal an independent SQL query over the dishes the request was
    understood as (so this checks the search, area and filter logic, separately from the parser tests)."""
    rng = random.Random(2026)
    ref = get_reference(db)
    aliases = [r["alias"] for r in db.execute("select alias from public.dish_aliases where script = 'latin' order by 1")]
    areas = sorted(ref.areas)
    words = ["biryani", "starters", "desserts", "pizza", "something", "chicken", "paneer", "drinks", "dosa"]
    checked = 0
    for _ in range(40):
        q = rng.choice(aliases) if rng.random() < 0.6 else rng.choice(words)
        area = rng.choice(areas)
        f = {"is_veg": rng.choice([None, True, False]), "max_spice": rng.choice([None, 0, 1, 2, 3]),
             "max_price": rng.choice([None, 100, 250, 500])}
        res = search_dishes(db, q, area=area, **f)
        if res["status"] not in ("ok", "no_match_with_filters", "none_near_area"):
            continue
        m = understand(q, ref.dish_index, lambda t: 0)
        dish_ids = list(m.tiers) or [d for d, r in ref.dish_index.dishes.items() if r["course"] == "main"]
        flt = res["filters"]
        expected = {r["item_id"] for r in db.execute(f"""
            select m.item_id from public.menu_items m join public.dishes d using (dish_id)
            where m.is_available and m.dish_id = any(%(d)s)
              and exists (select 1 from public.branches b, public.areas a
                          where a.area_id = %(a)s and b.restaurant_id = m.restaurant_id and b.open_for_demo
                            and (b.area_id = a.area_id or {HAVERSINE} <= %(km)s))
              and (%(v)s::boolean is null or d.is_veg = %(v)s) and (%(s)s::int is null or d.spice_level <= %(s)s)
              and (%(mn)s::int is null or d.spice_level >= %(mn)s) and (%(p)s::int is null or m.price <= %(p)s)""",
            {"d": dish_ids, "a": area, "km": NEAR_KM, "v": flt["is_veg"], "s": flt["max_spice"],
             "mn": flt["min_spice"], "p": flt["max_price"]})}
        if res["status"] == "ok":
            check_results(db, res)
            assert res["totals"]["items"] == len(expected), q
            assert {r["item_id"] for r in res["results"]} <= expected
        else:
            assert expected == set(), q
        checked += 1
    assert checked >= 30
