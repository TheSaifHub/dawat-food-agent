"""The demo-persona seeding helper (app/tools/demo.py). The public POST /demo/start route and anonymous sign-ins were
removed in D-064 (Google is the only sign-in); what stays is the library that builds sample orders through the real
tools, which test_order_numbers uses. The route is gone: tests/test_google_auth.py proves that.

Was: per-visitor demo accounts (Phase 7b, D-048).

Strict: who may become a persona (anonymous only, id only from the token), the once-only claim, a vegetarian persona
never gets meat, sample orders go through the real confirmation gate at real prices, and a failure keeps nothing.
Plain: what the seeded account looks like (preferences, address, three backdated, delivered sample orders)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.auth import get_verifier
from app.db import get_conn
from app.main import app
from app.tools import demo
from app.tools.users import ensure_user

client = TestClient(app)


_STATE: dict = {}


class _Resp:
    def __init__(self, body: dict):
        self._body = body
        self.status_code = {"ok": 200, "already_started": 200, "not_anonymous": 403, "persona_locked": 409}.get(body["status"], 422)

    def json(self) -> dict:
        return self._body


@pytest.fixture
def api(db):
    _STATE["db"] = db


def start(uid, persona="priya", *, anonymous=True):
    ensure_user(_STATE["db"], uid)                            # the profile the website creates on the first request
    return _Resp(demo.start_demo(_STATE["db"], uid, persona, is_anonymous=anonymous))


def one(db, sql, *args):
    return db.execute(sql, args).fetchone()


def sample_orders(db, user_id):
    return db.execute("""select o.order_id, o.status, o.is_sample, o.created_at, o.items_total, o.delivery_fee, o.taxes,
                                o.grand_total, c.status as cart_status, c.confirmed_total
                         from public.orders o join public.carts c using (cart_id)
                         where o.user_id = %s order by o.created_at""", (user_id,)).fetchall()


# ─── who may become a persona (strict) ───────────────────────────────────────────────────────────────────




def test_an_email_account_is_never_turned_into_a_persona(api, db, demo_users):
    priya_seed = demo_users[-1]
    before = db.execute("select key, value, source from public.user_preferences where user_id = %s order by key",
                        (priya_seed,)).fetchall()
    r = start(demo_users[0], "arjun", anonymous=False)
    assert r.status_code == 403 and r.json()["status"] == "not_anonymous"
    assert one(db, "select demo_persona from public.users where user_id = %s", demo_users[0])["demo_persona"] is None
    assert db.execute("select key, value, source from public.user_preferences where user_id = %s order by key",
                      (priya_seed,)).fetchall() == before








# ─── once per account (strict) ───────────────────────────────────────────────────────────────────────────

def test_the_same_persona_twice_seeds_once(api, db, anon_user):
    token = anon_user
    assert start(token).json()["status"] == "ok"
    n = len(sample_orders(db, anon_user))
    r = start(token)
    assert r.status_code == 200 and r.json()["status"] == "already_started"
    assert len(sample_orders(db, anon_user)) == n


def test_switching_persona_is_refused_and_changes_nothing(api, db, anon_user):
    token = anon_user
    start(token, "priya")
    prefs = db.execute("select key, value from public.user_preferences where user_id = %s order by key",
                       (anon_user,)).fetchall()
    r = start(token, "arjun")
    assert r.status_code == 409 and r.json()["status"] == "persona_locked"
    assert db.execute("select key, value from public.user_preferences where user_id = %s order by key",
                      (anon_user,)).fetchall() == prefs
    assert one(db, "select display_name from public.users where user_id = %s", anon_user)["display_name"] == "Priya (demo)"





# ─── the seeded account (strict on diet and the gate; plain on shape) ───────────────────────────────────

def test_priya_gets_her_preferences_address_and_three_vegetarian_sample_orders(api, db, anon_user):
    r = start(anon_user, "priya")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["display_name"] == "Priya (demo)" and body["sample_orders"] == 3
    prefs = {row["key"]: (row["value"], row["source"]) for row in
             db.execute("select key, value, source from public.user_preferences where user_id = %s", (anon_user,))}
    assert prefs == {k: (v, "seed") for k, v in demo.PERSONAS["priya"]["prefs"].items()}
    addr = one(db, "select area_id, is_default, line1 from public.addresses where user_id = %s", anon_user)
    assert addr["area_id"] == "madhapur" and addr["is_default"] and "fictional" in addr["line1"]
    items = db.execute("""select oi.is_veg, d.is_veg as menu_veg, d.spice_level from public.order_items oi
                          join public.orders o using (order_id) join public.menu_items m using (item_id)
                          join public.dishes d using (dish_id)
                          where o.user_id = %s""", (anon_user,)).fetchall()
    assert len(items) >= 3
    assert all(i["is_veg"] and i["menu_veg"] and i["spice_level"] <= 1 for i in items)


def test_sample_orders_went_through_the_gate_at_menu_prices(api, db, anon_user):
    start(anon_user, "arjun")
    orders = sample_orders(db, anon_user)
    assert len(orders) == 3
    for o in orders:
        assert o["cart_status"] == "ordered" and o["confirmed_total"] == o["grand_total"]
        assert o["grand_total"] == o["items_total"] + o["delivery_fee"] + o["taxes"]
    wrong = db.execute("""select count(*) as n from public.order_items oi join public.orders o using (order_id)
                          join public.menu_items m using (item_id)
                          where o.user_id = %s and oi.unit_price <> m.price""", (anon_user,)).fetchone()["n"]
    assert wrong == 0


def test_sample_orders_are_backdated_delivered_and_flagged(api, db, anon_user):
    start(anon_user, "arjun")
    orders = sample_orders(db, anon_user)
    now = one(db, "select now() as t")["t"]
    assert all(o["status"] == "delivered" and o["is_sample"] for o in orders)
    ages = sorted(round((now - o["created_at"]).total_seconds() / 86400) for o in orders)
    assert ages[0] >= 1 and ages[-1] <= 14 and len(set(ages)) == 3
    for o in orders:
        timeline = [r["status"] for r in db.execute(
            "select status from public.order_status_events where order_id = %s order by created_at", (o["order_id"],))]
        assert timeline == ["placed", "confirmed", "preparing", "picked_up", "on_the_way", "delivered"]
    assert one(db, "select count(*) as n from public.carts where user_id = %s and status = 'open'", anon_user)["n"] == 0





def test_a_real_order_is_never_marked_sample(db, demo_users):
    assert one(db, "select count(*) as n from public.orders where is_sample and user_id = any(%s)",
               list(demo_users))["n"] == 0
    assert one(db, "select column_default from information_schema.columns where table_name = 'orders' "
                   "and column_name = 'is_sample'")["column_default"] == "false"


def test_a_dish_that_cannot_be_found_is_skipped_not_invented(api, db, anon_user, monkeypatch):
    persona = {**demo.PERSONAS["priya"], "orders": [(13, "zzz no such dish", 1, []), *demo.PERSONAS["priya"]["orders"][1:]]}
    monkeypatch.setitem(demo.PERSONAS, "priya", persona)
    r = start(anon_user, "priya")
    assert r.json()["sample_orders"] == 2 and len(sample_orders(db, anon_user)) == 2
    assert one(db, "select count(*) as n from public.carts where user_id = %s and status = 'open'", anon_user)["n"] == 0


def test_two_visitors_get_separate_accounts(api, db):
    a, b = uuid.uuid4(), uuid.uuid4()
    for uid in (a, b):
        db.execute("insert into auth.users (id, is_anonymous) values (%s, true)", (uid,))
    start(a, "priya")
    start(b, "priya")
    assert len(sample_orders(db, a)) == 3 and len(sample_orders(db, b)) == 3
    assert one(db, "select count(distinct cart_id) as n from public.orders where user_id = any(%s)", [a, b])["n"] == 6


def test_a_vegetarian_persona_skips_meat_even_when_it_is_asked_for(api, db, anon_user, monkeypatch):
    """Both guards: the search filter (a meat first dish finds nothing) and the per-item check on same-branch extras."""
    persona = {**demo.PERSONAS["priya"],
               "orders": [(13, "chicken biryani", 1, []),
                          (7, "paneer butter masala", 1, [("Chicken Tikka", 1), ("Chicken Dum Biryani", 1), ("Mutton Seekh Kebab", 1),
                                                          ("Butter Naan", 1)])]}
    monkeypatch.setitem(demo.PERSONAS, "priya", persona)
    r = start(anon_user, "priya")
    assert r.json()["sample_orders"] == 1
    names = [row["dish_name"] for row in db.execute(
        "select oi.dish_name, oi.is_veg from public.order_items oi join public.orders o using (order_id) "
        "where o.user_id = %s and oi.is_veg", (anon_user,))]
    meat = db.execute("select count(*) as n from public.order_items oi join public.orders o using (order_id) "
                      "where o.user_id = %s and not oi.is_veg", (anon_user,)).fetchone()["n"]
    assert meat == 0 and "Paneer Butter Masala" in names


def test_fits_checks_diet_and_spice():
    priya, arjun = demo.PERSONAS["priya"], demo.PERSONAS["arjun"]
    assert not demo._fits({"is_veg": False, "spice_level": 0}, priya)
    assert not demo._fits({"is_veg": True, "spice_level": 2}, priya)
    assert demo._fits({"is_veg": True, "spice_level": 1}, priya)
    assert demo._fits({"is_veg": False, "spice_level": 3}, arjun)


def test_an_order_that_fails_after_adding_leaves_nothing_for_the_next(api, db, anon_user, monkeypatch):
    """The first sample's items are in the cart when its confirm fails: they must be rolled back, not carried into the
    second sample order."""
    real, calls = demo.confirm_cart, []

    def first_fails(*a, **k):
        calls.append(1)
        return {"status": "cannot_confirm"} if len(calls) == 1 else real(*a, **k)
    monkeypatch.setattr(demo, "confirm_cart", first_fails)
    r = start(anon_user, "priya")
    assert r.json()["sample_orders"] == 2
    names = {row["dish_name"] for row in db.execute(
        "select oi.dish_name from public.order_items oi join public.orders o using (order_id) where o.user_id = %s",
        (anon_user,))}
    assert "Masala Dosa" not in names and "Filter Coffee" not in names
    assert db.execute("select count(*) as n from public.cart_items ci join public.carts c using (cart_id) "
                      "where c.user_id = %s and c.status = 'open'", (anon_user,)).fetchone()["n"] == 0
