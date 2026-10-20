"""Short order numbers (Phase 7e, migration 0013, D-057): "DW1042" in checkouts, history and tracking.

Strict where identity is involved: an order number is small and guessable, so tracking by number must be scoped to the
signed-in user exactly like tracking by id. Another user's number is answered like one that doesn't exist."""

import uuid

import pytest

from app.tools import demo, orders
from app.tools.history import get_user_history


@pytest.fixture
def two_visitors(db):
    ids = []
    for persona in ("priya", "arjun"):
        uid = uuid.uuid4()
        db.execute("insert into auth.users (id, is_anonymous) values (%s, true)", (uid,))
        db.execute("insert into public.users (user_id, display_name) values (%s, 'Guest')", (uid,))
        assert demo.start_demo(db, uid, persona, is_anonymous=True)["sample_orders"] == 3
        ids.append(uid)
    return ids


def numbers(db, user_id):
    return [r["order_no"] for r in db.execute("select order_no from public.orders where user_id = %s order by order_no",
                                              (user_id,))]


def test_every_order_has_a_unique_number_from_1001(db, two_visitors):
    a, b = two_visitors
    all_numbers = numbers(db, a) + numbers(db, b)
    assert len(set(all_numbers)) == 6 and min(all_numbers) >= 1001


def test_history_and_tracking_show_the_dw_number(db, two_visitors):
    a = two_visitors[0]
    history = get_user_history(db, a)
    shown = sorted(o["order_number"] for c in history["checkouts"] for o in c["orders"])
    assert shown == sorted(f"DW{n}" for n in numbers(db, a))
    assert all(o["is_sample"] for c in history["checkouts"] for o in c["orders"])
    first = history["checkouts"][0]["orders"][0]
    tracked = orders.track_order(db, a, first["order_id"])
    assert tracked["order_number"] == first["order_number"]
    # the tracking page links back to the branch and marks sample orders (7g)
    assert tracked["branch_id"] == first["branch_id"] and tracked["is_sample"] is True


@pytest.mark.parametrize("form", ["DW{n}", "dw{n}", "#DW{n}", "# DW {n}", "DW-{n}", "{n}", " {n} "])
def test_track_by_number_in_the_ways_people_write_it(db, two_visitors, form):
    a = two_visitors[0]
    n = numbers(db, a)[0]
    out = orders.track_order(db, a, form.format(n=n))
    assert out["status"] == "ok" and out["order_number"] == f"DW{n}"


def test_another_users_number_looks_like_no_order_at_all(db, two_visitors):
    a, b = two_visitors
    theirs = numbers(db, b)[0]
    out = orders.track_order(db, a, f"DW{theirs}")
    assert out == orders.NOT_FOUND
    assert orders.track_order(db, a, "DW999999") == orders.NOT_FOUND          # truly missing: the same answer


@pytest.mark.parametrize("bad", ["DWX12", "order 12", "DW 12 34", "", "DW", "12.5", "-12"])
def test_malformed_numbers_are_refused(db, two_visitors, bad):
    assert orders.track_order(db, two_visitors[0], bad)["status"] == "invalid_input"


def test_a_placed_order_reports_its_number(db, two_visitors):
    a = two_visitors[0]
    placed = [o for c in get_user_history(db, a)["checkouts"] for o in c["orders"]]
    assert all(o["order_number"].startswith("DW") and o["order_number"][2:].isdigit() for o in placed)
