"""Chat with Dawat AI from the terminal, signed in as a demo user (for Saif; Session 15).

    .venv\\Scripts\\python backend\\chat_cli.py                  (from D:\\DAWAT; signed in as Demo Priya)
    .venv\\Scripts\\python backend\\chat_cli.py --user arjun     (arjun | priya | family)

It runs exactly what POST /chat runs (the same prompt, models, tools, loop and conversation store), minus the
HTTP and sign-in layer: each tool step is printed as it happens, then the reply.

NOTHING IS KEPT. The whole session runs inside one database transaction that is rolled back when you quit, so
you can add to the cart and place orders freely. It uses the LOCAL test database (TEST_DATABASE_URL), never
Supabase (D-052). (Model requests are real and
count against the free quotas.)

Commands:  /new  start a fresh conversation      /quit  (or Ctrl+C)  leave
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import psycopg  # noqa: E402

from app.localdb import use_test_database  # noqa: E402

TEST_DSN = use_test_database()          # D-052: the local test database, never Supabase

from app import config  # noqa: E402
from app.agent import cards, llm, loop, store  # noqa: E402
from app.agent.prompts import system_prompt  # noqa: E402
from app.db import CONNECT_KWARGS  # noqa: E402

USERS = {"priya": "Priya", "arjun": "Arjun", "family": "Family"}
if sys.stdout.isatty():
    if sys.platform == "win32":
        import os
        os.system("")                                  # switches on colour codes in the classic Windows console
    GREY, GOLD, BOLD, RESET = "\033[90m", "\033[33m", "\033[1m", "\033[0m"
else:
    GREY = GOLD = BOLD = RESET = ""


def step_line(t: dict) -> str:
    s = t["result_summary"]
    counts = ", ".join(f"{k.removesuffix('_count')} {v}" for k, v in s.items() if k.endswith("_count"))
    args = ", ".join(f"{k}={v}" for k, v in t["arguments"].items())
    ok = "" if t["ok"] else "  (refused)"
    return f"{GREY}  · {t['tool_name']}({args}) → {s.get('status')}{' · ' + counts if counts else ''}" \
           f"  [{t['latency_ms']} ms]{ok}{RESET}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Chat with Dawat AI as a demo user. Nothing is kept.")
    ap.add_argument("--user", choices=sorted(USERS), default="priya")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stdin):
        stream.reconfigure(encoding="utf-8")          # ₹, Telugu and Hindi in the Windows console
    text, version = system_prompt()

    with psycopg.connect(TEST_DSN, autocommit=True, **CONNECT_KWARGS) as conn:
        user = conn.execute("select user_id, display_name from public.users where is_demo and display_name like %s",
                            (f"%{USERS[args.user]}%",)).fetchone()
        print(f"{BOLD}Dawat AI{RESET} · signed in as {user['display_name']} · prompt {version} · "
              f"models {config.LLM_PRIMARY_MODEL} → {config.LLM_FALLBACK_MODEL} → {config.LLM_FALLBACK_2_MODEL}")
        print(f"{GREY}Nothing is kept: everything is rolled back when you quit. /new = fresh chat, /quit = leave.{RESET}\n")
        with conn.transaction(force_rollback=True):
            conversation = store.open_conversation(conn, user["user_id"])
            while True:
                try:
                    message = input(f"{BOLD}you ›{RESET} ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if not message:
                    continue
                if message == "/quit":
                    break
                if message == "/new":
                    conversation = store.open_conversation(conn, user["user_id"])
                    print(f"{GREY}(new conversation){RESET}\n")
                    continue
                turn = loop.run_turn(conn, store.load_history(conn, conversation), message, user["user_id"],
                                     system_prompt=text, prompt_version=version, chat=llm.chat,
                                     on_step=lambda t: print(step_line(t), flush=True))
                store.save_turn(conn, conversation, turn)
                models = " → ".join(dict.fromkeys(c["model"] or "none" for c in turn.llm_calls))
                note = "" if turn.status == "ok" else f" [{turn.status}]"
                print(f"{GOLD}dawat ›{RESET} {turn.reply}")
                if turn.card:                                 # the confirmation card (D-046)
                    print(f"{BOLD}  ┌ {cards.text(turn.card)}{RESET}")
                print(f"{GREY}  ({models}{note}){RESET}\n")
    print(f"{GREY}Rolled back: nothing from this session was kept.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
