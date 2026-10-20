"""Saving and loading Dawat AI conversations (Phase 6e, D-037). Plain functions on a connection, like the tools.

    open_conversation(conn, user_id, conversation_id=None) → conversation_id, or None if it isn't this user's
    load_history(conn, conversation_id) → the earlier messages, in the LLM's format, ready for run_turn
    save_turn(conn, conversation_id, turn) → the message_id of the reply (traces point at it)
    messages_in_last_hour(conn, user_id) → how many messages this user sent in the last hour (the usage limit)
    take_daily_slot(conn, cap) → True and counted, or False when today's global cap is reached (D-048)

Identity: every lookup is by (conversation_id AND user_id from the verified token). Another user's conversation is
answered exactly like one that doesn't exist (None), as with carts and orders (D-026).
"""

import json
import uuid
from contextlib import contextmanager

from psycopg import Connection
from psycopg.types.json import Jsonb

HISTORY_MESSAGES = 40       # the most recent messages replayed to the model (the token budget, D-033/D-035)
CONTENT_LIMIT = 20_000      # messages.content check (0003)


def open_conversation(conn: Connection, user_id: uuid.UUID, conversation_id=None) -> uuid.UUID | None:
    if conversation_id is None:
        return conn.execute("insert into public.conversations (user_id) values (%s) returning conversation_id",
                            (user_id,)).fetchone()["conversation_id"]
    try:
        cid = uuid.UUID(str(conversation_id))
    except ValueError:
        return None
    row = conn.execute("select conversation_id from public.conversations where conversation_id = %s and user_id = %s",
                       (cid, user_id)).fetchone()
    return row["conversation_id"] if row else None


def load_history(conn: Connection, conversation_id: uuid.UUID, limit: int = HISTORY_MESSAGES) -> list[dict]:
    """The last `limit` messages, starting at a user message so a tool call is never separated from its result."""
    rows = conn.execute("""select payload from public.messages where conversation_id = %s and payload is not null
                           order by message_id desc limit %s""", (conversation_id, limit)).fetchall()
    history = [r["payload"] for r in reversed(rows)]
    while history and history[0].get("role") != "user":
        history.pop(0)
    return history


def _readable(message: dict) -> str:
    """What messages.content holds: the text the chat shows, or a short label for tool traffic."""
    if message["role"] == "tool":
        return f"[{message.get('name', 'tool')} result]"
    if message.get("tool_calls"):
        return "[calls " + ", ".join(c["function"]["name"] for c in message["tool_calls"]) + "]"
    return (message.get("content") or "")[:CONTENT_LIMIT]


def save_turn(conn: Connection, conversation_id: uuid.UUID, turn) -> int:
    """Every message of the turn (payload as sent to the model) and every tool trace, in one transaction."""
    with conn.transaction():
        reply_id = None
        for m in turn.messages:
            payload = json.loads(json.dumps(m, default=str))           # plain JSON (LiteLLM objects included)
            reply_id = conn.execute("""insert into public.messages (conversation_id, role, content, payload)
                                       values (%s, %s, %s, %s) returning message_id""",
                                    (conversation_id, m["role"], _readable(m), Jsonb(payload))).fetchone()["message_id"]
        for t in turn.traces:
            conn.execute("""insert into public.agent_traces (conversation_id, message_id, step, tool_name, arguments,
                                result_summary, ok, error, latency_ms, provider, model, prompt_version)
                            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                         (conversation_id, reply_id, t["step"], t["tool_name"], Jsonb(t["arguments"]),
                          Jsonb(t["result_summary"]), t["ok"], t["error"], t["latency_ms"], t["provider"], t["model"],
                          t["prompt_version"]))
        conn.execute("update public.conversations set updated_at = now() where conversation_id = %s", (conversation_id,))
    return reply_id


def forget_card(conn: Connection, message_id: int) -> None:
    """Remove the confirmation card from a saved reply nobody saw (the client left before it was delivered), so the
    next message's yes can never act on it (D-075). The reply text and everything else stay."""
    from app.agent.cards import CARD_KEY
    conn.execute("update public.messages set payload = payload - %s where message_id = %s", (CARD_KEY, message_id))


def messages_in_last_hour(conn: Connection, user_id: uuid.UUID) -> int:
    return conn.execute("""select count(*) as n from public.messages m join public.conversations c using (conversation_id)
                           where c.user_id = %s and m.role = 'user' and m.created_at > now() - interval '1 hour'""",
                        (user_id,)).fetchone()["n"]


def take_daily_slot(conn: Connection, cap: int) -> bool:
    """One message's slot from today's global count (D-048), or False at the cap. A single statement: the conflict
    update only fires while count < cap, so two messages at once can't both take the last slot. The day is IST."""
    if cap <= 0:
        return False
    row = conn.execute("""insert into public.chat_daily_usage as u (day, count)
                          values ((now() at time zone 'Asia/Kolkata')::date, 1)
                          on conflict (day) do update set count = u.count + 1, updated_at = now()
                          where u.count < %s
                          returning u.count""", (cap,)).fetchone()
    return row is not None


@contextmanager
def user_turn_lock(conn: Connection, user_id: uuid.UUID):
    """One chat turn at a time per user (D-046, fourth rule-breaker run): two messages sent at once both loaded the
    same history and both used one diet card. A session-level advisory lock on the turn's own connection; the second
    request waits, then loads the history the first one saved."""
    conn.execute("select pg_advisory_lock(hashtextextended(%s, 46))", (str(user_id),))
    try:
        yield
    finally:
        conn.execute("select pg_advisory_unlock(hashtextextended(%s, 46))", (str(user_id),))
