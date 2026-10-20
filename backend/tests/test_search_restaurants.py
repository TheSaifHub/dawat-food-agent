"""search_restaurants (D-023) on the real seeded data, read inside a rolled-back transaction.

Checks go back to the database, not to the tool's own output: every returned branch exists and belongs to
its restaurant, and "near the area" is re-computed in SQL."""

import pytest

from app.tools.reference import clear_reference_cache
from app.tools.restaurants import NEAR_KM, search_restaurants


def first(res):
    return res["results"][0]


@pytest.mark.parametrize("q", ["mehfil", "MEHFIL", "  Mehfil ", "hotel mehfil", "mehfil restaurant", "mehfill", "Mehfil's"])
def test_spelling_case_and_generic_words_find_the_same_chain(db, q):
    res = search_restaurants(db, q)
    assert res["status"] == "ok"
    assert first(res)["restaurant_id"] == "r-mehfil" and first(res)["is_chain"]


@pytest.mark.parametrize("q, rid", [("mc donalds", "r-mcdonald-s"), ("McDonald's", "r-mcdonald-s"), ("dominos", "r-domino-s"),
                                    ("paradice", "r-paradise"), ("pista house", "r-pista-house"), ("KFC", "r-kfc")])
def test_known_chains(db, q, rid):
    assert first(search_restaurants(db, q))["restaurant_id"] == rid


@pytest.mark.parametrize("q, name", [("paradise", "Hotel Paradise"), ("niloufer", "Cafe Niloufer"),
                                     ("persis paradise", "Hotel Persis Paradise")])
def test_generic_words_in_names_do_not_block_an_exact_match(db, q, name):
    res = search_restaurants(db, q)
    assert next(r for r in res["results"] if r["name"] == name)["match"] == "exact"


def test_a_chain_without_an_area_needs_a_choice(db):
    res = search_restaurants(db, "paradise")
    assert res["needs_choice"] is True and "selected_branch_id" not in res
    assert res["choices_total"] >= 12
    labels = [(c["restaurant_id"], c["label"]) for c in res["choices"]]
    assert len(labels) == len(set(labels))          # every choice is distinguishable


def test_separate_restaurants_sharing_a_name_are_distinct_choices(db):
    res = search_restaurants(db, "hot chips")
    ids = {r["restaurant_id"] for r in res["results"]}
    assert len(ids) >= 5 and res["needs_choice"] is True
    assert len({c["restaurant_id"] for c in res["choices"]}) == len(res["choices"])
    assert len({c["area"] for c in res["choices"]}) >= 5   # they can be told apart by area


def test_an_area_that_narrows_to_one_branch_selects_it(db):
    res = search_restaurants(db, "paradise", area="Secunderabad")
    assert res["needs_choice"] is False
    b = db.execute("select restaurant_id from public.branches where branch_id = %s", (res["selected_branch_id"],)).fetchone()
    assert b["restaurant_id"] == "r-paradise"


def test_whole_name_typo_outranks_a_word_typo(db):
    res = search_restaurants(db, "paradice", area="secunderabad")
    assert first(res)["restaurant_id"] == "r-paradise" and first(res)["match"] == "fuzzy"
    assert res["needs_choice"] is False              # Hotel Persis Paradise is only a fuzzy_word match


def test_branches_returned_with_an_area_really_are_near_it(db):
    res = search_restaurants(db, "dominos", area="Madhapur")
    ids = [b["branch_id"] for r in res["results"] for b in r["branches"]]
    assert ids
    far = db.execute("""
        select b.branch_id from public.branches b, public.areas a
        where a.area_id = 'madhapur' and b.branch_id = any(%s) and b.area_id <> a.area_id
          and 6371 * 2 * asin(sqrt(power(sin(radians(b.lat - a.lat) / 2), 2)
              + cos(radians(a.lat)) * cos(radians(b.lat)) * power(sin(radians(b.lon - a.lon) / 2), 2))) > %s""",
        (ids, NEAR_KM)).fetchall()
    assert far == []


def test_no_branch_near_the_area_is_said_not_hidden(db):
    res = search_restaurants(db, "mehfil", area="Kondapur")
    assert res["status"] == "none_near_area" and res["results"] == []
    mehfil = next(n for n in res["not_near_area"] if n["restaurant_id"] == "r-mehfil")
    assert mehfil["nearest_branches"] and all(b["distance_km"] > NEAR_KM for b in mehfil["nearest_branches"])


@pytest.mark.parametrize("area, status", [("Manikonda", "outside_coverage"), ("kompally", "unknown_area"),
                                          ("Hyderabad", "needs_area")])
def test_an_unresolvable_area_stops_the_search(db, area, status):
    res = search_restaurants(db, "kfc", area=area)
    assert res["status"] == status and "results" not in res


def test_a_close_typo_in_the_area_is_resolved_and_flagged(db):
    res = search_restaurants(db, "kfc", area="gachibouli")
    assert res["area"]["area_id"] == "gachibowli" and "area_note" in res


def test_a_looser_typo_in_the_area_asks_before_searching(db):
    res = search_restaurants(db, "kfc", area="madhapoor")
    assert res["status"] == "confirm_area" and "results" not in res
    assert res["area_resolution"]["candidate"]["area_id"] == "madhapur"


@pytest.mark.parametrize("q", ["biryani", "chicken biryani", "Chinese food", "pure veg meals"])
def test_food_only_queries_go_to_search_dishes(db, q):
    assert search_restaurants(db, q)["status"] == "dish_query"


def test_food_words_next_to_a_name_are_kept_for_the_menu_step(db):
    res = search_restaurants(db, "paradise biryani")
    assert first(res)["restaurant_id"] == "r-paradise" and res["food_words"] == ["biryani"]


def test_unknown_restaurants_are_not_guessed(db):
    res = search_restaurants(db, "Xyzzy Qwerty Palace")
    assert res["status"] == "no_match" and res["results"] == []


@pytest.mark.parametrize("q", ["", "   ", "x" * 101, None])
def test_invalid_queries(db, q):
    assert search_restaurants(db, q)["status"] == "invalid_input"


@pytest.mark.parametrize("q, area", [("paradise", None), ("hot chips", None), ("dominos", "Madhapur"), ("bawarchi", None)])
def test_every_returned_branch_exists_and_belongs_to_its_restaurant(db, q, area):
    res = search_restaurants(db, q, area)
    pairs = [(r["restaurant_id"], b["branch_id"]) for r in res["results"] for b in r["branches"]]
    pairs += [(c["restaurant_id"], c["branch_id"]) for c in res.get("choices", [])]
    rows = db.execute("select restaurant_id, branch_id from public.branches where open_for_demo and branch_id = any(%s)",
                      ([b for _, b in pairs],)).fetchall()
    assert {(r["restaurant_id"], r["branch_id"]) for r in rows} == set(pairs)


def test_closed_branches_are_never_offered(db):
    shah = search_restaurants(db, "shah ghouse")["selected_branch_id"]
    db.execute("update public.branches set open_for_demo = false where branch_id = %s", (shah,))   # rolled back
    clear_reference_cache()
    try:
        res = search_restaurants(db, "shah ghouse")
        offered = [b["branch_id"] for r in res["results"] for b in r["branches"]]
        assert shah not in offered
    finally:
        clear_reference_cache()                    # the next test must not see the closed branch
