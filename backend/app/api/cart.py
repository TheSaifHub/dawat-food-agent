"""Cart and ordering routes (D-027): the website's half of the one shared cart (the chat uses the same tools).

Signed-in only. Request bodies carry ids and quantities, never a price or a user id: extra fields are refused (422),
so a client can't even try to send its own price. Every response is the tool's JSON, including the whole cart.
Ordering is the same gate as in chat: GET /cart → the user clicks "confirm" on that summary → POST /cart/confirm
with its quote_id → POST /orders.
"""

from typing import Annotated

from fastapi import APIRouter, Path, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import Conn, CurrentUser, respond
from app.pricing import MAX_QTY
from app.tools import cart as cart_tools
from app.tools.history import MAX_LIMIT as HISTORY_MAX, DEFAULT_LIMIT as HISTORY_DEFAULT
from app.tools.history import get_user_history
from app.tools.orders import confirm_cart, payment_required, track_order

router = APIRouter(tags=["cart and orders"])
Id = Annotated[str, Field(min_length=1, max_length=120)]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AddItem(Body):
    item_id: Id
    branch_id: Id
    qty: Annotated[int, Field(ge=1, le=MAX_QTY, strict=True)] = 1


class Delivery(Body):
    area: Annotated[str | None, Field(max_length=80)] = None
    address_id: Annotated[str | None, Field(max_length=40)] = None


class Confirm(Body):
    cart_id: Id
    quote_id: Id


class PlaceOrder(Body):
    cart_id: Id


@router.get("/cart")
def view_cart(user: CurrentUser, conn: Conn):
    return respond(cart_tools.view_cart(conn, user.user_id))


@router.post("/cart/items")
def add_item(user: CurrentUser, conn: Conn, body: AddItem):
    return respond(cart_tools.add_to_cart(conn, user.user_id, body.item_id, body.branch_id, body.qty))


@router.delete("/cart/items/{item_id}")
def remove_item(user: CurrentUser, conn: Conn, item_id: Annotated[str, Path(max_length=120)],
                branch_id: Annotated[str | None, Query(max_length=40)] = None,
                qty: Annotated[int | None, Query(ge=1, le=MAX_QTY)] = None):
    """Without qty, the item is removed entirely; branch_id is needed only if it's in the cart from two branches."""
    return respond(cart_tools.remove_from_cart(conn, user.user_id, item_id, branch_id=branch_id, qty=qty))


@router.put("/cart/delivery")
def set_delivery(user: CurrentUser, conn: Conn, body: Delivery):
    return respond(cart_tools.set_delivery(conn, user.user_id, area=body.area, address_id=body.address_id), write=True)


@router.post("/cart/confirm")
def confirm(user: CurrentUser, conn: Conn, body: Confirm):
    """Only after the user confirmed the summary that carried this quote_id."""
    return respond(confirm_cart(conn, user.user_id, body.cart_id, body.quote_id, source="website"))


@router.post("/orders")
def place(user: CurrentUser, conn: Conn, body: PlaceOrder):
    """Orders exist only after a verified test payment (D-061): this runs the same checks as before and answers 409
    payment_required (nothing created). Pay with POST /payments/start then POST /payments/verify."""
    return respond(payment_required(conn, user.user_id, body.cart_id))


@router.get("/orders")
def history(user: CurrentUser, conn: Conn, limit: Annotated[int, Query(ge=1, le=HISTORY_MAX)] = HISTORY_DEFAULT):
    return respond(get_user_history(conn, user.user_id, limit=limit))


@router.get("/orders/{order_id}")
def track(user: CurrentUser, conn: Conn, order_id: Annotated[str, Path(max_length=40)]):
    return respond(track_order(conn, user.user_id, order_id))
