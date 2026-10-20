"""The global daily chat cap (Phase 7b, D-048): one count per IST day across ALL users, so many demo accounts can't
use up the free Gemini quota.

Strict where it protects the quota: the model is never called at the cap, a refused request spends nothing, and
messages sent at the same moment can't push the count past the cap (a real race on separate connections)."""

import datetime as dt
import threading
from zoneinfo import ZoneInfo

import psycopg
import pytest
from psycopg.rows import dict_row

from app import config
from app.agent import store
from app.api import chat as chat_api
from tests.test_chat_api import model, post, rows, signed_in, users  # noqa: F401  (fixtures used by name)

CAP = 5


def ist_today() -> dt.date:
    return dt.datetime.now(ZoneInfo("Asia/Kolkata")).date()


def set_today(db, count: int) -> None:
    db.execute("""insert into public.chat_daily_usage (day, count) values (%s, %s)
                  on conflict (day) do update set count = excluded.count""", (ist_today(), count))


def today_count(db) -> int | None:
    row = db.execute("select count from public.chat_daily_usage where day = %s", (ist_today(),)).fetchone()
    return row["count"] if row else None


@pytest.fixture
def cap(monkeypatch):
    monkeypatch.setattr(config, "CHAT_DAILY_CAP", CAP)
    return CAP


def counts(db, user_id) -> tuple[int, int]:
    r = db.execute("""select (select count(*) from public.conversations where user_id = %s) as convs,
                             (select count(*) from public.messages m join public.conversations c using (conversation_id)
                              where c.user_id = %s) as msgs""", (user_id, user_id)).fetchone()
    return r["convs"], r["msgs"]


# ─── strict: at the cap nothing happens ──────────────────────────────────────────────────────────────────

def test_at_the_cap_the_model_is_never_called_and_nothing_is_saved(signed_in, db, users, cap, monkeypatch):
    set_today(db, cap)
    before = counts(db, users["priya"])
    script = model(monkeypatch)                                             # no steps: any call would fail
    r = post(signed_in["priya"], {"message": "biryani in Madhapur"})
    assert r.status_code == 429
    assert r.json() == {"status": "daily_limit", "message": chat_api.DAILY_LIMIT_MESSAGE}
    assert script.seen == [] and counts(db, users["priya"]) == before and today_count(db) == cap


def test_the_cap_is_shared_by_every_user(signed_in, db, cap, monkeypatch):
    set_today(db, cap - 1)
    model(monkeypatch, "Hi Priya")
    assert post(signed_in["priya"], {"message": "hi"}).status_code == 200
    script = model(monkeypatch)
    assert post(signed_in["arjun"], {"message": "hi"}).status_code == 429 and script.seen == []


def test_each_message_takes_exactly_one_slot(signed_in, db, cap, monkeypatch):
    set_today(db, 2)
    model(monkeypatch, "Hi")
    assert post(signed_in["priya"], {"message": "hi"}).status_code == 200
    assert today_count(db) == 3


def test_the_first_message_of_the_day_creates_the_ist_row(db, cap):
    db.execute("delete from public.chat_daily_usage where day = %s", (ist_today(),))   # rolled back by the fixture
    assert store.take_daily_slot(db, cap) is True and today_count(db) == 1


def test_cap_zero_turns_chat_off(db):
    set_today(db, 0)
    assert store.take_daily_slot(db, 0) is False and today_count(db) == 0


def test_cap_zero_turns_chat_off_on_a_fresh_day_too(db):
    db.execute("delete from public.chat_daily_usage where day = %s", (ist_today(),))   # rolled back by the fixture
    assert store.take_daily_slot(db, 0) is False and today_count(db) is None


# ─── strict: a refused request spends no slot ────────────────────────────────────────────────────────────

def test_the_hourly_limit_is_checked_first_and_spends_no_slot(signed_in, db, users, cap, monkeypatch):
    set_today(db, 0)
    conv = rows(db, "insert into public.conversations (user_id) values (%s) returning conversation_id", users["priya"])
    for i in range(chat_api.LIMIT_PER_HOUR):
        db.execute("insert into public.messages (conversation_id, role, content) values (%s, 'user', %s)",
                   (conv[0]["conversation_id"], f"m{i}"))
    r = post(signed_in["priya"], {"message": "one more"})
    assert r.status_code == 429 and r.json()["status"] == "rate_limited" and today_count(db) == 0


def test_someone_elses_conversation_spends_no_slot(signed_in, db, users, cap, monkeypatch):
    set_today(db, 0)
    conv = rows(db, "insert into public.conversations (user_id) values (%s) returning conversation_id", users["arjun"])
    r = post(signed_in["priya"], {"message": "hi", "conversation_id": str(conv[0]["conversation_id"])})
    assert r.status_code == 404 and today_count(db) == 0


def test_an_existing_conversation_continues_under_the_cap(signed_in, db, users, cap, monkeypatch):
    set_today(db, 0)
    conv = rows(db, "insert into public.conversations (user_id) values (%s) returning conversation_id", users["priya"])
    model(monkeypatch, "Hi again")
    r = post(signed_in["priya"], {"message": "hi", "conversation_id": str(conv[0]["conversation_id"])})
    assert r.status_code == 200 and str(conv[0]["conversation_id"]) in r.text and today_count(db) == 1


# ─── strict: the race ────────────────────────────────────────────────────────────────────────────────────

def test_messages_at_the_same_moment_cannot_pass_the_cap(db_conn):
    """8 messages race for the LAST slot, each on its own connection, released together. Exactly one may win.
    This commits to the LOCAL test database (D-052), so today's row is put back exactly as it was afterwards."""
    today = ist_today()
    saved = db_conn.execute("select count from public.chat_daily_usage where day = %s", (today,)).fetchone()
    db_conn.execute("""insert into public.chat_daily_usage (day, count) values (%s, %s)
                       on conflict (day) do update set count = excluded.count""", (today, CAP - 1))
    start, results = threading.Barrier(8), []

    def one():
        with psycopg.connect(config.DATABASE_URL, autocommit=True, row_factory=dict_row,
                             prepare_threshold=None) as conn:
            start.wait()
            results.append(store.take_daily_slot(conn, CAP))

    try:
        threads = [threading.Thread(target=one) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        final = db_conn.execute("select count from public.chat_daily_usage where day = %s", (today,)).fetchone()
        assert len(results) == 8 and results.count(True) == 1 and final["count"] == CAP
    finally:
        if saved is None:
            db_conn.execute("delete from public.chat_daily_usage where day = %s", (today,))
        else:
            db_conn.execute("update public.chat_daily_usage set count = %s where day = %s", (saved["count"], today))
