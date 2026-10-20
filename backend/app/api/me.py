"""GET /me: who am I? POST /me/name: confirm or change my name. GET /me/addresses: where can I get food delivered?
The user id (and the Google account name) come only from the verified token (app.api.deps.current_user)."""

from pydantic import BaseModel, ConfigDict
from fastapi import APIRouter

from app.api.deps import Conn, CurrentUser, respond
from app.tools.users import confirm_name, list_addresses

router = APIRouter(tags=["users"])


class MeResponse(BaseModel):
    user_id: str
    display_name: str
    is_demo: bool
    name_confirmed: bool
    account_name: str | None      # the name Google gave us (from the verified token), for "Keep it, or change it?"


class NameBody(BaseModel):
    """`name` omitted or null = keep the Google account name (taken from the token, not from here)."""
    model_config = ConfigDict(extra="forbid")
    name: str | None = None


@router.get("/me", response_model=MeResponse)
def me(user: CurrentUser) -> dict:
    return {"user_id": str(user.user_id), "display_name": user.display_name, "is_demo": user.is_demo,
            "name_confirmed": user.name_confirmed, "account_name": user.account_name}


@router.post("/me/name")
def set_my_name(body: NameBody, user: CurrentUser, conn: Conn):
    return respond(confirm_name(conn, user.user_id, user.account_name, body.name))


@router.get("/me/addresses")
def my_addresses(user: CurrentUser, conn: Conn):
    return respond(list_addresses(conn, user.user_id))
