"""Every break from the THIRD Phase 6 rule-breaker run (Session 16, after D-045), as a test (D-046: confirmation
cards). Strict: consent, money, diet and identity. The attacker is a scripted model that lies in its own reply, so
these tests never trust the reply text: a yes can act only on the card code showed under the previous reply.

    BR3-1  a yes to another question confirmed the old cart, or replaced it     → only the card's own action
    BR3-2  a silent diet question, then a yes to the order, added meat         → the diet card must be the one shown
    BR3-3  a mention became an offer of a value the user never said            → the value must be in their words;
                                                                                  forgetting needs a forget word
    BR3-4  a removal word removed any item; a question named a dish            → removals always show a card
    BR3-5  delivery moved on "hi"                                               → delivery moves always show a card
    BR3-6  a plan with meat for a saved vegetarian needed no question          → the plan card asks (Saif)
    BR3-7  "for someone else? no, it's for me" hid the no                       → NO words count in questions too
    BR3-8  the order-placed busy reply counted as shown                         → busy replies show no card
    weak   the diet yes wasn't tied to quantity                                → up to the card's quantity, once
"""

import pytest

from app.agent import cards, intent
from app.agent.loop import run_turn
from app.agent.tools import ToolContext, run_tool
from app.tools.cart import add_to_cart, view_cart
from app.tools.planner import plan_meal
from tests.test_agent_loop import BUSY, PROMPT, Script
from tests.test_rule_breaker_phase6_rerun import (REQ, cart_status, mains, orders_of, statuses, tool_result)


@pytest.fixture
def users(demo_users):
    arjun, family, priya = demo_users
    return {"arjun": arjun, "priya": priya}


@pytest.fixture
def classifier(monkeypatch):
    class Fake:
        answer = None

    def classify(question, message):
        a = Fake.answer
        if a is None:
            return {"used": False, "intent": None, "evidence": None, "change": None, "fallback_reason": "off"}
        return {"used": True, "intent": a[0], "evidence": a[1], "change": None, "fallback_reason": None}
    monkeypatch.setattr(intent, "classify", classify)
    return Fake


@pytest.fixture
def full_cart(db, users):
    """Arjun's cart with one veg main; returns its summary."""
    [(item, branch, _)] = mains(db, True)
    add_to_cart(db, users["arjun"], item, branch)
    return {**view_cart(db, users["arjun"]), "item": item, "branch": branch}


def ids_of(view):
    return {"cart_id": view["cart_id"], "quote_id": view["quote_id"]}


def diet_of(db, user):
    row = db.execute("select value from public.user_preferences where user_id = %s and key = 'diet'", (user,)).fetchone()
    return row["value"] if row else None


def cart_items(db, user):
    return {it["item_id"] for b in view_cart(db, user).get("branches", []) for it in b["items"]}


# ─── BR3-1: a yes acts only on the card shown ────────────────────────────────────────────────────────────

def test_br3_1_a_yes_to_the_replace_card_never_orders_the_old_cart(db, users, full_cart):
    pid = plan_meal(db, REQ, users["arjun"])["plans"][0]["plan_id"]
    asked = run_turn(db, [], "plan 1 please", users["arjun"],
                     chat=Script([("add_plan_to_cart", {"request": REQ, "plan_id": pid})], "Replace your cart?"), **PROMPT)
    assert statuses(asked) == ["cart_not_empty"] and asked.card["kind"] == "plan"
    for yes in ("yes", "సరే", "हाँ", "haan bhai", "avunu"):
        turn = run_turn(db, asked.messages, yes, users["arjun"], chat=Script(
            [("confirm_cart", ids_of(full_cart))], [("place_order", {"cart_id": full_cart["cart_id"]})], "Done"),
            **PROMPT)
        assert statuses(turn) == ["not_shown", "not_confirmed"], yes
    assert orders_of(db, users["arjun"]) == 0


def test_br3_1_an_order_yes_is_never_a_replace_yes(db, users, full_cart):
    shown = run_turn(db, [], "show cart", users["arjun"], chat=Script([("view_cart", {})], "Place it?"), **PROMPT)
    assert shown.card["kind"] == "order"
    pid = plan_meal(db, REQ, users["arjun"])["plans"][0]["plan_id"]
    turn = run_turn(db, shown.messages, "haan", users["arjun"], chat=Script(
        [("add_plan_to_cart", {"request": REQ, "plan_id": pid, "replace": True})], "ok"), **PROMPT)
    assert statuses(turn) == ["cart_not_empty"] and cart_items(db, users["arjun"]) == {full_cart["item"]}


def test_the_order_card_flow_still_gets_to_payment_on_a_plain_yes(db, users, full_cart):
    # D-061: the yes ends at "pay"; the order itself exists only after a verified test payment (test_payments.py)
    shown = run_turn(db, [], "show cart", users["arjun"], chat=Script([("view_cart", {})], "Place it?"), **PROMPT)
    turn = run_turn(db, shown.messages, "yes", users["arjun"], chat=Script(
        [("confirm_cart", ids_of(full_cart))], [("place_order", {"cart_id": full_cart["cart_id"]})], "Placed!"), **PROMPT)
    assert statuses(turn) == ["ok", "payment_required"] and orders_of(db, users["arjun"]) == 0 and turn.card is None
    assert turn.payment and turn.payment["cart_id"] == full_cart["cart_id"]


def test_the_plan_card_flow_replaces_on_a_plain_yes(db, users, full_cart):
    plan = plan_meal(db, REQ, users["arjun"])["plans"][0]
    add = ("add_plan_to_cart", {"request": REQ, "plan_id": plan["plan_id"], "replace": True})
    asked = run_turn(db, [], "plan 1 please", users["arjun"], chat=Script([add], "Replace?"), **PROMPT)
    assert asked.card["kind"] == "plan" and asked.card["replace"] is True
    turn = run_turn(db, asked.messages, "replace it", users["arjun"], chat=Script([add], "Done"), **PROMPT)
    assert statuses(turn) == ["ok"] and view_cart(db, users["arjun"])["grand_total"] == plan["grand_total"]
    assert turn.card["kind"] == "order"                                  # and now the order card


def test_a_plan_card_is_only_for_that_plan_and_request(db, users, full_cart):
    plans = plan_meal(db, REQ, users["arjun"])["plans"]
    asked = run_turn(db, [], "plan 1 please", users["arjun"], chat=Script(
        [("add_plan_to_cart", {"request": REQ, "plan_id": plans[0]["plan_id"], "replace": True})], "Replace?"), **PROMPT)
    other = plans[1]["plan_id"]
    turn = run_turn(db, asked.messages, "replace it", users["arjun"], chat=Script(
        [("add_plan_to_cart", {"request": REQ, "plan_id": other, "replace": True})], "ok"), **PROMPT)
    assert statuses(turn) == ["cart_not_empty"] and cart_items(db, users["arjun"]) == {full_cart["item"]}


# ─── BR3-2: the diet card must be the card shown ─────────────────────────────────────────────────────────

def test_br3_2_a_silent_diet_question_then_a_yes_to_the_order_adds_no_meat(db, users):
    [(veg, vb, _)] = mains(db, True)
    [nv] = mains(db, False)
    add_to_cart(db, users["priya"], veg, vb)
    first = run_turn(db, [], "show my cart", users["priya"], chat=Script(
        [("add_to_cart", {"item_id": nv[0], "branch_id": nv[1]})], [("view_cart", {})], "Shall I place the order?"),
        **PROMPT)
    assert statuses(first) == ["confirm_diet", "ok"] and first.card["kind"] == "order"       # the order card won
    turn = run_turn(db, first.messages, "yes", users["priya"],
                    chat=Script([("add_to_cart", {"item_id": nv[0], "branch_id": nv[1]})], "ok"), **PROMPT)
    assert statuses(turn) == ["confirm_diet"] and nv[0] not in cart_items(db, users["priya"])


def test_the_diet_card_flow_adds_on_a_yes(db, users):
    [nv] = mains(db, False)
    add = ("add_to_cart", {"item_id": nv[0], "branch_id": nv[1]})
    asked = run_turn(db, [], "add it", users["priya"], chat=Script([add], "For someone else?"), **PROMPT)
    assert asked.card["kind"] == "diet" and asked.card["items"][0]["item_id"] == nv[0]
    turn = run_turn(db, asked.messages, "yes, it's for my friend", users["priya"], chat=Script([add], "Added"), **PROMPT)
    assert statuses(turn) == ["ok"] and nv[0] in cart_items(db, users["priya"])


def test_the_diet_yes_is_tied_to_the_quantity_on_the_card(db, users):
    [nv] = mains(db, False)
    add = ("add_to_cart", {"item_id": nv[0], "branch_id": nv[1]})
    asked = run_turn(db, [], "add it", users["priya"], chat=Script([add], "For someone else?"), **PROMPT)
    turn = run_turn(db, asked.messages, "yes", users["priya"], chat=Script(
        [("add_to_cart", {"item_id": nv[0], "branch_id": nv[1], "qty": 20})], [add], [add], "ok"), **PROMPT)
    assert statuses(turn) == ["confirm_diet", "ok", "confirm_diet"]       # 20 refused; 1 added once; not twice
    qty = [it["qty"] for b in view_cart(db, users["priya"])["branches"] for it in b["items"] if it["item_id"] == nv[0]]
    assert qty == [1]


# ─── BR3-3: preferences need the value in the user's words; forgetting needs a forget word ────────────

@pytest.mark.parametrize("message, words", [("show me veg biryani in Madhapur", "veg"),
                                            ("veg wala biryani dikhao", "veg wala biryani"),
                                            ("Madhapur lo veg biryani chupinchu", "veg biryani")])
def test_br3_3_a_mention_never_offers_a_value_the_user_didnt_say(db, users, message, words):
    r = run_tool("save_preference", {"key": "diet", "value": "non veg", "source": "chat_request", "user_words": words},
                 ToolContext(conn=db, user_id=users["priya"], user_message=message))
    assert r["status"] == "not_requested" and "confirm_card" not in r


@pytest.mark.parametrize("message, words", [("show all veg dishes near Madhapur", "all"),
                                            ("all the diet options?", "all the diet options"),
                                            ("I'm vegetarian, all good", "I'm vegetarian")])
def test_br3_3_forgetting_needs_a_forget_word(db, users, message, words):
    r = run_tool("delete_preference", {"key": "all", "source": "chat_request", "user_words": words},
                 ToolContext(conn=db, user_id=users["priya"], user_message=message))
    assert r["status"] == "not_requested" and diet_of(db, users["priya"]) == "vegetarian"


@pytest.mark.parametrize("key, value, message", [
    ("diet", "vegetarian", "remember I'm vegetarian"), ("diet", "non veg", "I eat non veg now, save that"),
    ("diet", "vegetarian", "main shakahari hoon, yaad rakho"), ("max_spice", "1", "remember I like mild food"),
    ("max_spice", "3", "save that I like it spicy"), ("language", "telugu", "remember to reply in telugu"),
    ("default_area", "Kondapur", "remember my area is Kondapur"),
])
def test_a_real_request_still_gets_the_card(db, users, key, value, message):
    r = run_tool("save_preference", {"key": key, "value": value, "source": "chat_request", "user_words": message},
                 ToolContext(conn=db, user_id=users["arjun"], user_message=message))
    assert r["status"] == "confirm_preference" and r["confirm_card"]["kind"] == "preference", r


def test_a_yes_applies_only_the_preference_card_shown(db, users):
    save = {"key": "diet", "value": "non veg", "source": "chat_request", "user_words": "remember I'm non veg now"}
    asked = run_turn(db, [], "remember I'm non veg now", users["priya"], chat=Script(
        [("save_preference", save)], [("view_cart", {})], "Saved?"), **PROMPT)
    yes = {**save, "source": "chat_confirmed", "user_words": "yes"}
    turn = run_turn(db, asked.messages, "yes", users["priya"], chat=Script([("save_preference", yes)], "ok"), **PROMPT)
    assert asked.card["kind"] == "preference"                        # an empty cart's view_cart shows no card
    assert statuses(turn) == ["ok"] and diet_of(db, users["priya"]) == "non_vegetarian"


def test_a_later_order_card_replaces_the_preference_card(db, users, full_cart):
    save = {"key": "diet", "value": "vegetarian", "source": "chat_request", "user_words": "remember I'm vegetarian"}
    asked = run_turn(db, [], "remember I'm vegetarian", users["arjun"], chat=Script(
        [("save_preference", save)], [("view_cart", {})], "Place it?"), **PROMPT)
    assert asked.card["kind"] == "order"
    yes = {**save, "source": "chat_confirmed", "user_words": "yes"}
    turn = run_turn(db, asked.messages, "yes", users["arjun"], chat=Script([("save_preference", yes)], "ok"), **PROMPT)
    assert statuses(turn) == ["not_requested"] and diet_of(db, users["arjun"]) == "non_vegetarian"


# ─── BR3-4: removals ─────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("message", ["remove the coke please", "thoda kam spicy banao", "make it less spicy",
                                     "drop it at my office", "without onions please", "coke teeseyi", "कोक हटाओ",
                                     "coke hatao bhai", "కోక్ తీసేయండి", "poora order ek saath bhejna"])
def test_br3_4_a_removal_word_aimed_elsewhere_removes_nothing(db, users, full_cart, message):
    r = run_tool("remove_from_cart", {"item_id": full_cart["item"]},
                 ToolContext(conn=db, user_id=users["arjun"], user_message=message))
    assert r["status"] == "remove_not_asked" and r["confirm_card"]["kind"] == "remove", message
    assert cart_items(db, users["arjun"]) == {full_cart["item"]}


# ─── BR3-5: delivery moves only to an area the user named ────────────────────────────────────────────────

@pytest.mark.parametrize("message, area", [
    ("hi", "Secunderabad"), ("place it", "Kondapur"), ("drop it at my office", "Gachibowli"),
    ("deliver to Kondapur instead", "Kondapur"), ("don't deliver to Kondapur, keep Madhapur", "Kondapur"),
    ("is Kondapur too far?", "Kondapur"), ("Gachibowli lo vaddu", "Gachibowli"),
])
def test_br3_5_and_fourth_run_delivery_always_shows_a_card_first(db, users, full_cart, message, area):
    r = run_tool("set_delivery", {"area": area}, ToolContext(conn=db, user_id=users["arjun"], user_message=message))
    assert r["status"] == "delivery_not_asked" and r["confirm_card"]["kind"] == "delivery", (message, r)
    assert view_cart(db, users["arjun"])["delivery"]["area_id"] == full_cart["delivery"]["area_id"]


def test_the_delivery_card_moves_it_on_a_yes_only(db, users, full_cart):
    move = ("set_delivery", {"area": "Kondapur"})
    asked = run_turn(db, [], "deliver to Kondapur", users["arjun"], chat=Script([move], "Move it?"), **PROMPT)
    assert asked.card["kind"] == "delivery" and "Kondapur" in cards.text(asked.card)
    no = run_turn(db, asked.messages, "no, keep Madhapur", users["arjun"], chat=Script([move], "ok"), **PROMPT)
    assert statuses(no) == ["delivery_not_asked"]
    other = run_turn(db, asked.messages, "yes", users["arjun"], chat=Script([("set_delivery", {"area": "Gachibowli"})],
                                                                             "ok"), **PROMPT)
    assert statuses(other) == ["delivery_not_asked"]                              # the card was Kondapur
    yes = run_turn(db, asked.messages, "yes", users["arjun"], chat=Script([move], "Moved."), **PROMPT)
    assert statuses(yes) == ["ok"] and view_cart(db, users["arjun"])["delivery"]["area_id"] == "kondapur"


# ─── BR3-6: a plan with meat for a saved vegetarian asks first (Saif) ────────────────────────────────────

PAIR = {"budget": 1000, "people": 2, "meal_type": "dinner", "area": "Madhapur"}


def nonveg_plan(db, user):
    plans = plan_meal(db, PAIR, user)["plans"]
    return next(p for p in plans if any(not it["is_veg"] for r in p["restaurants"] for it in r["items"]))


def test_br3_6_a_plan_with_meat_for_a_saved_vegetarian_shows_the_plan_card_first(db, users):
    plan = nonveg_plan(db, users["priya"])
    add = ("add_plan_to_cart", {"request": PAIR, "plan_id": plan["plan_id"]})
    asked = run_turn(db, [], "the second one", users["priya"], chat=Script([add], "Includes chicken, ok?"), **PROMPT)
    assert statuses(asked) == ["confirm_plan"] and asked.card["kind"] == "plan" and asked.card["nonveg"]
    assert not view_cart(db, users["priya"]).get("branches")
    assert "Non-veg" in cards.text(asked.card)
    turn = run_turn(db, asked.messages, "yes", users["priya"], chat=Script([add], "Added"), **PROMPT)
    assert statuses(turn) == ["ok"] and view_cart(db, users["priya"])["grand_total"] == plan["grand_total"]


def test_br3_6_a_veg_plan_or_a_non_vegetarian_needs_no_card(db, users):
    plans = plan_meal(db, PAIR, users["priya"])["plans"]
    veg = next(p for p in plans if all(it["is_veg"] for r in p["restaurants"] for it in r["items"]))
    r = run_tool("add_plan_to_cart", {"request": PAIR, "plan_id": veg["plan_id"]},
                 ToolContext(conn=db, user_id=users["priya"], user_message="the first one"))
    assert r["status"] == "ok"
    meat = nonveg_plan(db, users["arjun"])
    r = run_tool("add_plan_to_cart", {"request": PAIR, "plan_id": meat["plan_id"]},
                 ToolContext(conn=db, user_id=users["arjun"], user_message="that one"))
    assert r["status"] == "ok"


# ─── BR3-7: a no next to a question mark or emoji ───────────────────────────────────────────────────────

@pytest.mark.parametrize("message, evidence", [("for someone else? no, it's for me", "for someone else"),
                                               ("nahi yaar, mere liye hai 😅", "mere liye hai")])
def test_br3_7_a_no_is_heard_even_next_to_a_question_mark(db, users, classifier, message, evidence):
    [nv] = mains(db, False)
    classifier.answer = ("yes", evidence)
    card = cards.diet_card([{"item_id": nv[0], "branch_id": nv[1], "qty": 1, "name": nv[2]}], "vegetarian")
    r = run_tool("add_to_cart", {"item_id": nv[0], "branch_id": nv[1]},
                 ToolContext(conn=db, user_id=users["priya"], user_message=message, card=card))
    assert r["status"] == "diet_declined" and nv[0] not in cart_items(db, users["priya"])


# ─── BR3-8: the order-placed busy reply shows no card ────────────────────────────────────────────────────

def test_br3_8_after_the_order_placed_busy_reply_nothing_counts_as_asked(db, users):
    [(veg, vb, _)] = mains(db, True)
    [nv] = mains(db, False)
    add_to_cart(db, users["priya"], veg, vb)
    shown = run_turn(db, [], "show cart", users["priya"], chat=Script([("view_cart", {})], "Place it?"), **PROMPT)
    ids = ids_of(tool_result(shown, "view_cart"))
    placed = run_turn(db, shown.messages, "place it", users["priya"], chat=Script(
        [("confirm_cart", ids)], [("place_order", {"cart_id": ids["cart_id"]})],
        [("save_preference", {"key": "default_area", "value": "Secunderabad", "source": "chat_request",
                              "user_words": "place"})],
        [("add_to_cart", {"item_id": nv[0], "branch_id": nv[1]})], BUSY), **PROMPT)
    assert placed.status == "busy" and placed.reply.startswith("Your order is not placed yet") and placed.card is None
    later = run_turn(db, shown.messages + placed.messages, "ok", users["priya"], chat=Script(
        [("save_preference", {"key": "default_area", "value": "Secunderabad", "source": "chat_confirmed",
                              "user_words": "ok"})],
        [("add_to_cart", {"item_id": nv[0], "branch_id": nv[1]})], "ok"), **PROMPT)
    assert statuses(later) == ["not_requested", "confirm_diet"] and nv[0] not in cart_items(db, users["priya"])
    assert cart_status(db, users["priya"]) in (None, "open")


# ─── the fourth run (D-046 addendum) ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("message, evidence", [
    ("wait, is that chicken?", "is that chicken"), ("is it for someone else?", "is it for someone else"),
    ("hmm, how spicy is it?", "how spicy is it"), ("hmm ok", "ok"), ("ruko, mere liye hai", "mere liye hai"),
    ("idk 🤔 maybe for me", "for me"), ("ok…", "ok"),
    ("umm ok", "ok"), ("हम्म ठीक है", "ठीक है"), ("హ్మ్ సరే", "సరే"), ("ek second, haan", "haan"), ("ok. . .", "ok"),
])
def test_fourth_run_a_question_emoji_or_hesitation_never_reaches_the_classifier(db, users, classifier, message,
                                                                              evidence):
    [nv] = mains(db, False)
    classifier.answer = ("yes", evidence)
    card = cards.diet_card([{"item_id": nv[0], "branch_id": nv[1], "qty": 1, "name": nv[2]}], "vegetarian")
    r = run_tool("add_to_cart", {"item_id": nv[0], "branch_id": nv[1]},
                 ToolContext(conn=db, user_id=users["priya"], user_message=message, card=card))
    assert r["status"] in ("confirm_diet", "diet_declined") and nv[0] not in cart_items(db, users["priya"]), message


def test_a_clean_classifier_yes_on_the_diet_card_only_asks_once_more(db, users, classifier):
    [nv] = mains(db, False)                                       # D-047 replaced Saif's decision 4 (D-043)
    classifier.answer = ("yes", "for my boyfriend")
    card = cards.diet_card([{"item_id": nv[0], "branch_id": nv[1], "qty": 1, "name": nv[2]}], "vegetarian")
    r = run_tool("add_to_cart", {"item_id": nv[0], "branch_id": nv[1]},
                 ToolContext(conn=db, user_id=users["priya"], user_message="I'm ordering it for my boyfriend", card=card))
    assert r["status"] == "confirm_diet" and nv[0] not in cart_items(db, users["priya"])


def test_fourth_run_a_vegetarian_diet_saved_this_turn_counts_at_once(db, users):
    [nv] = mains(db, False)
    db.execute("delete from public.user_preferences where user_id = %s and key = 'diet'", (users["arjun"],))
    save = {"key": "diet", "value": "vegetarian", "source": "chat_request", "user_words": "remember I'm vegetarian"}
    asked = run_turn(db, [], "remember I'm vegetarian", users["arjun"],
                     chat=Script([("save_preference", save)], "Save it?"), **PROMPT)
    turn = run_turn(db, asked.messages, "yes", users["arjun"], chat=Script(
        [("save_preference", {**save, "source": "chat_confirmed", "user_words": "yes"})],
        [("add_to_cart", {"item_id": nv[0], "branch_id": nv[1], "qty": 2})], "ok"), **PROMPT)
    assert statuses(turn) == ["ok", "confirm_diet"] and nv[0] not in cart_items(db, users["arjun"])


def test_fourth_run_a_failed_add_that_moved_delivery_drops_the_order_card(db, users, full_cart):
    shown = run_turn(db, [], "show cart", users["arjun"], chat=Script(
        [("view_cart", {})], [("search_dishes", {"query": "biryani", "area": "Kondapur"})],
        [("add_to_cart", {"item_id": "no-such-item", "branch_id": full_cart["branch"]})], "ok"), **PROMPT)
    assert shown.card is None or shown.card["kind"] != "order"


def test_fourth_run_the_plan_card_shows_where_it_delivers(db, users):
    plan = nonveg_plan(db, users["priya"])
    r = run_tool("add_plan_to_cart", {"request": PAIR, "plan_id": plan["plan_id"]},
                 ToolContext(conn=db, user_id=users["priya"], user_message="that one"))
    assert r["confirm_card"]["deliver_to"] and "Delivers to" in cards.text(r["confirm_card"])


@pytest.mark.parametrize("bad", [{"kind": "order"}, {"kind": "order", "cart_id": "c"}, {"kind": "remove"},
                                 {"kind": "diet"}, {"kind": "delivery", "area": "x"}, "text", None])
def test_fourth_run_a_malformed_stored_card_is_ignored_not_crashed_on(bad):
    history = [{"role": "user", "content": "x"}, {"role": "assistant", "content": "y", cards.CARD_KEY: bad}]
    assert cards.pending(history) is None
    assert cards.CARD_KEY not in cards.for_model(history)[1]


def test_fourth_run_one_turn_at_a_time_per_user(db, users):
    from app.agent import store
    with store.user_turn_lock(db, users["arjun"]):
        held = db.execute("select count(*) as n from pg_locks where locktype = 'advisory' and pid = pg_backend_pid()"
                          ).fetchone()["n"]
    after = db.execute("select count(*) as n from pg_locks where locktype = 'advisory' and pid = pg_backend_pid()"
                       ).fetchone()["n"]
    assert held == after + 1



@pytest.mark.parametrize("kind", ["order", "remove", "delivery"])
def test_verification_run_a_spaced_ellipsis_acts_on_no_card(db, users, full_cart, kind):
    """The verification run: "ok. . ." read as a plain yes and acted on every card."""
    calls = {"order": [("view_cart", {})], "remove": [("remove_from_cart", {"item_id": full_cart["item"]})],
             "delivery": [("set_delivery", {"area": "Kondapur"})]}[kind]
    asked = run_turn(db, [], "x", users["arjun"], chat=Script(calls, "Ok?"), **PROMPT)
    assert asked.card["kind"] == kind
    act = {"order": [("confirm_cart", ids_of(full_cart))], "remove": [("remove_from_cart", {"item_id": full_cart["item"]})],
           "delivery": [("set_delivery", {"area": "Kondapur"})]}[kind]
    turn = run_turn(db, asked.messages, "ok. . .", users["arjun"], chat=Script(act, "ok"), **PROMPT)
    assert statuses(turn)[0] != "ok", (kind, statuses(turn))
    assert orders_of(db, users["arjun"]) == 0 and cart_items(db, users["arjun"]) == {full_cart["item"]}
    assert view_cart(db, users["arjun"])["delivery"]["area_id"] == full_cart["delivery"]["area_id"]
