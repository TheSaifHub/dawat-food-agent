"""Database connections for the tools layer and the API (D-022).

The backend connects as the table owner, so Row Level Security does NOT protect anything here. Every
query on user-owned tables must filter by the user id from app.auth.require_user; the tools layer takes
that id as a parameter and its tests prove one user can't reach another user's rows.

Tools never open connections themselves: they receive one. The API gets it from `get_conn` (one pooled
connection per request, committed on success, rolled back on error). Tests pass a connection inside a
transaction that is always rolled back, so they never leave data behind.
"""

import os
import threading
from collections.abc import Iterator

from fastapi import HTTPException
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app import config
from app.localdb import UnsafeTestDatabase, is_local

# The Supabase free tier allows only a few pooled connections; this is plenty for a demo and leaves room
# for scripts (migrate, seed) running at the same time.
POOL_MIN, POOL_MAX = 1, 4
CONNECT_KWARGS = {
    "row_factory": dict_row,
    "connect_timeout": 15,
    # No server-side prepared statements: they break behind Supabase's transaction pooler (port 6543),
    # in case the deployment ever switches to it. The cost is negligible at demo scale.
    "prepare_threshold": None,
}

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        if not config.DATABASE_URL:
            raise HTTPException(503, "The database is not configured on this server.")
        # Second layer of D-052: inside a test run (tests/conftest.py sets DAWAT_TEST_RUN), the app may only ever
        # open a pool on this machine, even if something loaded the Supabase DATABASE_URL first.
        if os.environ.get("DAWAT_TEST_RUN") == "1" and not is_local(config.DATABASE_URL):
            raise UnsafeTestDatabase("A test run tried to open a database pool that isn't local. Refused (D-052).")
        with _pool_lock:
            if _pool is None:
                _pool = ConnectionPool(config.DATABASE_URL, min_size=POOL_MIN, max_size=POOL_MAX, kwargs=CONNECT_KWARGS,
                                       timeout=10, open=True, name="dawat")
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def get_conn() -> Iterator[Connection]:
    """FastAPI dependency: one connection per request; commit if the route succeeds, roll back if it raises."""
    with get_pool().connection() as conn:
        yield conn
