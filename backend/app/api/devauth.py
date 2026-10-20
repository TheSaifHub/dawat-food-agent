"""The local dev login's routes (D-059), mounted ONLY when app.devauth.enabled() (see app/main.py).

    GET  /dev/auth/users        the seed users (is_demo: the ones chat_cli and the evals use) to sign in as
    POST /dev/auth/google       the fake Google user ("Continue with Google" in local mode): a local-only name and
                                email, the same user each time ({"new_user": true} makes a fresh one)
    POST /dev/auth/seed-user    {user_id} of a seed user → a token for that user

These play the part of Supabase Auth: they create the account and hand out the token. Every other route still takes
the user id only from a verified token. Each handler re-checks enabled() as well, so a router mounted by mistake
answers 404.
"""

import json
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from app import devauth
from app.api.deps import Conn

router = APIRouter(prefix="/dev/auth", tags=["dev"])


def _require_enabled() -> None:
    if not devauth.enabled():
        raise HTTPException(404, "Not Found")


class SeedUserBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: uuid.UUID


@router.get("/users")
def seed_users(conn: Conn):
    _require_enabled()
    rows = conn.execute("select user_id, display_name from public.users where is_demo order by display_name").fetchall()
    return {"users": [{"user_id": str(r["user_id"]), "display_name": r["display_name"]} for r in rows]}


# The fake Google user (D-064): what "Continue with Google" signs in as in local dev mode. A local-only name and email;
# it exists only in the local auth.users, created by this route, which exists only when the dev login is enabled.
FAKE_GOOGLE_NAME = "Local Tester"
FAKE_GOOGLE_EMAIL = "local.tester@dawat.local"
_FAKE_NS = uuid.UUID("5f1c3f0e-6b0a-4d63-9f6e-0d0a7a1d2b11")


class FakeGoogleBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_user: bool = False          # true: a brand-new fake user (to test the first-time "Confirm your name" again)


@router.post("/google")
def fake_google(conn: Conn, body: FakeGoogleBody | None = None):
    _require_enabled()
    fresh = bool(body and body.new_user)
    user_id = uuid.uuid4() if fresh else uuid.uuid5(_FAKE_NS, FAKE_GOOGLE_EMAIL)
    email = f"local.tester.{user_id.hex[:8]}@dawat.local" if fresh else FAKE_GOOGLE_EMAIL
    conn.execute("""insert into auth.users (id, email, raw_user_meta_data) values (%s, %s, %s)
                    on conflict (id) do nothing""",
                 (user_id, email, json.dumps({"dev_login": True, "full_name": FAKE_GOOGLE_NAME, "provider": "google"})))
    return devauth.issue_token(user_id, display_name=FAKE_GOOGLE_NAME, email=email)


@router.post("/seed-user")
def seed_user(body: SeedUserBody, conn: Conn):
    _require_enabled()
    row = conn.execute("select u.display_name from public.users u join auth.users a on a.id = u.user_id "
                       "where u.user_id = %s and u.is_demo", (body.user_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "No such seed user.")
    return devauth.issue_token(body.user_id, display_name=row["display_name"])
