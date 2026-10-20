"""Paying for a confirmed cart, test payments only (Phase 8, D-061; gateway switch D-062). Plain-JSON results.

The order of things (Saif, Session 21: payment is required for every order, from the website and from the chat):

  1. The user confirms the cart summary (confirm_cart, with the quote_id they were shown).
  2. start_payment(cart_id): the confirmed cart's quote must be unchanged. The SERVER creates a Razorpay order for the
     confirmed grand_total (the browser never sends an amount) and records a payment_attempts row: user, cart, quote,
     amount, Razorpay order id. The same quote gets the same attempt back (opening checkout twice is harmless).
  3. The browser opens Razorpay checkout and gets back (order_id, payment_id, signature).
  4. verify_payment(...): ONLY now do orders exist. In this order:
       a. the three values must look right (shape);
       b. the attempt is looked up by Razorpay order id AND the signed-in user (another user's is "not found");
       c. the HMAC signature must match. A bad signature changes nothing at all (no "failed" mark an attacker could use);
       d. a repeat of an already-paid attempt returns the same orders, once; a different payment id for it is refused;
       e. the cart must still be confirmed with the very quote that was paid. If it isn't (an item changed price, the
          user edited the cart while the checkout window was open) NO ORDER is created, the attempt is marked
          needs_refund, and the user is told plainly (Saif's decision 2: in test mode the refund is simulated);
       f. otherwise the orders are created paid, one per restaurant under one checkout_id, and the attempt is closed.
Every lookup is scoped to the user id from the verified token. Nothing here trusts a client value except the three
strings Razorpay returns, and those are checked cryptographically.
"""

import logging
import uuid

from psycopg import Connection

from app.payments import gateway, simulated
from app.tools.orders import NOT_FOUND, _checkout, confirmed_cart_gate, place_order

log = logging.getLogger("dawat.payments")

ATTEMPT_TTL_MINUTES = 30            # an unpaid attempt older than this is not reused (and the chat may re-open its cart)

UNAVAILABLE = {"status": "payment_unavailable",
               "message": "Payments are not available right now. Nothing was charged and nothing was ordered. "
                          "Please try again in a minute."}
NOT_CONFIGURED = {"status": "payments_not_configured",
                  "message": "Test payments are not set up on this server. Nothing was charged or ordered."}


def start_payment(conn: Connection, user_id: uuid.UUID, cart_id: str, *, create_order=None) -> dict:
    """Open (or reopen) the payment for the user's confirmed cart. `create_order` is replaceable for tests."""
    try:
        key = gateway.key_id()
    except gateway.PaymentsNotConfigured:
        return dict(NOT_CONFIGURED)
    answer, cart, current = confirmed_cart_gate(conn, user_id, cart_id)      # locks the cart row
    if answer is not None:
        return answer
    cid, quote, total = cart["cart_id"], cart["confirmed_quote"], current["grand_total"]
    live = conn.execute(f"""select attempt_id, razorpay_order_id, amount from public.payment_attempts
                            where cart_id = %s and user_id = %s and status = 'created' and quote_id = %s
                              and created_at > now() - interval '{ATTEMPT_TTL_MINUTES} minutes'
                            order by created_at desc limit 1""", (cid, user_id, quote)).fetchone()
    if live is not None and live["amount"] == total:
        return _start_answer(key, live["razorpay_order_id"], total, cid, quote, live["attempt_id"], reused=True)
    # Any older unpaid attempt of this cart is for a different quote or too old: it can no longer complete an order.
    conn.execute("update public.payment_attempts set status = 'expired' where cart_id = %s and status = 'created'", (cid,))
    attempt_id = uuid.uuid4()
    try:
        made = (create_order or gateway.create_order)(total, str(attempt_id))
    except gateway.PaymentsNotConfigured:
        return dict(NOT_CONFIGURED)
    except gateway.RazorpayError as e:
        log.warning("payment order creation failed: %s", e)
        return dict(UNAVAILABLE)
    conn.execute("""insert into public.payment_attempts (attempt_id, user_id, cart_id, quote_id, amount, razorpay_order_id)
                    values (%s, %s, %s, %s, %s, %s)""", (attempt_id, user_id, cid, quote, total, made["razorpay_order_id"]))
    return _start_answer(key, made["razorpay_order_id"], total, cid, quote, attempt_id, reused=False)


def _start_answer(key: str, razorpay_order_id: str, total: int, cart_id, quote: str, attempt_id, *, reused: bool) -> dict:
    return {"status": "ok", "key_id": key, "razorpay_order_id": razorpay_order_id, "amount": total * 100,
            "amount_rupees": total, "currency": gateway.CURRENCY, "cart_id": str(cart_id), "quote_id": quote,
            "attempt_id": str(attempt_id), "reused": reused, "name": "Dawat",
            "gateway": gateway.mode(),
            "description": "Demo order (test payment, no real money)",
            "message": f"Open checkout for ₹{total}. This is a test payment; no real money moves."}


def verify_payment(conn: Connection, user_id: uuid.UUID, razorpay_order_id, razorpay_payment_id, razorpay_signature) -> dict:
    """Check a finished checkout and, only then, create the orders. See the module docstring for the order of checks."""
    if not gateway.ids_look_valid(razorpay_order_id, razorpay_payment_id, razorpay_signature):
        return {"status": "invalid_input", "message": "The payment details are not in the expected form."}
    try:
        gateway.key_id()
    except gateway.PaymentsNotConfigured:
        return dict(NOT_CONFIGURED)
    a = conn.execute("""select attempt_id, cart_id, quote_id, amount, status, razorpay_payment_id, checkout_id
                        from public.payment_attempts where razorpay_order_id = %s and user_id = %s for update""",
                     (razorpay_order_id, user_id)).fetchone()
    if a is None:
        return {**NOT_FOUND, "message": "No such payment for this user."}
    if not gateway.verify_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
        return {"status": "bad_signature",
                "message": "The payment could not be verified, so nothing was ordered. If money was taken in the test "
                           "checkout, nothing is lost: try paying again."}
    if a["status"] == "paid":
        if a["razorpay_payment_id"] != razorpay_payment_id:
            return {"status": "payment_conflict",
                    "message": "This order was already paid with a different payment. Nothing new was ordered."}
        return {"status": "already_paid", **_checkout(conn, user_id, a["checkout_id"]), "payment_status": "paid",
                "message": "Already paid; these are the orders from that payment. Nothing new was ordered."}
    if a["status"] == "needs_refund":
        if a["razorpay_payment_id"] != razorpay_payment_id:
            return {"status": "payment_conflict", "message": "A different payment was already recorded for this order."}
        return _needs_refund(a["amount"])

    # 'created' or 'expired' (an expired attempt only means a newer one was opened or it is old): either may complete
    # the order, but only if the cart still holds the very quote and total it was opened for.
    answer, cart, current = _still_matches(conn, user_id, a)
    if answer is not None:
        # The signature is valid, so the payment happened. No order is created (the user never confirmed THIS total).
        conn.execute("""update public.payment_attempts set status = 'needs_refund', razorpay_payment_id = %s
                        where attempt_id = %s""", (razorpay_payment_id, a["attempt_id"]))
        return _needs_refund(a["amount"])
    placed = place_order(conn, user_id, str(a["cart_id"]),
                         payment={"order_id": razorpay_order_id, "payment_id": razorpay_payment_id})
    if placed["status"] != "ok":                  # the gate re-ran inside place_order; it can only differ if a race changed it
        conn.execute("""update public.payment_attempts set status = 'needs_refund', razorpay_payment_id = %s
                        where attempt_id = %s""", (razorpay_payment_id, a["attempt_id"]))
        return _needs_refund(a["amount"])
    conn.execute("""update public.payment_attempts set status = 'paid', razorpay_payment_id = %s, checkout_id = %s
                    where attempt_id = %s""", (razorpay_payment_id, placed["checkout_id"], a["attempt_id"]))
    return {**placed, "payment_status": "paid",
            "message": "Payment verified and the order is placed (test payment). Share the order numbers and totals exactly as given."}


def _still_matches(conn: Connection, user_id: uuid.UUID, a: dict):
    """(None, cart, view) when the cart is still confirmed with the quote and total that this attempt was for."""
    row = conn.execute("""select status, confirmed_quote, confirmed_total from public.carts
                          where cart_id = %s and user_id = %s for update""", (a["cart_id"], user_id)).fetchone()
    if row is None or row["status"] != "confirmed" or row["confirmed_quote"] != a["quote_id"] or row["confirmed_total"] != a["amount"]:
        return "moved_on", None, None
    answer, cart, current = confirmed_cart_gate(conn, user_id, str(a["cart_id"]))
    if answer is not None or current["grand_total"] != a["amount"] or current.get("quote_id") != a["quote_id"]:
        return "moved_on", None, None
    return None, cart, current


def _needs_refund(amount: int) -> dict:
    return {"status": "needs_refund", "amount": amount,
            "message": f"Your test payment of ₹{amount} went through, but your cart or its prices changed before it "
                       "finished, so no order was placed. In this demo the refund is simulated: nothing real was "
                       "charged. Please check your cart and order again."}


SIM_FAILED = {"status": "payment_failed",
              "message": "The test payment failed. Nothing was charged and no order was placed; your cart is still "
                         "confirmed, so you can try again."}


def simulate_payment(conn: Connection, user_id: uuid.UUID, razorpay_order_id, outcome, method, card_number=None,
                     upi_id=None) -> dict:
    """The simulated gateway's checkout step (D-062): the stand-in for the user paying in Razorpay's window.

    Only for the user's own open attempt, and only with a fixed test card or UPI id (anything else is refused and never
    kept). A failing outcome, or a failing test instrument, changes nothing: no order, the cart stays confirmed, and
    the same attempt can be paid again. A success returns exactly what Razorpay's checkout would: the order id, a
    pay_TEST_ payment id and the HMAC signature, to be sent to POST /payments/verify."""
    try:
        if gateway.mode() != "simulated":
            return {"status": "payments_not_configured", "message": "The simulated payment gateway is not switched on."}
    except gateway.PaymentsNotConfigured:
        return dict(NOT_CONFIGURED)
    if outcome not in ("success", "failure") or method not in ("card", "upi") or not gateway.ids_look_valid(
            razorpay_order_id, "pay_x", "0" * 64):
        return {"status": "invalid_input", "message": "The payment details are not in the expected form."}
    instrument = simulated.instrument_outcome(method, card_number, upi_id)
    if instrument is None:
        return {"status": "invalid_input",
                "message": "Only the test values are accepted: see the test card and UPI list. Never enter a real card."}
    a = conn.execute("select attempt_id, status from public.payment_attempts where razorpay_order_id = %s and user_id = %s",
                     (razorpay_order_id, user_id)).fetchone()
    if a is None:
        return {**NOT_FOUND, "message": "No such payment for this user."}
    if a["status"] in ("paid", "needs_refund"):
        return {"status": "payment_conflict", "message": "This payment is already finished."}
    if outcome == "failure" or instrument == "failure":
        return dict(SIM_FAILED)
    payment_id = simulated.new_payment_id()
    return {"status": "ok", "razorpay_order_id": razorpay_order_id, "razorpay_payment_id": payment_id,
            "razorpay_signature": simulated.sign(razorpay_order_id, payment_id),
            "message": "Test payment approved. Now send these three values to /payments/verify."}
