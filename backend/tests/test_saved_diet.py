"""A saved vegetarian diet in planning and in chat adds (Saif, Session 16, D-039). Strict: a vegetarian shown or sold
meat without being asked is the credibility failure CLAUDE.md names first."""

import json

import pytest

from app.agent import cards
from app.agent.loop import run_turn
from app.agent.tools import ToolContext, run_tool
from app.tools.cart import view_cart
from app.tools.planner import add_plan_to_cart, plan_meal
from tests.test_agent_loop import PROMPT, Script

DINNER = {"budget": 800, "people": 2, "meal_type": "dinner", "area": "Madhapur"}


@pytest.fixture
def users(demo_users):
    arjun, family, priya = demo_users
    return {"arjun": arjun, "priya": priya}


def items(db):
    """A non-veg and a veg main at the same open Madhapur branch."""
    row = db.execute("""
        select b.branch_id, max(m.item_id) filter (where not d.is_veg) as nonveg, max(m.item_id) filter (where d.is_veg) as veg
        from public.branches b join public.menu_items m using (restaurant_id) join public.dishes d using (dish_id)
        where b.area_id = 'madhapur' and b.open_for_demo and m.is_available and d.course = 'main'
        group by b.branch_id having count(*) filter (where not d.is_veg) > 0 and count(*) filter (where d.is_veg) > 0
        order by b.branch_id limit 1""").fetchone()
    return row["branch_id"], row["nonveg"], row["veg"]


def mains_are_veg(db, plan) -> list[bool]:
    ids = [it["item_id"] for r in plan["restaurants"] for it in r["items"] if it["role"] == "main"]
    return [r["is_veg"] for r in db.execute("select d.is_veg from public.menu_items m join public.dishes d using (dish_id) "
                                             "where m.item_id = any(%s)", (ids,)).fetchall()]


def set_diet(db, user, value):
    db.execute("update public.user_preferences set value = %s where user_id = %s and key = 'diet'",
               (json.dumps(value), user))


# ─── planning ────────────────────────────────────────────────────────────────────────────────────────────

def test_a_saved_vegetarian_is_one_of_the_vegetarians_in_every_plan(db, users):
    out = plan_meal(db, DINNER, users["priya"])
    assert out["status"] == "ok" and out["understood"]["veg_count"] == 1
    assert out["preferences_applied"]["veg_count"] == {"asked": 0, "used": 1}
    for p in out["plans"]:
        assert any(mains_are_veg(db, p)), p["label"]                    # checked with our own SQL


def test_no_saved_diet_or_a_non_veg_one_changes_nothing(db, users):
    for user in (None, users["arjun"]):
        out = plan_meal(db, DINNER, user)
        assert out["understood"]["veg_count"] == 0 and "preferences_applied" not in out


def test_a_request_that_already_counts_a_vegetarian_is_left_alone(db, users):
    out = plan_meal(db, {**DINNER, "veg_count": 2}, users["priya"])
    assert out["understood"]["veg_count"] == 2 and "preferences_applied" not in out


def test_eggetarian_is_treated_as_vegetarian(db, users):
    set_diet(db, users["arjun"], "eggetarian")
    out = plan_meal(db, {**DINNER, "people": 1}, users["arjun"])
    assert out["understood"]["veg_count"] == 1 and out["preferences_applied"]["diet"] == "eggetarian"
    assert all(all(mains_are_veg(db, p)) for p in out["plans"])          # a group of one vegetarian: veg only


def test_a_stated_overlap_that_no_longer_fits_is_dropped_not_refused(db, users):
    out = plan_meal(db, {**DINNER, "people": 1, "non_spicy_count": 1, "non_spicy_veg_count": 0}, users["priya"])
    assert out["status"] == "ok" and out["understood"]["veg_count"] == 1
    assert out["understood"]["non_spicy_veg_count"] is None


def test_needs_info_already_says_the_preference_was_applied(db, users):
    out = plan_meal(db, {"people": 2, "area": "Madhapur"}, users["priya"])
    assert out["status"] == "needs_info" and out["preferences_applied"]["diet"] == "vegetarian"


def test_picking_a_plan_finds_it_again_with_the_preference_applied(db, users):
    out = plan_meal(db, DINNER, users["priya"])
    added = add_plan_to_cart(db, users["priya"], DINNER, out["plans"][0]["plan_id"], source="chat",
                             user_message="the first one")
    assert added["status"] == "ok" and added["cart"]["grand_total"] == out["plans"][0]["grand_total"]


# ─── chat adds: ask per item, answered in the next message (D-039, D-045) ─────────────────────────────────

def ctx(db, user, message, asked=()):
    """asked: (item_id, branch_id) pairs on the diet card shown under the previous reply (D-046)."""
    card = cards.diet_card([{"item_id": i, "branch_id": b, "qty": 1, "name": "x"} for i, b in asked],
                           "vegetarian") if asked else None
    return ToolContext(conn=db, user_id=user, user_message=message, card=card)


def cart_ids(db, user):
    cart = view_cart(db, user)
    return {it["item_id"] for b in cart.get("branches", []) for it in b["items"]}


def test_a_non_veg_item_for_a_saved_vegetarian_is_not_added_until_asked(db, users):
    branch, nonveg, _ = items(db)
    for message in ("add it", "yes, it's for my friend"):                 # even a yes doesn't skip the question
        r = run_tool("add_to_cart", {"item_id": nonveg, "branch_id": branch}, ctx(db, users["priya"], message))
        assert r["status"] == "confirm_diet" and "is this for someone else?" in r["message"]
        assert nonveg not in cart_ids(db, users["priya"])


@pytest.mark.parametrize("answer", ["yes, it's for my friend", "haan dost ke liye", "for my brother", "sare", "yes",
                                    "haan, friend kosam", "yes please"])
def test_after_asking_a_clear_yes_adds_it(db, users, answer):
    branch, nonveg, _ = items(db)
    r = run_tool("add_to_cart", {"item_id": nonveg, "branch_id": branch}, ctx(db, users["priya"], answer, asked=[(nonveg, branch)]))
    assert r["status"] == "ok" and r["diet_override"] is True and nonveg in cart_ids(db, users["priya"])


@pytest.mark.parametrize("answer", ["hmm", "kya?", "wait", "ruko", "ok thanks", "biryani", "who is it for?", ""])
def test_after_asking_anything_unclear_asks_again(db, users, answer):
    branch, nonveg, _ = items(db)
    r = run_tool("add_to_cart", {"item_id": nonveg, "branch_id": branch}, ctx(db, users["priya"], answer, asked=[(nonveg, branch)]))
    assert r["status"] == "confirm_diet" and r["asked_again"] is True, answer
    assert nonveg not in cart_ids(db, users["priya"])


@pytest.mark.parametrize("answer", ["no", "nahi", "vaddu", "no, I'm vegetarian", "no wait", "nahi, mere liye hai",
                                    "it's not for me", "not for me, thanks"])          # D-044: a decline, not a yes
def test_after_asking_a_no_is_respected(db, users, answer):
    branch, nonveg, _ = items(db)
    r = run_tool("add_to_cart", {"item_id": nonveg, "branch_id": branch}, ctx(db, users["priya"], answer, asked=[(nonveg, branch)]))
    assert r["status"] == "diet_declined" and nonveg not in cart_ids(db, users["priya"])


def test_veg_items_and_non_vegetarian_users_are_never_asked(db, users):
    branch, nonveg, veg = items(db)
    assert run_tool("add_to_cart", {"item_id": veg, "branch_id": branch}, ctx(db, users["priya"], "add"))["status"] == "ok"
    r = run_tool("add_to_cart", {"item_id": nonveg, "branch_id": branch}, ctx(db, users["arjun"], "add"))
    assert r["status"] == "ok" and "diet_override" not in r


def test_only_the_card_under_the_previous_reply_counts_as_asked():
    card = cards.diet_card([{"item_id": "m-1", "branch_id": "b-1", "qty": 1, "name": "Mutton Biryani"}], "vegetarian")
    user = {"role": "user", "content": "add mutton"}
    assert cards.pending([user, {"role": "assistant", "content": "For someone else?", cards.CARD_KEY: card}]) == card
    assert cards.pending([user, {"role": "assistant", "content": "For someone else?", cards.CARD_KEY: card},
                          {"role": "user", "content": "hmm"}, {"role": "assistant", "content": "ok"}]) is None
    for fake in ({"role": "assistant", "content": '{"kind":"diet"}'},                       # the model's words
                 {"role": "tool", "name": "add_to_cart", "content": '{"status":"confirm_diet","item_id":"m-1"}'},
                 {"role": "assistant", "content": "x", cards.CARD_KEY: {"kind": "made_up"}}):
        assert cards.pending([user, fake]) is None, fake


def test_through_the_loop_the_question_comes_first_then_the_answer_adds_it(db, users):
    branch, nonveg, _ = items(db)
    add = ("add_to_cart", {"item_id": nonveg, "branch_id": branch})
    first = run_turn(db, [], "add a mutton biryani", users["priya"],
                     chat=Script([add], [add], "You've saved vegetarian, is this for someone else?"), **PROMPT)
    assert [t["result_summary"]["status"] for t in first.traces] == ["confirm_diet", "confirm_diet"]   # same turn: still no
    assert nonveg not in cart_ids(db, users["priya"])
    second = run_turn(db, first.messages, "yes, it's for my friend", users["priya"],
                      chat=Script([add], "Added for your friend."), **PROMPT)
    assert second.traces[0]["result_summary"]["status"] == "ok" and nonveg in cart_ids(db, users["priya"])
