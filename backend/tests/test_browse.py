"""Browsing by area (Phase 7c, D-056): GET /areas/{area_id}/restaurants and /areas/{area_id}/home.

Plain tests (public, read-only, no money is charged here), but every number on a card is checked against the
database with independent code: in range means the cart would accept it; the fee is the pricing rule; the
price for one is the real median main price. Nothing on a card may be estimated."""

import math
import statistics

import pytest
from fastapi.testclient import TestClient

from app import pricing
from app.db import get_conn
from app.main import app
from app.tools import browse

client = TestClient(app)
AREA = "madhapur"


@pytest.fixture
def api(db):
    def test_db():
        yield db
    app.dependency_overrides[get_conn] = test_db


def haversine_km(lat1, lon1, lat2, lon2):
    """Independent of app.tools.reference.km."""
    r = 6371.0088
    p1, p2, dp, dl = map(math.radians, (lat1, lat2, lat2 - lat1, lon2 - lon1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@pytest.fixture
def truth(db):
    """From the database, not the reference copy: each restaurant's nearest open branch in range of Madhapur."""
    a = db.execute("select lat, lon from public.areas where area_id = %s", (AREA,)).fetchone()
    best = {}
    for b in db.execute("select branch_id, restaurant_id, lat, lon from public.branches where open_for_demo"):
        d = haversine_km(b["lat"], b["lon"], a["lat"], a["lon"])
        if round(d * 1000) <= 8000 and (b["restaurant_id"] not in best or d < best[b["restaurant_id"]]):
            best[b["restaurant_id"]] = d
    return best


def everything(db, **filters):
    out = browse.restaurants_near(db, AREA, limit=browse.MAX_LIMIT, **filters)
    cards, offset = list(out["restaurants"]), out["offset"]
    while offset + browse.MAX_LIMIT < out["total"]:
        offset += browse.MAX_LIMIT
        cards += browse.restaurants_near(db, AREA, offset=offset, limit=browse.MAX_LIMIT, **filters)["restaurants"]
    return out, cards


# ─── what is listed, and the numbers on each card ────────────────────────────────────────────────────────

def test_exactly_the_restaurants_that_can_deliver_are_listed(db, truth):
    out, cards = everything(db)
    assert out["total"] == len(cards) == len(truth) > 100
    assert {c["restaurant_id"] for c in cards} == set(truth)
    assert all(c["branch"]["distance_km"] <= 8.0 for c in cards)


def test_each_card_shows_its_nearest_branch_and_the_pricing_fee(db, truth):
    _, cards = everything(db)
    for c in cards:
        assert c["branch"]["distance_km"] == pytest.approx(truth[c["restaurant_id"]], abs=0.051)
        assert c["delivery_fee"] == pricing.delivery_fee(0, truth[c["restaurant_id"]])
        assert 25 <= c["delivery_fee"] <= 85


def test_price_for_one_is_the_median_single_serving_main(db):
    """Single-serving mains; a menu without them (a café) falls back to all mains, then to everything available."""
    _, cards = everything(db)
    fallbacks = 0
    for c in cards[:80]:
        rows = db.execute("""select m.price, d.course, d.serves from public.menu_items m join public.dishes d using (dish_id)
                             where m.restaurant_id = %s and m.is_available""", (c["restaurant_id"],)).fetchall()
        single = [r["price"] for r in rows if r["course"] == "main" and r["serves"] == 1]
        mains = [r["price"] for r in rows if r["course"] == "main"]
        prices = single or mains or [r["price"] for r in rows]
        fallbacks += not single
        assert c["price_for_one"] == statistics.median_low(prices)
    assert fallbacks < 80                                   # most restaurants have single-serving mains


def test_mild_mains_are_counted_from_the_menu(db):
    _, cards = everything(db)
    for c in cards[:40]:
        n = db.execute("""select count(*) as n from public.menu_items m join public.dishes d using (dish_id)
                          where m.restaurant_id = %s and m.is_available and d.course = 'main' and d.spice_level <= 1""",
                       (c["restaurant_id"],)).fetchone()["n"]
        assert c["mild_mains"] == n and c["mild_friendly"] == (n >= browse.MILD_FRIENDLY_MIN)


def test_more_branches_in_range_counts_the_others(db):
    _, cards = everything(db)
    dominos = next(c for c in cards if c["name"] == "Domino's")
    a = db.execute("select lat, lon from public.areas where area_id = %s", (AREA,)).fetchone()
    n = sum(1 for b in db.execute("""select lat, lon from public.branches b join public.restaurants r using (restaurant_id)
                                     where r.restaurant_id = %s and b.open_for_demo""", (dominos["restaurant_id"],))
            if round(haversine_km(b["lat"], b["lon"], a["lat"], a["lon"]) * 1000) <= 8000)
    assert dominos["more_branches_in_range"] == n - 1


# ─── filters, sorting, pages ─────────────────────────────────────────────────────────────────────────────

def test_veg_only_lists_only_pure_veg_restaurants(db):
    _, cards = everything(db, veg_only=True)
    assert cards and all(c["veg_only"] for c in cards)
    ids = [c["restaurant_id"] for c in cards]
    veg = {r["restaurant_id"] for r in db.execute("select restaurant_id from public.restaurants where veg_only")}
    assert set(ids) <= veg


def test_cuisine_filter_is_case_insensitive_and_facets_ignore_it(db):
    full = browse.restaurants_near(db, AREA, cuisine="south indian", limit=browse.MAX_LIMIT)
    assert full["filters"]["cuisine"] == "South Indian"
    assert all("South Indian" in c["cuisines"] for c in full["restaurants"])
    plain = browse.restaurants_near(db, AREA)
    assert full["cuisine_facets"] == plain["cuisine_facets"]
    facet = next(f for f in plain["cuisine_facets"] if f["cuisine"] == "South Indian")
    assert facet["restaurants"] == full["total"]


def test_max_km_max_price_and_mild(db):
    _, near = everything(db, max_km=2)
    assert near and all(c["branch"]["distance_km"] <= 2.0 for c in near)
    _, cheap = everything(db, max_price_for_one=200)
    assert cheap and all(c["price_for_one"] <= 200 for c in cheap)
    _, mild = everything(db, mild=True)
    assert mild and all(c["mild_friendly"] for c in mild)


@pytest.mark.parametrize("sort, key", [("distance", lambda c: c["branch"]["distance_km"]),
                                       ("price", lambda c: c["price_for_one"]),
                                       ("name", lambda c: c["name"].lower())])
def test_sorting(db, sort, key):
    _, cards = everything(db, sort=sort)
    values = [key(c) for c in cards]
    assert values == sorted(values)


def test_pages_join_up_without_gaps_or_repeats(db):
    _, cards = everything(db)
    ids = [c["restaurant_id"] for c in cards]
    assert len(ids) == len(set(ids))
    page2 = browse.restaurants_near(db, AREA, offset=24, limit=24)["restaurants"]
    assert [c["restaurant_id"] for c in page2] == ids[24:48]


def test_no_match_is_an_honest_empty(db):
    out = browse.restaurants_near(db, AREA, max_km=0.05, veg_only=True)
    assert out["status"] == "empty" and out["restaurants"] == [] and out["message"]


# ─── areas and bad input ─────────────────────────────────────────────────────────────────────────────────

def test_area_names_resolve_like_the_chat(db):
    assert browse.restaurants_near(db, "Madhapur")["area"]["area_id"] == "madhapur"
    assert browse.restaurants_near(db, "manikonda")["status"] == "outside_coverage"
    assert browse.restaurants_near(db, "qwertyuiop")["status"] == "unknown_area"


@pytest.mark.parametrize("kwargs", [{"cuisine": "martian"}, {"max_km": 9}, {"max_km": 0}, {"sort": "rating"},
                                    {"limit": 0}, {"limit": 49}, {"offset": -1}, {"max_price_for_one": 0}])
def test_bad_filters_are_refused(db, kwargs):
    assert browse.restaurants_near(db, AREA, **kwargs)["status"] == "invalid_input"


# ─── home ────────────────────────────────────────────────────────────────────────────────────────────────

def test_home_chains_have_the_most_branches_in_range_first(db, truth):
    home = browse.area_home(db, AREA)
    assert home["restaurants_in_range"] == len(truth)
    counts = [c["more_branches_in_range"] for c in home["chains"]]
    assert home["chains"] and all(c["is_chain"] for c in home["chains"]) and counts == sorted(counts, reverse=True)
    assert all(c["cuisine"] != "Multi-cuisine" for c in home["cuisines"])
    assert 0 < len(home["cuisines"]) <= browse.HOME_CUISINES


# ─── the routes ──────────────────────────────────────────────────────────────────────────────────────────

def test_routes_are_public_and_validate(api):
    assert client.get(f"/areas/{AREA}/home").status_code == 200
    r = client.get(f"/areas/{AREA}/restaurants", params={"veg_only": "true", "sort": "price", "limit": 5})
    assert r.status_code == 200 and len(r.json()["restaurants"]) <= 5
    assert client.get(f"/areas/{AREA}/restaurants", params={"sort": "rating"}).status_code == 422
    assert client.get(f"/areas/{AREA}/restaurants", params={"max_km": 20}).status_code == 422
    assert client.get("/areas/qwertyuiop/restaurants").json()["status"] == "unknown_area"


# ─── a branch's page header (7d) ─────────────────────────────────────────────────────────────────────────

def test_branch_info_lists_the_other_branches_and_the_osm_position(db):
    b = db.execute("""select b.branch_id, b.restaurant_id, b.lat, b.lon from public.branches b
                      join public.restaurants r using (restaurant_id) where r.name = 'Paradise' and b.open_for_demo
                      order by b.branch_id limit 1""").fetchone()
    info = browse.branch_info(db, b["branch_id"])
    assert info["status"] == "ok" and info["restaurant"]["name"] == "Paradise"
    assert (info["branch"]["lat"], info["branch"]["lon"]) == (b["lat"], b["lon"])
    siblings = {r["branch_id"] for r in db.execute(
        "select branch_id from public.branches where restaurant_id = %s and open_for_demo and branch_id <> %s",
        (b["restaurant_id"], b["branch_id"]))}
    assert {o["branch_id"] for o in info["other_branches"]} == siblings and len(siblings) > 3
    assert "delivery" not in info


def test_branch_delivery_is_judged_like_the_cart(db):
    _, cards = everything(db)
    near = cards[0]["branch"]["branch_id"]
    ok = browse.branch_info(db, near, area=AREA)["delivery"]
    assert ok["status"] == "ok" and ok["delivery_fee"] == cards[0]["delivery_fee"]
    far = db.execute("""select branch_id, lat, lon from public.branches where open_for_demo order by lat desc limit 1""").fetchone()
    a = db.execute("select lat, lon from public.areas where area_id = 'charminar'").fetchone()
    d = browse.branch_info(db, far["branch_id"], area="charminar")["delivery"]
    in_range = round(haversine_km(far["lat"], far["lon"], a["lat"], a["lon"]) * 1000) <= 8000
    assert d["status"] == ("ok" if in_range else "too_far") and (d["delivery_fee"] is None) == (not in_range)


def test_branch_info_unknown_and_area_answers(db, api):
    assert browse.branch_info(db, "b-n0")["status"] == "unknown_branch"
    _, cards = everything(db)
    assert browse.branch_info(db, cards[0]["branch"]["branch_id"], area="manikonda")["delivery"]["status"] == "outside_coverage"
    assert client.get("/branches/b-n0").status_code == 404
    assert client.get(f"/branches/{cards[0]['branch']['branch_id']}", params={"area": AREA}).json()["delivery"]["status"] == "ok"
