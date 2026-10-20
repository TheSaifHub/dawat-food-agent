"""Apply the SQL migrations in backend/db/migrations/ to the Supabase Postgres database (D-020).

SAFE BY DEFAULT: without --apply it only connects, reads what has been applied, and prints the plan.

Rules
  · files are named NNNN_name.sql and numbered 0001, 0002, … with no gaps
  · each file is applied at most once, in its own transaction, and recorded in public.schema_migrations
    with its sha256; if an applied file has since been edited, the run stops (write a new migration instead)
  · a Postgres advisory lock stops two runs from applying at the same time
  · nothing here drops or deletes anything; the connection string and password are never printed

Run from the project root:
    .venv\\Scripts\\python backend\\db\\migrate.py                    # Supabase: show the plan (no changes)
    .venv\\Scripts\\python backend\\db\\migrate.py --apply            # Supabase: apply pending migrations
    .venv\\Scripts\\python backend\\db\\migrate.py --local [--test|--apply]   # the LOCAL test database

--test (run pending migrations, then roll back) is a rehearsal, so it runs ONLY with --local (D-052). The order for
a new migration: --local --test, --local --apply, the test suite (local), then --apply on Supabase.
"""

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
MIGRATIONS = HERE / "migrations"
NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
LOCK_KEY = 7868535  # any fixed number; the OSM relation id is as good as any
LEDGER = """
create table if not exists public.schema_migrations (
  version    text primary key,
  filename   text not null,
  sha256     text not null,
  applied_at timestamptz not null default now()
);
alter table public.schema_migrations enable row level security;
revoke all on public.schema_migrations from anon, authenticated;
"""


def local_migrations() -> list[tuple[str, Path, str]]:
    files = sorted(MIGRATIONS.glob("*.sql"))
    bad = [f.name for f in files if not NAME.match(f.name)]
    if bad:
        sys.exit(f"Badly named migration files: {bad} (expected NNNN_name.sql). Nothing done.")
    out = [(NAME.match(f.name).group(1), f, hashlib.sha256(f.read_bytes()).hexdigest()) for f in files]
    expected = [f"{i:04d}" for i in range(1, len(out) + 1)]
    if [v for v, _, _ in out] != expected:
        sys.exit(f"Migration numbers must run 0001… without gaps; found {[v for v, _, _ in out]}. Nothing done.")
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="apply pending migrations (default: only show the plan)")
    mode.add_argument("--test", action="store_true",
                      help="run pending migrations inside ONE transaction and ROLL BACK: proves the SQL works, changes nothing")
    ap.add_argument("--local", action="store_true", help="target the LOCAL test database (TEST_DATABASE_URL)")
    args = ap.parse_args()

    if args.local:
        sys.path.insert(0, str(HERE.parent))
        from app.localdb import require_test_dsn
        dsn = require_test_dsn()
        print("Target: the LOCAL test database")
    else:
        if args.test:
            sys.exit("--test is a rehearsal and runs only on the local test database: add --local (D-052). Nothing done.")
        load_dotenv(HERE.parent / ".env")
        dsn = os.getenv("DATABASE_URL", "").strip()
        if not dsn:
            sys.exit("DATABASE_URL is not set in backend/.env. Nothing done.")
        print("Target: Supabase (DATABASE_URL)")
    local = local_migrations()

    with psycopg.connect(dsn, connect_timeout=15, autocommit=True) as conn:
        conn.execute("select pg_advisory_lock(%s)", (LOCK_KEY,))
        try:
            exists = conn.execute("select to_regclass('public.schema_migrations') is not null").fetchone()[0]
            applied = dict(conn.execute("select version, sha256 from public.schema_migrations").fetchall()) if exists else {}

            changed = [(v, f.name) for v, f, h in local if v in applied and applied[v] != h]
            unknown = sorted(set(applied) - {v for v, _, _ in local})
            if changed or unknown:
                print(f"STOP: applied migrations were edited {changed} or are missing locally {unknown}.")
                print("Never edit an applied migration; add a new one instead. Nothing done.")
                return 1
            pending = [(v, f, h) for v, f, h in local if v not in applied]

            print(f"Database: {'ledger found' if exists else 'no schema_migrations table yet (fresh database)'}")
            for v, f, h in local:
                print(f"  {'applied ' if v in applied else 'PENDING '} {f.name}  sha256 {h[:12]}…")
            if not pending:
                print("Nothing to apply.")
                return 0
            if args.test:
                print(f"\nTEST: running {len(pending)} pending migration(s) in one transaction, then rolling back …")
                with conn.transaction(force_rollback=True):
                    conn.execute(LEDGER)
                    for v, f, h in pending:
                        conn.execute(f.read_text(encoding="utf-8"))
                        print(f"  ok  {f.name}")
                    tables = conn.execute("select count(*) from information_schema.tables where table_schema = 'public' "
                                          "and table_type = 'BASE TABLE'").fetchone()[0]
                    print(f"  tables in public with these applied: {tables}")
                left = conn.execute("select count(*) from information_schema.tables where table_schema = 'public' "
                                    "and table_type = 'BASE TABLE'").fetchone()[0]
                print(f"Rolled back. Tables in public now: {left} (unchanged). Nothing was applied.")
                return 0
            if not args.apply:
                print(f"\n{len(pending)} pending. Dry run only: rehearse with --local --test, apply with --apply"
                      + ("" if args.local else " (after they pass locally, D-052)") + ".")
                return 0

            conn.execute(LEDGER)
            for v, f, h in pending:
                print(f"Applying {f.name} …", end=" ", flush=True)
                with conn.transaction():  # all or nothing per file
                    conn.execute(f.read_text(encoding="utf-8"))
                    conn.execute("insert into public.schema_migrations (version, filename, sha256) values (%s, %s, %s)",
                                 (v, f.name, h))
                print("done")
            tables = conn.execute("select count(*) from information_schema.tables where table_schema = 'public' "
                                  "and table_type = 'BASE TABLE'").fetchone()[0]
            no_rls = [r[0] for r in conn.execute(
                "select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace "
                "where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity order by 1").fetchall()]
            print(f"\nApplied {len(pending)} migration(s). Tables in public: {tables}. Tables WITHOUT RLS: {no_rls or 'none'}")
            return 0 if not no_rls else 1
        finally:
            conn.execute("select pg_advisory_unlock(%s)", (LOCK_KEY,))


if __name__ == "__main__":
    sys.exit(main())
