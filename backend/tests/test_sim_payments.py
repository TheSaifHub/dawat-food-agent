"""The simulated payment gateway (D-062). MONEY CODE: full rigour. No network, no keys.

What must hold:
  · /payments/start works with no Razorpay keys, for the server-computed total, and says which gateway it is;
  · a success returns (order_TEST…, pay_TEST_…, HMAC signature) and /payments/verify then creates the orders, once;
  · a failure (outcome or failing test instrument) creates no order, leaves the cart confirmed, and can be retried;
  · only the fixed test cards / UPI ids are accepted; real-looking card numbers are refused and never echoed;
  · another user's order looks missing; a paid/refunded attempt can't be "paid" again;
  · a signature made with the wrong key, or for a non-TEST payment id, is rejected in simulated mode;
  · with PAYMENT_GATEWAY=razorpay the simulate step is off; an unknown value means "not configured".
"""

import hashlib

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.payments import gateway, razorpay, simulated
from app.tools import payments
from app.tools.cart import add_to_cart
from app.tools.orders import place_order
from tests.test_api_routes import as_user, call  # noqa: F401 (fixture by name)
from tests.test_orders import confirm, item, order_count, two_restaurant_cart, users  # noqa: F401

client = TestClient(app)
OK_CARD, OK_UPI, FAIL_CARD, FAIL_UPI = "4111 1111 1111 1111", "success@razorpay", "4000 0000 0000 0002", "failure@razorpay"
REAL_LOOKING = "4929 1234 5678 9017"


@pytest.fixture(autouse=True)
def simulated_gateway(monkeypatch):
    monkeypatch.setattr(config, "PAYMENT_GATEWAY", "simulated")
    monkeypatch.setattr(config, "RAZORPAY_KEY_ID", None)
    monkeypatch.setattr(config, "RAZORPAY_KEY_SECRET", None)
    monkeypatch.setattr(config, "PAYMENT_SIM_SECRET", hashlib.sha256(b"dawat-sim-test").hexdigest())


@pytest.fixture
def started(db, users, two_restaurant_cart):
    shown = confirm(db, users["priya"])
    res = payments.start_payment(db, users["priya"], shown["cart_id"])
    assert res["status"] == "ok", res
    return shown, res


def checkout(db, user, order_id, outcome="success", method="card", card=OK_CARD, upi=None):
    return payments.simulate_payment(db, user, order_id, outcome, method, card if method == "card" else None, upi)


def attempt(db, order_id):
    return db.execute("select * from public.payment_attempts where razorpay_order_id = %s", (order_id,)).fetchone()


def cart_status(db, cart_id):
    return db.execute("select status from public.carts where cart_id = %s", (cart_id,)).fetchone()["status"]


# ═══ start / verify with no Razorpay account ═════════════════════════════════════════════════════════════
def test_start_needs_no_keys_and_uses_the_server_total(started):
    shown, res = started
    assert res["gateway"] == "simulated" and res["key_id"] == simulated.KEY_ID
    assert res["razorpay_order_id"].startswith("order_TEST") and res["amount_rupees"] == shown["grand_total"]
    assert res["amount"] == shown["grand_total"] * 100


def test_a_successful_test_payment_creates_the_orders_once(db, users, started):
    shown, res = started
    oid = res["razorpay_order_id"]
    paid = checkout(db, users["priya"], oid)
    assert paid["status"] == "ok" and paid["razorpay_order_id"] == oid
    assert simulated.SIM_PAYMENT_ID.fullmatch(paid["razorpay_payment_id"])
    assert order_count(db, users["priya"]) == 0                       # the checkout step alone creates nothing
    done = payments.verify_payment(db, users["priya"], oid, paid["razorpay_payment_id"], paid["razorpay_signature"])
    assert done["status"] == "ok" and done["grand_total"] == shown["grand_total"] and order_count(db, users["priya"]) == 2
    assert attempt(db, oid)["status"] == "paid" and attempt(db, oid)["razorpay_payment_id"] == paid["razorpay_payment_id"]
    again = payments.verify_payment(db, users["priya"], oid, paid["razorpay_payment_id"], paid["razorpay_signature"])
    assert again["status"] == "already_paid" and order_count(db, users["priya"]) == 2


def test_orders_paid_this_way_carry_their_payment_ids(db, users, started):
    _, res = started
    paid = checkout(db, users["priya"], res["razorpay_order_id"])
    payments.verify_payment(db, users["priya"], res["razorpay_order_id"], paid["razorpay_payment_id"], paid["razorpay_signature"])
    rows = db.execute("select payment_status, razorpay_order_id, razorpay_payment_id from public.orders where user_id = %s",
                      (users["priya"],)).fetchall()
    assert rows and all(r["payment_status"] == "paid" and r["razorpay_payment_id"].startswith("pay_TEST_")
                        and r["razorpay_order_id"] == res["razorpay_order_id"] for r in rows)


# ═══ failure ═════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("kwargs", [
    {"outcome": "failure", "method": "card", "card": OK_CARD},
    {"outcome": "failure", "method": "upi", "upi": OK_UPI},
    {"outcome": "success", "method": "card", "card": FAIL_CARD},       # a failing test instrument always fails
    {"outcome": "success", "method": "upi", "upi": FAIL_UPI},
])
def test_a_failed_payment_creates_no_order_and_the_cart_stays_confirmed(db, users, started, kwargs):
    shown, res = started
    r = checkout(db, users["priya"], res["razorpay_order_id"], **kwargs)
    assert r["status"] == "payment_failed" and "razorpay_signature" not in r and "razorpay_payment_id" not in r
    assert order_count(db, users["priya"]) == 0 and cart_status(db, shown["cart_id"]) == "confirmed"
    assert attempt(db, res["razorpay_order_id"])["status"] == "created"


def test_after_a_failure_the_same_attempt_can_be_paid(db, users, started):
    shown, res = started
    checkout(db, users["priya"], res["razorpay_order_id"], outcome="failure")
    again = payments.start_payment(db, users["priya"], shown["cart_id"])
    assert again["razorpay_order_id"] == res["razorpay_order_id"] and again["reused"] is True
    paid = checkout(db, users["priya"], res["razorpay_order_id"])
    done = payments.verify_payment(db, users["priya"], res["razorpay_order_id"], paid["razorpay_payment_id"], paid["razorpay_signature"])
    assert done["status"] == "ok" and order_count(db, users["priya"]) == 2


# ═══ only fixed test values ══════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("card", [REAL_LOOKING, "4242424242424242", "0000000000000000", "", "4111", "4111111111111112",
                                  "4111 1111 1111 1111 1", "abcd", None])
def test_any_card_that_is_not_a_listed_test_card_is_refused(db, users, started, card):
    _, res = started
    r = payments.simulate_payment(db, users["priya"], res["razorpay_order_id"], "success", "card", card, None)
    assert r["status"] == "invalid_input" and "razorpay_signature" not in r
    assert not any(part and part in str(r) for part in (card,) if isinstance(part, str) and len(part) > 3)   # never echoed
    assert attempt(db, res["razorpay_order_id"])["status"] == "created"


@pytest.mark.parametrize("upi", ["someone@okaxis", "success@razorpay.evil", "", "success", None])
def test_any_upi_id_that_is_not_a_listed_test_id_is_refused(db, users, started, upi):
    _, res = started
    assert payments.simulate_payment(db, users["priya"], res["razorpay_order_id"], "success", "upi", None, upi)["status"] == "invalid_input"


def test_method_and_instrument_must_agree(db, users, started):
    _, res = started
    oid = res["razorpay_order_id"]
    assert payments.simulate_payment(db, users["priya"], oid, "success", "card", OK_CARD, OK_UPI)["status"] == "invalid_input"
    assert payments.simulate_payment(db, users["priya"], oid, "success", "upi", OK_CARD, OK_UPI)["status"] == "invalid_input"
    assert payments.simulate_payment(db, users["priya"], oid, "success", "wallet", OK_CARD, None)["status"] == "invalid_input"
    assert payments.simulate_payment(db, users["priya"], oid, "maybe", "card", OK_CARD, None)["status"] == "invalid_input"


@pytest.mark.parametrize("card", ["4111111111111111", "4111-1111-1111-1111", " 4111 1111 1111 1111"[1:], "5555555555554444"])
def test_the_listed_test_cards_work_with_or_without_separators(db, users, started, card):
    _, res = started
    assert payments.simulate_payment(db, users["priya"], res["razorpay_order_id"], "success", "card", card, None)["status"] == "ok"


# ═══ who and when ════════════════════════════════════════════════════════════════════════════════════════
def test_another_users_order_looks_missing(db, users, started):
    _, res = started
    assert checkout(db, users["arjun"], res["razorpay_order_id"])["status"] == "not_found"
    assert checkout(db, users["priya"], "order_TESTdoesnotexist")["status"] == "not_found"


def test_a_paid_or_refunded_attempt_cannot_be_paid_again(db, users, started):
    _, res = started
    oid = res["razorpay_order_id"]
    paid = checkout(db, users["priya"], oid)
    payments.verify_payment(db, users["priya"], oid, paid["razorpay_payment_id"], paid["razorpay_signature"])
    assert checkout(db, users["priya"], oid)["status"] == "payment_conflict"


def test_paying_after_the_cart_changed_is_a_simulated_refund_not_an_order(db, users, started):
    shown, res = started
    oid = res["razorpay_order_id"]
    paid = checkout(db, users["priya"], oid)
    add_to_cart(db, users["priya"], *item(db, "Hi-Tech Bawarchi", "Chicken Dum Biryani", "madhapur"))     # re-opens the cart
    done = payments.verify_payment(db, users["priya"], oid, paid["razorpay_payment_id"], paid["razorpay_signature"])
    assert done["status"] == "needs_refund" and order_count(db, users["priya"]) == 0
    assert checkout(db, users["priya"], oid)["status"] == "payment_conflict"


# ═══ signatures in simulated mode ════════════════════════════════════════════════════════════════════════
def test_a_signature_from_another_key_is_rejected(db, users, started):
    _, res = started
    oid, pid = res["razorpay_order_id"], simulated.new_payment_id()
    forged = razorpay.sign(oid, pid, hashlib.sha256(b"someone-else").hexdigest())
    r = payments.verify_payment(db, users["priya"], oid, pid, forged)
    assert r["status"] == "bad_signature" and order_count(db, users["priya"]) == 0 and attempt(db, oid)["status"] == "created"


def test_a_signed_payment_id_that_is_not_a_test_id_is_rejected(db, users, started):
    _, res = started
    oid = res["razorpay_order_id"]
    for pid in ("pay_Real0001", "pay_TEST_short", "pay_TEST_" + "z" * 13):
        r = payments.verify_payment(db, users["priya"], oid, pid, simulated.sign(oid, pid))
        assert r["status"] in ("bad_signature", "invalid_input") and order_count(db, users["priya"]) == 0


def test_the_signature_is_the_same_hmac_as_razorpays():
    key = hashlib.sha256(b"dawat-sim-test").hexdigest()
    assert simulated.sign("order_TESTabc", "pay_TEST_abcdef123456") == razorpay.sign("order_TESTabc", "pay_TEST_abcdef123456", key)
    assert simulated.verify_signature("order_TESTabc", "pay_TEST_abcdef123456", simulated.sign("order_TESTabc", "pay_TEST_abcdef123456"))
    assert not simulated.verify_signature("order_TESTabc", "pay_TEST_abcdef123456", "0" * 64)
    assert not simulated.verify_signature(None, None, None)


# ═══ the switch ══════════════════════════════════════════════════════════════════════════════════════════
def test_razorpay_mode_has_no_simulated_checkout(db, users, started, monkeypatch):
    _, res = started
    monkeypatch.setattr(config, "PAYMENT_GATEWAY", "razorpay")
    assert checkout(db, users["priya"], res["razorpay_order_id"])["status"] == "payments_not_configured"


@pytest.mark.parametrize("value", ["", "paypal", "SIMULATED ", None])
def test_an_unknown_gateway_means_not_configured(db, users, two_restaurant_cart, monkeypatch, value):
    shown = confirm(db, users["priya"])
    monkeypatch.setattr(config, "PAYMENT_GATEWAY", value)
    assert payments.start_payment(db, users["priya"], shown["cart_id"])["status"] == "payments_not_configured"
    with pytest.raises(gateway.PaymentsNotConfigured):
        gateway.mode()


def test_razorpay_mode_still_needs_its_keys(db, users, two_restaurant_cart, monkeypatch):
    shown = confirm(db, users["priya"])
    monkeypatch.setattr(config, "PAYMENT_GATEWAY", "razorpay")
    assert payments.start_payment(db, users["priya"], shown["cart_id"])["status"] == "payments_not_configured"


# ═══ over HTTP ═══════════════════════════════════════════════════════════════════════════════════════════
def http_cart(db, token):
    item_id, branch_id = item(db, "Hi-Tech Bawarchi", "Chicken Dum Biryani", "madhapur")
    call("post", "/cart/items", token, json={"item_id": item_id, "branch_id": branch_id, "qty": 2})
    cart = call("get", "/cart", token).json()
    assert call("post", "/cart/confirm", token, json={"cart_id": cart["cart_id"], "quote_id": cart["quote_id"]}).status_code == 200
    return cart


def test_the_whole_flow_over_http_with_a_failure_first(db, as_user):
    t = as_user["priya"]
    cart = http_cart(db, t)
    s = call("post", "/payments/start", t, json={"cart_id": cart["cart_id"]})
    assert s.status_code == 200 and s.json()["gateway"] == "simulated"
    oid = s.json()["razorpay_order_id"]
    bad = call("post", "/payments/simulate", t, json={"razorpay_order_id": oid, "outcome": "failure", "method": "upi", "upi_id": OK_UPI})
    assert bad.status_code == 402 and bad.json()["status"] == "payment_failed"
    assert call("get", "/orders", t).json()["status"] == "empty" and call("get", "/cart", t).json().get("confirmed_total") == cart["grand_total"]
    good = call("post", "/payments/simulate", t, json={"razorpay_order_id": oid, "outcome": "success", "method": "card", "card_number": OK_CARD})
    assert good.status_code == 200
    v = call("post", "/payments/verify", t, json={k: good.json()[k] for k in ("razorpay_order_id", "razorpay_payment_id", "razorpay_signature")})
    assert v.status_code == 200 and v.json()["grand_total"] == cart["grand_total"] and len(v.json()["orders"]) == 1


def test_http_refuses_a_real_card_and_extra_fields(db, as_user):
    t = as_user["priya"]
    oid = call("post", "/payments/start", t, json={"cart_id": http_cart(db, t)["cart_id"]}).json()["razorpay_order_id"]
    base = {"razorpay_order_id": oid, "outcome": "success", "method": "card"}
    r = call("post", "/payments/simulate", t, json={**base, "card_number": REAL_LOOKING})
    assert r.status_code == 422 and REAL_LOOKING.replace(" ", "") not in r.text.replace(" ", "")
    for extra in ({"cvv": "123"}, {"expiry": "12/30"}, {"amount": 1}):
        assert call("post", "/payments/simulate", t, json={**base, "card_number": OK_CARD, **extra}).status_code == 422
    assert call("post", "/payments/simulate", t, json={**base, "card_number": 4111111111111111}).status_code == 422


def test_http_other_user_gets_404_and_no_token_gets_401(db, as_user):
    t = as_user["priya"]
    oid = call("post", "/payments/start", t, json={"cart_id": http_cart(db, t)["cart_id"]}).json()["razorpay_order_id"]
    body = {"razorpay_order_id": oid, "outcome": "success", "method": "card", "card_number": OK_CARD}
    assert call("post", "/payments/simulate", as_user["arjun"], json=body).status_code == 404
    assert call("post", "/payments/simulate", None, json=body).status_code == 401
