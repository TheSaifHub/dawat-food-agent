"""The local simulated payment gateway (D-062): what Razorpay's checkout and API do, with no account and no network.

It exists because Razorpay's test keys need identity onboarding Saif declined. It keeps the real flow honest:
  · an order id from "the gateway" (order_TEST…), created by the server for the server-computed amount;
  · a checkout step (POST /payments/simulate) that returns (order_id, payment_id, signature) on success;
  · the signature is the same HMAC-SHA256 over "<order_id>|<payment_id>", with a local key, and POST
    /payments/verify checks it exactly as it would a Razorpay one.
Payment ids look like pay_TEST_xxxxxxxxxxxx.

Safety rules, each tested:
  · ONLY fixed test values are accepted: a short list of test card numbers and two test UPI ids. Any other card number,
    including a real-looking one, is refused and never echoed, logged or stored. CVV and expiry are not accepted at all.
  · This gateway moves no money and proves nothing about a real payment: it must never front real money. That is out
    of scope for this project (CLAUDE.md), and the real path stays behind PAYMENT_GATEWAY=razorpay.
"""

import hmac
import re
import secrets
import uuid

from app import config
from app.payments import razorpay

KEY_ID = "sim_gateway"                      # a public label; there is no real key id
TEST_CARDS = {"4111111111111111": "success", "5555555555554444": "success", "4000000000000002": "failure"}
TEST_UPI = {"success@razorpay": "success", "failure@razorpay": "failure"}
SIM_PAYMENT_ID = re.compile(r"^pay_TEST_[A-Za-z0-9]{12}$")
_per_process_key = secrets.token_hex(32)


def _signing_key() -> str:
    return config.PAYMENT_SIM_SECRET or _per_process_key


def create_order(amount_rupees: int, receipt: str, **_) -> dict:
    if not isinstance(amount_rupees, int) or isinstance(amount_rupees, bool) or amount_rupees < 1:
        raise ValueError("amount must be a positive whole number of rupees")
    return {"razorpay_order_id": "order_TEST" + uuid.uuid4().hex[:16], "amount_paise": amount_rupees * 100,
            "currency": razorpay.CURRENCY}


def new_payment_id() -> str:
    return "pay_TEST_" + secrets.token_hex(6)


def sign(order_id: str, payment_id: str) -> str:
    return razorpay.sign(order_id, payment_id, _signing_key())


def verify_signature(order_id, payment_id, signature) -> bool:
    """True only for a well-formed trio, a TEST payment id, and a matching signature. Never raises for bad input."""
    if not razorpay.ids_look_valid(order_id, payment_id, signature) or not SIM_PAYMENT_ID.fullmatch(payment_id):
        return False
    return hmac.compare_digest(sign(order_id, payment_id).encode("ascii"), signature.encode("ascii"))


def normalise_card(raw) -> str:
    return re.sub(r"[ -]", "", raw) if isinstance(raw, str) else ""


def instrument_outcome(method, card_number, upi_id) -> str | None:
    """'success' / 'failure' for a fixed test instrument; None for anything else (refused). The value is never kept."""
    if method == "card" and upi_id is None:
        return TEST_CARDS.get(normalise_card(card_number))
    if method == "upi" and card_number is None and isinstance(upi_id, str):
        return TEST_UPI.get(upi_id.strip().lower())
    return None
