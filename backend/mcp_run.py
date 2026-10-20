"""Start the Dawat MCP server for Claude Desktop, LOCAL mode only (D-065, Saif: no Supabase until 30 Oct).

    .venv\\Scripts\\python backend\\mcp_run.py --as priya      (priya | arjun | family)

It points this one process at the local dawat_dev database and turns on the local dev login (the same five locks as
dev_server.py, D-059), then signs the chosen seed user in with a fresh dev token and hands it to the server as
DAWAT_MCP_TOKEN. The server still verifies that token on every call like any other. Nothing is written to any file.
The token lasts 12 hours; restart the server (restart Claude Desktop) for a new one.

Everything on stdout is the MCP protocol, so messages here go to stderr.
"""

import argparse
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

USERS = {"priya": "Priya", "arjun": "Arjun", "family": "Family"}


def say(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Dawat MCP server (local dev login, local dawat_dev database).")
    ap.add_argument("--as", dest="who", choices=sorted(USERS), default="priya", help="the seed user to sign in as")
    args = ap.parse_args()

    from app.localdb import dev_dsn                 # exits with a clear message if the local database isn't set up
    os.environ["DATABASE_URL"] = dev_dsn()          # wins over backend/.env (load_dotenv never overrides)
    os.environ["DAWAT_DEV_LOGIN"] = "1"
    from app import devauth
    import psycopg
    from psycopg.rows import dict_row

    devauth.enabled()                               # raises, loudly, if any lock refuses
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
        user = conn.execute("select user_id, display_name from public.users where is_demo and display_name like %s",
                            (f"%{USERS[args.who]}%",)).fetchone()
    if user is None:
        sys.exit(f"No seed user matching {USERS[args.who]!r} in the local dev database. Nothing was started.")
    issued = devauth.issue_token(uuid.UUID(str(user["user_id"])), display_name=user["display_name"])
    os.environ["DAWAT_MCP_TOKEN"] = issued["access_token"]
    say(f"Dawat MCP server (LOCAL) · signed in as {user['display_name']} · dev database · token for 12 h")

    from app.mcp_server import main as serve
    serve()


if __name__ == "__main__":
    main()
