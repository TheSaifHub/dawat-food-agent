"""User profiles (Phase 4). Preferences: app/tools/preferences.py; order history: app/tools/history.py.

Every function takes `user_id` from the verified token (app.auth), never from the LLM or a request body.
Results are plain JSON-ready dicts.
"""

import re
import unicodedata
import uuid

from psycopg import Connection

DEFAULT_DISPLAY_NAME = "Dawat user"
NAME_MAX = 60
_ZERO_WIDTH_OK = {"‌", "‍"}        # joiners that Telugu, Hindi and Urdu names need to be spelled correctly
_ENTITY = re.compile(r"&#?\w+;")


def validate_name(raw: object) -> tuple[str | None, str | None]:
    """(name, None) when `raw` is an acceptable display name, else (None, why).

    Trimmed (inner runs of spaces become one space), 1 to 60 characters, no control or invisible formatting
    characters (newlines, tabs, bidi overrides, zero-width spaces; the two joiners Indian scripts need are allowed),
    and no HTML: `<`, `>` and character references like `&lt;` are refused. A name is shown as text everywhere, but
    refusing markup here means no other place ever has to wonder."""
    if not isinstance(raw, str):
        return None, "Please enter a name."
    for ch in raw:
        cat = unicodedata.category(ch)
        if ch in _ZERO_WIDTH_OK or cat == "Zs":     # other spaces are only whitespace: normalised below
            continue
        if cat[0] == "C" or cat in ("Zl", "Zp"):
            return None, "That name has characters Dawat can't show. Please use letters, numbers and spaces."
    name = " ".join(raw.split())
    if not name:
        return None, "Please enter a name."
    if len(name) > NAME_MAX:
        return None, f"Please keep your name to {NAME_MAX} characters or fewer."
    if "<" in name or ">" in name or _ENTITY.search(name):
        return None, "A name can't contain < or > or HTML."
    return name, None


def ensure_user(conn: Connection, user_id: uuid.UUID, display_name: str | None = None) -> dict | None:
    """Return the user's profile row, creating it on their first request after sign-in.

    Supabase Auth creates the auth.users row; public.users (our profile table) is created here, lazily, with the
    name from the VERIFIED token (Google's account name). An existing row is never changed here, so a token can't
    rename a user: only confirm_name() does that.
    Returns None if the account no longer exists: a deleted user's token stays valid until it expires.
    """
    conn.execute("""insert into public.users (user_id, display_name)
                    select id, %s from auth.users where id = %s
                    on conflict (user_id) do nothing""",
                 ((display_name or DEFAULT_DISPLAY_NAME)[:NAME_MAX], user_id))
    row = conn.execute("select user_id, display_name, is_demo, name_confirmed from public.users where user_id = %s",
                       (user_id,)).fetchone()
    if row is None:
        return None
    return {"user_id": str(row["user_id"]), "display_name": row["display_name"], "is_demo": row["is_demo"],
            "name_confirmed": row["name_confirmed"]}


def confirm_name(conn: Connection, user_id: uuid.UUID, account_name: str | None, name: object = None) -> dict:
    """The "Confirm your name" step. `user_id` and `account_name` come from the verified token, never from the body.

    `name` None means "keep it": the name stored is the token's own account name. A string is the user's chosen
    name, validated by validate_name. Only this user's row is touched (where user_id = the token's). Confirming
    again later is allowed and simply renames."""
    chosen, why = validate_name(account_name if name is None else name)
    if chosen is None:
        return {"status": "invalid_input", "message": why}
    row = conn.execute("""update public.users set display_name = %s, name_confirmed = true
                          where user_id = %s returning display_name, name_confirmed""", (chosen, user_id)).fetchone()
    if row is None:
        return {"status": "unknown_user", "message": "This account no longer exists."}
    return {"status": "ok", "display_name": row["display_name"], "name_confirmed": row["name_confirmed"]}


def list_addresses(conn: Connection, user_id: uuid.UUID) -> dict:
    """The user's saved delivery addresses, default first. Only ever this user's (user_id from the token)."""
    rows = conn.execute("""select a.address_id, a.label, a.line1, a.area_id, ar.name as area, a.is_default
                           from public.addresses a join public.areas ar using (area_id)
                           where a.user_id = %s order by a.is_default desc, a.created_at, a.address_id""",
                        (user_id,)).fetchall()
    return {"status": "ok" if rows else "empty",
            "addresses": [{**dict(r), "address_id": str(r["address_id"])} for r in rows]}
