"""D-052: tests, evals and rehearsals only ever reach a database on this machine. No database needed: these check the
guard itself (app/localdb.py) and the second layer in app/db.py, with made-up connection strings (no passwords:
only the host matters)."""

import os

import pytest

from app import config, db, localdb
from app.localdb import UnsafeTestDatabase, is_local

REMOTE = [
    "postgresql://postgres.abcd@aws-0-ap-south-1.pooler.supabase.com:5432/postgres",
    "postgresql://postgres@db.abcdefgh.supabase.co:5432/postgres",
    "postgresql://u@192.168.1.65:5432/dawat_test",                         # another machine on the LAN
    "postgresql://u@localhost.evil.com:5432/dawat_test",
    "host=127.0.0.1,db.abcdefgh.supabase.co dbname=dawat_test user=u",     # one local host isn't enough
    "postgresql://u@127.0.0.1:5432/dawat_test?hostaddr=10.0.0.5",
]
LOCAL = [
    "postgresql://postgres@127.0.0.1:5432/dawat_test",
    "postgresql://postgres@localhost/dawat_test",
    "postgresql://postgres@[::1]:5432/dawat_test",
    "host=localhost dbname=dawat_test user=postgres",
    "dbname=dawat_test user=postgres",                                     # no host: libpq's local default
]


@pytest.mark.parametrize("dsn", REMOTE)
def test_remote_databases_are_not_local(dsn):
    assert not is_local(dsn)


@pytest.mark.parametrize("dsn", LOCAL)
def test_this_machine_is_local(dsn):
    assert is_local(dsn)


@pytest.mark.parametrize("dsn", [None, "", "   ", "not a connection string ==="])
def test_nothing_or_garbage_is_not_local(dsn):
    assert not is_local(dsn)


@pytest.mark.parametrize("dsn", REMOTE)
def test_a_remote_test_database_is_refused(monkeypatch, dsn):
    monkeypatch.setenv("TEST_DATABASE_URL", dsn)
    with pytest.raises(UnsafeTestDatabase):
        localdb.test_dsn()
    with pytest.raises(SystemExit):
        localdb.require_test_dsn()


def test_unset_means_none_and_scripts_stop(monkeypatch, tmp_path):
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setattr(localdb, "ENV_FILE", tmp_path / "missing.env")
    assert localdb.test_dsn() is None
    with pytest.raises(SystemExit):
        localdb.require_test_dsn()


def test_the_env_file_is_read_without_loading_the_supabase_url(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("DATABASE_URL=postgresql://u@db.x.supabase.co/postgres\n"
                   "TEST_DATABASE_URL=postgresql://u@127.0.0.1/dawat_test\n", encoding="utf-8")
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setattr(localdb, "ENV_FILE", env)
    before = dict(os.environ)
    assert localdb.test_dsn() == "postgresql://u@127.0.0.1/dawat_test"
    assert dict(os.environ) == before                                     # nothing else was loaded


def test_this_test_run_itself_is_on_the_local_database_or_none():
    """conftest.py set this before the app was imported: never the Supabase URL from backend/.env."""
    assert config.DATABASE_URL is None or is_local(config.DATABASE_URL)


@pytest.mark.parametrize("dsn", REMOTE[:2])
def test_the_app_pool_refuses_a_remote_database_during_a_test_run(monkeypatch, dsn):
    """The second layer: even if something put the Supabase URL into the config, no pool is opened."""
    monkeypatch.setattr(db, "_pool", None)
    monkeypatch.setattr(config, "DATABASE_URL", dsn)
    monkeypatch.setenv("DAWAT_TEST_RUN", "1")
    with pytest.raises(UnsafeTestDatabase):
        db.get_pool()
    assert db._pool is None
