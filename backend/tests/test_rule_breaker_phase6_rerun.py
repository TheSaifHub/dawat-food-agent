"""Every break from the Phase 6 rule-breaker RE-RUN (Session 16, after D-044), as a test that must now hold (D-045).
Strict: consent, money, diet and identity. The classifier is off (conftest) unless a test sets it.

    BR-1..3  names, filler and areas hid a change inside a "strong yes"      → only unambiguous messages are a yes
    BR-4     a quote seen only in a tool result was confirmed                 → only the quote the last reply stated
    BR-5     remove first, then add a plan, skipped the replace question      → removals need asking; a cart that had
                                                                                items at the turn's start needs the yes
    BR-6     an unclear retraction left the cart confirmed for a later "ok"   → a confirmation lasts one turn
    BR-7     the diet yes covered any item, forever                           → per item, the next message only
    BR-8     mentions and questions changed preferences; a bare yes saved     → two steps, questions never count
    weak     set_delivery wasn't locked; fuzzy names                          → locked; names play no part
"""

import inspect
import json

import pytest

from app.agent import cards, intent
from app.agent.llm import BUSY_MESSAGE
from app.agent.loop import run_turn
from app.agent.tools import ToolContext, run_tool
from app.tools.cart import add_to_cart, view_cart
from app.tools.consent import DIET_YES, REPLACE_YES, consent
from app.tools.planner import plan_meal
from tests.test_agent_loop import PROMPT, Script, stating_total

SAIF = "haan saudi arebian rest wala order palce kardo."


@pytest.fixture
def users(demo_users):
    arjun, family, priya = demo_users
    return {"arjun": arjun, "priya": priya}


@pytest.fixture
def classifier(monkeypatch):
    """Set .answer to (intent, evidence[, change]); the default is "model unavailable"."""
    class Fake:
        answer = None

    def classify(question, message):
        a = Fake.answer
        if a is None:
            return {"used": False, "intent": None, "evidence": None, "change": None, "fallback_reason": "off"}
        return {"used": True, "intent": a[0], "evidence": a[1], "change": a[2] if len(a) > 2 else None,
                "fallback_reason": None}
    monkeypatch.setattr(intent, "classify", classify)
    return Fake


def mains(db, veg: bool, n: int = 1):
    """n different mains at the same open Madhapur branch: [(item_id, branch_id, name)]."""
    rows = db.execute("""
        with b as (select b.branch_id, b.restaurant_id from public.branches b join public.menu_items m using (restaurant_id)
                   join public.dishes d using (dish_id) where b.area_id = 'madhapur' and b.open_for_demo
                   and m.is_available and d.course = 'main' and d.is_veg = %s
                   group by 1, 2 having count(*) >= %s order by 1 limit 1)
        select m.item_id, b.branch_id, d.name from b join public.menu_items m using (restaurant_id)
        join public.dishes d using (dish_id) where m.is_available and d.course = 'main' and d.is_veg = %s
        order by m.item_id limit %s""", (veg, n, veg, n)).fetchall()
    assert len(rows) == n
    return [(r["item_id"], r["branch_id"], r["name"]) for r in rows]


def orders_of(db, user):
    return db.execute("select count(*) as n from public.orders where user_id = %s", (user,)).fetchone()["n"]


def cart_status(db, user):
    row = db.execute("select status from public.carts where user_id = %s and status in ('open', 'confirmed')",
                     (user,)).fetchone()
    return row["status"] if row else None


def statuses(turn):
    return [t["result_summary"]["status"] for t in turn.traces]


def tool_result(turn, name):
    return [json.loads(m["content"]) for m in turn.messages if m.get("role") == "tool" and m["name"] == name][-1]


@pytest.fixture
def shown(db, users):
    """Arjun's cart with one veg main, and the turn whose reply showed its summary with the total."""
    [(item, branch, _)] = mains(db, True)
    add_to_cart(db, users["arjun"], item, branch)
    turn = run_turn(db, [], "show my cart", users["arjun"], chat=Script([("view_cart", {})], stating_total()), **PROMPT)
    summary = tool_result(turn, "view_cart")
    return {"ids": {"cart_id": summary["cart_id"], "quote_id": summary["quote_id"]}, "history": turn.messages,
            "total": summary["grand_total"], "item": item, "branch": branch}


def order_script(ids, reply="Done"):
    return Script([("confirm_cart", ids)], [("place_order", {"cart_id": ids["cart_id"]})], reply)


# ─── BR-1..3: no "strong yes" any more ───────────────────────────────────────────────────────────────────

BR_1_3 = [
    "haan Paneer Biryani order kar do",                     # BR-1: a different dish, named; cart had Veg Dum Biryani
    "ok confirm the order at my office", "yes place the order for one", "haan one biryani order kar do",   # BR-2
    "ok place the order at kondapur", "haan order kar do kondapur wala",                                    # BR-3
    "yes confirm the order from Hi-Tech Bawarchi - Kondapur", "haan Paradse wala order kar do",   # names, fuzzy names
    SAIF,
]


@pytest.mark.parametrize("message", BR_1_3)
def test_br1_3_extra_words_are_never_a_yes_in_any_answer_set(message):
    for also in (frozenset(), REPLACE_YES, DIET_YES):
        assert consent(message, also_yes=also)["consent"] != "yes", (message, also)


def test_names_play_no_part_in_the_yes_check_any_more():
    assert set(inspect.signature(consent).parameters) == {"message", "also_yes"}


@pytest.mark.parametrize("message", BR_1_3)
def test_br1_3_place_no_order_even_when_the_classifier_says_yes(db, users, shown, classifier, message):
    classifier.answer = ("yes", message.split()[0])
    turn = run_turn(db, shown["history"], message, users["arjun"], chat=order_script(shown["ids"]), **PROMPT)
    assert statuses(turn) == ["confirm_intent", "no_clear_yes"], message          # one natural question instead
    assert orders_of(db, users["arjun"]) == 0 and cart_status(db, users["arjun"]) == "open"


def test_saifs_message_gets_one_question_then_a_plain_yes_orders(db, users, shown, classifier):
    classifier.answer = ("yes", "order palce kardo")
    asked = run_turn(db, shown["history"], SAIF, users["arjun"],
                     chat=Script([("confirm_cart", shown["ids"])], stating_total("Saudi Arebian ka order place kar doon?")),
                     **PROMPT)
    assert statuses(asked) == ["confirm_intent"] and orders_of(db, users["arjun"]) == 0
    history = shown["history"] + asked.messages
    classifier.answer = ("yes", "haan")
    done = run_turn(db, history, "haan", users["arjun"], chat=order_script(shown["ids"]), **PROMPT)
    assert statuses(done) == ["ok", "payment_required"] and orders_of(db, users["arjun"]) == 0     # D-061: pay next


# ─── BR-4: only the summary the last reply stated ────────────────────────────────────────────────────────

def test_br4_a_total_seen_only_in_a_tool_result_cannot_be_confirmed(db, users, shown):
    [_, (other, branch, _)] = mains(db, True, 2)
    added = run_turn(db, shown["history"], "add one more main", users["arjun"],
                     chat=Script([("add_to_cart", {"item_id": other, "branch_id": branch, "qty": 3})],
                                 "Added it. Your cart has 1 item."), **PROMPT)      # the new total was never stated
    quote = tool_result(added, "add_to_cart")["cart"]["quote_id"]
    history = shown["history"] + added.messages
    turn = run_turn(db, history, "yes place the order", users["arjun"],
                    chat=order_script({"cart_id": shown["ids"]["cart_id"], "quote_id": quote}), **PROMPT)
    assert statuses(turn) == ["not_shown", "not_confirmed"] and orders_of(db, users["arjun"]) == 0
    old = run_turn(db, history, "yes place the order", users["arjun"], chat=order_script(shown["ids"]), **PROMPT)
    assert statuses(old)[0] == "not_shown" and orders_of(db, users["arjun"]) == 0     # the older summary neither


VIEW = {"status": "ok", "can_confirm": True, "cart_id": "c-1", "quote_id": "q1", "grand_total": 1964,
        "delivery": {"area": "Madhapur", "address_label": "Home"},
        "branches": [{"restaurant": "Mehfil", "items": [{"name": "Chicken Biryani", "qty": 2, "line_total": 600}]}]}


def test_the_order_card_shows_items_delivery_and_total():
    card = cards.order_card(VIEW)
    line = cards.text(card)
    assert card["quote_id"] == "q1" and card["cart_id"] == "c-1"
    assert "Chicken Biryani ×2 ₹600" in line and "Home, Madhapur" in line and "₹1,964" in line
    assert cards.order_card({**VIEW, "can_confirm": False}) is None and cards.order_card({"status": "empty"}) is None


def test_one_card_per_turn_and_a_later_cart_change_drops_an_order_card():
    order = cards.order_card(VIEW)
    diet = cards.diet_card([{"item_id": "m-1", "branch_id": "b-1", "qty": 1, "name": "Mutton"}], "vegetarian")
    assert cards.from_results([("view_cart", {"status": "ok", "confirm_card": order})]) == order
    assert cards.from_results([("view_cart", {"status": "ok", "confirm_card": order}),
                               ("add_to_cart", {"status": "ok"})]) is None          # the summary is stale
    assert cards.from_results([("view_cart", {"status": "ok", "confirm_card": order}),
                               ("add_to_cart", {"status": "confirm_diet", "confirm_card": diet})]) == diet   # the latest
    two = cards.diet_card([{"item_id": "m-2", "branch_id": "b-1", "qty": 1, "name": "Chicken"}], "vegetarian")
    merged = cards.from_results([("add_to_cart", {"confirm_card": diet}), ("add_to_cart", {"confirm_card": two})])
    assert [it["item_id"] for it in merged["items"]] == ["m-1", "m-2"]
    assert cards.from_results([("view_cart", {"status": "ok", "confirm_card": order}),
                               ("place_order", {"status": "ok"})]) is None


def test_only_the_last_reply_carries_the_pending_card_and_the_model_never_sees_the_key():
    order = cards.order_card(VIEW)
    history = [{"role": "user", "content": "cart"}, {"role": "assistant", "content": "Shall I place it?",
                                                       cards.CARD_KEY: order}]
    assert cards.pending(history) == order
    assert cards.pending(history + [{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}]) is None
    seen = cards.for_model(history)
    assert cards.CARD_KEY not in seen[1] and "₹1,964" in seen[1]["content"] and cards.CARD_KEY in history[1]


def test_a_busy_or_step_cap_turn_shows_no_card(db, users, shown):
    from tests.test_agent_loop import BUSY
    turn = run_turn(db, [], "show cart", users["arjun"], chat=Script([("view_cart", {})], BUSY), **PROMPT)
    assert turn.status == "busy" and turn.card is None and cards.CARD_KEY not in turn.messages[-1]


# ─── BR-5: removing first never skips the replace question ───────────────────────────────────────────────

REQ = {"budget": 600, "people": 1, "meal_type": "meal", "area": "Madhapur"}


def test_br5_an_unasked_removal_is_refused_and_the_plan_needs_the_replace_yes(db, users, shown):
    before = view_cart(db, users["arjun"])["quote_id"]
    pid = plan_meal(db, REQ, users["arjun"])["plans"][0]["plan_id"]
    script = Script([("remove_from_cart", {"item_id": shown["item"]})],
                    [("add_plan_to_cart", {"request": REQ, "plan_id": pid})],
                    [("add_plan_to_cart", {"request": REQ, "plan_id": pid, "replace": True})], "ok")
    turn = run_turn(db, [], "plan 1 please", users["arjun"], chat=script, **PROMPT)
    assert statuses(turn) == ["remove_not_asked", "cart_not_empty", "cart_locked"]
    assert view_cart(db, users["arjun"])["quote_id"] == before


def test_br5_even_an_asked_removal_shows_a_card_and_the_plan_still_asks(db, users, shown):
    pid = plan_meal(db, REQ, users["arjun"])["plans"][0]["plan_id"]
    script = Script([("remove_from_cart", {"item_id": shown["item"]})],
                    [("add_plan_to_cart", {"request": REQ, "plan_id": pid, "replace": True})], "ok")
    turn = run_turn(db, [], "remove everything and add plan 1", users["arjun"], chat=script, **PROMPT)
    assert statuses(turn) == ["remove_not_asked", "cart_not_empty"]       # D-046: removals always show a card
    assert view_cart(db, users["arjun"]).get("branches") and turn.card["kind"] == "plan"


def test_br5_an_unasked_removal_in_one_turn_cannot_empty_the_cart_for_the_next(db, users, shown):
    first = run_turn(db, [], "show me plans", users["arjun"],
                     chat=Script([("remove_from_cart", {"item_id": shown["item"]})], "ok"), **PROMPT)
    assert statuses(first) == ["remove_not_asked"] and view_cart(db, users["arjun"]).get("branches")


@pytest.mark.parametrize("message", [
    "ok", "no", "cancel", "nahi", "vaddu", "show me the plans", "add a coke", "yes place it", "remove it",
    "isko hatao", "make it less spicy", "coke hatao bhai", "clear the cart", "empty my cart", "remove everything",
    "sab hatao", "don't remove the avocado toast", "pet khali hai bhai", "remove nothing, all good",
])
def test_removal_from_chat_always_shows_a_card_first(db, users, shown, message):
    # D-046 (fourth run): every check on the user's own words let something through, so no words remove anything
    r = run_tool("remove_from_cart", {"item_id": shown["item"]},
                 ToolContext(conn=db, user_id=users["arjun"], user_message=message))
    assert r["status"] == "remove_not_asked" and r["confirm_card"]["kind"] == "remove", (message, r)
    assert view_cart(db, users["arjun"]).get("branches")


def test_the_remove_card_flow_removes_exactly_the_card_once(db, users, shown):
    add_to_cart(db, users["arjun"], shown["item"], shown["branch"], 3)          # now ×4
    asked = run_turn(db, [], "remove one", users["arjun"],
                     chat=Script([("remove_from_cart", {"item_id": shown["item"], "qty": 1})], "Remove it?"), **PROMPT)
    assert statuses(asked) == ["remove_not_asked"] and asked.card["items"][0]["qty"] == 1
    one = {"item_id": shown["item"], "branch_id": shown["branch"], "qty": 1}
    done = run_turn(db, asked.messages, "yes", users["arjun"], chat=Script(
        [("remove_from_cart", {"item_id": shown["item"], "qty": 2})], [("remove_from_cart", one)],
        [("remove_from_cart", one)], "Removed."), **PROMPT)
    assert statuses(done) == ["remove_not_asked", "ok", "remove_not_asked"]    # other qty asks; the card works once
    qty = [it["qty"] for b in view_cart(db, users["arjun"])["branches"] for it in b["items"]]
    assert qty == [3]


@pytest.mark.parametrize("answer", ["no, keep it", "nahi, mat hatao", "hmm", "is it fresh?", "ok cool"])
def test_anything_but_a_yes_to_the_remove_card_removes_nothing(db, users, shown, answer):
    asked = run_turn(db, [], "remove it", users["arjun"],
                     chat=Script([("remove_from_cart", {"item_id": shown["item"]})], "Remove it?"), **PROMPT)
    turn = run_turn(db, asked.messages, answer, users["arjun"],
                    chat=Script([("remove_from_cart", {"item_id": shown["item"]})], "ok"), **PROMPT)
    assert statuses(turn) == ["remove_not_asked"] and view_cart(db, users["arjun"]).get("branches"), answer


def test_clearing_the_cart_is_one_card_for_every_item(db, users, shown):
    [_, (other, branch, _)] = mains(db, True, 2)
    add_to_cart(db, users["arjun"], other, branch)
    script = Script([("remove_from_cart", {"item_id": shown["item"]}), ("remove_from_cart", {"item_id": other})],
                    "Clear these?")
    asked = run_turn(db, [], "clear my cart", users["arjun"], chat=script, **PROMPT)
    assert {it["item_id"] for it in asked.card["items"]} == {shown["item"], other}
    done = run_turn(db, asked.messages, "haan", users["arjun"], chat=Script(
        [("remove_from_cart", {"item_id": shown["item"]}), ("remove_from_cart", {"item_id": other})], "Done"), **PROMPT)
    assert statuses(done) == ["ok", "ok"] and not view_cart(db, users["arjun"]).get("branches")


# ─── BR-6: a confirmation lasts one turn ─────────────────────────────────────────────────────────────────

def test_br6_a_confirmed_cart_is_open_again_at_the_next_message(db, users, shown):
    first = run_turn(db, shown["history"], "yes", users["arjun"],
                     chat=Script([("confirm_cart", shown["ids"])], "Confirmed."), **PROMPT)
    assert statuses(first) == ["ok"] and cart_status(db, users["arjun"]) == "confirmed"
    history = shown["history"] + first.messages
    second = run_turn(db, history, "achha, ek baat", users["arjun"], chat=Script("Haan bolo?"), **PROMPT)
    assert cart_status(db, users["arjun"]) == "open"                     # an unclear retraction leaves nothing confirmed
    history += second.messages
    third = run_turn(db, history, "ok", users["arjun"],
                     chat=Script([("place_order", {"cart_id": shown["ids"]["cart_id"]})], "Done"), **PROMPT)
    assert statuses(third) == ["not_confirmed"] and orders_of(db, users["arjun"]) == 0


# ─── BR-7: the diet yes covers only the items asked about, in the next message ──────────────────────────

def _add(item):
    return [("add_to_cart", {"item_id": item[0], "branch_id": item[1]})]


def test_br7_the_yes_covers_only_the_item_asked_about(db, users):
    a, b = mains(db, False, 2)
    asked = run_turn(db, [], "add the first one", users["priya"],
                     chat=Script(_add(a), "You've saved vegetarian, is this for someone else?"), **PROMPT)
    assert statuses(asked) == ["confirm_diet"]
    turn = run_turn(db, asked.messages, "yes, it's for my friend", users["priya"],
                    chat=Script(_add(b), _add(a), "Added."), **PROMPT)
    assert statuses(turn) == ["confirm_diet", "ok"]
    ids = {it["item_id"] for br in view_cart(db, users["priya"])["branches"] for it in br["items"]}
    assert ids == {a[0]}


def test_br7_the_yes_expires_after_one_message(db, users):
    [a] = mains(db, False)
    asked = run_turn(db, [], "add it", users["priya"],
                     chat=Script(_add(a), "You've saved vegetarian, is this for someone else?"), **PROMPT)
    later = run_turn(db, asked.messages, "hmm let me see the menu first", users["priya"], chat=Script("Sure."), **PROMPT)
    history = asked.messages + later.messages
    turn = run_turn(db, history, "yes, it's for my friend", users["priya"], chat=Script(_add(a), "ok"), **PROMPT)
    assert statuses(turn) == ["confirm_diet"] and not view_cart(db, users["priya"]).get("branches")


def test_br7_after_the_add_another_one_asks_again(db, users):
    [a] = mains(db, False)
    asked = run_turn(db, [], "add it", users["priya"], chat=Script(_add(a), "For someone else?"), **PROMPT)
    added = run_turn(db, asked.messages, "yes", users["priya"], chat=Script(_add(a), "Added."), **PROMPT)
    assert statuses(added) == ["ok"]
    again = run_turn(db, asked.messages + added.messages, "add one more", users["priya"],
                     chat=Script(_add(a), "ok"), **PROMPT)
    assert statuses(again) == ["confirm_diet"]


def test_br7_a_busy_reply_means_the_question_was_never_asked(db, users):
    [a] = mains(db, False)
    from tests.test_agent_loop import BUSY
    asked = run_turn(db, [], "add it", users["priya"], chat=Script(_add(a), BUSY), **PROMPT)
    assert asked.status == "busy"
    turn = run_turn(db, asked.messages, "yes", users["priya"], chat=Script(_add(a), "ok"), **PROMPT)
    assert statuses(turn) == ["confirm_diet"]


# ─── BR-8: preferences from chat take two steps; questions never count ──────────────────────────────────

def diet_of(db, user):
    row = db.execute("select value from public.user_preferences where user_id = %s and key = 'diet'", (user,)).fetchone()
    return row["value"] if row else None


@pytest.mark.parametrize("message, status", [("is the paneer biryani veg?", "not_requested"),
                                             ("is the paneer biryani veg", "not_requested")])   # D-046: no forget word
def test_br8_a_question_or_a_mention_never_deletes_the_diet(db, users, message, status):
    r = run_tool("delete_preference", {"key": "diet", "source": "chat_request", "user_words": message.rstrip("?")},
                 ToolContext(conn=db, user_id=users["priya"], user_message=message))
    assert r["status"] == status and diet_of(db, users["priya"]) == "vegetarian"


@pytest.mark.parametrize("tool, args", [
    ("save_preference", {"key": "diet", "value": "non veg", "source": "chat_confirmed", "user_words": "yes"}),
    ("delete_preference", {"key": "diet", "source": "chat_confirmed", "user_words": "yes"}),
])
def test_br8_a_bare_yes_with_no_offer_changes_nothing(db, users, tool, args):
    r = run_tool(tool, args, ToolContext(conn=db, user_id=users["priya"], user_message="yes"))
    assert r["status"] == "not_requested" and diet_of(db, users["priya"]) == "vegetarian"


SAVE = {"key": "diet", "value": "non veg", "source": "chat_request", "user_words": "remember I'm non veg now"}
YES = {**SAVE, "source": "chat_confirmed", "user_words": "yes"}


def test_two_steps_end_to_end(db, users):
    asked = run_turn(db, [], "remember I'm non veg now", users["priya"],
                     chat=Script([("save_preference", SAVE)], "Should I save Non-vegetarian?"), **PROMPT)
    assert statuses(asked) == ["confirm_preference"] and diet_of(db, users["priya"]) == "vegetarian"
    assert asked.card["kind"] == "preference"
    assert asked.card["offer"] == {"action": "save", "key": "diet", "value": "non_vegetarian"}
    assert "Non-vegetarian" in cards.text(asked.card)
    wrong = run_turn(db, asked.messages, "yes", users["priya"],
                     chat=Script([("save_preference", {**YES, "value": "eggetarian"})], "ok"), **PROMPT)
    assert statuses(wrong) == ["not_requested"] and diet_of(db, users["priya"]) == "vegetarian"   # not what was offered
    saved = run_turn(db, asked.messages, "yes", users["priya"], chat=Script([("save_preference", YES)], "Saved."),
                     **PROMPT)
    assert statuses(saved) == ["ok"] and diet_of(db, users["priya"]) == "non_vegetarian"


def test_an_offer_lasts_one_message_and_needs_a_shown_question(db, users):
    asked = run_turn(db, [], "remember I'm non veg now", users["priya"],
                     chat=Script([("save_preference", SAVE)], "Should I save Non-vegetarian?"), **PROMPT)
    later = run_turn(db, asked.messages, "show me biryani", users["priya"], chat=Script("Here."), **PROMPT)
    turn = run_turn(db, asked.messages + later.messages, "yes", users["priya"],
                    chat=Script([("save_preference", YES)], "ok"), **PROMPT)
    assert statuses(turn) == ["not_requested"]
    from tests.test_agent_loop import BUSY
    busy = run_turn(db, [], "remember I'm non veg now", users["priya"],
                    chat=Script([("save_preference", SAVE)], BUSY), **PROMPT)
    turn = run_turn(db, busy.messages, "yes", users["priya"], chat=Script([("save_preference", YES)], "ok"), **PROMPT)
    assert statuses(turn) == ["not_requested"] and diet_of(db, users["priya"]) == "vegetarian"


def test_an_unclear_answer_to_the_offer_saves_nothing(db, users):
    asked = run_turn(db, [], "remember I'm non veg now", users["priya"],
                     chat=Script([("save_preference", SAVE)], "Should I save Non-vegetarian?"), **PROMPT)
    for message in ("yes but only on weekends", "ok thanks", "hmm"):
        turn = run_turn(db, asked.messages, message, users["priya"],
                        chat=Script([("save_preference", {**YES, "user_words": message.split()[0]})], "ok"), **PROMPT)
        assert statuses(turn) == ["not_requested"], message
    assert diet_of(db, users["priya"]) == "vegetarian"


# ─── weak spots ──────────────────────────────────────────────────────────────────────────────────────────

def test_set_delivery_is_locked_after_a_refused_replace(db, users, shown):
    pid = plan_meal(db, REQ, users["arjun"])["plans"][0]["plan_id"]
    script = Script([("add_plan_to_cart", {"request": REQ, "plan_id": pid, "replace": True})],
                    [("set_delivery", {"area": "Kondapur"})], "ok")
    before = view_cart(db, users["arjun"])["quote_id"]
    turn = run_turn(db, [], "show me the plans", users["arjun"], chat=script, **PROMPT)
    assert statuses(turn) == ["cart_not_empty", "cart_locked"] and view_cart(db, users["arjun"])["quote_id"] == before


def test_br5_a_cart_emptied_by_a_remove_card_still_needs_the_plan_card_that_turn(db, users, shown):
    asked = run_turn(db, [], "remove it", users["arjun"],
                     chat=Script([("remove_from_cart", {"item_id": shown["item"]})], "Remove it?"), **PROMPT)
    pid = plan_meal(db, REQ, users["arjun"])["plans"][0]["plan_id"]
    turn = run_turn(db, asked.messages, "yes", users["arjun"], chat=Script(
        [("remove_from_cart", {"item_id": shown["item"]})],
        [("add_plan_to_cart", {"request": REQ, "plan_id": pid, "replace": True})], "ok"), **PROMPT)
    assert statuses(turn) == ["ok", "cart_not_empty"] and not view_cart(db, users["arjun"]).get("branches")
    assert turn.card["kind"] == "plan" and turn.card["replace"] is True    # the cart had items when the turn began


def test_the_remove_card_is_for_its_branch_only(db, users):
    """Fourth run, weak spot: the same item from two branches; the card names one branch, the yes removes only it."""
    rows = db.execute("""select b.restaurant_id, array_agg(b.branch_id order by b.branch_id) as bs from public.branches b
                         where b.open_for_demo and b.area_id in ('madhapur', 'kondapur', 'gachibowli', 'hitec-city',
                         'jubilee-hills') group by 1 having count(*) >= 2 order by 1""").fetchall()
    for r in rows:
        item = db.execute("select item_id from public.menu_items where restaurant_id = %s and is_available "
                          "order by item_id limit 1", (r["restaurant_id"],)).fetchone()["item_id"]
        a, b = r["bs"][:2]
        if [add_to_cart(db, users["arjun"], item, x)["status"] for x in (a, b)] == ["ok", "ok"]:
            break
    else:
        pytest.skip("no item available from two delivering branches")
    asked = run_turn(db, [], "remove it", users["arjun"],
                     chat=Script([("remove_from_cart", {"item_id": item, "branch_id": a})], "Remove?"), **PROMPT)
    assert asked.card["items"][0]["branch_id"] == a
    turn = run_turn(db, asked.messages, "yes", users["arjun"], chat=Script(
        [("remove_from_cart", {"item_id": item, "branch_id": b})], [("remove_from_cart", {"item_id": item})], "ok"),
        **PROMPT)
    assert statuses(turn) == ["remove_not_asked", "ok"]                 # the other branch asks; no branch = the card's
    left = {br["branch_id"] for br in view_cart(db, users["arjun"])["branches"] for it in br["items"] if it["item_id"] == item}
    assert left == {b}
