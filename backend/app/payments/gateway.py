"""Which payment gateway is in use (D-062): the local simulated one (default) or Razorpay test mode (D-061).

One switch, config.PAYMENT_GATEWAY. The payment tools call only this module, so the routes, the payment_attempts
ledger and the order-creation rules are identical for both. An unknown value means "not configured".
"""

from app import config
from app.payments import razorpay, simulated
from app.payments.razorpay import PaymentsNotConfigured, RazorpayError  # noqa: F401 (re-exported)

CURRENCY = razorpay.CURRENCY


def mode() -> str:
    if config.PAYMENT_GATEWAY not in ("simulated", "razorpay"):
        raise PaymentsNotConfigured("PAYMENT_GATEWAY must be 'simulated' or 'razorpay'.")
    return config.PAYMENT_GATEWAY


def key_id() -> str:
    return simulated.KEY_ID if mode() == "simulated" else razorpay.key_id()


def create_order(amount_rupees: int, receipt: str) -> dict:
    return simulated.create_order(amount_rupees, receipt) if mode() == "simulated" else razorpay.create_order(amount_rupees, receipt)


def ids_look_valid(order_id, payment_id, signature) -> bool:
    return razorpay.ids_look_valid(order_id, payment_id, signature)


def verify_signature(order_id, payment_id, signature) -> bool:
    if mode() == "simulated":
        return simulated.verify_signature(order_id, payment_id, signature)
    return razorpay.verify_signature(order_id, payment_id, signature)
