"""Read-only check of the applied schema (D-020): tables, row-level security, policies, browser privileges, triggers.

Changes nothing. Fails (exit 1) if an expected table is missing, any table in public lacks RLS, or the browser
roles (anon, authenticated) hold any privilege on a table, view or sequence in public.

Run from the project root:
    .venv\\Scripts\\python backend\\db\\verify_schema.py
"""

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

EXPECTED = {"areas", "area_aliases", "restaurants", "branches", "dishes", "dish_aliases", "menu_items", "users",
            "user_preferences", "addresses", "carts", "cart_items", "orders", "order_items", "order_status_events",
            "conversations", "messages", "agent_traces", "schema_migrations", "food_terms", "chat_daily_usage",
            "reference_version", "payment_attempts"}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    problems = []
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=15) as conn:
        conn.read_only = True
        rows = conn.execute("""
            select c.relname, c.relrowsecurity,
                   (select count(*) from pg_policies p where p.schemaname = 'public' and p.tablename = c.relname),
                   (select count(*) from public.schema_migrations) as migrations
            from pg_class c join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = 'public' and c.relkind = 'r' order by 1""").fetchall()
        grants = conn.execute("""
            select grantee, table_name, string_agg(privilege_type, ',' order by privilege_type)
            from information_schema.role_table_grants
            where table_schema = 'public' and grantee in ('anon', 'authenticated')
            group by 1, 2 order by 1, 2""").fetchall()
        seq_grants = conn.execute("""
            select count(*) from information_schema.usage_privileges
            where object_schema = 'public' and object_type = 'SEQUENCE' and grantee in ('anon', 'authenticated')""").fetchone()[0]
        triggers = conn.execute("""
            select event_object_table, trigger_name from information_schema.triggers
            where trigger_schema = 'public' group by 1, 2 order by 1, 2""").fetchall()
        views = [r[0] for r in conn.execute(
            "select table_name from information_schema.views where table_schema = 'public' order by 1").fetchall()]

    names = {r[0] for r in rows}
    print(f"{'table':<22} {'RLS':<5} policies")
    for name, rls, policies, _ in rows:
        print(f"  {name:<20} {'on' if rls else 'OFF':<5} {policies}")
        if not rls:
            problems.append(f"RLS off: {name}")
    missing, extra = EXPECTED - names, names - EXPECTED
    print(f"\n{len(rows)} tables (expected {len(EXPECTED)}); missing: {sorted(missing) or 'none'}; unexpected: {sorted(extra) or 'none'}")
    print(f"views: {views}")
    print(f"migrations recorded: {rows[0][3] if rows else 0}")
    print(f"browser-role table/view grants: {grants or 'none'}; sequence grants: {seq_grants}")
    print(f"triggers ({len(triggers)}): " + ", ".join(f"{t}.{n}" for t, n in triggers))
    problems += [f"missing table {m}" for m in sorted(missing)]
    problems += [f"browser role {g} has {p} on {t}" for g, t, p in grants]
    if seq_grants:
        problems.append(f"{seq_grants} sequence grant(s) to browser roles")
    print("\nSCHEMA OK" if not problems else f"\nPROBLEMS: {problems}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
