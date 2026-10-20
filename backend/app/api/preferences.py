"""Saved preferences on the website's settings screen (D-027): view, set, forget.

Signed-in only, and always the token's own user (there is no user id in any path or body). A change made here is
explicit by nature (the user pressed save), so it is stored with source "settings"; Dawat AI's chat writes go
through the same tool with the user's own words instead.
"""

from typing import Annotated

from fastapi import APIRouter, Path
from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr

from app.api.deps import Conn, CurrentUser, respond
from app.tools.preferences import delete_preference, get_preferences, save_preference

router = APIRouter(prefix="/me/preferences", tags=["preferences"])
Key = Annotated[str, Path(max_length=20)]


class PreferenceValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: StrictStr | StrictInt


@router.get("")
def view(user: CurrentUser, conn: Conn):
    return respond(get_preferences(conn, user.user_id))


@router.put("/{key}")
def save(user: CurrentUser, conn: Conn, key: Key, body: PreferenceValue):
    return respond(save_preference(conn, user.user_id, key, body.value, "settings"), write=True)


@router.delete("/{key}")
def forget(user: CurrentUser, conn: Conn, key: Key):
    """key is one preference (diet, max_spice, default_area, language), or "all"."""
    return respond(delete_preference(conn, user.user_id, key, "settings"))
