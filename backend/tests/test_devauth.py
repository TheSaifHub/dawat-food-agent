"""The local dev login (D-059): it works locally, and it can never be on in a deployed app.

Lock 1: only the launcher sets the flag; the flag in the env file refuses.
Lock 2: flag + a remote database, or + a hosting platform's marker, or a flag value other than 1 → refuses, and
        app.main refuses to import (checked in a real subprocess, so the server never starts).
Lock 3: flag off → no /dev routes, the Supabase verifier, and a dev token is a 401. Flag on → Supabase-shaped and
        forged tokens are refused too.
Plus the routes themselves (a guest account, a seed user) and dev_server.py's environment for each mode.
"""

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth, config, devauth
from app.auth import AuthError, JwksKeys, TokenVerifier
from app.db import get_conn
from app.main import app as main_app
from tests.conftest import ISSUER, KID

BACKEND = Path(__file__).resolve().parents[1]
LOCAL_DSN = "host=127.0.0.1 port=5432 dbname=dawat_dev user=postgres"
REMOTE_DSN = "host=db.made-up-project.supabase.co port=5432 dbname=postgres user=postgres"
MARKERS = ("RENDER", "VERCEL")


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """No flag, no hosting markers, a local database, an env file without the flag, a throwaway key file."""
    for name in (devauth.FLAG, *MARKERS):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "DATABASE_URL", LOCAL_DSN)
    env_file = tmp_path / "backend.env"
    env_file.write_text("SUPABASE_URL=https://made-up.supabase.co\n", encoding="utf-8")
    monkeypatch.setattr(devauth, "ENV_FILE", env_file)
    monkeypatch.setattr(devauth, "KEY_FILE", tmp_path / "devkey" / "es256.pem")
    monkeypatch.setattr(devauth, "_key", None)
    monkeypatch.setattr(auth, "_verifier", None)
    return env_file


@pytest.fixture
def dev_on(clean_env, monkeypatch):
    monkeypatch.setenv(devauth.FLAG, "1")
    assert devauth.enabled() is True
    return clean_env


# ── locks 1 and 2: when it is on, off, or refused ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value", [None, "", "  ", "0"])
def test_off_values_are_off_even_on_a_platform_with_a_remote_db(clean_env, monkeypatch, value):
    if value is not None:
        monkeypatch.setenv(devauth.FLAG, value)
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(config, "DATABASE_URL", REMOTE_DSN)
    assert devauth.enabled() is False


def test_on_only_with_flag_1_local_db_no_platform(dev_on):
    assert devauth.enabled() is True


@pytest.mark.parametrize("value", ["true", "yes", "on", "2", "1x", "01"])
def test_any_other_flag_value_refuses(clean_env, monkeypatch, value):
    monkeypatch.setenv(devauth.FLAG, value)
    with pytest.raises(devauth.DevLoginRefused):
        devauth.enabled()


@pytest.mark.parametrize("marker", MARKERS)
@pytest.mark.parametrize("marker_value", ["true", "1", ""])
def test_a_hosting_platform_refuses(dev_on, monkeypatch, marker, marker_value):
    monkeypatch.setenv(marker, marker_value)          # present at all, even empty, is enough
    with pytest.raises(devauth.DevLoginRefused, match="hosting platform"):
        devauth.enabled()


@pytest.mark.parametrize("dsn", [REMOTE_DSN, None, "",
                                 "host=127.0.0.1,db.made-up.supabase.co dbname=x user=u",
                                 "postgresql://u@db.made-up.supabase.co:5432/postgres"])
def test_a_database_not_on_this_machine_refuses(dev_on, monkeypatch, dsn):
    monkeypatch.setattr(config, "DATABASE_URL", dsn)
    with pytest.raises(devauth.DevLoginRefused, match="isn't on this machine"):
        devauth.enabled()


@pytest.mark.parametrize("line", ["DAWAT_DEV_LOGIN=1", "DAWAT_DEV_LOGIN=0", "DAWAT_DEV_LOGIN="])
def test_the_flag_in_the_env_file_refuses(dev_on, line):
    dev_on.write_text(f"SUPABASE_URL=https://made-up.supabase.co\n{line}\n", encoding="utf-8")
    with pytest.raises(devauth.DevLoginRefused, match="env file"):
        devauth.enabled()


def test_the_real_env_file_has_no_flag():
    """Lock 1 on this machine: if Saif's backend env file ever gets the flag, this fails (no value is read out)."""
    from dotenv import dotenv_values
    if devauth.ENV_FILE.exists():
        assert devauth.FLAG not in dotenv_values(devauth.ENV_FILE)


def _import_main(env_changes: dict) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in (devauth.FLAG, *MARKERS, "DAWAT_TEST_RUN")}
    env.update(env_changes)
    code = ("import app.main as m; "
            "print('DEV_ROUTES', sorted(p for p in m.app.openapi()['paths'] if p.startswith('/dev')))")
    return subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env, capture_output=True, text=True,
                          timeout=120)


@pytest.mark.parametrize("changes", [
    {"RENDER": "true"},
    {"VERCEL": "1"},
    {"DATABASE_URL": REMOTE_DSN},
    {"DAWAT_DEV_LOGIN": "true"},
], ids=["render", "vercel", "remote-db", "bad-value"])
def test_the_server_refuses_to_start(changes):
    """The real app.main import, in a fresh process, as uvicorn does it: it raises, so no server starts."""
    r = _import_main({"DAWAT_DEV_LOGIN": "1", "DATABASE_URL": LOCAL_DSN, **changes})
    assert r.returncode != 0
    assert "DevLoginRefused" in r.stderr and "Refusing to start" in r.stderr
    assert "DEV_ROUTES" not in r.stdout


def test_the_server_starts_with_dev_routes_only_when_enabled():
    on = _import_main({"DAWAT_DEV_LOGIN": "1", "DATABASE_URL": LOCAL_DSN})
    assert on.returncode == 0, on.stderr
    assert "'/dev/auth/google'" in on.stdout and "'/dev/auth/seed-user'" in on.stdout
    off = _import_main({"DATABASE_URL": LOCAL_DSN})
    assert off.returncode == 0, off.stderr
    assert "DEV_ROUTES []" in off.stdout


# ── lock 3: off means it doesn't exist ─────────────────────────────────────────────────────────────────────────────

def test_this_test_process_has_no_dev_routes():
    assert not [p for p in main_app.openapi()["paths"] if p.startswith("/dev")]
    client = TestClient(main_app)
    for method, path in (("post", "/dev/auth/google"), ("post", "/dev/auth/seed-user"), ("get", "/dev/auth/users")):
        assert getattr(client, method)(path).status_code == 404


def _dev_token(monkeypatch, user_id=None) -> str:
    monkeypatch.setenv(devauth.FLAG, "1")
    token = devauth.issue_token(user_id or uuid.uuid4())["access_token"]
    monkeypatch.delenv(devauth.FLAG)
    return token


def test_off_get_verifier_is_supabase_and_refuses_a_dev_token(clean_env, monkeypatch, signing_key):
    token = _dev_token(monkeypatch)
    monkeypatch.setattr(config, "SUPABASE_URL", "https://test-project.supabase.co")
    assert auth.get_verifier().issuer == ISSUER
    # Supabase's keys (the test key stands in for its JWKS): the dev token's key id is unknown there
    jwk = jwt.algorithms.ECAlgorithm.to_jwk(signing_key.public_key(), as_dict=True)
    jwks = {"keys": [{**jwk, "kid": KID, "alg": "ES256", "use": "sig"}]}
    with pytest.raises(AuthError):
        TokenVerifier(ISSUER, JwksKeys("unused", fetch=lambda url: jwks).get).verify(token)
    # and even if its key were somehow trusted, the issuer is not Supabase's
    with pytest.raises(AuthError):
        TokenVerifier(ISSUER, lambda kid: devauth._public_key()).verify(token)


def test_issue_and_verifier_refuse_when_off(clean_env):
    with pytest.raises(devauth.DevLoginRefused):
        devauth.issue_token(uuid.uuid4())
    with pytest.raises(devauth.DevLoginRefused):
        devauth.verifier()


# ── on: the same checks as Supabase's ──────────────────────────────────────────────────────────────────────────────

def test_on_get_verifier_is_the_dev_one_and_accepts_its_tokens(dev_on):
    uid = uuid.uuid4()
    t = devauth.issue_token(uid)
    v = auth.get_verifier()
    assert v.issuer == devauth.ISSUER
    user = v.verify(t["access_token"])
    assert user.user_id == uid and user.display_name is None
    named = v.verify(devauth.issue_token(uid, display_name="Priya")["access_token"])
    assert named.display_name == "Priya"
    assert t["expires_at"] - time.time() <= devauth.TOKEN_LIFETIME_S


def test_on_refuses_supabase_shaped_forged_and_altered_tokens(dev_on, make_token, attacker_key):
    v = auth.get_verifier()
    now = int(time.time())
    base = {"iss": devauth.ISSUER, "aud": "authenticated", "role": "authenticated", "sub": str(uuid.uuid4()),
            "iat": now, "exp": now + 600}
    key, kid = devauth._private_key(), devauth.key_id()

    def dev_signed(**changes):
        return jwt.encode({**base, **changes}, key, algorithm="ES256", headers={"kid": kid})
    bad = {
        "supabase-shaped (test key, Supabase issuer)": make_token(),
        "attacker key with the dev key id": jwt.encode(base, attacker_key, algorithm="ES256", headers={"kid": kid}),
        "dev key, Supabase issuer": dev_signed(iss=ISSUER),
        "dev key, expired": dev_signed(iat=now - 7200, exp=now - 3600),
        "dev key, anon role": dev_signed(role="anon"),
        "dev key, wrong audience": dev_signed(aud="public"),
        "HS256 with the dev key id": jwt.encode(base, "secret", algorithm="HS256", headers={"kid": kid}),
    }
    accepted = []
    for name, token in bad.items():
        try:
            v.verify(token)
            accepted.append(name)
        except AuthError:
            pass
    assert accepted == []


def test_the_key_persists_across_restarts(dev_on, monkeypatch):
    kid = devauth.key_id()
    assert devauth.KEY_FILE.exists()
    monkeypatch.setattr(devauth, "_key", None)                # a restart reloads the same key
    assert devauth.key_id() == kid


# ── the routes, on the local test database (rolled back) ───────────────────────────────────────────────────────────

@pytest.fixture
def dev_client(dev_on, db):
    from app.api.devauth import router
    app = FastAPI()
    app.include_router(router)

    def test_db():
        yield db
    app.dependency_overrides[get_conn] = test_db
    return TestClient(app)


def _me(db, token):
    def test_db():
        yield db
    main_app.dependency_overrides[get_conn] = test_db
    return TestClient(main_app).get("/me", headers={"Authorization": f"Bearer {token}"})


def test_fake_google_user_is_a_local_account_the_backend_accepts(dev_client, db):
    r = dev_client.post("/dev/auth/google")
    assert r.status_code == 200
    body = r.json()
    row = db.execute("select email, is_anonymous, raw_user_meta_data from auth.users where id = %s", (body["user_id"],)).fetchone()
    assert row["email"] == "local.tester@dawat.local" and row["is_anonymous"] is False
    assert row["raw_user_meta_data"]["full_name"] == "Local Tester"
    me = _me(db, body["access_token"])
    assert me.status_code == 200 and me.json()["user_id"] == body["user_id"]
    assert me.json()["display_name"] == "Local Tester" and me.json()["account_name"] == "Local Tester"
    assert me.json()["name_confirmed"] is False
    assert dev_client.post("/dev/auth/google").json()["user_id"] == body["user_id"]       # the same user each time
    fresh = dev_client.post("/dev/auth/google", json={"new_user": True}).json()
    assert fresh["user_id"] != body["user_id"]                                            # unless a fresh one is asked for
    assert dev_client.post("/dev/auth/google", json={"new_user": True, "email": "x@y.z"}).status_code == 422


def test_seed_user_signs_in_only_seed_users(dev_client, db, demo_users, anon_user):
    listed = dev_client.get("/dev/auth/users").json()["users"]
    assert {u["user_id"] for u in listed} == {str(u) for u in demo_users}
    r = dev_client.post("/dev/auth/seed-user", json={"user_id": str(demo_users[0])})
    assert r.status_code == 200
    me = _me(db, r.json()["access_token"])
    assert me.status_code == 200 and me.json()["user_id"] == str(demo_users[0]) and me.json()["is_demo"] is True
    db.execute("insert into public.users (user_id, display_name) values (%s, 'Guest')", (anon_user,))
    for uid in (anon_user, uuid.uuid4()):                     # a real but non-seed account, and no account
        assert dev_client.post("/dev/auth/seed-user", json={"user_id": str(uid)}).status_code == 404
    assert dev_client.post("/dev/auth/seed-user",
                           json={"user_id": str(demo_users[0]), "name": "x"}).status_code == 422


def test_routes_mounted_by_mistake_answer_404_when_off(dev_client, monkeypatch):
    monkeypatch.delenv(devauth.FLAG)
    assert dev_client.post("/dev/auth/google").status_code == 404
    assert dev_client.get("/dev/auth/users").status_code == 404


# ── dev_server.py: what each mode passes to the server ─────────────────────────────────────────────────────────────

def test_dev_server_modes(monkeypatch):
    import dev_server
    from psycopg.conninfo import conninfo_to_dict
    from app.localdb import is_local
    monkeypatch.setenv(devauth.FLAG, "1")                     # even if the calling shell had it set…
    assert devauth.FLAG not in dev_server._server_env(supabase=True)       # …--supabase never passes it on
    local = dev_server._server_env(supabase=False)
    assert local[devauth.FLAG] == "1"
    dev_db_ok = is_local(local["DATABASE_URL"]) and conninfo_to_dict(local["DATABASE_URL"])["dbname"] == "dawat_dev"
    assert dev_db_ok                                          # a bare bool: a failure never prints the password
