"""Google-only sign-in and the "Confirm your name" step (D-064). Identity code, so strict.

Strict: the name shown comes from the VERIFIED token (never the body); a changed name is validated on the server;
a user can only ever change their own name; the flag is set only by the confirm step; nothing but the website flow
reads the flag; the demo route and anonymous sign-ins are gone.
"""

import re
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth import get_verifier
from app.db import get_conn
from app.main import app
from app.tools.users import NAME_MAX, confirm_name, ensure_user, validate_name

client = TestClient(app)
APP = Path(__file__).resolve().parents[1] / "app"


@pytest.fixture
def api(db, verifier):
    app.dependency_overrides[get_verifier] = lambda: verifier

    def test_db():
        yield db
    app.dependency_overrides[get_conn] = test_db


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def google_user(db) -> uuid.UUID:
    uid = uuid.uuid4()
    db.execute("insert into auth.users (id, email) values (%s, %s)", (uid, f"{uid.hex[:8]}@example.com"))
    return uid


def me(token):
    return client.get("/me", headers=bearer(token)).json()


def stored(db, uid):
    return db.execute("select display_name, name_confirmed from public.users where user_id = %s", (uid,)).fetchone()


# ── validation (pure) ──────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    ("Saif", "Saif"), ("  Saif   Ibrahim  ", "Saif Ibrahim"), ("A", "A"), ("a" * NAME_MAX, "a" * NAME_MAX),
    ("AT&T Fan", "AT&T Fan"), ("D'Souza-Rao", "D'Souza-Rao"), ("తెలుగు పేరు", "తెలుగు పేరు"),
    ("क्ष‍त्रिय", "क्ष‍त्रिय"), ("ک‌تاب", "ک‌تاب"),               # joiners Indian/Urdu names need
    ("a b", "a b"),                                                             # a no-break space is only a space
])
def test_good_names_are_kept_and_tidied(raw, expected):
    assert validate_name(raw) == (expected, None)


@pytest.mark.parametrize("raw", [
    "", "   ", "\n", "a" * (NAME_MAX + 1), "x" * 500,
    "<b>Bob</b>", "Bob<", ">Bob", "<script>alert(1)</script>", "Bob &lt;b&gt;", "Bob &#60;", "Bob &amp;",
    "line\nbreak", "tab\there", "nul\x00", "bell\x07", "esc\x1b[31m", "del\x7f", "next\x85line", "para sep",
    "line sep", "zero​width", "bidi‮evil", "bidi⁦x", "bom﻿x", "soft­hyphen",
    "wordjoin⁠x", "privateuse", "unassigned\U000e0080tag",
    None, 5, 1.5, True, ["Bob"], {"a": 1},
])
def test_bad_names_are_refused(raw):
    name, why = validate_name(raw)
    assert name is None and why


def test_the_length_limit_counts_characters_after_trimming():
    assert validate_name(" " + "a" * NAME_MAX + " ")[0] == "a" * NAME_MAX
    assert validate_name("a" * NAME_MAX + "b")[0] is None
    assert validate_name("ఆ" * NAME_MAX)[0] == "ఆ" * NAME_MAX                         # characters, not bytes
    assert validate_name("a    b")[0] == "a b"


# ── the profile and the flag ───────────────────────────────────────────────────────────────────────────────────────

def test_a_new_profile_takes_the_token_name_and_is_not_confirmed(api, db, google_user, make_token):
    body = me(make_token(google_user, user_metadata={"full_name": "Asha Rao"}))
    assert body["display_name"] == "Asha Rao" and body["account_name"] == "Asha Rao" and body["name_confirmed"] is False
    assert stored(db, google_user)["name_confirmed"] is False


def test_a_token_without_a_name_gets_the_default_and_no_account_name(api, db, google_user, make_token):
    body = me(make_token(google_user))
    assert body["display_name"] == "Dawat user" and body["account_name"] is None and body["name_confirmed"] is False


def test_the_seed_users_count_as_confirmed(api, db, demo_users, make_token):
    for uid in demo_users:
        assert me(make_token(uid))["name_confirmed"] is True


def test_keep_stores_the_name_from_the_token_and_sets_the_flag(api, db, google_user, make_token):
    token = make_token(google_user, user_metadata={"full_name": "Asha Rao"})
    me(token)
    r = client.post("/me/name", json={}, headers=bearer(token))
    assert r.status_code == 200 and r.json() == {"status": "ok", "display_name": "Asha Rao", "name_confirmed": True}
    assert stored(db, google_user) == {"display_name": "Asha Rao", "name_confirmed": True}
    assert me(token)["name_confirmed"] is True


def test_keep_with_null_is_the_same_as_keep(api, db, google_user, make_token):
    token = make_token(google_user, user_metadata={"full_name": "Asha Rao"})
    assert client.post("/me/name", json={"name": None}, headers=bearer(token)).status_code == 200
    assert stored(db, google_user)["display_name"] == "Asha Rao"


def test_a_changed_name_is_validated_trimmed_and_stored(api, db, google_user, make_token):
    token = make_token(google_user, user_metadata={"full_name": "Asha Rao"})
    r = client.post("/me/name", json={"name": "   Asha   R.  "}, headers=bearer(token))
    assert r.status_code == 200 and r.json()["display_name"] == "Asha R."
    assert stored(db, google_user) == {"display_name": "Asha R.", "name_confirmed": True}
    assert me(token)["account_name"] == "Asha Rao"                    # Google's name is still the token's


@pytest.mark.parametrize("bad", ["", "   ", "x" * 61, "<img src=x>", "Bob\nSmith", "a​b", "&lt;"])
def test_a_bad_name_is_422_and_changes_nothing(api, db, google_user, make_token, bad):
    token = make_token(google_user, user_metadata={"full_name": "Asha Rao"})
    me(token)
    r = client.post("/me/name", json={"name": bad}, headers=bearer(token))
    assert r.status_code == 422 and r.json()["status"] == "invalid_input"
    assert stored(db, google_user) == {"display_name": "Asha Rao", "name_confirmed": False}


@pytest.mark.parametrize("body", [{"name": 5}, {"name": ["x"]}, {"name": {"a": 1}}, {"name": True}])
def test_a_name_that_is_not_text_is_422(api, db, google_user, make_token, body):
    token = make_token(google_user, user_metadata={"full_name": "Asha Rao"})
    me(token)
    assert client.post("/me/name", json=body, headers=bearer(token)).status_code == 422
    assert stored(db, google_user)["name_confirmed"] is False


def test_keeping_when_the_google_name_is_unusable_asks_for_a_name(api, db, google_user, make_token):
    """A token name with markup (or none at all) is never stored as it is: the user has to type one."""
    for meta in ({}, {"full_name": "<b>x</b>"}):
        token = make_token(google_user, user_metadata=meta)
        me(token)
        r = client.post("/me/name", json={}, headers=bearer(token))
        assert r.status_code == 422 and r.json()["status"] == "invalid_input"
        assert stored(db, google_user)["name_confirmed"] is False


# ── the name comes only from the token; a user can only change their own ──────────────────────────────────────────

@pytest.mark.parametrize("body", [{"user_id": "x"}, {"account_name": "Hacker"}, {"name": "Okay", "user_id": "x"},
                                  {"name": "Okay", "name_confirmed": False}, {"display_name": "Hacker"}])
def test_extra_fields_are_refused(api, db, google_user, make_token, body):
    token = make_token(google_user, user_metadata={"full_name": "Asha Rao"})
    me(token)
    assert client.post("/me/name", json=body, headers=bearer(token)).status_code == 422
    assert stored(db, google_user) == {"display_name": "Asha Rao", "name_confirmed": False}


def test_nothing_but_the_token_decides_whose_name_changes(api, db, google_user, demo_users, make_token):
    victim = demo_users[0]
    before = stored(db, victim)
    token = make_token(google_user, user_metadata={"full_name": "Asha Rao"})
    me(token)
    for url in (f"/me/name?user_id={victim}", f"/me/name?sub={victim}", f"/me/{victim}/name"):
        client.post(url, json={"name": "Hacked"}, headers={**bearer(token), "X-User-Id": str(victim)})
    assert stored(db, victim) == before


def test_keep_uses_the_callers_token_name_not_anyone_elses(api, db, google_user, make_token):
    a = make_token(google_user, user_metadata={"full_name": "Asha Rao"})
    other = uuid.uuid4()
    db.execute("insert into auth.users (id, email) values (%s, 'other@example.com')", (other,))
    b = make_token(other, user_metadata={"full_name": "Other Person"})
    me(a)
    me(b)
    client.post("/me/name", json={}, headers=bearer(a))
    assert stored(db, google_user) == {"display_name": "Asha Rao", "name_confirmed": True}
    assert stored(db, other) == {"display_name": "Other Person", "name_confirmed": False}      # untouched by A


def test_a_token_cannot_rename_an_existing_profile_by_itself(api, db, google_user, make_token):
    me(make_token(google_user, user_metadata={"full_name": "First Name"}))
    assert me(make_token(google_user, user_metadata={"full_name": "Second Name"}))["display_name"] == "First Name"


def test_the_confirm_step_needs_a_token(verifier):
    app.dependency_overrides[get_verifier] = lambda: verifier

    def no_db():
        raise AssertionError("a rejected request must not open a database connection")
        yield  # noqa
    app.dependency_overrides[get_conn] = no_db
    assert client.post("/me/name", json={}).status_code == 401
    assert client.post("/me/name", json={}, headers=bearer("junk")).status_code == 401


def test_a_deleted_account_cannot_confirm(api, db, make_token):
    assert client.post("/me/name", json={}, headers=bearer(make_token(uuid.uuid4()))).status_code == 401


def test_confirm_name_on_a_missing_profile_is_unknown_user(db):
    assert confirm_name(db, uuid.uuid4(), "Asha", None)["status"] == "unknown_user"


def test_the_tool_function_touches_only_the_given_row(db, google_user, demo_users):
    ensure_user(db, google_user, "Asha Rao")
    q = "select user_id, display_name, name_confirmed from public.users order by user_id"
    before = db.execute(q).fetchall()
    assert confirm_name(db, google_user, "Asha Rao", "New Name")["status"] == "ok"
    after = db.execute(q).fetchall()
    assert [a["user_id"] for a, b in zip(after, before) if a != b] == [google_user]


# ── the flag is the website's alone ────────────────────────────────────────────────────────────────────────────────

def test_only_the_profile_code_knows_the_flag():
    readers = {str(p.relative_to(APP)) for p in APP.rglob("*.py") if "name_confirmed" in p.read_text(encoding="utf-8")}
    assert readers == {str(Path("tools/users.py")), str(Path("api/deps.py")), str(Path("api/me.py"))}, readers


def test_a_user_who_has_not_confirmed_is_still_a_full_working_user(db, demo_users):
    from app.api.deps import current_user
    from app.auth import AuthUser
    uid = demo_users[0]
    db.execute("update public.users set name_confirmed = false where user_id = %s", (uid,))
    profile = current_user(AuthUser(user_id=uid, display_name=None), db)
    assert profile.name_confirmed is False and profile.user_id == uid


def test_the_migration_is_additive_and_defaults_to_false(db):
    col = db.execute("""select column_default, is_nullable, data_type from information_schema.columns
                        where table_schema = 'public' and table_name = 'users' and column_name = 'name_confirmed'""").fetchone()
    assert col == {"column_default": "false", "is_nullable": "NO", "data_type": "boolean"}


# ── Google is the only sign-in: the demo route and anonymous tokens are gone ───────────────────────────────────────

def test_the_demo_route_does_not_exist():
    assert "/demo/start" not in app.openapi()["paths"]
    assert client.post("/demo/start", json={"persona": "priya"}).status_code in (404, 405)
    assert not (APP / "api" / "demo.py").exists()
    assert not re.search(r"demo_router|api\.demo|/demo/start", (APP / "main.py").read_text(encoding="utf-8"))


@pytest.mark.parametrize("flag", [True, "true", 1])
def test_an_anonymous_token_is_401_on_every_kind_of_route(api, db, google_user, make_token, flag):
    token = make_token(google_user, is_anonymous=flag)
    for method, url in (("get", "/me"), ("post", "/me/name"), ("get", "/cart"), ("post", "/chat")):
        r = getattr(client, method)(url, headers=bearer(token), **({"json": {"message": "hi"}} if method == "post" else {}))
        assert r.status_code == 401, (url, r.status_code)
    assert db.execute("select count(*) as n from public.users where user_id = %s", (google_user,)).fetchone()["n"] == 0


def test_no_dev_route_exists_in_this_process():
    assert not [p for p in app.openapi()["paths"] if p.startswith("/dev")]
