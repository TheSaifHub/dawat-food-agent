"""The local test database (Saif's rule, 2026-10-06, D-052): tests, evals, the rule-breaker and migration rehearsals
run ONLY against a PostgreSQL on this machine, never against Supabase.

    test_dsn()          → TEST_DATABASE_URL if set, else None; raises UnsafeTestDatabase if it isn't local
    require_test_dsn()  → the same, but exits with a clear message when it is missing or not local
    is_local(dsn)       → True only if every host in the connection string is this machine

TEST_DATABASE_URL is read from the environment or backend/.env WITHOUT loading the rest of that file, so importing
this never puts the Supabase DATABASE_URL into the environment. Nothing here prints a connection string.
"""

import os
import sys
from pathlib import Path

from dotenv import dotenv_values
from psycopg.conninfo import conninfo_to_dict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
VAR = "TEST_DATABASE_URL"


class UnsafeTestDatabase(RuntimeError):
    """The test connection string points somewhere other than this machine."""


def is_local(dsn: str | None) -> bool:
    if not dsn or not dsn.strip():
        return False
    try:
        info = conninfo_to_dict(dsn)
    except Exception:
        return False
    hosts = [h.strip() for key in ("host", "hostaddr") for h in str(info.get(key) or "").split(",") if h.strip()]
    # No host at all means libpq's default (a local socket / localhost); every listed host must be local.
    return all(h.lower() in LOCAL_HOSTS for h in hosts)


def _raw() -> str | None:
    value = os.environ.get(VAR)
    if value is None and ENV_FILE.exists():
        value = dotenv_values(ENV_FILE).get(VAR)
    return value.strip() if value and value.strip() else None


def test_dsn() -> str | None:
    dsn = _raw()
    if dsn is not None and not is_local(dsn):
        raise UnsafeTestDatabase(f"{VAR} must point at a PostgreSQL on this machine (localhost / 127.0.0.1 / ::1). "
                                 "Tests, evals and rehearsals never run against Supabase (D-052). Nothing was run.")
    return dsn


def require_test_dsn() -> str:
    try:
        dsn = test_dsn()
    except UnsafeTestDatabase as e:
        sys.exit(str(e))
    if dsn is None:
        sys.exit(f"{VAR} is not set in backend/.env. Set it to the local test database "
                 "(postgresql://postgres:<password>@127.0.0.1:5432/dawat_test). Nothing was run.")
    return dsn


DEV_DB_NAME = "dawat_dev"


def dev_dsn() -> str:
    """The local DEVELOPMENT database (D-059): the same local server as TEST_DATABASE_URL, database dawat_dev. Kept
    apart from dawat_test so clicking around the dev site never disturbs a test run, and a test run never touches
    what the dev site shows. Exits like require_test_dsn when the test database isn't set or isn't local."""
    from psycopg.conninfo import make_conninfo
    dsn = make_conninfo(require_test_dsn(), dbname=DEV_DB_NAME)
    if not is_local(dsn):                     # can't happen (same hosts), but this is the dev login's database lock
        sys.exit("The dev database must be on this machine. Nothing was run.")
    return dsn


def use_test_database() -> str:
    """For scripts (evals, chat_cli, test_triggers): call BEFORE importing app.config. Points this whole process,
    the app's own pool included, at the local test database, or exits. Returns the connection string."""
    dsn = require_test_dsn()
    os.environ["DATABASE_URL"] = dsn
    os.environ["DAWAT_TEST_RUN"] = "1"
    return dsn
