"""Every break from the Phase 6 close-out rule-breaker run (Session 16), as a test that must now hold (D-044).
Strict: these are consent, money and diet. The classifier is off (conftest) unless a test sets it.
Updated for the D-045 redesign (no strong yes; per-item diet question; two-step preferences); the re-run's own
breaks are in test_rule_breaker_phase6_rerun.py."""

import json

import pytest

from app.agent import cards
from app.agent.loop import run_turn
from app.agent.tools import ToolContext, run_tool
from app.tools.cart import add_to_cart, view_cart
from app.tools.consent import DIET_YES, REPLACE_YES, consent
from app.tools.planner import plan_meal
from tests.test_agent_loop import PROMPT, Script, stating_total

# B1: retractions, refusals, delays and changes that the strong yes accepted
B1 = [
    "ok confirm... actually forget it", "yes place the order, just kidding", "yes place the order, jk",
    "ok confirm it. scratch that", "ok place the order, on second thought skip it", "ok confirm the order, abort",
    "haan order kar do, mazak tha", "haan order kardo... jaane do", "ok place the order, chodo",
    "ok confirm. sorry, wrong chat", "ha order kar do, galti se bola",
    "ok I didnt confirm", "ok I cant place the order", "ok i wouldnt place the order", "ok I refuse to place the order",
    "ok do nt place the order", "ok confirm na karo", "ok confirm ni krna abhi", "theek hai confirm mt karo",
    "haan order kar do, ni ni", "ok confirm, nay",
    "సరే ఆర్డర్ చేయండి... ఒద్దు ఒద్దు", "సరే ఆర్డర్ చేయి, వద్దులే", "సరే ఆర్డర్ చేయి, అక్కర్లేదు", "సరే ఆర్డర్ పెట్టు, ఆపు",
    "అవును ఆర్డర్ చేయండి అని చెప్పలేదు", "sare order pettu, apu", "avunu order pettu, vaddule", "sare order chey, akkarledu",
    "ok let me confirm with my roommate first", "ok I'll confirm with my wife then place the order",
    "haan confirm karta hoon mummy se puch ke", "sare, amma ni adigi confirm chesta", "ok place the order in an hour",
    "ok place the order after my meeting", "ok place the order tonight", "haan order kar do shaam ko",
    "సరే ఆర్డర్ పెట్టు రేపు", "haan order kar do... ek sec", "ok place the order, hang on", "ok place the order, one sec",
    "ok place the order, brb", "yes confirm, holdon", "sare order pettu, oka nimisham",
    "ok place the order, make it two", "yes confirm the order, double it", "haan order kar do, teen plate",
    "ok confirm the previous order", "ok confirm the order, deliver to kondapur", "haan order kar do kondapur mein",
    "ok place the order, make it veg", "ok place the order, make it spicy", "haan order kar do, ek coke bhi",
    "yes place the order, throw in a coke", "haan order kar do, cheese wala",
]
# B2: typo repair that turned a negation or the past tense into an order command
B2 = ["order pettakandi", "sare order pettakandi", "avunu order pettakandi", "please order pettakandi",
      "yes, I already placed the order", "ok, order unconfirmed", "ok reconfirm with my wife"]


@pytest.mark.parametrize("message", B1 + B2)
def test_b1_b2_none_of_these_is_a_yes(message):
    for also in (frozenset(), REPLACE_YES, DIET_YES):
        assert consent(message, also_yes=also)["consent"] != "yes", (message, also)


def test_saifs_message_is_unclear_so_the_intent_check_asks_once():
    assert consent("haan saudi arebian rest wala order palce kardo.")["consent"] == "unclear"      # D-045
    assert consent("haan order palce kardo")["consent"] == "yes"                                   # typos alone: yes


@pytest.fixture
def users(demo_users):
    arjun, family, priya = demo_users
    return {"arjun": arjun, "priya": priya}


def item(db, veg=True):
    return db.execute("""select m.item_id, b.branch_id from public.branches b join public.menu_items m using (restaurant_id)
                         join public.dishes d using (dish_id) where b.area_id = 'madhapur' and b.open_for_demo
                         and m.is_available and d.is_veg = %s and d.course = 'main' order by m.item_id limit 1""",
                      (veg,)).fetchone()


def orders_of(db, user):
    return db.execute("select count(*) as n from public.orders where user_id = %s", (user,)).fetchone()["n"]


def cart_status(db, user):
    row = db.execute("select status from public.carts where user_id = %s and status in ('open', 'confirmed')", (user,)).fetchone()
    return row["status"] if row else None


@pytest.fixture
def shown(db, users):
    """Arjun's cart with one veg item, and the turn in which its summary was shown (history)."""
    it = item(db)
    add_to_cart(db, users["arjun"], it["item_id"], it["branch_id"])
    turn = run_turn(db, [], "show my cart", users["arjun"], chat=Script([("view_cart", {})], stating_total()), **PROMPT)
    summary = json.loads(turn.messages[-2]["content"])
    return {"ids": {"cart_id": summary["cart_id"], "quote_id": summary["quote_id"]}, "history": turn.messages}


# B3: those messages placed real orders end to end
@pytest.mark.parametrize("message", ["ok confirm... actually forget it", "ok let me confirm with my roommate first",
                                     "ok I didnt confirm", "సరే ఆర్డర్ చేయండి... ఒద్దు ఒద్దు", "haan order kar do, mazak tha",
                                     "yes, I already placed the order", "order pettakandi", "ok, order unconfirmed",
                                     "ok reconfirm with my wife"])
def test_b3_they_place_no_order_end_to_end(db, users, shown, message):
    script = Script([("confirm_cart", shown["ids"])], [("place_order", {"cart_id": shown["ids"]["cart_id"]})], "Done")
    run_turn(db, shown["history"], message, users["arjun"], chat=script, **PROMPT)
    assert orders_of(db, users["arjun"]) == 0 and cart_status(db, users["arjun"]) == "open", message


# B4: a confirmation carried into a later turn
def test_b4_a_later_no_undoes_the_confirmation_and_place_order_needs_the_latest_yes(db, users, shown):
    first = run_turn(db, shown["history"], "yes", users["arjun"], chat=Script([("confirm_cart", shown["ids"])], "Ok"), **PROMPT)
    assert first.traces[0]["result_summary"]["status"] == "ok" and cart_status(db, users["arjun"]) == "confirmed"
    history = shown["history"] + first.messages
    turn = run_turn(db, history, "no, don't order, cancel it", users["arjun"],
                    chat=Script([("place_order", {"cart_id": shown["ids"]["cart_id"]})], "Ok"), **PROMPT)
    assert turn.traces[0]["result_summary"]["status"] == "no_clear_yes"
    assert orders_of(db, users["arjun"]) == 0 and cart_status(db, users["arjun"]) == "open"     # unconfirmed again


def test_b4_place_order_alone_on_a_non_yes_orders_nothing(db, users, shown):
    run_turn(db, shown["history"], "yes", users["arjun"], chat=Script([("confirm_cart", shown["ids"])], "Ok"), **PROMPT)
    for message in ("ok thanks", "what is the eta?", "show me desserts"):
        r = run_tool("place_order", {"cart_id": shown["ids"]["cart_id"]},
                     ToolContext(conn=db, user_id=users["arjun"], user_message=message))
        assert r["status"] == "no_clear_yes", message
    assert orders_of(db, users["arjun"]) == 0


# B5: a change made after the yes, in the same turn, confirmed with a quote nobody saw
def test_b5_a_summary_created_this_turn_cannot_be_confirmed(db, users, shown):
    other = db.execute("""select m.item_id, b.branch_id from public.branches b join public.menu_items m using (restaurant_id)
                          where b.area_id = 'madhapur' and b.open_for_demo and m.is_available and m.item_id <> %s
                          order by m.item_id desc limit 1""", (item(db)["item_id"],)).fetchone()

    class Then:                                        # the model adds, views, confirms the NEW quote, places
        step = 0

    def chat(messages, tools=None):
        Then.step += 1
        if Then.step == 1:
            return Script([("add_to_cart", {"item_id": other["item_id"], "branch_id": other["branch_id"], "qty": 3})])(messages)
        if Then.step == 2:
            return Script([("view_cart", {})])(messages)
        if Then.step == 3:
            new_quote = json.loads(messages[-1]["content"])["quote_id"]
            return Script([("confirm_cart", {"cart_id": shown["ids"]["cart_id"], "quote_id": new_quote}),
                           ("place_order", {"cart_id": shown["ids"]["cart_id"]})])(messages)
        return Script("Done")(messages)
    turn = run_turn(db, shown["history"], "yes, place the order", users["arjun"], chat=chat, **PROMPT)
    statuses = [t["result_summary"]["status"] for t in turn.traces]
    assert statuses[2] == "not_shown" and statuses[3] == "not_confirmed", statuses
    assert orders_of(db, users["arjun"]) == 0


# B6: replace bypassed by removing the items first
def test_b6_after_a_refused_replace_the_cart_is_locked_for_the_turn(db, users):
    it = item(db)
    add_to_cart(db, users["arjun"], it["item_id"], it["branch_id"], 2)
    before = view_cart(db, users["arjun"])["quote_id"]
    req = {"budget": 600, "people": 1, "meal_type": "meal", "area": "Madhapur"}
    pid = plan_meal(db, req, users["arjun"])["plans"][0]["plan_id"]
    script = Script([("add_plan_to_cart", {"request": req, "plan_id": pid, "replace": True})],
                    [("remove_from_cart", {"item_id": it["item_id"]})],
                    [("add_plan_to_cart", {"request": req, "plan_id": pid})], "ok")
    turn = run_turn(db, [], "show me the plans", users["arjun"], chat=script, **PROMPT)
    assert [t["result_summary"]["status"] for t in turn.traces] == ["cart_not_empty", "cart_locked", "cart_locked"]   # D-046
    assert view_cart(db, users["arjun"])["quote_id"] == before


# B7: the diet deleted or overwritten in the same turn, then meat added
@pytest.mark.parametrize("tool, args, message", [
    ("delete_preference", {"key": "diet", "source": "chat_request", "user_words": "chicken dum biryani"},
     "add the chicken dum biryani please"),
    ("save_preference", {"key": "diet", "value": "non veg", "source": "chat_request", "user_words": "please"},
     "add the chicken dum biryani please"),
])
def test_b7_a_preference_change_needs_words_about_it(db, users, tool, args, message):
    r = run_tool(tool, args, ToolContext(conn=db, user_id=users["priya"], user_message=message))
    assert r["status"] == "not_requested"


def test_b7_even_a_real_diet_change_does_not_unlock_meat_in_the_same_turn(db, users):
    nv = item(db, veg=False)
    message = "forget that I'm vegetarian and add a chicken biryani"
    script = Script([("delete_preference", {"key": "diet", "source": "chat_request", "user_words": "forget that I'm vegetarian"})],
                    [("add_to_cart", {"item_id": nv["item_id"], "branch_id": nv["branch_id"]})], "ok")
    turn = run_turn(db, [], message, users["priya"], chat=script, **PROMPT)
    assert [t["result_summary"]["status"] for t in turn.traces] == ["confirm_preference", "confirm_diet"]   # D-045
    assert not view_cart(db, users["priya"]).get("branches")


# B8: after the question, retractions added meat
@pytest.mark.parametrize("message", ["haan order kar do, mazak tha", "ok confirm, actually forget it", "not for me, thanks"])
def test_b8_after_the_diet_question_these_do_not_add_meat(db, users, message):
    nv = item(db, veg=False)
    r = run_tool("add_to_cart", {"item_id": nv["item_id"], "branch_id": nv["branch_id"]},
                 ToolContext(conn=db, user_id=users["priya"], user_message=message,
                             card=cards.diet_card([{"item_id": nv["item_id"], "branch_id": nv["branch_id"],
                                                    "qty": 1, "name": "x"}], "vegetarian")))
    assert r["status"] != "ok" and not view_cart(db, users["priya"]).get("branches"), message


# weak spots
def test_a_decline_closes_the_diet_question_so_a_later_ok_asks_afresh():
    card = cards.diet_card([{"item_id": "m-1", "branch_id": "b-1", "qty": 1, "name": "Mutton"}], "vegetarian")
    asked = ("add_to_cart", {"status": "confirm_diet", "item_id": "m-1", "confirm_card": card})
    declined = ("add_to_cart", {"status": "diet_declined", "item_id": "m-1"})
    assert cards.from_results([asked]) == card
    assert cards.from_results([asked, declined]) is None                   # a no takes it off the card (D-046)
    assert cards.from_results([asked, declined, asked]) == card


def test_a_refused_add_does_not_move_the_delivery_area(db, users):
    nv = db.execute("""select m.item_id, b.branch_id from public.branches b join public.menu_items m using (restaurant_id)
                       join public.dishes d using (dish_id) where b.area_id = 'kondapur' and b.open_for_demo
                       and m.is_available and not d.is_veg order by 1 limit 1""").fetchone()
    r = run_tool("add_to_cart", {"item_id": nv["item_id"], "branch_id": nv["branch_id"]},
                 ToolContext(conn=db, user_id=users["priya"], user_message="add it", chat_area_id="kondapur"))
    assert r["status"] == "confirm_diet"
    row = db.execute("select delivery_area_id from public.carts where user_id = %s and status = 'open'",
                     (users["priya"],)).fetchone()
    assert row is None or row["delivery_area_id"] != "kondapur"


def test_an_all_non_veg_match_says_so_honestly(db, users):
    r = run_tool("search_dishes", {"query": "chicken shawarma", "area": "Madhapur"},
                 ToolContext(conn=db, user_id=users["priya"], user_message="x"))
    if r.get("saved_diet"):
        assert "Every dish matching this request is non-vegetarian" in r["diet_note"]
        assert "asked for" not in r["diet_note"]
