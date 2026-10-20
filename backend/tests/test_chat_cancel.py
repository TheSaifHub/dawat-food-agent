"""A chat turn stops when the client leaves (D-075). Consent and money are involved (a cart that keeps changing after the
user walked away, a confirmation card nobody saw), so these tests are strict.

The stop is looked at only BETWEEN steps: before each model call and before each tool call. A tool already running
always finishes whole. The model is a scripted fake (tests/test_agent_loop.Script); tools and the database are real,
rolled back."""

import asyncio
import json
import threading
import time
from contextlib import contextmanager

import pytest

from app.agent import cards, llm, loop, store
from app.agent.loop import CANCELLED_MESSAGE, CANCELLED_WITH_CART, NOT_RUN_CANCELLED, run_turn
from app.api import chat as chat_api
from app.auth import get_verifier
from app.db import get_conn
from app.main import app
from app.tools import cart as cart_tools
from tests.test_agent_loop import PROMPT, Script, assert_well_formed


@pytest.fixture
def users(demo_users):
    arjun, family, priya = demo_users
    return {"arjun": arjun, "priya": priya}


def veg_items(db, n=2):
    """Veg dishes in Madhapur from different restaurants, the same ones every run."""
    return db.execute("""select distinct on (b.restaurant_id) m.item_id, b.branch_id
                         from public.menu_items m join public.branches b using (restaurant_id)
                         join public.dishes d using (dish_id)
                         where b.area_id = 'madhapur' and m.is_available and b.open_for_demo and d.is_veg
                         order by b.restaurant_id, m.item_id limit %s""", (n,)).fetchall()


def nonveg_item(db):
    return db.execute("""select m.item_id, b.branch_id from public.menu_items m
                         join public.branches b using (restaurant_id) join public.dishes d using (dish_id)
                         where b.area_id = 'madhapur' and m.is_available and b.open_for_demo and not d.is_veg
                         order by m.item_id, b.branch_id limit 1""").fetchone()


def add(item):
    return ("add_to_cart", {"item_id": item["item_id"], "branch_id": item["branch_id"]})


def cart_lines(db, user):
    c = cart_tools.view_cart(db, user)
    return {(b["branch_id"], i["item_id"]): i["qty"] for b in c.get("branches", []) for i in b["items"]}


class StopAfter:
    """should_stop that says go on until `n` steps have been reported, then stop (set by on_step)."""

    def __init__(self, n):
        self.n, self.seen = n, 0

    def on_step(self, trace):
        self.seen += 1

    def __call__(self):
        return self.seen >= self.n


# ─── the loop ────────────────────────────────────────────────────────────────────────────────────────────

def test_a_normal_turn_is_unaffected_by_a_stop_check_that_never_fires(db, users):
    a, b = veg_items(db)
    script = Script([add(a), add(b)], "Added both.")
    turn = run_turn(db, [], "add both", users["priya"], chat=script, should_stop=lambda: False, **PROMPT)
    assert (turn.status, turn.reply) == ("ok", "Added both.")
    assert set(cart_lines(db, users["priya"])) == {(a["branch_id"], a["item_id"]), (b["branch_id"], b["item_id"])}
    assert not any(NOT_RUN_CANCELLED in json.dumps(m) for m in turn.messages)
    assert [t["ok"] for t in turn.traces] == [True, True] and len(script.seen) == 2
    assert_well_formed(turn.messages)


def test_stopped_before_the_first_model_call_nothing_runs(db, users):
    script = Script()                                                # any model call would fail
    turn = run_turn(db, [], "add something", users["priya"], chat=script, should_stop=lambda: True, **PROMPT)
    assert (turn.status, turn.reply, turn.traces, turn.card, turn.plans) == ("cancelled", CANCELLED_MESSAGE, [], None, None)
    assert script.seen == [] and cart_lines(db, users["priya"]) == {}
    assert turn.messages == [{"role": "user", "content": "add something"}, {"role": "assistant", "content": CANCELLED_MESSAGE}]


def test_stopped_between_two_tool_calls_the_second_never_runs(db, users):
    a, b = veg_items(db)
    stop = StopAfter(1)
    script = Script([add(a), add(b)], "unreachable")
    turn = run_turn(db, [], "add both", users["priya"], chat=script, on_step=stop.on_step, should_stop=stop, **PROMPT)
    lines = cart_lines(db, users["priya"])
    assert lines == {(a["branch_id"], a["item_id"]): 1}              # the first stays whole, the second never happened
    assert (turn.status, turn.reply) == ("cancelled", CANCELLED_WITH_CART)
    assert len(turn.traces) == 1 and len(script.seen) == 1           # and the model was not asked again
    tool_answers = [m["content"] for m in turn.messages if m["role"] == "tool"]
    assert tool_answers[1] == NOT_RUN_CANCELLED                      # the unrun call is answered: the history is valid
    assert_well_formed(turn.messages)


def test_a_stop_during_a_tool_does_not_cut_it_short(db, users, monkeypatch):
    a, b = veg_items(db)
    flag = {"stop": False}
    real = loop._run_one

    def run_one(conn, call, ctx):
        flag["stop"] = True                                          # the client leaves while this tool is running
        return real(conn, call, ctx)
    monkeypatch.setattr(loop, "_run_one", run_one)
    turn = run_turn(db, [], "add both", users["priya"], chat=Script([add(a), add(b)], "x"),
                    should_stop=lambda: flag["stop"], **PROMPT)
    assert cart_lines(db, users["priya"]) == {(a["branch_id"], a["item_id"]): 1}      # that tool finished whole
    assert turn.traces[0]["ok"] is True and turn.status == "cancelled"
    assert_well_formed(turn.messages)


def test_what_was_committed_before_the_stop_is_a_valid_cart(db, users):
    """Restaurant A's dish is in; restaurant B's never was. The cart is a normal, orderable cart for A alone."""
    a, b = veg_items(db)
    stop = StopAfter(1)
    run_turn(db, [], "add both", users["priya"], chat=Script([add(a), add(b)], "x"), on_step=stop.on_step,
             should_stop=stop, **PROMPT)
    c = cart_tools.view_cart(db, users["priya"])
    assert [br["branch_id"] for br in c["branches"]] == [a["branch_id"]]
    assert c["can_confirm"] is True and c["grand_total"] == c["branches"][0]["total"]


def test_a_turn_that_finishes_as_the_client_leaves_shows_no_card_and_no_plans(db, users):
    item = nonveg_item(db)                                           # a saved vegetarian asking for non-veg: a diet card
    control = run_turn(db, [], "add it", users["priya"], chat=Script([add(item)], "Is it for someone else?"), **PROMPT)
    assert control.status == "ok" and control.card and control.card["kind"] == "diet"      # the control: it has a card
    stop = StopAfter(1)
    turn = run_turn(db, [], "add it", users["priya"], chat=Script([add(item)], "Is it for someone else?"),
                    on_step=stop.on_step, should_stop=stop, **PROMPT)
    assert turn.status == "cancelled" and turn.card is None and turn.plans is None
    assert cards.pending(turn.messages) is None                      # nothing a later "yes" could act on


def test_the_model_finishing_after_the_client_left_still_leaves_no_card(db, users):
    item = nonveg_item(db)
    flag = {"stop": False}

    def final_text(messages):
        flag["stop"] = True                                          # the client leaves while the model writes its answer
        return "Is it for someone else?"
    turn = run_turn(db, [], "add it", users["priya"], chat=Script([add(item)], final_text),
                    should_stop=lambda: flag["stop"], **PROMPT)
    assert turn.status == "cancelled" and turn.card is None and turn.plans is None
    assert cards.pending(turn.messages) is None


def test_a_card_earned_before_a_mid_turn_stop_is_not_shown(db, users):
    """The first tool asks the diet question (a card); the stop lands before the second tool. The card must not survive:
    nobody saw it, and a later yes could otherwise act on it."""
    item, other = nonveg_item(db), veg_items(db)[0]
    control = run_turn(db, [], "add both", users["priya"], chat=Script([add(item), add(other)], "Done."), **PROMPT)
    assert control.card and control.card["kind"] == "diet"                 # the control: both tools ran, a card is shown
    stop = StopAfter(1)
    turn = run_turn(db, [], "add both", users["priya"], chat=Script([add(item), add(other)], "unreachable"),
                    on_step=stop.on_step, should_stop=stop, **PROMPT)
    assert turn.status == "cancelled" and turn.card is None and turn.plans is None
    assert cards.pending(turn.messages) is None
    assert [m["content"] for m in turn.messages if m["role"] == "tool"][-1] == NOT_RUN_CANCELLED


def test_plan_options_are_not_built_for_a_cancelled_turn(db, users):
    request = {"query": "x"}
    plan_call = ("plan_meal", {"budget": 800, "people": 2, "veg_count": 2, "meal_type": "dinner", "area": "Madhapur"})
    control = run_turn(db, [], "plan", users["priya"], chat=Script([plan_call], "Here are plans."), **PROMPT)
    assert control.status == "ok" and control.plans                  # the control
    flag = {"stop": False}

    def final_text(messages):
        flag["stop"] = True
        return "Here are plans."
    turn = run_turn(db, [], "plan", users["priya"], chat=Script([plan_call], final_text), should_stop=lambda: flag["stop"], **PROMPT)
    assert turn.status == "cancelled" and turn.plans is None and request


def test_the_conversation_carries_on_after_a_cancelled_turn(db, users):
    a, b = veg_items(db)
    stop = StopAfter(1)
    first = run_turn(db, [], "add both", users["priya"], chat=Script([add(a), add(b)], "x"), on_step=stop.on_step,
                     should_stop=stop, **PROMPT)
    history = first.messages
    script = Script("Anything else?")
    second = run_turn(db, history, "no thanks", users["priya"], chat=script, **PROMPT)
    assert second.status == "ok"
    sent = script.seen[0]
    asked = [c["id"] for m in sent if m.get("role") == "assistant" for c in m.get("tool_calls") or []]
    answered = [m["tool_call_id"] for m in sent if m.get("role") == "tool"]
    assert sorted(asked) == sorted(answered)                          # a request the model provider would accept


def test_a_payment_already_built_survives_a_stop(db, users, monkeypatch):
    """place_order's payment object is built from the tool result; a stop afterwards must not lose it."""
    a, _ = veg_items(db)
    real = loop._run_one
    state = {"n": 0}

    def run_one(conn, call, ctx):
        state["n"] += 1
        result, error, ms = real(conn, call, ctx)
        if call["name"] == "place_order":
            result = {"status": "payment_required", "cart_id": "c-1", "quote_id": "q-1", "grand_total": 321}
        return result, error, ms
    monkeypatch.setattr(loop, "_run_one", run_one)
    stop = StopAfter(1)
    turn = run_turn(db, [], "order", users["priya"], chat=Script([("place_order", {"cart_id": "c-1"}), add(a)], "x"),
                    on_step=stop.on_step, should_stop=stop, **PROMPT)
    assert turn.payment == {"cart_id": "c-1", "quote_id": "q-1", "grand_total": 321}
    assert turn.status == "cancelled" and state["n"] == 1


def test_saving_a_cancelled_turn_and_forgetting_a_card(db, users):
    cid = db.execute("insert into public.conversations (user_id) values (%s) returning conversation_id",
                     (users["priya"],)).fetchone()["conversation_id"]
    item = nonveg_item(db)
    turn = run_turn(db, [], "add it", users["priya"], chat=Script([add(item)], "Is it for someone else?"), **PROMPT)
    assert turn.card                                                  # a finished turn with a card
    reply_id = store.save_turn(db, cid, turn)
    assert cards.pending(store.load_history(db, cid)) is not None
    store.forget_card(db, reply_id)
    history = store.load_history(db, cid)
    assert cards.pending(history) is None
    assert history[-1]["content"] == "Is it for someone else?"        # the words stay, only the card goes
    assert db.execute("select count(*) as n from public.agent_traces where conversation_id = %s", (cid,)).fetchone()["n"] == 1


# ─── the endpoint: a real client disconnect, driven at the ASGI level ────────────────────────────────────

@pytest.fixture
def signed_in(db, users, verifier, make_token):
    app.dependency_overrides[get_verifier] = lambda: verifier

    def test_db():
        yield db
    app.dependency_overrides[get_conn] = test_db

    @contextmanager
    def same_db():
        yield db
    app.dependency_overrides[chat_api.chat_connection] = lambda: same_db
    return {name: make_token(uid) for name, uid in users.items()}


async def drive(token, body, *, disconnect_when, gone: asyncio.Event | None = None):
    """POST /chat straight into the ASGI app. `disconnect_when(event_name)` returning True makes the client go away
    right after it receives that event (later sends fail, like a real closed connection). `gone` can also be set from
    outside (from another thread, via call_soon_threadsafe) to make the client leave at a moment the test chooses."""
    gone = gone or asyncio.Event()
    got: list[str] = []
    state = {"sent_body": False}

    async def receive():
        if not state["sent_body"]:
            state["sent_body"] = True
            return {"type": "http.request", "body": json.dumps(body).encode(), "more_body": False}
        await gone.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if gone.is_set():
            raise OSError("client gone")
        if message["type"] == "http.response.body" and message.get("body"):
            for block in message["body"].decode().strip().split("\n\n"):
                name = block.split("\n", 1)[0].removeprefix("event: ")
                got.append(name)
                if disconnect_when(name):
                    gone.set()

    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"}, "http_version": "1.1", "method": "POST",
             "path": "/chat", "raw_path": b"/chat", "root_path": "", "scheme": "http", "query_string": b"",
             "headers": [(b"host", b"test"), (b"content-type", b"application/json"),
                         (b"authorization", f"Bearer {token}".encode())],
             "client": ("127.0.0.1", 5000), "server": ("test", 80)}
    await asyncio.wait_for(app(scope, receive, send), timeout=20)
    return got


def wait_for_worker(timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not [t for t in threading.enumerate() if t.name == "dawat-chat-turn" and t.is_alive()]:
            return
        time.sleep(0.02)
    raise AssertionError("the chat worker did not finish")


def pause_after_first_tool(monkeypatch):
    """The worker waits after its first tool, so the test can disconnect at a known point (no timing luck)."""
    paused, resume = threading.Event(), threading.Event()
    real = loop._run_one
    count = {"n": 0}

    def run_one(conn, call, ctx):
        out = real(conn, call, ctx)
        count["n"] += 1
        if count["n"] == 1:
            paused.set()
            assert resume.wait(20)
        return out
    monkeypatch.setattr(loop, "_run_one", run_one)
    return paused, resume


def pause_after_first_step_event(monkeypatch):
    """The worker waits right after its first step has been handed to the stream (so the stream's next send happens
    while the worker is paused)."""
    paused, resume = threading.Event(), threading.Event()
    real = loop.run_turn

    def run_turn_pausing(*args, on_step=None, **kwargs):
        n = {"steps": 0}

        def stepper(trace):
            on_step(trace)
            n["steps"] += 1
            if n["steps"] == 1:
                paused.set()
                assert resume.wait(20)
        return real(*args, on_step=stepper, **kwargs)
    monkeypatch.setattr(loop, "run_turn", run_turn_pausing)
    return paused, resume


def test_a_real_disconnect_stops_the_turn_at_the_next_step(signed_in, db, users, monkeypatch):
    a, b = veg_items(db)
    monkeypatch.setattr(llm, "chat", Script([add(a), add(b)], "unreachable"))
    paused, resume = pause_after_first_tool(monkeypatch)
    monkeypatch.setattr(chat_api, "DISCONNECT_POLL_S", 0.05)

    async def scenario():
        task = asyncio.create_task(drive(signed_in["priya"], {"message": "add both"}, disconnect_when=lambda e: e == "start"))
        await asyncio.get_running_loop().run_in_executor(None, paused.wait, 20)
        got = await task                                              # the client left; the stream ended
        resume.set()                                                  # now the worker may go on: it must not
        return got
    got = asyncio.run(scenario())
    wait_for_worker()
    assert got == ["start"]
    assert cart_lines(db, users["priya"]) == {(a["branch_id"], a["item_id"]): 1}      # the second dish never went in
    saved = db.execute("select role, content from public.messages order by message_id desc limit 1").fetchone()
    assert saved["role"] == "assistant" and saved["content"] == CANCELLED_WITH_CART


def test_the_response_closes_its_stream_when_the_client_is_gone(signed_in, db, users, monkeypatch):
    """Not left for garbage collection: the generator's own `finally` is what tells the turn to stop."""
    a, b = veg_items(db)
    monkeypatch.setattr(llm, "chat", Script([add(a), add(b)], "unreachable"))
    paused, resume = pause_after_first_step_event(monkeypatch)
    monkeypatch.setattr(chat_api, "DISCONNECT_POLL_S", 60)                 # the quiet-stream poll cannot be what notices
    spies = []
    original = chat_api._events

    class Spy:
        def __init__(self, gen):
            self.gen, self.closed = gen, False

        def __aiter__(self):
            return self

        async def __anext__(self):
            return await self.gen.__anext__()

        async def aclose(self):
            self.closed = True
            await self.gen.aclose()

    def spying(*args, **kwargs):
        spies.append(Spy(original(*args, **kwargs)))
        return spies[-1]
    monkeypatch.setattr(chat_api, "_events", spying)

    async def scenario():
        # the client leaves after `start`; the next event's send then fails (as with a closed connection)
        task = asyncio.create_task(drive(signed_in["priya"], {"message": "add both"}, disconnect_when=lambda e: e == "start"))
        await asyncio.get_running_loop().run_in_executor(None, paused.wait, 20)
        await task
        closed_by_response = spies[0].closed
        resume.set()
        return closed_by_response
    closed = asyncio.run(scenario())
    wait_for_worker()
    assert closed is True
    assert cart_lines(db, users["priya"]) == {(a["branch_id"], a["item_id"]): 1}


def run_with_card_turn(signed_in, db, monkeypatch, *, leave_after_save):
    item = nonveg_item(db)                                            # saved vegetarian + non-veg dish = a diet card
    monkeypatch.setattr(llm, "chat", Script([add(item)], "Is it for someone else?"))
    monkeypatch.setattr(chat_api, "DISCONNECT_POLL_S", 0.05)
    holder: dict = {}
    real_save = store.save_turn

    def save_then_maybe_leave(conn, conversation_id, turn):
        reply_id = real_save(conn, conversation_id, turn)
        if leave_after_save:                                          # the client leaves just as the turn is saved
            holder["loop"].call_soon_threadsafe(holder["gone"].set)
            time.sleep(0.6)                                           # long enough for the stream to notice
        return reply_id
    monkeypatch.setattr(store, "save_turn", save_then_maybe_leave)

    async def scenario():
        holder["loop"], holder["gone"] = asyncio.get_running_loop(), asyncio.Event()
        return await drive(signed_in["priya"], {"message": "add it"}, disconnect_when=lambda e: False, gone=holder["gone"])
    got = asyncio.run(scenario())
    wait_for_worker()
    row = db.execute("select payload from public.messages where role = 'assistant' order by message_id desc limit 1").fetchone()
    return got, row["payload"]


def test_a_card_for_a_turn_that_finished_as_the_client_left_is_stripped(signed_in, db, monkeypatch):
    got, payload = run_with_card_turn(signed_in, db, monkeypatch, leave_after_save=True)
    assert got[0] == "start" and "done" not in got                     # the client really left mid-stream
    assert cards.CARD_KEY not in payload and payload["content"] == "Is it for someone else?"


def test_the_same_turn_keeps_its_card_when_the_client_stays(signed_in, db, monkeypatch):
    got, payload = run_with_card_turn(signed_in, db, monkeypatch, leave_after_save=False)
    assert got == ["start", "step", "reply", "done"]
    assert payload[cards.CARD_KEY]["kind"] == "diet"                   # the control: without a disconnect the card stays


def test_a_normal_turn_over_the_same_driver_is_untouched(signed_in, db, users, monkeypatch):
    a, b = veg_items(db)
    monkeypatch.setattr(llm, "chat", Script([add(a), add(b)], "Added both."))
    got = asyncio.run(drive(signed_in["priya"], {"message": "add both"}, disconnect_when=lambda e: False))
    wait_for_worker()
    assert got == ["start", "step", "step", "reply", "done"]
    assert set(cart_lines(db, users["priya"])) == {(a["branch_id"], a["item_id"]), (b["branch_id"], b["item_id"])}
    saved = db.execute("select content from public.messages where role = 'assistant' order by message_id desc limit 1").fetchone()
    assert saved["content"] == "Added both."
