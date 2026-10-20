"""One chat turn of Dawat AI (Phase 6c, D-034): model → tools → model … → a reply.

    run_turn(conn, history, user_message, user_id, system_prompt=..., prompt_version=...) → Turn

The loop:
  1. Send the system prompt, the conversation so far and the user's message to the model (app.agent.llm.chat:
     primary once, fallback once).
  2. If it asks for tools, run each one through app.agent.tools.run_tool, which checks the arguments and fills in
     identity, the user's own message and the chat source. Feed a compact copy of each result back. Repeat.
  3. When it answers in text, that's the reply.

Limits and failures (Saif, Session 14):
  · At most MAX_TOOL_CALLS (8) tool calls per turn. Calls the model asks for beyond that are not run; the user
    gets STEP_CAP_MESSAGE.
  · Both models failing → the busy message. If something was added to the cart this turn, it says so
    (BUSY_WITH_CART). If an order was placed this turn, the reply is built by code from the order itself, so the
    user is never left unsure whether they ordered.
  · A tool that crashes is rolled back on its own (nothing from it is saved), the model gets a short generic
    error, and the details go only to the server log.

Transactions: each tool call runs in `with conn.transaction()`. On an autocommit connection (the chat route, 6e)
that is a real transaction, committed as soon as the tool succeeds, so an added item is saved even if the model
fails a moment later, and no transaction is ever held open while waiting for the model. Inside an outer
transaction (the tests) it is a savepoint, so a failing tool still rolls back alone.

What the model is sent back is compact (compact_result): internal fields and nulls dropped, long lists capped, no
spaces. Every price, total, id and the `understood` / `message` fields are kept as they are. The token budget is
shared with the tool list (D-033).
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field, replace
from typing import Callable

from psycopg import Connection

from app.agent import cards, llm
from app.agent.names import correct_names
from app.tools import cart as cart_tools
from app.tools.payments import ATTEMPT_TTL_MINUTES
from app.tools.preferences import saved_diet
from app.agent.tools import ToolContext, run_tool, tool_schemas

log = logging.getLogger("dawat.agent")

MAX_TOOL_CALLS = 8
STEP_CAP_MESSAGE = "That took more steps than I can manage in one go. Could you say it again, a bit more simply?"
BUSY_WITH_CART = ("Dawat AI is busy right now. Anything already added is in your cart. "
                  "Please try again in a minute.")
CART_ADDING_TOOLS = ("add_to_cart", "add_plan_to_cart")

DROP_KEYS = {"dish_id", "restaurant_id", "lat", "lon", "score", "match", "planner", "course"}
MAX_LIST, MAX_MENU_ITEMS = 15, 60
SUMMARY_TEXT = 200


@dataclass
class Turn:
    reply: str
    status: str                                     # ok | step_cap | busy
    messages: list[dict]                            # this turn's messages, to append to the conversation
    traces: list[dict] = field(default_factory=list)  # one per tool call (→ agent_traces in 6e)
    llm_calls: list[dict] = field(default_factory=list)  # every model call: model, attempts, seconds, usage
    corrections: list[list[str]] = field(default_factory=list)  # restaurant names fixed in the reply (D-041)
    card: dict | None = None                        # the confirmation card shown under the reply (D-046)
    plans: list[dict] | None = None                 # this turn's plan options, shown as cards in the web chat (D-058)
    payment: dict | None = None                     # {cart_id, quote_id, grand_total}: the app shows a Pay button (D-061)


# ─── what goes back to the model, and into the trace ─────────────────────────────────────────────────────

def compact_result(value, key: str | None = None):
    """Drop internal fields and nulls; cap long lists (with a count of what's not shown). Values never change."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in DROP_KEYS or v is None:
                continue
            if isinstance(v, list):
                cap = MAX_MENU_ITEMS if k == "items" else MAX_LIST
                if len(v) > cap:
                    out[f"{k}_not_shown"] = len(v) - cap
                    v = v[:cap]
            out[k] = compact_result(v, k)
        return out
    if isinstance(value, list):
        return [compact_result(v, key) for v in value]
    return value


def to_model(result: dict) -> str:
    return json.dumps(compact_result(result), ensure_ascii=False, separators=(",", ":"), default=str)


def summarise(result: dict) -> dict:
    """The trace's short result: top-level text and numbers as they are (message shortened), list sizes."""
    out = {}
    for k, v in result.items():
        if isinstance(v, str):
            out[k] = v if len(v) <= SUMMARY_TEXT else v[:SUMMARY_TEXT] + "…"
        elif isinstance(v, (int, float, bool)):
            out[k] = v
        elif isinstance(v, list):
            out[f"{k}_count"] = len(v)
    return out


def _arguments_for_trace(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
    except json.JSONDecodeError:
        parsed = None
    return parsed if isinstance(parsed, dict) else {"_unparsed": str(raw)[:SUMMARY_TEXT]}


def _tool_results(messages: list[dict]) -> list:
    out = []
    for m in messages:
        if m.get("role") == "tool":
            try:
                out.append(json.loads(m.get("content") or "{}"))
            except json.JSONDecodeError:
                continue
    return out


def latest_area(messages: list[dict]) -> str | None:
    """The area_id this conversation's tool results most recently resolved: a dish or restaurant search in an area,
    a plan's delivery area, or a delivery the cart was set to (D-042). Only tool results count."""
    found = None
    for r in _tool_results(messages):
        if not isinstance(r, dict) or r.get("status") not in ("ok", "over_budget", "no_match_with_filters",
                                                               "none_near_area", "needs_choice"):
            continue
        for key in ("area", "delivery"):
            v = r.get(key)
            if isinstance(v, dict) and isinstance(v.get("area_id"), str):
                found = v["area_id"]
    return found


REPLACE_REFUSED = ("cart_not_empty", "no_clear_yes", "confirm_intent", "wants_change")


# ─── one tool call ───────────────────────────────────────────────────────────────────────────────────────

def _run_one(conn: Connection, call: dict, ctx: ToolContext) -> tuple[dict, str | None, int]:
    """(result, error for the trace, latency ms). Its own transaction: committed on success, rolled back on a crash."""
    started = time.perf_counter()
    try:
        with conn.transaction():
            result = run_tool(call["name"], call["arguments"], ctx)
        error = None
    except Exception as e:                                   # a bug or a database error inside the tool
        log.exception("tool %s failed", call["name"])
        result = {"status": "tool_error",
                  "message": "That step failed and nothing from it was saved. Tell the user something went wrong "
                             "with that step; don't guess its result."}
        error = type(e).__name__
    return result, error, round((time.perf_counter() - started) * 1000)


def _payment_pending_reply(payment: dict) -> str:
    """Built by code when the model fails after the user said yes (D-061): the order is NOT placed until they pay."""
    return (f"Your order is not placed yet: total ₹{payment['grand_total']}. Dawat AI is busy right now, so I can't "
            "say more. Tap Pay to finish, or open your cart.")


# ─── the turn ────────────────────────────────────────────────────────────────────────────────────────────

CANCELLED_MESSAGE = "Stopped. Nothing more was done."
CANCELLED_WITH_CART = "Stopped. What was already added is in your cart; nothing more was done."
NOT_RUN_CANCELLED = '{"status":"not_run","message":"Cancelled before this ran."}'


def run_turn(conn: Connection, history: list[dict], user_message: str, user_id: uuid.UUID | None, *,
             system_prompt: str, prompt_version: str, chat: Callable = llm.chat,
             on_step: Callable[[dict], None] | None = None,
             should_stop: Callable[[], bool] | None = None) -> Turn:
    """One user message → one reply. `history` is the conversation's earlier messages (no system message).
    `on_step(trace)` is called after each tool call, so the chat can show it live (the thinking panel, 6e).

    `should_stop()` (D-075: the client left) is looked at only BETWEEN steps: before each model call and before each
    tool call, never inside a tool (each tool is its own transaction and always finishes whole). When it says stop,
    the tools not yet run get a "not_run" answer (so the saved history never has a call without an answer), the turn
    ends with status "cancelled" and a code-built reply, and it shows NO card and NO plan options: a card nobody
    saw must never be something a later "yes" can act on. Whatever was committed before stays."""
    stopped = should_stop or (lambda: False)
    had_items = False
    if user_id:
        # D-045: a confirmation lasts only for the turn of its yes. Any cart still confirmed when a new message
        # arrives is re-opened, so confirm_cart and place_order must both follow the SAME clear yes.
        # Phase 8 (D-061): a cart whose payment is open (a live, unpaid attempt for its confirmed quote) is left alone,
        # so a chat message sent while the Razorpay window is open can't undo the website's confirmation.
        with conn.transaction():
            for row in conn.execute(f"""select c.cart_id from public.carts c
                                       where c.user_id = %s and c.status = 'confirmed'
                                         and not exists (select 1 from public.payment_attempts p
                                                         where p.cart_id = c.cart_id and p.status = 'created'
                                                           and p.quote_id = c.confirmed_quote
                                                           and p.created_at > now() - interval '{ATTEMPT_TTL_MINUTES} minutes')""",
                                    (user_id,)).fetchall():
                cart_tools.reopen(conn, row["cart_id"])
        current = cart_tools.view_cart(conn, user_id)
        had_items = bool(current.get("branches") or current.get("unavailable"))
    ctx = ToolContext(conn=conn, user_id=user_id, user_message=user_message, card=cards.pending(history),
                      turn_diet=saved_diet(conn, user_id) if user_id else None, cart_had_items=had_items)
    locked = False
    new = [{"role": "user", "content": user_message}]
    turn = Turn(reply="", status="ok", messages=new)
    tools = tool_schemas()
    calls_made = 0
    added_to_cart, payment = False, None
    results: list[tuple[str, dict]] = []                  # this turn's tool results, for its one card (D-046)

    while True:
        if stopped():
            turn.status = "cancelled"
            turn.reply = CANCELLED_WITH_CART if added_to_cart else CANCELLED_MESSAGE
            break
        try:
            answer = chat([{"role": "system", "content": system_prompt}, *cards.for_model(history), *new], tools)
        except llm.LLMUnavailable as e:
            turn.llm_calls.append({"model": None, "attempts": e.attempts, "seconds": None, "usage": None})
            turn.status = "busy"
            turn.reply = (_payment_pending_reply(payment) if payment else
                          BUSY_WITH_CART if added_to_cart else llm.BUSY_MESSAGE)
            break
        turn.llm_calls.append({"model": answer["model"], "attempts": answer["attempts"],
                               "seconds": answer["seconds"], "usage": answer["usage"]})
        calls = answer["message"]["tool_calls"]
        if not calls:
            turn.reply, turn.corrections = correct_names(answer["message"]["content"], _tool_results(history + new))
            if turn.corrections:                              # logged like a step, so evals and the panel see it
                turn.traces.append({"step": calls_made + 1, "tool_name": "name_correction", "arguments": {},
                                    "result_summary": {"status": "ok", "corrections": turn.corrections}, "ok": True,
                                    "error": None, "latency_ms": 0, "provider": answer["model"].split("/", 1)[0],
                                    "model": answer["model"], "prompt_version": prompt_version})
            break
        new.append(answer["raw_message"])                     # unchanged: Gemini needs its thought signatures

        capped = False
        cancelled = False
        for call in calls:
            ctx = replace(ctx, chat_area_id=latest_area(history + new), cart_locked=locked)
            if cancelled or stopped():                        # between tools only; the one before this has finished
                cancelled = True
                new.append({"role": "tool", "tool_call_id": call["id"], "name": call["name"], "content": NOT_RUN_CANCELLED})
                continue
            if calls_made >= MAX_TOOL_CALLS:                  # every tool call needs an answer in the history
                capped = True
                new.append({"role": "tool", "tool_call_id": call["id"], "name": call["name"],
                            "content": '{"status":"not_run","message":"Step limit reached for this turn."}'})
                continue
            calls_made += 1
            result, error, ms = _run_one(conn, call, ctx)
            ok = error is None and result.get("status") not in ("invalid_arguments", "unknown_tool", "tool_error")
            if call["name"] == "add_plan_to_cart" and result.get("status") in REPLACE_REFUSED:
                locked = True                                  # fix 4 (D-044): no cart changes for the rest of the turn
            if ok and result.get("status") == "ok":
                added_to_cart |= call["name"] in CART_ADDING_TOOLS
            if ok and call["name"] == "place_order" and result.get("status") == "payment_required":
                payment = {"cart_id": result["cart_id"], "quote_id": result["quote_id"],
                           "grand_total": result["grand_total"]}
            turn.traces.append({"step": calls_made, "tool_name": call["name"],
                                "arguments": _arguments_for_trace(call["arguments"]),
                                "result_summary": summarise(result), "ok": ok, "error": error, "latency_ms": ms,
                                "provider": answer["model"].split("/", 1)[0], "model": answer["model"],
                                "prompt_version": prompt_version})
            if ok:
                results.append((call["name"], result))
            if on_step:
                on_step(turn.traces[-1])
            new.append({"role": "tool", "tool_call_id": call["id"], "name": call["name"],
                        "content": to_model(result)})
        if cancelled:
            turn.status = "cancelled"
            turn.reply = CANCELLED_WITH_CART if added_to_cart else CANCELLED_MESSAGE
            break
        if capped:
            turn.status, turn.reply = "step_cap", STEP_CAP_MESSAGE
            break

    if turn.status == "ok" and stopped():                    # the client left while the model was finishing
        turn.status = "cancelled"
    turn.payment = payment              # code-built from the tool result, so it shows even if the model failed after
    final = {"role": "assistant", "content": turn.reply}
    if turn.status == "ok":                                   # a busy or step-cap reply shows no card
        turn.card = cards.from_results(results)
        if turn.card:
            final[cards.CARD_KEY] = turn.card
        planned = [r for name, r in results if name == "plan_meal" and r.get("status") == "ok"]
        turn.plans = cards.plan_options(planned[-1]) if planned else None
    new.append(final)
    return turn
