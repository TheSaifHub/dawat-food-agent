"""POST /chat (Phase 6e, D-037): sign-in, the hourly limit, conversations per user, live steps, saved turns.

Identity and the usage limit get the strict tests; the stream format and persistence get plain ones. The model
is a scripted fake (tests/test_agent_loop.Script); tools and the database are real, rolled back."""

import json
import uuid
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.agent import llm
from app.agent.prompts import CURRENT
from app.api import chat as chat_api
from app.auth import get_verifier
from app.db import get_conn
from app.main import app
from tests.test_agent_loop import BUSY, Script

client = TestClient(app)


@pytest.fixture
def users(demo_users):
    arjun, family, priya = demo_users
    return {"arjun": arjun, "priya": priya}


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


def post(token, body):
    return client.post("/chat", json=body, headers={"Authorization": f"Bearer {token}"} if token else {})


def events(response) -> list[tuple[str, dict]]:
    out = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def model(monkeypatch, *steps) -> Script:
    script = Script(*steps)
    monkeypatch.setattr(llm, "chat", script)
    return script


def rows(db, sql, *args):
    return db.execute(sql, args).fetchall()


# ─── identity and the limit (strict) ─────────────────────────────────────────────────────────────────────

def test_no_token_no_chat(verifier):
    app.dependency_overrides[get_verifier] = lambda: verifier
    assert post(None, {"message": "hi"}).status_code == 401


@pytest.mark.parametrize("body", [{"message": "hi", "user_id": "someone"}, {"message": ""}, {"message": "   "},
                                  {"message": 5}, {"message": "x" * 2001}, {"conversation_id": "nope", "message": "hi"}])
def test_a_bad_body_is_refused_before_any_model_call(signed_in, monkeypatch, body):
    script = model(monkeypatch)                                             # no steps: any call would fail
    assert post(signed_in["priya"], body).status_code == 422 and script.seen == []


def test_another_users_conversation_is_answered_as_missing(signed_in, db, users, monkeypatch):
    model(monkeypatch, "Hello Priya")
    first = events(post(signed_in["priya"], {"message": "hi"}))
    cid = first[0][1]["conversation_id"]
    script = model(monkeypatch)
    for cid_try in (cid, str(uuid.uuid4())):
        r = post(signed_in["arjun"], {"message": "show me her chat", "conversation_id": cid_try})
        assert r.status_code == 404 and r.json()["status"] == "not_found"
    assert script.seen == []
    assert rows(db, "select count(*) as n from public.messages where conversation_id = %s", cid)[0]["n"] == 2


def test_the_hourly_limit_stops_before_the_model(signed_in, db, users, monkeypatch):
    conv = rows(db, "insert into public.conversations (user_id) values (%s) returning conversation_id", users["priya"])
    for i in range(chat_api.LIMIT_PER_HOUR):
        db.execute("insert into public.messages (conversation_id, role, content) values (%s, 'user', %s)",
                   (conv[0]["conversation_id"], f"m{i}"))
    script = model(monkeypatch)
    r = post(signed_in["priya"], {"message": "one more"})
    assert r.status_code == 429 and r.json()["message"] == chat_api.LIMIT_MESSAGE and script.seen == []
    model(monkeypatch, "Hi Arjun")                                          # another user is not limited
    assert post(signed_in["arjun"], {"message": "hi"}).status_code == 200


def test_messages_older_than_an_hour_do_not_count(signed_in, db, users, monkeypatch):
    conv = rows(db, "insert into public.conversations (user_id) values (%s) returning conversation_id", users["priya"])
    for i in range(chat_api.LIMIT_PER_HOUR):
        db.execute("""insert into public.messages (conversation_id, role, content, created_at)
                      values (%s, 'user', %s, now() - interval '61 minutes')""", (conv[0]["conversation_id"], f"m{i}"))
    model(monkeypatch, "Hi again")
    assert post(signed_in["priya"], {"message": "hi"}).status_code == 200


# ─── the stream and what is saved (plain) ────────────────────────────────────────────────────────────────

def test_steps_stream_live_then_the_reply_and_everything_is_saved(signed_in, db, monkeypatch):
    model(monkeypatch, [("search_dishes", {"query": "chicken biryani", "area": "Madhapur"})], "Found some!")
    r = post(signed_in["priya"], {"message": "biryani in Madhapur"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    ev = events(r)
    assert [e for e, _ in ev] == ["start", "step", "reply", "done"]
    step = ev[1][1]
    assert (step["tool"], step["status"], step["ok"]) == ("search_dishes", "ok", True) and step["counts"]["results_count"]
    reply = ev[2][1]
    assert (reply["text"], reply["status"]) == ("Found some!", "ok")
    cid = ev[0][1]["conversation_id"]
    saved = rows(db, "select role, content, payload from public.messages where conversation_id = %s order by message_id", cid)
    assert [m["role"] for m in saved] == ["user", "assistant", "tool", "assistant"]
    assert saved[0]["content"] == "biryani in Madhapur" and saved[1]["content"] == "[calls search_dishes]"
    assert saved[1]["payload"]["tool_calls"][0]["function"]["name"] == "search_dishes"
    traces = rows(db, "select step, tool_name, ok, message_id, prompt_version from public.agent_traces "
                      "where conversation_id = %s", cid)
    last = rows(db, "select max(message_id) as m from public.messages where conversation_id = %s", cid)[0]["m"]
    assert [(t["step"], t["tool_name"], t["ok"], t["message_id"], t["prompt_version"]) for t in traces] == [
        (1, "search_dishes", True, last, CURRENT)]


def test_the_next_turn_replays_the_conversation(signed_in, monkeypatch):
    model(monkeypatch, [("search_dishes", {"query": "chicken biryani", "area": "Madhapur"})], "Found some!")
    cid = events(post(signed_in["priya"], {"message": "biryani in Madhapur"}))[0][1]["conversation_id"]
    script = model(monkeypatch, "The first one is ₹280.")
    events(post(signed_in["priya"], {"message": "which is cheapest?", "conversation_id": cid}))
    sent = script.seen[0]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "tool", "assistant", "user"]
    assert sent[2]["provider_specific_fields"] == {"thought_signatures": ["sig"]}      # replayed unchanged
    assert sent[-1]["content"] == "which is cheapest?" and sent[0]["content"].startswith("You are Dawat AI")


def test_busy_is_a_normal_reply_and_still_saved(signed_in, db, monkeypatch):
    model(monkeypatch, BUSY)
    ev = events(post(signed_in["priya"], {"message": "hi"}))
    assert ev[1] == ("reply", {"text": llm.BUSY_MESSAGE, "status": "busy", "message_id": ev[1][1]["message_id"],
                               "card": None, "card_text": None, "plans": None, "payment": None})   # a busy reply shows no card (D-046)


def test_a_crash_is_a_generic_error_event(signed_in, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("secret internal detail")
    monkeypatch.setattr(llm, "chat", boom)
    r = post(signed_in["priya"], {"message": "hi"})
    ev = events(r)
    assert [e for e, _ in ev] == ["start", "error", "done"] and "secret" not in r.text
    assert ev[1][1]["message"] == chat_api.ERROR_MESSAGE


# ─── plan options as cards (D-058) ──────────────────────────────────────────────────────────────────────

PLAN_REQUEST = {"budget": 900, "people": 2, "veg_count": 1, "area": "Madhapur"}


def test_plan_options_come_from_the_planner_itself(signed_in, db, users, monkeypatch):
    from app.planner.plan import plan_meal
    model(monkeypatch, [("plan_meal", PLAN_REQUEST)], "Here are three ideas.")
    ev = events(post(signed_in["priya"], {"message": "₹900 for 2, one is veg, Madhapur"}))
    plans = ev[-2][1]["plans"]
    truth = plan_meal(db, PLAN_REQUEST, users["priya"])            # the same request for the same user, planned again
    assert truth["status"] == "ok" and plans
    assert [(p["plan_id"], p["label"], p["grand_total"], p["diet_note"]) for p in plans] == [
        (t["plan_id"], t["label"], t["grand_total"], t["diet_note"]) for t in truth["plans"]]
    for shown, real in zip(plans, truth["plans"]):
        assert [(i["name"], i["qty"], i["line_total"], i["is_veg"]) for r in shown["restaurants"] for i in r["items"]] == [
            (i["name"], i["qty"], i["line_total"], i["is_veg"]) for r in real["restaurants"] for i in r["items"]]
        assert sum(r["total"] for r in shown["restaurants"]) == shown["grand_total"]


@pytest.mark.parametrize("request_", [{"people": 2, "area": "Madhapur"},                   # needs_info: no budget
                                      {"budget": 150, "people": 4, "area": "Madhapur"}])    # over_budget
def test_no_plan_cards_unless_the_planner_said_ok(signed_in, monkeypatch, request_):
    model(monkeypatch, [("plan_meal", request_)], "Tell me more.")
    ev = events(post(signed_in["priya"], {"message": "plan something"}))
    assert ev[-2][0] == "reply" and ev[-2][1]["plans"] is None


def test_a_busy_turn_after_planning_shows_no_plan_cards(signed_in, monkeypatch):
    model(monkeypatch, [("plan_meal", PLAN_REQUEST)], BUSY)
    ev = events(post(signed_in["priya"], {"message": "₹900 for 2"}))
    assert ev[-2][1]["status"] == "busy" and ev[-2][1]["plans"] is None