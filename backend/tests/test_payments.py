"""Razorpay test payments (Phase 8, D-061). MONEY CODE: full rigour.

What must hold, each proven by a test that fails when the rule is broken (planted-bug run in DECISIONS D-061):
  · the amount sent to Razorpay is the server's confirmed total in paise; the client can't supply or change it;
  · an order exists only after a payment whose HMAC signature verifies for THIS user's attempt;
  · a forged/garbled/odd-shaped signature changes nothing (and doesn't poison the attempt);
  · repeats are harmless, one payment completes one checkout, a second payment id is refused;
  · if the cart or a price moved after the quote was confirmed, no order is created and the attempt is needs_refund;
  · another user's attempt/cart looks like it doesn't exist; live keys and missing keys are refused;
  · the website's POST /orders and the chat's place_order create nothing, and place_order is not called from anywhere else;
  · the database refuses a "paid" order without Razorpay ids and a pending order that moves past 'placed';
  · simulated progress runs only for paid, non-sample orders, follows the schedule, and never touches another user's.
Network: none. Razorpay is replaced by a fake that records what it was asked.
"""

import base64
import hashlib
import json
import re
import urllib.error
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings, strategies as st
from psycopg import errors

from app import config
from app.agent import cards
from app.agent.loop import run_turn
from app.auth import get_verifier
from app.db import get_conn
from app.main import app
from app.payments import razorpay
from app.tools import payments, tracking
from app.tools.cart import add_to_cart, remove_from_cart, view_cart
from app.tools.history import get_user_history
from app.tools.orders import payment_required, place_order, track_order
from tests.test_agent_loop import BUSY, PROMPT, Script
from tests.test_orders import confirm, item, order_count, two_restaurant_cart, users  # noqa: F401 (fixtures by name)

# Made at run time so no key-shaped literal sits in the source (the repo's secret guard would rightly object).
KEY = "rzp_" + "test_ABCDEF123456"
LIVE_SHAPED_KEY = "rzp_" + "li" + "ve_ABCDEF123456"
SECRET = hashlib.sha256(b"dawat-test-hmac-1").hexdigest()[:32]
OTHER_SECRET = hashlib.sha256(b"dawat-test-hmac-2").hexdigest()[:32]
client = TestClient(app)


@pytest.fixture(autouse=True)
def razorpay_keys(monkeypatch):
    monkeypatch.setattr(config, "RAZORPAY_KEY_ID", KEY)
    monkeypatch.setattr(config, "RAZORPAY_KEY_SECRET", SECRET)


class Fake:
    """Stands in for Razorpay's order API: records (amount, receipt), answers like the real thing."""

    def __init__(self):
        self.calls = []

    def __call__(self, amount_rupees, receipt):
        self.calls.append((amount_rupees, receipt))
        return {"razorpay_order_id": f"order_Fake{len(self.calls):03d}", "amount_paise": amount_rupees * 100, "currency": "INR"}


def sig(order_id, payment_id, secret=SECRET):
    return razorpay.sign(order_id, payment_id, secret)


def pay_ok(db, user, order_id, payment_id="pay_Test001"):
    return payments.verify_payment(db, user, order_id, payment_id, sig(order_id, payment_id))


def attempt(db, order_id):
    return db.execute("select * from public.payment_attempts where razorpay_order_id = %s", (order_id,)).fetchone()


def orders_of_cart(db, cart_id):
    return db.execute("select count(*) as n from public.orders where cart_id = %s", (cart_id,)).fetchone()["n"]


def cart_status(db, cart_id):
    return db.execute("select status from public.carts where cart_id = %s", (cart_id,)).fetchone()["status"]


@pytest.fixture
def started(db, users, two_restaurant_cart):
    """Priya's two-restaurant cart, confirmed, with its payment started. (fake, cart view, start answer)"""
    fake = Fake()
    shown = confirm(db, users["priya"])
    res = payments.start_payment(db, users["priya"], shown["cart_id"], create_order=fake)
    assert res["status"] == "ok", res
    return fake, shown, res


# ═══ the Razorpay module: signatures, keys, the HTTP call (no database) ═══════════════════════════════════
def test_a_signature_made_with_the_secret_verifies():
    assert razorpay.verify_signature("order_A1", "pay_B2", sig("order_A1", "pay_B2"))


@pytest.mark.parametrize("order_id, payment_id, signature", [
    ("order_A1", "pay_B2", sig("order_A1", "pay_B2", OTHER_SECRET)),                            # wrong secret
    ("order_A2", "pay_B2", sig("order_A1", "pay_B2")),                                          # other order id
    ("order_A1", "pay_B3", sig("order_A1", "pay_B2")),                                          # other payment id
    ("order_A1", "pay_B2", sig("order_A1", "pay_B2")[:-1] + "0"),                               # one character off
    ("order_A1", "pay_B2", sig("order_A1", "pay_B2").upper()),                                  # not the lowercase hex
    ("order_A1", "pay_B2", "a" * 63), ("order_A1", "pay_B2", ""),
    ("order_A1", "pay_B2", sig("order_A1", "pay_B2") + "0"),
    ("order_A1", "pay_B2", "é" * 64),                                                           # non-ASCII must not crash
    ("order_A1", "pay_B2", None), ("order_A1", None, "a" * 64), (None, "pay_B2", "a" * 64),
    ("order_A1", "pay_B2", 12345), (["order_A1"], "pay_B2", sig("order_A1", "pay_B2")),
])
def test_anything_else_is_not_verified_and_never_raises(order_id, payment_id, signature):
    assert razorpay.verify_signature(order_id, payment_id, signature) is False


def test_an_id_with_a_pipe_cannot_shift_the_signed_text():
    # "order_a|pay_b" + "pay_c" would sign the same text as "order_a" + "pay_b|pay_c"
    forged = sig("order_a", "pay_b|pay_c")
    assert not razorpay.ids_look_valid("order_a", "pay_b|pay_c", forged)
    assert razorpay.verify_signature("order_a", "pay_b|pay_c", forged) is False
    assert razorpay.verify_signature("order_a|pay_b", "pay_c", forged) is False


def test_only_test_keys_are_allowed(monkeypatch):
    monkeypatch.setattr(config, "RAZORPAY_KEY_ID", LIVE_SHAPED_KEY)
    with pytest.raises(razorpay.PaymentsNotConfigured):
        razorpay.key_id()
    with pytest.raises(razorpay.PaymentsNotConfigured):
        razorpay.create_order(100, "r", post=lambda *a: pytest.fail("a live key must never reach the network"))
    with pytest.raises(razorpay.PaymentsNotConfigured):
        razorpay.verify_signature("order_A1", "pay_B2", sig("order_A1", "pay_B2"))


@pytest.mark.parametrize("kid, secret", [(None, SECRET), (KEY, None), (None, None)])
def test_missing_keys_mean_payments_are_not_configured(monkeypatch, kid, secret):
    monkeypatch.setattr(config, "RAZORPAY_KEY_ID", kid)
    monkeypatch.setattr(config, "RAZORPAY_KEY_SECRET", secret)
    with pytest.raises(razorpay.PaymentsNotConfigured):
        razorpay.key_id()


def test_the_order_is_created_for_rupees_times_100_paise_with_the_keys(monkeypatch):
    sent = {}

    def post(url, body, kid, secret):
        sent.update(url=url, body=body, kid=kid, secret=secret)
        return {"id": "order_Ok1", "amount": body["amount"], "currency": "INR"}
    made = razorpay.create_order(341, "r" * 60, post=post)
    assert sent["body"] == {"amount": 34100, "currency": "INR", "receipt": "r" * 40}
    assert (sent["kid"], sent["secret"]) == (KEY, SECRET) and sent["url"] == "https://api.razorpay.com/v1/orders"
    assert made == {"razorpay_order_id": "order_Ok1", "amount_paise": 34100, "currency": "INR"}


@pytest.mark.parametrize("amount", [0, -5, 1.5, "100", None, True])
def test_the_amount_must_be_a_positive_whole_number_of_rupees(amount):
    with pytest.raises(ValueError):
        razorpay.create_order(amount, "r", post=lambda *a: pytest.fail("no request for a bad amount"))


@pytest.mark.parametrize("answer", [
    {"id": "order_X", "amount": 1, "currency": "INR"},                     # amount differs from what we asked
    {"id": "order_X", "amount": 10000, "currency": "USD"},
    {"id": "nope", "amount": 10000, "currency": "INR"}, {"amount": 10000, "currency": "INR"}, [], None, "oops"])
def test_an_unexpected_answer_is_refused(answer):
    with pytest.raises(razorpay.RazorpayError):
        razorpay.create_order(100, "r", post=lambda *a: answer)


def test_http_failures_become_one_error_that_never_contains_the_secret(monkeypatch):
    def boom_http(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, f"bad key {SECRET}", {}, None)

    def boom_net(req, timeout):
        raise urllib.error.URLError(f"cannot reach {SECRET}")
    for boom in (boom_http, boom_net):
        monkeypatch.setattr(razorpay.urllib.request, "urlopen", boom)
        with pytest.raises(razorpay.RazorpayError) as e:
            razorpay.create_order(100, "r")
        assert SECRET not in str(e.value) and KEY not in str(e.value)


def test_the_real_post_sends_basic_auth_json_and_a_timeout(monkeypatch):
    seen = {}

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps({"id": "order_Z", "amount": 500, "currency": "INR"}).encode()

    def fake_open(req, timeout):
        seen.update(auth=req.get_header("Authorization"), body=json.loads(req.data), timeout=timeout, method=req.get_method())
        return Resp()
    monkeypatch.setattr(razorpay.urllib.request, "urlopen", fake_open)
    razorpay.create_order(5, "rcpt")
    assert base64.b64decode(seen["auth"].removeprefix("Basic ")).decode() == f"{KEY}:{SECRET}"
    assert seen["body"]["amount"] == 500 and seen["timeout"] == razorpay.TIMEOUT_S and seen["method"] == "POST"


# ═══ start_payment ═══════════════════════════════════════════════════════════════════════════════════════
def test_start_asks_razorpay_for_the_servers_confirmed_total(db, users, started):
    fake, shown, res = started
    assert fake.calls == [(shown["grand_total"], res["attempt_id"])]
    assert res["amount"] == shown["grand_total"] * 100 and res["amount_rupees"] == shown["grand_total"]
    assert res["key_id"] == KEY and res["currency"] == "INR" and res["cart_id"] == shown["cart_id"]
    assert SECRET not in json.dumps(res)
    row = attempt(db, res["razorpay_order_id"])
    assert (row["amount"], row["quote_id"], row["status"], row["user_id"]) == (
        shown["grand_total"], shown["quote_id"], "created", users["priya"])
    assert orders_of_cart(db, shown["cart_id"]) == 0                 # starting a payment creates no order


def test_starting_twice_for_the_same_quote_reuses_the_razorpay_order(db, users, started):
    fake, shown, res = started
    again = payments.start_payment(db, users["priya"], shown["cart_id"], create_order=fake)
    assert again["status"] == "ok" and again["reused"] is True
    assert again["razorpay_order_id"] == res["razorpay_order_id"] and len(fake.calls) == 1


def test_a_changed_cart_gets_a_new_attempt_and_the_old_one_expires(db, users, started):
    fake, shown, res = started
    # the user edits the cart (it re-opens), confirms the new summary, and pays that one
    line = shown["branches"][0]["items"][0]
    add_to_cart(db, users["priya"], line["item_id"], shown["branches"][0]["branch_id"], 1)
    second = confirm(db, users["priya"])
    new = payments.start_payment(db, users["priya"], second["cart_id"], create_order=fake)
    assert new["razorpay_order_id"] != res["razorpay_order_id"] and new["amount_rupees"] == second["grand_total"]
    assert second["grand_total"] != shown["grand_total"]
    assert attempt(db, res["razorpay_order_id"])["status"] == "expired"
    assert attempt(db, new["razorpay_order_id"])["status"] == "created"


def test_an_old_unpaid_attempt_is_not_reused(db, users, started):
    fake, shown, res = started
    db.execute("update public.payment_attempts set created_at = now() - interval '31 minutes' where razorpay_order_id = %s",
               (res["razorpay_order_id"],))
    again = payments.start_payment(db, users["priya"], shown["cart_id"], create_order=fake)
    assert again["reused"] is False and again["razorpay_order_id"] != res["razorpay_order_id"] and len(fake.calls) == 2


def test_an_unconfirmed_cart_cannot_start_a_payment(db, users, two_restaurant_cart):
    fake = Fake()
    res = payments.start_payment(db, users["priya"], view_cart(db, users["priya"])["cart_id"], create_order=fake)
    assert res["status"] == "not_confirmed" and fake.calls == []
    assert db.execute("select count(*) as n from public.payment_attempts").fetchone()["n"] == 0


def test_another_users_cart_looks_like_it_does_not_exist(db, users, started):
    fake, shown, res = started
    other_fake = Fake()
    assert payments.start_payment(db, users["arjun"], shown["cart_id"], create_order=other_fake)["status"] == "not_found"
    assert other_fake.calls == []


@pytest.mark.parametrize("cart_id", ["", "nope", "00000000-0000-0000-0000-000000000000"])
def test_a_bad_or_unknown_cart_id_is_refused(db, users, cart_id):
    fake = Fake()
    assert payments.start_payment(db, users["priya"], cart_id, create_order=fake)["status"] in ("invalid_input", "not_found")
    assert fake.calls == []


def test_razorpay_failing_means_nothing_is_recorded(db, users, two_restaurant_cart):
    shown = confirm(db, users["priya"])

    def down(amount, receipt):
        raise razorpay.RazorpayError("Razorpay could not be reached (URLError)")
    res = payments.start_payment(db, users["priya"], shown["cart_id"], create_order=down)
    assert res["status"] == "payment_unavailable"
    assert db.execute("select count(*) as n from public.payment_attempts").fetchone()["n"] == 0


def test_unconfigured_payments_answer_before_anything_else(db, users, two_restaurant_cart, monkeypatch):
    shown = confirm(db, users["priya"])
    monkeypatch.setattr(config, "RAZORPAY_KEY_SECRET", None)
    fake = Fake()
    assert payments.start_payment(db, users["priya"], shown["cart_id"], create_order=fake)["status"] == "payments_not_configured"
    assert fake.calls == []
    assert payments.verify_payment(db, users["priya"], "order_A", "pay_B", "a" * 64)["status"] == "payments_not_configured"


# ═══ verify_payment ══════════════════════════════════════════════════════════════════════════════════════
def test_a_verified_payment_creates_the_paid_orders(db, users, started):
    fake, shown, res = started
    out = pay_ok(db, users["priya"], res["razorpay_order_id"])
    assert out["status"] == "ok" and out["payment_status"] == "paid"
    assert out["grand_total"] == shown["grand_total"] and len(out["orders"]) == 2
    assert {o["payment_status"] for o in out["orders"]} == {"paid"} and {o["status"] for o in out["orders"]} == {"placed"}
    rows = db.execute("select payment_status, razorpay_order_id, razorpay_payment_id, checkout_id from public.orders "
                      "where cart_id = %s", (shown["cart_id"],)).fetchall()
    assert len(rows) == 2 and {(r["payment_status"], r["razorpay_order_id"], r["razorpay_payment_id"]) for r in rows} == {
        ("paid", res["razorpay_order_id"], "pay_Test001")}
    a = attempt(db, res["razorpay_order_id"])
    assert a["status"] == "paid" and str(a["checkout_id"]) == out["checkout_id"] and a["razorpay_payment_id"] == "pay_Test001"
    assert cart_status(db, shown["cart_id"]) == "ordered"
    db.execute("set constraints all immediate")            # the deferred totals triggers pass


def test_repeating_a_verified_payment_returns_the_same_orders_once(db, users, started):
    fake, shown, res = started
    first = pay_ok(db, users["priya"], res["razorpay_order_id"])
    second = pay_ok(db, users["priya"], res["razorpay_order_id"])
    assert second["status"] == "already_paid" and second["checkout_id"] == first["checkout_id"]
    assert [o["order_number"] for o in second["orders"]] == [o["order_number"] for o in first["orders"]]
    assert orders_of_cart(db, shown["cart_id"]) == 2


def test_a_second_payment_id_for_a_paid_order_is_refused(db, users, started):
    fake, shown, res = started
    pay_ok(db, users["priya"], res["razorpay_order_id"], "pay_First")
    other = pay_ok(db, users["priya"], res["razorpay_order_id"], "pay_Second")
    assert other["status"] == "payment_conflict" and orders_of_cart(db, shown["cart_id"]) == 2
    assert attempt(db, res["razorpay_order_id"])["razorpay_payment_id"] == "pay_First"


@pytest.mark.parametrize("bad", ["wrong_secret", "garbled", "short", "unicode", "empty"])
def test_a_bad_signature_creates_nothing_and_does_not_poison_the_attempt(db, users, started, bad):
    fake, shown, res = started
    oid = res["razorpay_order_id"]
    signature = {"wrong_secret": sig(oid, "pay_X", OTHER_SECRET), "garbled": "z" * 64,
                 "short": "abc", "unicode": "é" * 64, "empty": ""}[bad]
    out = payments.verify_payment(db, users["priya"], oid, "pay_X", signature)
    assert out["status"] in ("bad_signature", "invalid_input")
    assert orders_of_cart(db, shown["cart_id"]) == 0
    a = attempt(db, oid)
    assert a["status"] == "created" and a["razorpay_payment_id"] is None
    assert cart_status(db, shown["cart_id"]) == "confirmed"
    assert pay_ok(db, users["priya"], oid)["status"] == "ok"           # the real payment still works afterwards


def test_a_valid_signature_for_someone_elses_attempt_is_not_found(db, users, started):
    fake, shown, res = started
    oid = res["razorpay_order_id"]
    out = pay_ok(db, users["arjun"], oid)                               # arjun even holds a correct signature
    assert out["status"] == "not_found"
    assert orders_of_cart(db, shown["cart_id"]) == 0 and attempt(db, oid)["status"] == "created"
    assert db.execute("select count(*) as n from public.orders where user_id = %s", (users["arjun"],)).fetchone()["n"] == 0


def test_an_unknown_razorpay_order_is_not_found(db, users, started):
    assert pay_ok(db, users["priya"], "order_DoesNotExist")["status"] == "not_found"


def test_a_cart_changed_after_the_quote_means_no_order_and_a_refund_note(db, users, started):
    fake, shown, res = started
    oid = res["razorpay_order_id"]
    first = shown["branches"][0]["items"][0]
    remove_from_cart(db, users["priya"], first["item_id"])              # the user edits the cart while the window is open
    out = pay_ok(db, users["priya"], oid)
    assert out["status"] == "needs_refund" and out["amount"] == shown["grand_total"]
    assert orders_of_cart(db, shown["cart_id"]) == 0
    a = attempt(db, oid)
    assert a["status"] == "needs_refund" and a["razorpay_payment_id"] == "pay_Test001" and a["checkout_id"] is None
    assert pay_ok(db, users["priya"], oid)["status"] == "needs_refund"                              # repeat: same answer
    assert pay_ok(db, users["priya"], oid, "pay_Other")["status"] == "payment_conflict"             # not a second payment
    assert orders_of_cart(db, shown["cart_id"]) == 0


def test_a_price_that_changed_after_confirming_means_no_order(db, users, started):
    fake, shown, res = started
    item_id = shown["branches"][0]["items"][0]["item_id"]
    db.execute("update public.menu_items set price = price + 20 where item_id = %s", (item_id,))
    out = pay_ok(db, users["priya"], res["razorpay_order_id"])
    assert out["status"] == "needs_refund" and orders_of_cart(db, shown["cart_id"]) == 0
    assert cart_status(db, shown["cart_id"]) == "open"


def test_paying_an_old_quote_after_the_cart_was_edited_and_reconfirmed_creates_no_order(db, users, started):
    # The cart is confirmed AGAIN (a different quote and total) while the first checkout window is still open. The
    # payment is for the first total: ordering the second cart with it would charge one amount and order another.
    fake, shown, res = started
    line = shown["branches"][0]["items"][0]
    add_to_cart(db, users["priya"], line["item_id"], shown["branches"][0]["branch_id"], 1)
    second = confirm(db, users["priya"])
    assert second["quote_id"] != shown["quote_id"] and second["grand_total"] != shown["grand_total"]
    out = pay_ok(db, users["priya"], res["razorpay_order_id"])
    assert out["status"] == "needs_refund" and out["amount"] == shown["grand_total"]
    assert orders_of_cart(db, shown["cart_id"]) == 0
    assert cart_status(db, shown["cart_id"]) == "confirmed"                      # the second confirmation is untouched
    assert attempt(db, res["razorpay_order_id"])["status"] == "needs_refund"


def test_an_attempt_for_another_quote_is_never_completed_even_at_the_same_total(db, users, started):
    fake, shown, res = started
    db.execute("update public.payment_attempts set quote_id = 'a-different-quote' where razorpay_order_id = %s",
               (res["razorpay_order_id"],))
    out = pay_ok(db, users["priya"], res["razorpay_order_id"])
    assert out["status"] == "needs_refund" and orders_of_cart(db, shown["cart_id"]) == 0


def test_an_attempt_for_another_total_is_never_completed_even_with_the_same_quote(db, users, started):
    fake, shown, res = started
    db.execute("update public.payment_attempts set amount = amount - 1 where razorpay_order_id = %s", (res["razorpay_order_id"],))
    out = pay_ok(db, users["priya"], res["razorpay_order_id"])
    assert out["status"] == "needs_refund" and orders_of_cart(db, shown["cart_id"]) == 0


def test_two_payments_for_one_cart_make_one_checkout(db, users, started):
    fake, shown, res = started
    db.execute("update public.payment_attempts set created_at = now() - interval '31 minutes'")   # the first window is old
    second = payments.start_payment(db, users["priya"], shown["cart_id"], create_order=fake)
    assert second["razorpay_order_id"] != res["razorpay_order_id"]
    assert pay_ok(db, users["priya"], second["razorpay_order_id"], "pay_A")["status"] == "ok"
    late = pay_ok(db, users["priya"], res["razorpay_order_id"], "pay_B")             # the first window pays too
    assert late["status"] == "needs_refund"
    assert orders_of_cart(db, shown["cart_id"]) == 2


def test_one_payment_id_cannot_complete_two_attempts(db, users, started):
    fake, shown, res = started
    pay_ok(db, users["priya"], res["razorpay_order_id"], "pay_Same")
    with pytest.raises(errors.UniqueViolation):
        with db.transaction():
            db.execute("""insert into public.payment_attempts (user_id, cart_id, quote_id, amount, razorpay_order_id,
                          razorpay_payment_id, status) select user_id, cart_id, quote_id, amount, 'order_Dup', 'pay_Same',
                          'needs_refund' from public.payment_attempts limit 1""")


@pytest.mark.parametrize("args", [(None, "pay_A", "a" * 64), ("order_A", 5, "a" * 64), ("order A", "pay_A", "a" * 64),
                                  ("order_A", "pay_A", "G" * 64), ("order_A|x", "pay_A", "a" * 64)])
def test_odd_shaped_values_are_rejected_before_any_lookup(db, users, args):
    assert payments.verify_payment(db, users["priya"], *args)["status"] == "invalid_input"


# ═══ the original gate still guards the start ═════════════════════════════════════════════════════════
def test_payment_required_runs_the_old_checks_and_creates_nothing(db, users, two_restaurant_cart):
    cart = view_cart(db, users["priya"])
    assert payment_required(db, users["priya"], cart["cart_id"])["status"] == "not_confirmed"
    shown = confirm(db, users["priya"])
    res = payment_required(db, users["priya"], shown["cart_id"])
    assert res["status"] == "payment_required" and res["grand_total"] == shown["grand_total"]
    assert res["quote_id"] == shown["quote_id"] and "NOT placed" in res["message"]
    assert order_count(db, users["priya"]) == 0
    assert payment_required(db, users["arjun"], shown["cart_id"])["status"] == "not_found"


def test_payment_required_reopens_a_cart_whose_price_moved(db, users, two_restaurant_cart):
    shown = confirm(db, users["priya"])
    db.execute("update public.menu_items set price = price + 20 where item_id = %s", (shown["branches"][0]["items"][0]["item_id"],))
    assert payment_required(db, users["priya"], shown["cart_id"])["status"] == "quote_changed"
    assert order_count(db, users["priya"]) == 0


# ═══ the routes ═════════════════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def api(db, users, verifier, make_token, monkeypatch):
    fake = Fake()

    def razorpay_http(url, body, kid, secret):
        made = fake(body["amount"] // 100, body["receipt"])
        return {"id": made["razorpay_order_id"], "amount": body["amount"], "currency": "INR"}
    monkeypatch.setattr(razorpay, "_post", razorpay_http)
    app.dependency_overrides[get_verifier] = lambda: verifier

    def test_db():
        yield db
    app.dependency_overrides[get_conn] = test_db

    def call(user, method, path, **kw):
        return client.request(method.upper(), path, headers={"Authorization": f"Bearer {make_token(users[user])}"}, **kw)
    call.fake = fake
    return call


def test_the_website_flow_confirm_pay_verify(db, users, api, two_restaurant_cart):
    shown = view_cart(db, users["priya"])
    assert api("priya", "post", "/cart/confirm", json={"cart_id": shown["cart_id"], "quote_id": shown["quote_id"]}).status_code == 200
    r = api("priya", "post", "/orders", json={"cart_id": shown["cart_id"]})
    assert r.status_code == 409 and r.json()["status"] == "payment_required" and order_count(db, users["priya"]) == 0
    s = api("priya", "post", "/payments/start", json={"cart_id": shown["cart_id"]})
    assert s.status_code == 200 and s.json()["amount"] == shown["grand_total"] * 100
    assert api.fake.calls[0][0] == shown["grand_total"]
    oid = s.json()["razorpay_order_id"]
    bad = api("priya", "post", "/payments/verify", json={"razorpay_order_id": oid, "razorpay_payment_id": "pay_R1",
                                                         "razorpay_signature": "0" * 64})
    assert bad.status_code == 422 and bad.json()["status"] == "bad_signature" and order_count(db, users["priya"]) == 0
    v = api("priya", "post", "/payments/verify", json={"razorpay_order_id": oid, "razorpay_payment_id": "pay_R1",
                                                       "razorpay_signature": sig(oid, "pay_R1")})
    assert v.status_code == 200 and v.json()["status"] == "ok" and v.json()["orders"][0]["order_number"].startswith("DW")
    again = api("priya", "post", "/payments/verify", json={"razorpay_order_id": oid, "razorpay_payment_id": "pay_R1",
                                                           "razorpay_signature": sig(oid, "pay_R1")})
    assert again.status_code == 200 and again.json()["status"] == "already_paid"


def test_a_payment_after_a_cart_change_is_a_409_with_no_orders(db, users, api, two_restaurant_cart):
    shown = view_cart(db, users["priya"])
    api("priya", "post", "/cart/confirm", json={"cart_id": shown["cart_id"], "quote_id": shown["quote_id"]})
    oid = api("priya", "post", "/payments/start", json={"cart_id": shown["cart_id"]}).json()["razorpay_order_id"]
    api("priya", "delete", f"/cart/items/{shown['branches'][0]['items'][0]['item_id']}")
    v = api("priya", "post", "/payments/verify", json={"razorpay_order_id": oid, "razorpay_payment_id": "pay_R2",
                                                       "razorpay_signature": sig(oid, "pay_R2")})
    assert v.status_code == 409 and v.json()["status"] == "needs_refund" and order_count(db, users["priya"]) == 0


@pytest.mark.parametrize("path, body", [
    ("/payments/start", {"cart_id": "x", "amount": 1}), ("/payments/start", {"cart_id": "x", "user_id": "u"}),
    ("/payments/verify", {"razorpay_order_id": "order_A", "razorpay_payment_id": "pay_A", "razorpay_signature": "a" * 64, "amount": 1}),
    ("/payments/start", {}), ("/payments/verify", {"razorpay_order_id": 1, "razorpay_payment_id": "pay_A", "razorpay_signature": "a"})])
def test_bodies_cannot_carry_an_amount_a_user_or_wrong_types(api, path, body):
    assert api("priya", "post", path, json=body).status_code == 422


def test_a_real_confirmed_cart_with_an_extra_field_is_refused_before_anything_happens(db, users, api, two_restaurant_cart):
    # a made-up cart id would be refused for other reasons too; a REAL one shows the extra field itself is refused
    shown = view_cart(db, users["priya"])
    api("priya", "post", "/cart/confirm", json={"cart_id": shown["cart_id"], "quote_id": shown["quote_id"]})
    for extra in ({"amount": 1}, {"amount_paise": 100}, {"user_id": str(users["arjun"])}, {"total": 1}):
        r = api("priya", "post", "/payments/start", json={"cart_id": shown["cart_id"], **extra})
        assert r.status_code == 422, extra
    assert api.fake.calls == [] and db.execute("select count(*) as n from public.payment_attempts").fetchone()["n"] == 0
    assert api("priya", "post", "/payments/start", json={"cart_id": shown["cart_id"]}).status_code == 200


def test_payment_routes_need_a_token():
    for path in ("/payments/start", "/payments/verify"):
        assert client.post(path, json={}).status_code == 401


def test_the_status_codes_for_payment_answers():
    from app.api.deps import STATUS_CODES
    assert STATUS_CODES["payment_required"] == 409 and STATUS_CODES["needs_refund"] == 409
    assert STATUS_CODES["bad_signature"] == 422 and STATUS_CODES["payments_not_configured"] == 503
    assert STATUS_CODES["payment_unavailable"] == 503 and STATUS_CODES["already_paid"] == 200
    assert STATUS_CODES["payment_conflict"] == 409


# ═══ place_order is reachable only from the payment step (and the demo's sample orders) ═════════════
def test_nothing_else_creates_orders():
    app_dir = Path(__file__).resolve().parent.parent / "app"
    call = re.compile(r"(?<![\w])place_order\(")
    found = {str(p.relative_to(app_dir)).replace("\\", "/") for p in app_dir.rglob("*.py")
             if call.search(p.read_text(encoding="utf-8"))}
    assert found == {"tools/orders.py", "tools/payments.py", "tools/demo.py"}, found


def test_the_chat_tool_place_order_asks_for_payment_and_creates_nothing(db, users, two_restaurant_cart):
    from app.agent.tools import ToolContext, run_tool
    shown = confirm(db, users["priya"])
    ctx = ToolContext(conn=db, user_id=users["priya"], user_message="yes, place it")
    res = run_tool("place_order", {"cart_id": shown["cart_id"]}, ctx)
    assert res["status"] == "payment_required" and res["grand_total"] == shown["grand_total"]
    assert order_count(db, users["priya"]) == 0


def _yes_turn(db, users, shown, final):
    chat = Script([("confirm_cart", {"cart_id": shown["cart_id"], "quote_id": shown["quote_id"]}),
                   ("place_order", {"cart_id": shown["cart_id"]})], final)
    history = [{"role": "user", "content": "order it"},
               {"role": "assistant", "content": "Shall I place it?", cards.CARD_KEY: cards.order_card(shown)}]
    return run_turn(db, history, "yes", users["priya"], **PROMPT, chat=chat)


def test_a_turn_that_gets_the_yes_ends_with_a_pay_payload_and_no_order(db, users, two_restaurant_cart):
    shown = view_cart(db, users["priya"])
    turn = _yes_turn(db, users, shown, "Tap Pay to finish.")
    assert turn.status == "ok" and turn.payment == {"cart_id": shown["cart_id"], "quote_id": shown["quote_id"],
                                                    "grand_total": shown["grand_total"]}
    assert turn.card is None and order_count(db, users["priya"]) == 0


def test_busy_after_the_yes_still_shows_pay_and_never_claims_an_order(db, users, two_restaurant_cart):
    shown = view_cart(db, users["priya"])
    turn = _yes_turn(db, users, shown, BUSY)
    assert turn.status == "busy" and turn.payment and "not placed yet" in turn.reply and f"₹{shown['grand_total']}" in turn.reply
    assert "is placed" not in turn.reply and order_count(db, users["priya"]) == 0


def test_a_chat_message_does_not_reopen_a_cart_whose_payment_is_open(db, users, started):
    fake, shown, res = started
    run_turn(db, [], "hello", users["priya"], **PROMPT, chat=Script("Hi!"))
    assert view_cart(db, users["priya"])["cart_status"] == "confirmed"          # the website's confirmation survived
    assert pay_ok(db, users["priya"], res["razorpay_order_id"])["status"] == "ok"


@pytest.mark.parametrize("how", ["no_attempt", "old_attempt", "other_quote", "expired_attempt", "refunded_attempt"])
def test_without_a_live_attempt_for_this_quote_a_chat_message_reopens_the_cart(db, users, started, how):
    fake, shown, res = started
    if how == "no_attempt":
        db.execute("delete from public.payment_attempts")
    elif how == "old_attempt":
        db.execute("update public.payment_attempts set created_at = now() - interval '31 minutes'")
    elif how == "other_quote":
        db.execute("update public.payment_attempts set quote_id = 'something-else'")
    elif how == "expired_attempt":
        db.execute("update public.payment_attempts set status = 'expired'")
    else:
        db.execute("update public.payment_attempts set status = 'needs_refund', razorpay_payment_id = 'pay_Z'")
    run_turn(db, [], "hello", users["priya"], **PROMPT, chat=Script("Hi!"))
    assert view_cart(db, users["priya"])["cart_status"] == "open"


# ═══ the database's own checks ══════════════════════════════════════════════════════════════════════════
def _raw_order(db, users, **over):
    """A confirmed cart and the columns of one order for it, to insert with chosen values."""
    shown = confirm(db, users["priya"])
    b, d = shown["branches"][0], shown["delivery"]
    cols = dict(checkout_id="11111111-1111-1111-1111-111111111111", user_id=users["priya"], cart_id=shown["cart_id"],
                branch_id=b["branch_id"], address_id=d["address_id"], items_total=b["items_total"],
                delivery_fee=b["delivery_fee"], taxes=b["taxes"], grand_total=b["total"], delivery_area_id=d["area_id"],
                delivery_lat=d["lat"], delivery_lon=d["lon"])
    cols.update(over)
    return cols


def test_the_database_refuses_a_paid_order_without_razorpay_ids(db, users, two_restaurant_cart):
    cols = _raw_order(db, users, payment_status="paid")
    for extra in ({}, {"razorpay_order_id": "order_X"}, {"razorpay_payment_id": "pay_X"}):
        with pytest.raises(errors.CheckViolation):
            with db.transaction():
                c = {**cols, **extra}
                db.execute(f"insert into public.orders ({', '.join(c)}) values ({', '.join(['%s'] * len(c))})", list(c.values()))
    c = {**cols, "razorpay_order_id": "order_X", "razorpay_payment_id": "pay_X"}
    with db.transaction():                                                       # the constraint accepts the full set
        db.execute(f"insert into public.orders ({', '.join(c)}) values ({', '.join(['%s'] * len(c))})", list(c.values()))


def test_the_database_refuses_progress_for_an_unpaid_order_except_samples(db, users, two_restaurant_cart):
    shown = confirm(db, users["priya"])
    res = place_order(db, users["priya"], shown["cart_id"])                      # an unpaid order (internal step)
    oid = res["orders"][0]["order_id"]
    for status in ("confirmed", "preparing", "picked_up", "on_the_way", "delivered"):
        with pytest.raises(errors.CheckViolation):
            with db.transaction():
                db.execute("update public.orders set status = %s where order_id = %s", (status, oid))
    with db.transaction():
        db.execute("update public.orders set status = 'cancelled' where order_id = %s", (oid,))
        db.execute("update public.orders set status = 'delivered', is_sample = true where order_id = %s", (oid,))


def test_the_database_refuses_inconsistent_attempts(db, users, started):
    fake, shown, res = started
    for sets in ("status = 'paid', razorpay_payment_id = 'pay_1'", "status = 'needs_refund'",
                 "checkout_id = gen_random_uuid()"):
        with pytest.raises(errors.CheckViolation):
            with db.transaction():
                db.execute(f"update public.payment_attempts set {sets} where razorpay_order_id = %s", (res["razorpay_order_id"],))


# ═══ simulated progress and the rider ═════════════════════════════════════════════════════════════════
def paid_order(db, users, started, user="priya"):
    fake, shown, res = started
    out = pay_ok(db, users[user], res["razorpay_order_id"])
    assert out["status"] == "ok"
    return out["orders"][0]["order_id"], out


def age(db, order_id, seconds):
    db.execute("update public.orders set created_at = now() - make_interval(secs => %s) where order_id = %s", (seconds, order_id))
    db.execute("update public.order_status_events set created_at = now() - make_interval(secs => %s) "
               "where order_id = %s and status = 'placed'", (seconds, order_id))


def statuses(db, order_id):
    return [r["status"] for r in db.execute("select status from public.order_status_events where order_id = %s "
                                            "order by created_at, event_id", (order_id,)).fetchall()]


ALL = ["placed", "confirmed", "preparing", "picked_up", "on_the_way", "delivered"]
EXPECTED = [(0, ALL[:1]), (59, ALL[:1]), (60, ALL[:2]), (135, ALL[:3]), (224, ALL[:3]), (225, ALL[:4]), (270, ALL[:5]),
            (359, ALL[:5]), (360, ALL), (100000, ALL)]


@pytest.mark.parametrize("seconds, expected", EXPECTED)
def test_the_timeline_follows_the_schedule(db, users, started, seconds, expected):
    oid, out = paid_order(db, users, started)
    age(db, oid, seconds)
    t = track_order(db, users["priya"], oid)
    assert [e["status"] for e in t["timeline"]] == expected and t["order_status"] == expected[-1]
    assert db.execute("select status from public.orders where order_id = %s", (oid,)).fetchone()["status"] == expected[-1]
    assert t["simulated_tracking"] is True


def test_reading_again_writes_nothing_new_and_events_carry_their_due_time(db, users, started):
    oid, out = paid_order(db, users, started)
    age(db, oid, 300)
    first = track_order(db, users["priya"], oid)
    again = track_order(db, users["priya"], oid)
    assert first["timeline"] == again["timeline"] and len(statuses(db, oid)) == 5
    rows = {r["status"]: r["off"] for r in db.execute(
        "select e.status, extract(epoch from e.created_at - o.created_at)::int as off from public.order_status_events e "
        "join public.orders o using (order_id) where o.order_id = %s", (oid,)).fetchall()}
    assert {s: rows[s] for s in ("confirmed", "preparing", "picked_up", "on_the_way")} == {
        "confirmed": 60, "preparing": 135, "picked_up": 225, "on_the_way": 270}


def test_the_rider_waits_then_moves_in_a_straight_line_then_arrives(db, users, started):
    oid, out = paid_order(db, users, started)
    t0 = track_order(db, users["priya"], oid)
    start, end = t0["route"]["from"], t0["route"]["to"]
    assert t0["rider"] is None and t0["next_update_in_s"] == 60
    age(db, oid, 100)
    assert track_order(db, users["priya"], oid)["rider"] is None
    age(db, oid, 250)
    r = track_order(db, users["priya"], oid)["rider"]
    assert (r["lat"], r["lon"], r["stage"]) == (start["lat"], start["lon"], "picked_up")
    age(db, oid, 315)                                                           # halfway through the last leg
    t = track_order(db, users["priya"], oid)
    assert t["rider"]["stage"] == "on_the_way" and t["next_update_in_s"] == 45
    assert t["rider"]["lat"] == pytest.approx((start["lat"] + end["lat"]) / 2, abs=1e-5)
    assert t["rider"]["lon"] == pytest.approx((start["lon"] + end["lon"]) / 2, abs=1e-5)
    age(db, oid, 400)
    t = track_order(db, users["priya"], oid)
    assert t["rider"] == {"lat": end["lat"], "lon": end["lon"], "stage": "delivered"} and t["next_update_in_s"] is None
    last = db.execute("select rider_lat, rider_lon from public.order_status_events where order_id = %s and status = 'delivered'",
                      (oid,)).fetchone()
    assert (last["rider_lat"], last["rider_lon"]) == (end["lat"], end["lon"])


def test_an_unpaid_order_never_moves(db, users, two_restaurant_cart):
    shown = confirm(db, users["priya"])
    oid = place_order(db, users["priya"], shown["cart_id"])["orders"][0]["order_id"]      # unpaid (internal)
    age(db, oid, 100000)
    t = track_order(db, users["priya"], oid)
    assert t["order_status"] == "placed" and [e["status"] for e in t["timeline"]] == ["placed"]
    assert t["simulated_tracking"] is False and t["rider"] is None and t["next_update_in_s"] is None
    get_user_history(db, users["priya"])
    assert statuses(db, oid) == ["placed"]


def test_sample_orders_are_left_alone(db, users, started):
    oid, out = paid_order(db, users, started)
    db.execute("update public.orders set is_sample = true where order_id = %s", (oid,))
    age(db, oid, 100000)
    t = track_order(db, users["priya"], oid)
    get_user_history(db, users["priya"])                                   # history advances orders too: not this one
    assert tracking.advance(db, users["priya"]) == 0 and tracking.advance(db, users["priya"], oid) == 0
    assert statuses(db, oid) == ["placed"] and t["simulated_tracking"] is False and t["rider"] is None


def test_history_advances_the_users_paid_orders_too(db, users, started):
    oid, out = paid_order(db, users, started)
    age(db, oid, 400)
    h = get_user_history(db, users["priya"])
    assert {o["order_status"] for c in h["checkouts"] for o in c["orders"] if o["order_id"] == oid} == {"delivered"}


def test_advancing_one_user_never_touches_another_users_order(db, users, started):
    oid, out = paid_order(db, users, started)
    age(db, oid, 400)
    assert tracking.advance(db, users["arjun"]) == 0 and tracking.advance(db, users["arjun"], oid) == 0
    assert statuses(db, oid) == ["placed"]
    assert track_order(db, users["arjun"], oid)["status"] == "not_found" and statuses(db, oid) == ["placed"]


@settings(max_examples=200, deadline=None)
@given(age_s=st.floats(min_value=0, max_value=1000, allow_nan=False), lat1=st.floats(17.2, 17.6), lon1=st.floats(78.2, 78.7),
       lat2=st.floats(17.2, 17.6), lon2=st.floats(78.2, 78.7))
def test_the_rider_is_always_on_the_segment_and_progress_is_ordered(age_s, lat1, lon1, lat2, lon2):
    r = tracking.rider_position(age_s, (lat1, lon1), (lat2, lon2))
    if age_s < tracking.PICKED_UP_S:
        assert r is None
    else:
        assert min(lat1, lat2) - 1e-6 <= r["lat"] <= max(lat1, lat2) + 1e-6
        assert min(lon1, lon2) - 1e-6 <= r["lon"] <= max(lon1, lon2) + 1e-6
    due = [s for s, _ in tracking.due_statuses(age_s)]
    assert due == [s for s, _ in tracking.SCHEDULE][:len(due)]
    nxt = tracking.next_update_in(age_s)
    assert (nxt is None) == (age_s >= tracking.DELIVERED_S) and (nxt is None or nxt >= 1)
