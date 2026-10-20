"""Shared test fixtures (D-022).

- Tokens: signed with a throwaway ES256 key generated per test run, so auth tests need no network and
  no real account. A second "attacker" key is used to forge tokens.
- Database (`db` marker): a real connection to the LOCAL test database (TEST_DATABASE_URL, never Supabase: D-052)
  inside ONE transaction that is always rolled back. The fixture also checks that the user-owned tables have
  exactly the same row counts afterwards. Skipped automatically when TEST_DATABASE_URL is not set.
"""

import os
import time
import uuid

import jwt
import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from psycopg.rows import dict_row

# D-052, before anything imports app.config: the whole run (fixtures AND the app's own pool) uses the local test
# database. TEST_DATABASE_URL pointing elsewhere stops the run; unset means DATABASE_URL is blanked (load_dotenv
# never overrides a variable that is already set, even to ""), so database tests skip instead of reaching Supabase.
from app.localdb import UnsafeTestDatabase, is_local, test_dsn

try:
    _TEST_DSN = test_dsn()
except UnsafeTestDatabase as _e:
    pytest.exit(str(_e), returncode=2)
os.environ["DATABASE_URL"] = _TEST_DSN or ""
os.environ["DAWAT_TEST_RUN"] = "1"
# D-053: the reference copy checks its version stamp on every use in tests, so a menu change made inside a test's
# rolled-back transaction is seen by that test, and its undoing by the next one.
os.environ["REFERENCE_CHECK_S"] = "0"

from app import config  # noqa: E402  (must come after the environment is set)
from app.auth import TokenVerifier, AuthError  # noqa: E402
from app.db import CONNECT_KWARGS  # noqa: E402

ISSUER = "https://test-project.supabase.co/auth/v1"
KID = "test-key-1"
DROP = "<drop this claim>"   # pass as a claim value to leave that claim out (a string, so it compares equal
                             # even when a test module imports this file a second time as tests.conftest)
USER_TABLES = ("users", "user_preferences", "addresses", "carts", "cart_items", "orders", "order_items",
               "order_status_events", "conversations", "messages", "agent_traces")


@pytest.fixture(scope="session")
def signing_key():
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(scope="session")
def attacker_key():
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(scope="session")
def make_token(signing_key):
    def make(user_id: uuid.UUID | str | None = None, key=None, kid=KID, alg="ES256", **claims) -> str:
        now = int(time.time())
        payload = {"iss": ISSUER, "aud": "authenticated", "role": "authenticated",
                   "sub": str(user_id or uuid.uuid4()), "iat": now, "exp": now + 3600, **claims}
        payload = {k: v for k, v in payload.items() if not (isinstance(v, str) and v == DROP)}
        headers = {"kid": kid} if kid is not None else {}
        return jwt.encode(payload, key or signing_key, algorithm=alg, headers=headers)
    return make


@pytest.fixture(scope="session")
def verifier(signing_key):
    public = signing_key.public_key()

    def key_for_kid(kid: str):
        if kid != KID:
            raise AuthError("unknown signing key")
        return public
    return TokenVerifier(ISSUER, key_for_kid)


@pytest.fixture(autouse=True)
def _no_real_intent_model(monkeypatch):
    """The LLM intent check (D-043) never reaches a real model in tests: by default it reports itself unavailable,
    so behaviour is exactly the rules'. Tests of the check replace this with their own fake."""
    from app.agent import intent
    monkeypatch.setattr(intent, "classify", lambda question, message: {
        "used": False, "intent": None, "evidence": None, "change": None, "fallback_reason": "disabled in tests"})
    yield


@pytest.fixture(autouse=True)
def _razorpay_gateway_by_default(monkeypatch):
    """The payment tests written for Razorpay (D-061) keep running against that path; the simulated gateway (D-062,
    the app's default) is tested in test_sim_payments.py, which switches it on explicitly."""
    monkeypatch.setattr(config, "PAYMENT_GATEWAY", "razorpay")
    yield


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _counts(conn) -> dict:
    """Row counts of every user-owned table, in ONE round trip (the database is in Mumbai; 22 queries per test
    made the suite 4× slower)."""
    sql = "select " + ", ".join(f"(select count(*) from public.{t}) as {t}" for t in USER_TABLES)
    return dict(conn.execute(sql).fetchone())


@pytest.fixture(scope="session")
def db_conn():
    if not config.DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set; database tests skipped (they never use Supabase, D-052)")
    if not is_local(config.DATABASE_URL):                     # can't happen after the block above; checked anyway
        pytest.exit("The test database isn't local. Refused (D-052).", returncode=2)
    with psycopg.connect(config.DATABASE_URL, autocommit=True, **CONNECT_KWARGS) as conn:
        yield conn


@pytest.fixture
def db(db_conn):
    """A connection inside a transaction that is ALWAYS rolled back, plus a leftovers check."""
    before = _counts(db_conn)
    with db_conn.transaction(force_rollback=True):
        yield db_conn
    after = _counts(db_conn)
    assert after == before, f"a test left rows behind: {before} → {after}"


@pytest.fixture
def demo_users(db) -> list[uuid.UUID]:
    """The fictional demo users seeded by load_db.py (D-021): at least two, in a fixed order."""
    ids = [r["user_id"] for r in db.execute("select user_id from public.users where is_demo order by display_name")]
    if len(ids) < 2:
        pytest.skip("needs the seeded demo users (data_pipeline/load_db.py)")
    return ids


@pytest.fixture
def anon_user(db) -> uuid.UUID:
    """A fresh anonymous sign-in, as Supabase creates for "Try as Priya" (D-048): an auth.users row only, no profile."""
    uid = uuid.uuid4()
    db.execute("insert into auth.users (id, is_anonymous) values (%s, true)", (uid,))
    return uid


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "db" in item.fixturenames or "demo_users" in item.fixturenames:
            item.add_marker(pytest.mark.db)


@pytest.fixture(scope="session")
def supabase_url():
    if not config.SUPABASE_URL:
        pytest.skip("SUPABASE_URL not set; live test skipped")
    return config.SUPABASE_URL
