"""GET /me and the sign-in dependency (D-022).

Without a database: missing, malformed and forged tokens get 401 with a generic message, and never open a
database connection. With the database (rolled back): a valid token returns ITS user, whatever user id the
caller puts in the URL or headers, and an existing profile is never renamed by a token.
"""

import uuid

from fastapi.testclient import TestClient

from app.auth import AuthUnavailable, TokenVerifier, get_verifier
from app.db import get_conn
from app.main import app
from tests.conftest import ISSUER

client = TestClient(app)
GENERIC_401 = "Your session is invalid or has expired. Please sign in again."


def use(verifier, conn=None):
    app.dependency_overrides[get_verifier] = lambda: verifier
    if conn is None:
        def no_db():
            raise AssertionError("a rejected request must not open a database connection")
            yield  # noqa: unreachable; makes this a generator dependency like get_conn
        app.dependency_overrides[get_conn] = no_db
    else:
        def test_db():
            yield conn
        app.dependency_overrides[get_conn] = test_db


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_no_token_is_401_with_bearer_challenge(verifier):
    use(verifier)
    r = client.get("/me")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_wrong_scheme_is_401(verifier, make_token):
    use(verifier)
    assert client.get("/me", headers={"Authorization": f"Basic {make_token()}"}).status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer "}).status_code == 401


def test_forged_token_is_401_and_the_reason_is_not_revealed(verifier, make_token, attacker_key):
    use(verifier)
    r = client.get("/me", headers=bearer(make_token(key=attacker_key)))
    assert r.status_code == 401
    assert r.json() == {"detail": GENERIC_401}


def test_key_server_down_is_503_not_401(make_token):
    def down(kid):
        raise AuthUnavailable("could not load signing keys: URLError")
    use(TokenVerifier(ISSUER, down))
    r = client.get("/me", headers=bearer(make_token()))
    assert r.status_code == 503
    assert "URLError" not in r.text


def test_valid_token_returns_that_user(db, demo_users, verifier, make_token):
    a = demo_users[0]
    use(verifier, db)
    r = client.get("/me", headers=bearer(make_token(a)))
    assert r.status_code == 200
    assert r.json()["user_id"] == str(a)
    assert r.json()["is_demo"] is True


def test_user_id_in_url_or_headers_is_ignored(db, demo_users, verifier, make_token):
    a, b = demo_users[:2]
    use(verifier, db)
    r = client.get(f"/me?user_id={b}", headers={**bearer(make_token(a)), "X-User-Id": str(b), "X-Supabase-User": str(b)})
    assert r.status_code == 200
    assert r.json()["user_id"] == str(a)


def test_token_cannot_rename_an_existing_user(db, demo_users, verifier, make_token):
    a = demo_users[0]
    before = db.execute("select display_name from public.users where user_id = %s", (a,)).fetchone()["display_name"]
    use(verifier, db)
    r = client.get("/me", headers=bearer(make_token(a, user_metadata={"display_name": "Hacker"})))
    assert r.json()["display_name"] == before != "Hacker"


def test_token_for_a_deleted_account_is_401_and_creates_nothing(db, verifier, make_token):
    """A deleted user's token stays validly signed until it expires. It must get a clean 401, not a crash,
    and must not create a profile row (the db fixture also checks no rows were left behind)."""
    ghost = uuid.uuid4()
    use(verifier, db)
    r = client.get("/me", headers=bearer(make_token(ghost)))
    assert r.status_code == 401
    assert db.execute("select count(*) as n from public.users where user_id = %s", (ghost,)).fetchone()["n"] == 0


def test_me_has_no_anonymous_or_demo_fields_any_more(db, demo_users, verifier, make_token):
    use(verifier, db)
    body = client.get("/me", headers=bearer(make_token(demo_users[0]))).json()
    assert set(body) == {"user_id", "display_name", "is_demo", "name_confirmed", "account_name"}


def test_addresses_are_only_ever_your_own(db, demo_users, verifier, make_token):
    a, b = demo_users[:2]
    db.execute("""insert into public.addresses (user_id, label, line1, area_id, lat, lon)
                  select %s, 'Secret', 'Somewhere private (fictional)', area_id, lat, lon from public.areas
                  where area_id = 'charminar'""", (b,))
    use(verifier, db)
    mine = client.get("/me/addresses", headers=bearer(make_token(a))).json()["addresses"]
    theirs = client.get("/me/addresses", headers=bearer(make_token(b))).json()["addresses"]
    assert mine and all(x["label"] != "Secret" for x in mine)
    assert any(x["label"] == "Secret" for x in theirs)
    assert {x["address_id"] for x in mine}.isdisjoint({x["address_id"] for x in theirs})
    assert mine[0]["is_default"] and "area" in mine[0]
    r = client.get(f"/me/addresses?user_id={b}", headers={**bearer(make_token(a)), "X-User-Id": str(b)})
    assert r.json()["addresses"] == mine
