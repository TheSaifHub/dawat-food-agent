"""Shared pieces of every website route (D-027): the database connection, the signed-in user, and how a tool's JSON
becomes an HTTP response.

The routes are thin: they validate the request's shape, take the user id ONLY from the verified token, call the
same tools layer Dawat AI uses, and return the tool's JSON unchanged. No route computes a price or a total.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg import Connection

from app.auth import AuthUser, optional_user, require_user
from app.db import get_conn
from app.tools.users import ensure_user

log = logging.getLogger("dawat.api")

# scope="function": the connection is committed (or rolled back) BEFORE the response is sent. With FastAPI's default
# ("request") the commit runs after sending, so a commit that failed would already have been reported as success,
# e.g. an order the website showed as placed that never was. tests/test_api_routes.py proves a failed commit is a 500.
Conn = Annotated[Connection, Depends(get_conn, scope="function")]


@dataclass(frozen=True)
class Profile:
    user_id: uuid.UUID
    display_name: str
    is_demo: bool
    name_confirmed: bool = False       # the website's "Confirm your name" step is done (no backend rule reads it)
    account_name: str | None = None     # the name in the verified token (Google's), for that step


def current_user(user: Annotated[AuthUser, Depends(require_user)], conn: Conn) -> Profile:
    """The signed-in user's profile, created on their first request. The token is checked first (require_user is
    declared before the connection), so a rejected request never opens a database connection."""
    profile = ensure_user(conn, user.user_id, user.display_name)
    if profile is None:
        raise HTTPException(401, "This account no longer exists. Please sign in again.", headers={"WWW-Authenticate": "Bearer"})
    return Profile(user_id=user.user_id, display_name=profile["display_name"], is_demo=profile["is_demo"],
                   name_confirmed=profile["name_confirmed"], account_name=user.display_name)


CurrentUser = Annotated[Profile, Depends(current_user)]


def maybe_user(user: Annotated[AuthUser | None, Depends(optional_user)], conn: Conn) -> Profile | None:
    """The signed-in user's profile if a token was sent (and is valid), else None (anonymous browsing)."""
    return None if user is None else current_user(user, conn)


MaybeUser = Annotated[Profile | None, Depends(maybe_user)]

# Area answers are a normal reply to a search ("which Madhapur?") but mean a write did NOT happen. The planner's
# needs_info ("how many people?") is the same kind of answer.
AREA_ANSWERS = {"needs_area", "confirm_area", "unknown_area", "outside_coverage"}
NOT_DONE_ON_WRITE = AREA_ANSWERS | {"needs_info"}
STATUS_CODES = {
    # done, or an answer the page shows as it is
    "ok": 200, "empty": 200, "already_placed": 200, "needs_delivery_area": 200, "not_saved": 200,
    "dish_query": 200, "no_match": 200, "no_dish_match": 200, "no_match_with_filters": 200, "none_near_area": 200,
    "confirm_dish": 200, "area_conflict": 200, **{s: 200 for s in AREA_ANSWERS},
    "needs_info": 200, "over_budget": 200, "no_valid_plan": 200,
    # the request itself is wrong
    "invalid_input": 422, "not_on_this_menu": 422, "needs_branch": 422,
    # no such thing for this user (another user's cart or order looks exactly like a missing one)
    "not_found": 404, "unknown_item": 404, "unknown_branch": 404, "unknown_address": 404, "not_in_cart": 404,
    "unknown_user": 401,
    "not_requested": 403,
    # the planner refused its own output (a bug, logged): an honest "try again", no plan, no detail
    "planner_error": 503,
    # can't be done in the current state: the body says why and carries the fresh cart to show
    "item_unavailable": 409, "branch_unavailable": 409, "too_far": 409, "qty_limit": 409, "cannot_confirm": 409,
    "stale_quote": 409, "not_confirmed": 409, "no_clear_yes": 409, "quote_changed": 409, "plan_changed": 409, "cart_not_empty": 409,
    "confirm_preference": 409,          # a chat request only offers the change (D-045); the website uses "settings"
    # payments (Phase 8, D-061): an order exists only after a verified test payment
    "payment_required": 409, "payment_conflict": 409, "needs_refund": 409, "already_paid": 200,
    "bad_signature": 422, "payment_failed": 402, "payments_not_configured": 503, "payment_unavailable": 503,
    # demo accounts (D-048): already set up is fine; the other persona or a real account is refused
    "already_started": 200, "persona_locked": 409, "not_anonymous": 403,
}


def respond(result: dict, write: bool = False) -> JSONResponse:
    """The tool's JSON, unchanged, with a status code from its `status`. Returned (not raised) so that a 409 which
    changed something (quote_changed re-opens the cart) is still committed."""
    status = result.get("status")
    code = 422 if write and status in NOT_DONE_ON_WRITE else STATUS_CODES.get(status)
    if code is None:                                  # a bug: never guess a meaning, never leak the body
        log.error("tool returned an unmapped status %r", status)
        return JSONResponse({"detail": "Something went wrong on our side. Please try again."}, status_code=500)
    return JSONResponse(jsonable_encoder(result), status_code=code)
