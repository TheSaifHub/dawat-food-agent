"""Build the LOCAL test database from scratch or bring it up to date (D-052). Rerunnable; never touches Supabase.

    .venv\\Scripts\\python backend\\db\\local_setup.py          (from D:\\DAWAT)  the test database, dawat_test
    .venv\\Scripts\\python backend\\db\\local_setup.py --dev    the DEVELOPMENT database, dawat_dev (D-059): same
                                                             server; what the local dev site and dev login use

Steps, each one idempotent:
  1. check TEST_DATABASE_URL points at this machine (app/localdb.py) and the server is PostgreSQL 17 (as Supabase)
  2. create the database if it doesn't exist (connecting to the server's "postgres" maintenance database), with
     Supabase's text sorting (ICU en-US)
  3. match Supabase's settings: timezone UTC, search_path "$user", public, extensions
  4. run local_bootstrap.sql (stand-ins for Supabase's roles, auth.users, auth.uid(), the extensions schema)
  5. migrate.py --local --apply      (every migration, recorded in schema_migrations)
  6. load_db.py --local              (validated menus, reference data, the three demo users)
Nothing is deleted or dropped. The connection string and password are never printed.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))

from app.localdb import dev_dsn, require_test_dsn  # noqa: E402

SUPABASE_MAJOR = 17


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Build or update a local database (D-052, D-059).")
    ap.add_argument("--dev", action="store_true", help="the development database dawat_dev instead of dawat_test")
    dev = ap.parse_args().dev
    dsn = dev_dsn() if dev else require_test_dsn()
    name = conninfo_to_dict(dsn).get("dbname")
    if not name or name in ("postgres", "template0", "template1"):
        sys.exit("TEST_DATABASE_URL must name its own database (e.g. /dawat_test), not the server's built-in ones.")

    print("1. Server")
    try:
        admin = psycopg.connect(make_conninfo(dsn, dbname="postgres"), autocommit=True, connect_timeout=10)
    except psycopg.OperationalError as e:
        reason = str(e).splitlines()[0] if str(e) else type(e).__name__
        sys.exit(f"   Can't connect to the local PostgreSQL ({reason}). Is it installed and running, and is the "
                 "password in TEST_DATABASE_URL right? Nothing done.")
    with admin:
        major = admin.info.server_version // 10000
        print(f"   PostgreSQL {major} on this machine" + ("" if major == SUPABASE_MAJOR else
              f"   WARNING: Supabase runs {SUPABASE_MAJOR}; results may differ"))
        exists = admin.execute("select 1 from pg_database where datname = %s", (name,)).fetchone()
        print("2. Database")
        if exists:
            print(f"   {name} already exists")
        else:
            # Supabase sorts text with ICU en-US (datlocprovider 'i'); the same here, so ORDER BY agrees with production.
            admin.execute(sql.SQL("create database {} encoding 'UTF8' template template0 locale_provider icu "
                                  "icu_locale 'en-US'").format(sql.Identifier(name)))
            print(f"   created {name} (UTF8, ICU en-US collation like Supabase)")
        provider = admin.execute("select datlocprovider, datlocale from pg_database where datname = %s", (name,)).fetchone()
        print(f"   collation: provider {provider[0]!r}, locale {provider[1]!r}"
              + ("" if provider[0] == "i" else "   WARNING: Supabase uses ICU en-US; ORDER BY on text may differ"))
        print("3. Settings to match Supabase")
        admin.execute(sql.SQL("alter database {} set timezone = 'UTC'").format(sql.Identifier(name)))
        admin.execute(sql.SQL("alter database {} set search_path = \"$user\", public, extensions").format(sql.Identifier(name)))
        print("   timezone UTC; search_path \"$user\", public, extensions")

    print("4. Supabase stand-ins (local_bootstrap.sql)")
    with psycopg.connect(dsn, autocommit=True, connect_timeout=10) as conn:
        conn.execute((HERE / "local_bootstrap.sql").read_text(encoding="utf-8"))
    print("   roles, auth.users, auth.uid(), extensions schema: ok")

    for step, cmd in (("5. Migrations", [str(HERE / "migrate.py"), "--local", "--apply"]),
                      ("6. Seed", [str(ROOT / "data_pipeline" / "load_db.py"), "--local"])):
        print(step)
        cwd = ROOT / "data_pipeline" if "load_db" in cmd[0] else ROOT
        # migrate.py --local and load_db.py --local target TEST_DATABASE_URL. For --dev, that variable points at
        # dawat_dev in these two child processes only (app/localdb.py reads the environment before the env file).
        env = {**os.environ, "TEST_DATABASE_URL": dsn} if dev else None
        result = subprocess.run([sys.executable, *cmd], cwd=cwd, env=env)
        if result.returncode != 0:
            sys.exit(f"   {step} failed (exit {result.returncode}). Fix it and rerun; every step is safe to repeat.")
    print(f"\nLOCAL {'DEV' if dev else 'TEST'} DATABASE READY ({name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
