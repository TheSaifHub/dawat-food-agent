"""POST /chat: one message to Dawat AI, answered as a stream of events (Phase 6e, D-037).

Saif's choices (Session 15):
  · Sign-in required. The user id comes only from the verified token (CurrentUser), as on every private route.
  · Live steps, then the reply: each tool call is sent as a `step` event the moment it finishes (the "Dawat AI is
    thinking" panel); the reply arrives whole in a `reply` event. No word-by-word streaming.
  · At most 30 messages per user per hour, to protect the free model quotas. Over it: HTTP 429 with a plain message,
    and the model is never called.
  · D-048 (Phase 7b): also a global cap per IST day across all users (CHAT_DAILY_CAP), because anyone can make
    demo accounts. A slot is taken atomically after the cheap checks; at the cap: HTTP 429 status "daily_limit".

Events (text/event-stream):
  start  {conversation_id}
  step   {step, tool, arguments, status, ok, latency_ms, counts}     one per tool call, live
  reply  {text, status: ok | busy | step_cap, message_id, card, card_text, plans, payment}   card: the confirmation card to
         show under the reply (D-046), or null; the user's next yes can act only on it. plans: this turn's plan_meal
         options as cards (D-058), or null. payment: {cart_id, quote_id, grand_total} when the user said yes to an
         order and it now needs paying (D-061): show a Pay button that calls POST /payments/start; or null
  error  {message}                                                   only if something crashed (details in the log)
  done   {}

D-075 (Session 26): when the client disconnects the turn stops at the next STEP BOUNDARY (before the next model
call or the next tool call, never inside a tool or a database write). What already committed stays; the saved turn
is consistent (every tool call answered, no card, no plan options); a card of a turn that finished just as the
client left is stripped, so a later "yes" can never act on a card nobody saw. See loop.run_turn(should_stop=...).

The request's own connection checks the limit and the conversation, and is committed before streaming starts
(Conn is function-scoped). The turn runs on a separate AUTOCOMMIT connection, so each tool's change is saved as
soon as it succeeds (D-034), and the whole turn (messages + traces) is saved in one transaction at the end.
"""

import asyncio
import json
import logging
import threading
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.requests import ClientDisconnect
from pydantic import BaseModel, ConfigDict, Field, StrictStr

from app import config
from app.agent import cards, llm, loop, store
from app.agent.prompts import system_prompt
from app.api.deps import Conn, CurrentUser
from app.db import get_pool

log = logging.getLogger("dawat.chat")
router = APIRouter(tags=["dawat ai"])

LIMIT_PER_HOUR = 30
LIMIT_MESSAGE = "You've reached the demo limit for now. Please try again in a little while."
DAILY_LIMIT_MESSAGE = ("Dawat AI has reached today's demo limit. Browsing, the cart and checkout still work. "
                       "Please try again tomorrow.")
ERROR_MESSAGE = "Something went wrong on our side. Please try again."
MAX_MESSAGE = 2000
DISCONNECT_POLL_S = 0.5            # how often a quiet stream checks that the client is still there


class ChatBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: Annotated[StrictStr, Field(min_length=1, max_length=MAX_MESSAGE)]
    conversation_id: uuid.UUID | None = None


@contextmanager
def autocommit_connection() -> Iterator:
    with get_pool().connection() as conn:
        conn.autocommit = True
        try:
            yield conn
        finally:
            conn.autocommit = False          # the pool's other users expect commit-at-end (get_conn)


def chat_connection() -> Callable:
    """The factory the turn's connection comes from (a dependency, so tests can hand in their rolled-back one)."""
    return autocommit_connection


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _step(trace: dict) -> dict:
    summary = trace["result_summary"]
    return {"step": trace["step"], "tool": trace["tool_name"], "arguments": trace["arguments"],
            "status": summary.get("status"), "ok": trace["ok"], "latency_ms": trace["latency_ms"],
            "counts": {k: v for k, v in summary.items() if k.endswith("_count")}}


class _ClosingStream(StreamingResponse):
    """A stream that always closes its generator when the response is over, however it ended. When the client is gone,
    Starlette raises out of the send and would leave the generator suspended until garbage collection; closing it here
    runs its `finally` at once, which tells the running turn to stop (D-075). A vanished client is expected, not an error."""

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        except ClientDisconnect:
            pass
        finally:
            aclose = getattr(self.body_iterator, "aclose", None)
            if aclose is not None:
                await aclose()


async def _events(request: Request, open_conn: Callable, user_id: uuid.UUID, conversation_id: uuid.UUID,
                  message: str) -> AsyncIterator[str]:
    cancel = threading.Event()                        # set when the client is gone; the turn looks at it between steps
    loop_ = asyncio.get_running_loop()
    events: asyncio.Queue = asyncio.Queue()

    def emit(item) -> None:
        try:
            loop_.call_soon_threadsafe(events.put_nowait, item)
        except RuntimeError:                          # the server is shutting down: nobody is listening
            pass

    def work():
        try:
            with open_conn() as conn, store.user_turn_lock(conn, user_id):    # one turn at a time per user
                text, version = system_prompt()
                turn = loop.run_turn(conn, store.load_history(conn, conversation_id), message, user_id,
                                     system_prompt=text, prompt_version=version, chat=llm.chat,
                                     on_step=lambda t: emit(("step", _step(t))), should_stop=cancel.is_set)
                reply_id = store.save_turn(conn, conversation_id, turn)
                if cancel.is_set() and turn.card:     # the client left as the turn finished: nobody saw this card
                    store.forget_card(conn, reply_id)
            emit(("reply", {"text": turn.reply, "status": turn.status, "message_id": reply_id,
                            "card": turn.card, "card_text": cards.text(turn.card) if turn.card else None,
                            "plans": turn.plans, "payment": turn.payment}))
        except Exception:
            log.exception("chat turn failed")
            emit(("error", {"message": ERROR_MESSAGE}))
        finally:
            emit(None)

    try:
        yield _sse("start", {"conversation_id": str(conversation_id)})
        threading.Thread(target=work, daemon=True, name="dawat-chat-turn").start()
        while True:
            try:
                item = await asyncio.wait_for(events.get(), timeout=DISCONNECT_POLL_S)
            except asyncio.TimeoutError:
                if await request.is_disconnected():
                    return                            # the finally below tells the turn to stop
                continue
            if item is None:
                break
            yield _sse(*item)
        yield _sse("done", {})
    finally:
        cancel.set()                                  # the client left (or the stream ended: then nothing is running)


@router.post("/chat")
def chat(request: Request, body: ChatBody, user: CurrentUser, conn: Conn,
         open_conn: Annotated[Callable, Depends(chat_connection)]):
    if not body.message.strip():
        return JSONResponse({"status": "invalid_input", "message": "The message is empty."}, status_code=422)
    if store.messages_in_last_hour(conn, user.user_id) >= LIMIT_PER_HOUR:
        return JSONResponse({"status": "rate_limited", "message": LIMIT_MESSAGE}, status_code=429)
    conversation_id = None
    if body.conversation_id is not None:                         # checked before a daily slot is spent on it
        conversation_id = store.open_conversation(conn, user.user_id, body.conversation_id)
        if conversation_id is None:
            return JSONResponse({"status": "not_found", "message": "No such conversation for this user."},
                                status_code=404)
    if not store.take_daily_slot(conn, config.CHAT_DAILY_CAP):
        return JSONResponse({"status": "daily_limit", "message": DAILY_LIMIT_MESSAGE}, status_code=429)
    if conversation_id is None:
        conversation_id = store.open_conversation(conn, user.user_id)
    return _ClosingStream(_events(request, open_conn, user.user_id, conversation_id, body.message.strip()),
                             media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
