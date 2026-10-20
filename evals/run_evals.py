"""Run the scripted conversations against the real models (Phase 6f, D-038).

    .venv\\Scripts\\python evals\\run_evals.py                      (from D:\\DAWAT; all of phase6_cases.json)
    .venv\\Scripts\\python evals\\run_evals.py --only demo-500-spicy order-flow-hinglish

Each case runs the same code as POST /chat (prompt, models, tools, loop, conversation store) as its demo user,
inside a database transaction that is ROLLED BACK when the case ends: nothing is kept, orders included.
The database is the LOCAL test database (TEST_DATABASE_URL), never Supabase (D-052); the models are real.
Every reply goes through evals/checks.py. The result file (evals/results/phase6_<UTC time>.json) records the prompt
version, the configured models, and per turn the model that actually answered, so runs can be compared.
A short pause between turns keeps the run inside the free tiers' per-minute limits. No retries.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))
sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402

from app.localdb import use_test_database  # noqa: E402

TEST_DSN = use_test_database()          # D-052: evals run on the local test database only, never Supabase

from app import config  # noqa: E402
from app.agent import llm, loop, store  # noqa: E402
from app.agent.prompts import system_prompt  # noqa: E402
from app.db import CONNECT_KWARGS  # noqa: E402
from checks import check_turn, parse_tool_message  # noqa: E402

USERS = {"priya": "Priya", "arjun": "Arjun", "family": "Family"}


def orders_of(conn, user_id) -> int:
    return conn.execute("select count(*) as n from public.orders where user_id = %s", (user_id,)).fetchone()["n"]


def cart_nonveg(conn, user_id) -> int:
    return conn.execute("""select count(*) as n from public.cart_items ci join public.carts c using (cart_id)
                           join public.menu_items m using (item_id) join public.dishes d using (dish_id)
                           where c.user_id = %s and c.status in ('open', 'confirmed') and not d.is_veg""",
                        (user_id,)).fetchone()["n"]


def cart_lines(conn, user_id) -> int:
    return conn.execute("""select count(*) as n from public.cart_items ci join public.carts c using (cart_id)
                           where c.user_id = %s and c.status in ('open', 'confirmed')""", (user_id,)).fetchone()["n"]


def run_case(conn, case: dict, prompt: tuple[str, str], pause: float) -> dict:
    text, version = prompt
    user = conn.execute("select user_id from public.users where is_demo and display_name like %s",
                        (f"%{USERS[case['user']]}%",)).fetchone()["user_id"]
    out = {"id": case["id"], "user": case["user"], "turns": []}
    with conn.transaction(force_rollback=True):
        conversation = store.open_conversation(conn, user)
        seen_results, user_words = [], []
        for i, t in enumerate(case["turns"]):
            if i:
                time.sleep(pause)
            before = orders_of(conn, user)
            started = time.perf_counter()
            turn = loop.run_turn(conn, store.load_history(conn, conversation), t["say"], user,
                                 system_prompt=text, prompt_version=version, chat=llm.chat)
            seconds = round(time.perf_counter() - started, 1)
            store.save_turn(conn, conversation, turn)
            results = [parse_tool_message(m["content"]) for m in turn.messages
                       if m["role"] == "tool" and '"not_run"' not in m["content"]]
            seen_results += results
            user_words.append(t["say"])
            calls = [{"tool": tr["tool_name"], "arguments": tr["arguments"], "status": tr["result_summary"].get("status")}
                     for tr in turn.traces if tr["tool_name"] != "name_correction"]
            checks = check_turn(reply=turn.reply, status=turn.status, calls=calls, tool_results_so_far=seen_results,
                                this_turn_results=results, user_words=user_words, expect=t.get("expect", {}),
                                orders_placed=orders_of(conn, user) - before, cart_nonveg=cart_nonveg(conn, user),
                                cart_lines=cart_lines(conn, user))
            out["turns"].append({"say": t["say"], "reply": turn.reply, "status": turn.status, "seconds": seconds,
                                 "models": [c["model"] for c in turn.llm_calls],
                                 "usage": [c["usage"] for c in turn.llm_calls], "calls": calls,
                                 "name_corrections": turn.corrections, "checks": checks})
    out["passed"] = all(c["ok"] for t in out["turns"] for c in t["checks"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(ROOT / "phase6_cases.json"))
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--pause", type=float, default=4.0, help="seconds between turns (free-tier per-minute limits)")
    ap.add_argument("--repeat", type=int, default=1, help="run each case N times (models vary between runs)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    cases = [c for c in json.loads(Path(args.cases).read_text(encoding="utf-8"))["cases"]
             if not args.only or c["id"] in args.only] * args.repeat
    prompt = system_prompt()
    run = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "prompt_version": prompt[1],
           "models": [config.LLM_PRIMARY_MODEL, config.LLM_FALLBACK_MODEL, config.LLM_FALLBACK_2_MODEL],
           "cases_file": Path(args.cases).name, "repeat": args.repeat, "cases": []}
    with psycopg.connect(TEST_DSN, autocommit=True, **CONNECT_KWARGS) as conn:
        for n, case in enumerate(cases):
            if n:
                time.sleep(args.pause)
            result = run_case(conn, case, prompt, args.pause)
            run["cases"].append(result)
            failed = [f"{c['check']} ({c['detail']})" for t in result["turns"] for c in t["checks"] if not c["ok"]]
            print(f"{'PASS' if result['passed'] else 'FAIL'}  {case['id']}" + ("".join(f"\n        - {f}" for f in failed)))
    checks = [c for r in run["cases"] for t in r["turns"] for c in t["checks"]]
    run["summary"] = {"cases": len(run["cases"]), "cases_passed": sum(r["passed"] for r in run["cases"]),
                      "turns": sum(len(r["turns"]) for r in run["cases"]), "checks": len(checks),
                      "checks_passed": sum(c["ok"] for c in checks)}
    by_check: dict[str, list] = {}
    for c in checks:
        by_check.setdefault(c["check"].split(" ")[0] if c["check"].startswith(("called", "did")) else c["check"], []).append(c["ok"])
    run["summary"]["by_check"] = {k: f"{sum(v)}/{len(v)}" for k, v in sorted(by_check.items())}
    out = ROOT / "results" / f"phase6_{run['run_at'].replace(':', '').replace('+0000', 'Z')}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(run, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    s = run["summary"]
    print(f"\n{s['cases_passed']}/{s['cases']} cases passed · {s['checks_passed']}/{s['checks']} checks · "
          f"{s['turns']} turns · prompt {run['prompt_version']}\nby check: {s['by_check']}\nsaved {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
