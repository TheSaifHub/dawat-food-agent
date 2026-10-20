"""Phase 3d: check the Supabase settings in backend/.env and frontend/.env.local WITHOUT printing any secret.

What it prints: whether each variable is set, whether key prefixes are right, whether the project ref in the
URL matches the one in DATABASE_URL, which pooler host/port is used, and the database's Postgres version.
It never prints a key, a password or a full connection string. Connection errors are shown with the password
masked, plus the most likely reason.

Run from the project root:
    .venv\\Scripts\\python backend\\db\\check_connection.py
"""

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import dotenv_values, load_dotenv

BACKEND = Path(__file__).resolve().parent.parent
FRONTEND_ENV = BACKEND.parent / "frontend" / ".env.local"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(BACKEND / ".env")
    import os

    problems = []

    def ok(label, good, detail=""):
        print(f"  {'✓' if good else '✗'} {label}" + (f" ({detail})" if detail else ""))
        if not good:
            problems.append(label)

    print("backend/.env")
    url = os.getenv("SUPABASE_URL", "").strip()
    m = re.fullmatch(r"https://([a-z0-9]{20})\.supabase\.co/?", url)
    ok("SUPABASE_URL looks like https://<20-char ref>.supabase.co", bool(m),
       "not set" if not url else ("" if m else "unexpected format"))
    ref = m.group(1) if m else None

    secret = os.getenv("SUPABASE_SECRET_KEY", "").strip()
    ok("SUPABASE_SECRET_KEY starts with sb_secret_", secret.startswith("sb_secret_"),
       "not set" if not secret else ("" if secret.startswith("sb_secret_") else
                                     "looks like a legacy JWT key" if secret.startswith("eyJ") else "unexpected prefix"))

    dsn = os.getenv("DATABASE_URL", "").strip()
    password = ""
    if not dsn:
        ok("DATABASE_URL is set", False, "not set")
    else:
        u = urlparse(dsn)
        password = unquote(u.password or "")
        ok("DATABASE_URL scheme is postgresql://", u.scheme in ("postgresql", "postgres"), u.scheme)
        ok("password filled in (no [YOUR-PASSWORD] placeholder)", bool(password) and "YOUR-PASSWORD" not in dsn and "[" not in (u.password or ""))
        host = u.hostname or ""
        pooled = host.endswith(".pooler.supabase.com")
        ok("host is the Supabase pooler", pooled, host if pooled else "direct/other host: free plan direct connections are IPv6-only")
        ok("port 5432 (session pooler)", u.port == 5432, f"port {u.port}" + (" = transaction pooler" if u.port == 6543 else ""))
        user_ref = (u.username or "").split(".", 1)[1] if "." in (u.username or "") else None
        ok("user is postgres.<ref>", (u.username or "").startswith("postgres.") and bool(user_ref))
        if ref and user_ref:
            ok("project ref in SUPABASE_URL matches the one in DATABASE_URL", ref == user_ref)
        if u.password and re.search(r"[@:/?#\[\]]", unquote(u.password)) and u.password == unquote(u.password):
            print("  ! the password contains @ : / ? # [ ] unencoded; if the connection fails, URL-encode them (@ → %40)")

    print("frontend/.env.local")
    if not FRONTEND_ENV.exists():
        ok("frontend/.env.local exists", False)
    else:
        fe = {k: (v or "").strip() for k, v in dotenv_values(FRONTEND_ENV).items()}
        fe_url, pub = fe.get("NEXT_PUBLIC_SUPABASE_URL", ""), fe.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "")
        ok("NEXT_PUBLIC_SUPABASE_URL matches SUPABASE_URL", bool(fe_url) and fe_url.rstrip("/") == url.rstrip("/"))
        ok("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY starts with sb_publishable_", pub.startswith("sb_publishable_"),
           "not set" if not pub else ("" if pub.startswith("sb_publishable_") else "unexpected prefix"))
        leaked = [k for k, v in fe.items() if v.startswith(("sb_secret_", "postgres://", "postgresql://")) or (secret and v == secret)]
        ok("no secret key or database URL in any NEXT_PUBLIC_ value", not leaked, f"REMOVE: {leaked}" if leaked else "")

    print("database connection")
    if not dsn:
        print("  skipped: DATABASE_URL not set")
    else:
        import psycopg

        try:
            with psycopg.connect(dsn, connect_timeout=15) as conn:
                version = conn.execute("show server_version").fetchone()[0]
                user, db = conn.execute("select current_user, current_database()").fetchone()
                tables = conn.execute("select count(*) from information_schema.tables where table_schema = 'public'").fetchone()[0]
                trgm = conn.execute("select count(*) from pg_available_extensions where name = 'pg_trgm'").fetchone()[0]
            ok("connected", True, f"Postgres {version}, user {user.split('.')[0]}, database {db}")
            print(f"  · tables in schema public: {tables}  · pg_trgm available: {'yes' if trgm else 'no'}")
        except Exception as e:  # noqa: BLE001 — every failure is reported, with the password masked
            msg = str(e).replace(password, "***") if password else str(e)
            msg = re.sub(r"postgres(ql)?://[^\s'\"]+", "postgresql://***", msg)
            low = msg.lower()
            direct = re.search(r"\bdb\.[a-z0-9]{20}\.supabase\.co\b", low)
            reason = ("this is the DIRECT connection string (IPv6-only on the free plan); use the Session pooler string instead"
                      if direct else
                      "wrong password, or special characters in it not URL-encoded" if "password authentication failed" in low else
                      "user must be postgres.<project-ref> and the host must be your project's pooler region" if "tenant or user not found" in low else
                      "host name typo, or no internet/DNS" if "translate host name" in low or "name or service not known" in low or "getaddrinfo" in low else
                      "network blocked or timed out (firewall/VPN), or the direct IPv6 host was used" if "timeout" in low or "timed out" in low or "could not connect" in low else
                      "see the message")
            ok("connected", False, type(e).__name__)
            print(f"  message (password masked): {msg.strip()[:300]}")
            print(f"  likely reason: {reason}")

    print("\nALL CHECKS PASSED" if not problems else f"\n{len(problems)} problem(s): {problems}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
