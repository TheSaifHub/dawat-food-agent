"""get_menu (D-023): filters are exact, bad filters are refused, and every item/price is the database's own."""

import random

import pytest

from app.tools.menu import CATEGORIES, get_menu

PARADISE_SECUNDERABAD = "b-w274798850"


def a_branch_of(db, restaurant_id: str) -> str:
    return db.execute("select branch_id from public.branches where restaurant_id = %s and open_for_demo "
                      "order by branch_id limit 1", (restaurant_id,)).fetchone()["branch_id"]


def test_full_menu_equals_the_database(db):
    m = get_menu(db, PARADISE_SECUNDERABAD)
    rows = db.execute("""select m.item_id, m.price, d.is_veg, d.spice_level from public.menu_items m join public.dishes d
                         using (dish_id) where m.restaurant_id = 'r-paradise' and m.is_available""").fetchall()
    assert {(i["item_id"], i["price"], i["is_veg"], i["spice_level"]) for i in m["items"]} == \
           {(r["item_id"], r["price"], r["is_veg"], r["spice_level"]) for r in rows}
    assert m["items_on_full_menu"] == len(rows)


def test_a_category_request_returns_only_that_category(db):
    m = get_menu(db, PARADISE_SECUNDERABAD, category="biryani")
    assert m["items"] and {i["category"] for i in m["items"]} == {"biryani"}


@pytest.mark.parametrize("spelling", ["Biriyani", "biryanis", "BIRYANI", " briyani "])
def test_category_spellings(db, spelling):
    assert get_menu(db, PARADISE_SECUNDERABAD, category=spelling)["filters"]["category"] == "biryani"


def test_veg_filter_both_ways(db):
    veg = get_menu(db, PARADISE_SECUNDERABAD, is_veg=True)["items"]
    nonveg = get_menu(db, PARADISE_SECUNDERABAD, is_veg=False)["items"]
    assert veg and nonveg and all(i["is_veg"] for i in veg) and not any(i["is_veg"] for i in nonveg)


def test_veg_only_restaurant_has_nothing_non_veg(db):
    m = get_menu(db, a_branch_of(db, "r-minerva-coffee-shop"), is_veg=False)
    assert m["status"] == "ok" and m["items"] == [] and m["restaurant"]["veg_only"] and "message" in m


def test_chain_branches_share_one_menu(db):
    b1, b2 = [r["branch_id"] for r in db.execute(
        "select branch_id from public.branches where restaurant_id = 'r-paradise' order by branch_id limit 2")]
    assert get_menu(db, b1)["items"] == get_menu(db, b2)["items"]


def test_price_and_spice_limits_are_inclusive(db):
    """An item priced exactly at max_price (or at exactly max_spice) is included."""
    full = get_menu(db, PARADISE_SECUNDERABAD)["items"]
    for item in full[:: max(1, len(full) // 6)]:
        ids = {i["item_id"] for i in get_menu(db, PARADISE_SECUNDERABAD, max_price=item["price"],
                                               max_spice=item["spice_level"])["items"]}
        assert item["item_id"] in ids


def test_unavailable_items_are_hidden(db):
    item = get_menu(db, PARADISE_SECUNDERABAD)["items"][0]["item_id"]
    db.execute("update public.menu_items set is_available = false where item_id = %s", (item,))   # rolled back
    m = get_menu(db, PARADISE_SECUNDERABAD)
    assert item not in {i["item_id"] for i in m["items"]}


def test_empty_result_is_explained(db):
    m = get_menu(db, PARADISE_SECUNDERABAD, category="pizza")
    assert m["status"] == "ok" and m["items"] == [] and "categories_on_menu" in m and "message" in m


@pytest.mark.parametrize("kwargs", [
    {"category": "sushi"}, {"category": 5}, {"is_veg": "yes"}, {"is_veg": 1}, {"max_spice": 4}, {"max_spice": -1},
    {"max_spice": "2"}, {"max_spice": 2.5}, {"max_spice": True}, {"max_price": 0}, {"max_price": 250.5},
    {"max_price": "300"}, {"max_price": 10**7},
])
def test_bad_filters_are_refused_not_ignored(db, kwargs):
    assert get_menu(db, PARADISE_SECUNDERABAD, **kwargs)["status"] == "invalid_input"


@pytest.mark.parametrize("branch_id, status", [("b-n1", "unknown_branch"), ("paradise", "invalid_input"),
                                               ("b-n1; drop table x", "invalid_input"), (None, "invalid_input")])
def test_bad_branch_ids(db, branch_id, status):
    assert get_menu(db, branch_id)["status"] == status


def test_random_filters_on_random_branches_never_leak(db):
    """60 random branches (fixed seed) × random filter combinations: every item obeys every filter, and the
    unfiltered menu matches the database count."""
    rng = random.Random(2026)
    branches = [r["branch_id"] for r in db.execute("select branch_id from public.branches where open_for_demo order by 1")]
    counts = {r["restaurant_id"]: r["n"] for r in db.execute(
        "select restaurant_id, count(*) as n from public.menu_items where is_available group by 1")}
    for bid in rng.sample(branches, 60):
        f = {"category": rng.choice([None, *CATEGORIES]), "is_veg": rng.choice([None, True, False]),
             "max_spice": rng.choice([None, 0, 1, 2, 3]), "max_price": rng.choice([None, 60, 150, 300, 600])}
        m = get_menu(db, bid, **f)
        assert m["status"] == "ok"
        assert m["items_on_full_menu"] == counts[m["restaurant"]["restaurant_id"]]
        for i in m["items"]:
            assert f["category"] is None or i["category"] == f["category"]
            assert f["is_veg"] is None or i["is_veg"] == f["is_veg"]
            assert f["max_spice"] is None or i["spice_level"] <= f["max_spice"]
            assert f["max_price"] is None or i["price"] <= f["max_price"]
        # ...and nothing that matches is missing: the same filters, computed independently in SQL
        expected = {r["item_id"] for r in db.execute("""
            select m.item_id from public.menu_items m join public.dishes d using (dish_id)
            where m.restaurant_id = %(r)s and m.is_available
              and (%(c)s::text is null or d.category = %(c)s) and (%(v)s::boolean is null or d.is_veg = %(v)s)
              and (%(s)s::int is null or d.spice_level <= %(s)s) and (%(p)s::int is null or m.price <= %(p)s)""",
            {"r": m["restaurant"]["restaurant_id"], "c": f["category"], "v": f["is_veg"], "s": f["max_spice"],
             "p": f["max_price"]})}
        assert {i["item_id"] for i in m["items"]} == expected
