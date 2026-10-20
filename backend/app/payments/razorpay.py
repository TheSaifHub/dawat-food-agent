"""Razorpay TEST mode: create an order for a server-computed amount, and verify a payment signature (Phase 8, D-061).

Two jobs, both small on purpose:
  · create_order(amount_rupees, receipt): one HTTPS call to Razorpay (standard library only, 15 s timeout, no retry).
    The amount is the confirmed cart total computed by the server; nothing from the browser reaches it.
  · verify_signature(order_id, payment_id, signature): HMAC-SHA256 over "<order_id>|<payment_id>" with the key
    secret, compared in constant time. This is what proves the browser's payment really happened for OUR order.

Safety rules, each tested:
  · TEST MODE ONLY: a key id that doesn't start with rzp_test_ is refused (a live key can never be used by mistake).
  · Both keys blank → PaymentsNotConfigured (the routes answer 503); nothing else in the app depends on them.
  · The ids and the signature are checked for shape BEFORE they are compared or hashed. A "|" in an id would let one
    signed pair be read as another ("a|b"+"c" vs "a"+"b|c"), so ids may not contain it; a non-ASCII signature would
    crash a constant-time compare, so it is refused first.
  · The secret is never logged, returned, or put in an error message.
"""

import base64
import hashlib
import hmac
import json
import logging
import re
import urllib.error
import urllib.request
from typing import Callable

from app import config

log = logging.getLogger("dawat.payments")

API_ORDERS = "https://api.razorpay.com/v1/orders"
TEST_KEY_PREFIX = "rzp_test_"
TIMEOUT_S = 15
CURRENCY = "INR"

ORDER_ID = re.compile(r"^order_[A-Za-z0-9]{1,40}$")
PAYMENT_ID = re.compile(r"^pay_(?:TEST_)?[A-Za-z0-9]{1,40}$")      # pay_TEST_… = the simulated gateway (D-062)
SIGNATURE = re.compile(r"^[0-9a-f]{64}$")


class PaymentsNotConfigured(RuntimeError):
    """Keys missing, or not test keys. The routes answer 503 and say payments aren't available."""


class RazorpayError(RuntimeError):
    """Razorpay didn't give a usable answer (network, timeout, an error status, an unexpected body)."""


def key_id() -> str:
    """The public test key id (the browser needs it to open checkout). Raises PaymentsNotConfigured."""
    kid, secret = config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET
    if not kid or not secret:
        raise PaymentsNotConfigured("Razorpay test keys are not set.")
    if not kid.startswith(TEST_KEY_PREFIX):
        raise PaymentsNotConfigured("Only Razorpay TEST keys (rzp_test_…) are allowed in this project.")
    return kid


def _secret() -> str:
    key_id()                                   # the same checks
    return config.RAZORPAY_KEY_SECRET


def ids_look_valid(order_id, payment_id, signature) -> bool:
    return (isinstance(order_id, str) and ORDER_ID.fullmatch(order_id) is not None
            and isinstance(payment_id, str) and PAYMENT_ID.fullmatch(payment_id) is not None
            and isinstance(signature, str) and SIGNATURE.fullmatch(signature) is not None)


def sign(order_id: str, payment_id: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), f"{order_id}|{payment_id}".encode("utf-8"), hashlib.sha256).hexdigest()


def verify_signature(order_id, payment_id, signature) -> bool:
    """True only for a well-formed trio whose signature matches. Never raises for bad input."""
    if not ids_look_valid(order_id, payment_id, signature):
        return False
    return hmac.compare_digest(sign(order_id, payment_id, _secret()).encode("ascii"), signature.encode("ascii"))


def _post(url: str, body: dict, kid: str, secret: str) -> dict:
    token = base64.b64encode(f"{kid}:{secret}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Basic {token}"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RazorpayError(f"Razorpay answered HTTP {e.code}") from None      # the body may echo request data
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise RazorpayError(f"Razorpay could not be reached ({type(e).__name__})") from None


def create_order(amount_rupees: int, receipt: str, *, post: Callable | None = None) -> dict:
    """A Razorpay order for exactly this many rupees. `post` is replaceable so tests never touch the network."""
    if not isinstance(amount_rupees, int) or isinstance(amount_rupees, bool) or amount_rupees < 1:
        raise ValueError("amount must be a positive whole number of rupees")
    kid, secret = key_id(), _secret()
    paise = amount_rupees * 100
    answer = (post or _post)(API_ORDERS, {"amount": paise, "currency": CURRENCY, "receipt": receipt[:40]}, kid, secret)
    if not (isinstance(answer, dict) and isinstance(answer.get("id"), str) and ORDER_ID.fullmatch(answer["id"])
            and answer.get("amount") == paise and answer.get("currency") == CURRENCY):
        log.error("unexpected Razorpay order answer (shape or amount differs)")
        raise RazorpayError("Razorpay gave an unexpected answer")
    return {"razorpay_order_id": answer["id"], "amount_paise": paise, "currency": CURRENCY}
