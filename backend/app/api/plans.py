"""Meal planner routes (Phase 5f, D-029).

POST /plans        public; signed-in users get plans priced from their own delivery address (the same point their
                   cart uses). The body is a MealRequest, validated strictly by the planner itself.
POST /cart/plan    signed-in; puts a chosen plan in the cart by plan_id (never a list of items or prices from the
                   client). The user still confirms the cart summary before anything is ordered. replace=true is
                   the user's own click on the website's "Replace cart" dialog, so the route passes source="website".
"""

from typing import Annotated, Any

from fastapi import APIRouter, Body as JsonBody
from pydantic import Field, StrictBool

from app.api.cart import Body
from app.api.deps import Conn, CurrentUser, MaybeUser, respond
from app.tools.planner import add_plan_to_cart, plan_meal

router = APIRouter(tags=["meal planner"])


class AddPlan(Body):
    request: dict[str, Any]
    plan_id: Annotated[str, Field(min_length=1, max_length=64)]
    replace: StrictBool = False


@router.post("/plans")
def make_plans(conn: Conn, user: MaybeUser, request: Annotated[dict[str, Any], JsonBody()]):
    return respond(plan_meal(conn, request, user.user_id if user else None))


@router.post("/cart/plan")
def add_plan(user: CurrentUser, conn: Conn, body: AddPlan):
    return respond(add_plan_to_cart(conn, user.user_id, body.request, body.plan_id, replace=body.replace,
                                    source="website"), write=True)
