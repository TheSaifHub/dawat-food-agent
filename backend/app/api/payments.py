"""Payment routes (Phase 8, D-061; simulated gateway D-062): test payments only. Signed-in only; the user id comes only from the token.

POST /payments/start   {cart_id}  → the Razorpay order for the confirmed cart's server-computed total (+ the public test
                                    key id the browser needs). No amount is ever accepted from the client.
POST /payments/verify  {razorpay_order_id, razorpay_payment_id, razorpay_signature}  (exactly the three values
                                    Razorpay's checkout hands back) → verifies the signature, then creates the orders.
POST /payments/simulate {razorpay_order_id, outcome: success|failure, method: card|upi, card_number | upi_id}
                                    → the SIMULATED gateway's checkout step (only when PAYMENT_GATEWAY=simulated): fixed
                                    test card/UPI values only; success returns the three values for /verify.
Bodies are strict (extra fields refused). The flow and every refusal are described in app/tools/payments.py.
"""

from typing import Annotated

from fastapi import APIRouter
from pydantic import Field, StrictStr

from app.api.cart import Body, Id
from app.api.deps import Conn, CurrentUser, respond
from app.tools import payments

router = APIRouter(prefix="/payments", tags=["payments"])
Text = Annotated[StrictStr, Field(min_length=1, max_length=120)]


class StartPayment(Body):
    cart_id: Id


class VerifyPayment(Body):
    razorpay_order_id: Text
    razorpay_payment_id: Text
    razorpay_signature: Text


@router.post("/start")
def start(user: CurrentUser, conn: Conn, body: StartPayment):
    return respond(payments.start_payment(conn, user.user_id, body.cart_id), write=True)


class SimulatePayment(Body):
    razorpay_order_id: Text
    outcome: Text
    method: Text
    card_number: Annotated[StrictStr | None, Field(max_length=25)] = None
    upi_id: Annotated[StrictStr | None, Field(max_length=60)] = None


@router.post("/simulate")
def simulate(user: CurrentUser, conn: Conn, body: SimulatePayment):
    return respond(payments.simulate_payment(conn, user.user_id, body.razorpay_order_id, body.outcome, body.method,
                                             body.card_number, body.upi_id), write=True)


@router.post("/verify")
def verify(user: CurrentUser, conn: Conn, body: VerifyPayment):
    return respond(payments.verify_payment(conn, user.user_id, body.razorpay_order_id, body.razorpay_payment_id,
                                           body.razorpay_signature), write=True)
