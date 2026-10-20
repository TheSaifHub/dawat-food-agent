"""app.agent.loop (Phase 6c, D-034). A scripted fake model drives the loop; tools are the real ones on the
rolled-back database. Loop mechanics get plain tests; the yes check, identity and money get the strict ones."""

import json
import uuid

import pytest

from app.agent import cards, llm, loop
from app.agent.loop import (BUSY_WITH_CART, MAX_TOOL_CALLS, STEP_CAP_MESSAGE, compact_result, run_turn,
                            summarise)
from app.tools import restaurants

PROMPT = {"system_prompt": "You are Dawat AI (test prompt).", "prompt_version": "test-1"}


class Script:
    """A fake llm.chat: each entry is a reply text, a list of (tool, arguments) calls, an exception to raise, or a
    function of the messages so far that returns the reply text (e.g. one stating the total a tool gave)."""

    def __init__(self, *steps):
        self.steps, self.seen = list(steps), []

    def __call__(self, messages, tools=None):
        self.seen.append([dict(m) for m in messages])
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        if callable(step):
            step = step(messages)
        model = "gemini/test"
        if isinstance(step, str):
            return {"message": {"content": step, "tool_calls": []}, "raw_message": {"role": "assistant", "content": step},
                    "model": model, "attempts": [{"model": model, "outcome": "ok"}], "seconds": 0.01, "usage": {}}
        calls = [{"id": f"call_{len(self.seen)}_{i}", "name": n,
                  "arguments": a if isinstance(a, str) else json.dumps(a)} for i, (n, a) in enumerate(step)]
        raw = {"role": "assistant", "content": None, "provider_specific_fields": {"thought_signatures": ["sig"]},
               "tool_calls": [{"id": c["id"], "type": "function",
                               "function": {"name": c["name"], "arguments": c["arguments"]}} for c in calls]}
        return {"message": {"content": None, "tool_calls": calls}, "raw_message": raw, "model": model,
                "attempts": [{"model": model, "outcome": "ok"}], "seconds": 0.01, "usage": {}}


def stating_total(text="Shall I place the order?"):
    """A reply that shows the latest grand_total a tool returned, as a real summary does (D-045: the proof)."""
    def reply(messages):
        totals = [json.loads(m["content"]).get("grand_total") for m in messages if m.get("role") == "tool"]
        total = [x for x in totals if isinstance(x, int)][-1]
        return f"Total ₹{total:,}. {text}"
    return reply


BUSY = llm.LLMUnavailable([{"model": "gemini/test", "outcome": "overloaded"}, {"model": "groq/test", "outcome": "rate_limited"}])


def assert_well_formed(messages):
    """Every tool call the model made has exactly one tool answer, so the history is valid for the next request."""
    asked = [c["id"] for m in messages if m["role"] == "assistant" for c in m.get("tool_calls") or []]
    answered = [m["tool_call_id"] for m in messages if m["role"] == "tool"]
    assert sorted(asked) == sorted(answered)
    assert messages[0]["role"] == "user" and messages[-1]["role"] == "assistant" and messages[-1]["content"]


@pytest.fixture
def users(demo_users):
    arjun, family, priya = demo_users
    return {"arjun": arjun, "priya": priya}


def veg_item(db):
    """A veg item in Madhapur, the same one every run. Priya is a saved vegetarian, so a non-veg item would (rightly)
    get the diet card instead of being added; without ORDER BY the old query depended on physical row order."""
    return db.execute("select m.item_id, b.branch_id from public.menu_items m join public.branches b using "
                      "(restaurant_id) join public.dishes d using (dish_id) where b.area_id = 'madhapur' "
                      "and m.is_available and b.open_for_demo and d.is_veg order by m.item_id, b.branch_id "
                      "limit 1").fetchone()


# ─── mechanics (plain tests) ─────────────────────────────────────────────────────────────────────────────

def test_a_plain_answer_needs_no_tools(db):
    turn = run_turn(db, [], "hi", None, chat=Script("Hello! What would you like to eat?"), **PROMPT)
    assert (turn.status, turn.reply, turn.traces) == ("ok", "Hello! What would you like to eat?", [])
    assert turn.messages == [{"role": "user", "content": "hi"},
                             {"role": "assistant", "content": "Hello! What would you like to eat?"}]


def test_tools_run_and_their_compact_results_go_back(db):
    script = Script([("search_dishes", {"query": "chicken biryani", "area": "Madhapur"})], "Here are some biryanis.")
    turn = run_turn(db, [{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "ok"}],
                    "biryani in Madhapur", None, chat=script, **PROMPT)
    assert turn.reply == "Here are some biryanis." and turn.status == "ok"
    second_request = script.seen[1]
    assert second_request[0] == {"role": "system", "content": PROMPT["system_prompt"]}
    assert [m["role"] for m in second_request[1:]] == ["user", "assistant", "user", "assistant", "tool"]
    assert second_request[-2]["provider_specific_fields"] == {"thought_signatures": ["sig"]}   # sent back unchanged
    sent = json.loads(second_request[-1]["content"])
    assert sent["status"] == "ok" and sent["results"] and "dish_id" not in sent["results"][0]
    [trace] = turn.traces
    assert trace["step"] == 1 and trace["ok"] and trace["tool_name"] == "search_dishes"
    assert trace["arguments"] == {"query": "chicken biryani", "area": "Madhapur"}
    assert trace["result_summary"]["status"] == "ok" and trace["result_summary"]["results_count"] > 0
    assert (trace["provider"], trace["model"], trace["prompt_version"]) == ("gemini", "gemini/test", "test-1")
    assert_well_formed(turn.messages)


def test_a_bad_call_goes_back_to_the_model_to_fix(db):
    script = Script([("search_dishes", '{"query": "biryani", "area": "Madhapur"')],      # broken JSON
                    [("search_dishes", {"query": "biryani", "area": "Madhapur", "user_id": "x"})],
                    [("no_such_tool", {})],
                    [("search_dishes", {"query": "biryani", "area": "Madhapur"})], "Found them.")
    turn = run_turn(db, [], "biryani", None, chat=script, **PROMPT)
    assert turn.reply == "Found them." and [t["ok"] for t in turn.traces] == [False, False, False, True]
    assert json.loads(script.seen[1][-1]["content"])["status"] == "invalid_arguments"
    assert json.loads(script.seen[3][-1]["content"])["status"] == "unknown_tool"
    assert turn.traces[0]["arguments"] == {"_unparsed": '{"query": "biryani", "area": "Madhapur"'}


def test_the_step_cap_stops_a_looping_model(db):
    script = Script(*[[("search_restaurants", {"query": "Mehfil"})]] * (MAX_TOOL_CALLS + 1))
    turn = run_turn(db, [], "mehfil", None, chat=script, **PROMPT)
    assert (turn.status, turn.reply) == ("step_cap", STEP_CAP_MESSAGE)
    assert [t["step"] for t in turn.traces] == list(range(1, MAX_TOOL_CALLS + 1))
    assert len(script.seen) == MAX_TOOL_CALLS + 1
    assert json.loads(turn.messages[-2]["content"])["status"] == "not_run"
    assert_well_formed(turn.messages)


def test_a_turn_that_needs_exactly_eight_calls_still_answers(db):
    script = Script(*[[("search_restaurants", {"query": "Mehfil"})]] * MAX_TOOL_CALLS, "Done.")
    turn = run_turn(db, [], "mehfil", None, chat=script, **PROMPT)
    assert (turn.status, turn.reply, len(turn.traces)) == ("ok", "Done.", MAX_TOOL_CALLS)


def test_many_calls_in_one_answer_are_capped_too(db):
    script = Script([("search_restaurants", {"query": "Mehfil"})] * 11)
    turn = run_turn(db, [], "mehfil", None, chat=script, **PROMPT)
    assert turn.status == "step_cap" and len(turn.traces) == MAX_TOOL_CALLS and len(script.seen) == 1
    not_run = [m for m in turn.messages if m["role"] == "tool" and '"not_run"' in m["content"]]
    assert len(not_run) == 3
    assert_well_formed(turn.messages)


def test_a_crashing_tool_is_rolled_back_alone(db, users, monkeypatch):
    def crash(conn, **kwargs):
        conn.execute("insert into public.user_preferences (user_id, key, value, source) values (%s, 'language', "
                     "'\"te\"', 'seed') on conflict (user_id, key) do update set value = excluded.value",
                     (users["priya"],))
        raise RuntimeError("boom with internal details")
    monkeypatch.setattr(restaurants, "search_restaurants", crash)
    before = db.execute("select value from public.user_preferences where user_id = %s and key = 'language'",
                        (users["priya"],)).fetchone()
    item = veg_item(db)
    script = Script([("add_to_cart", {"item_id": item["item_id"], "branch_id": item["branch_id"]})],
                    [("search_restaurants", {"query": "Mehfil"})], "Sorry, that step failed.")
    turn = run_turn(db, [], "add it and find mehfil", users["priya"], chat=script, **PROMPT)
    after = db.execute("select value from public.user_preferences where user_id = %s and key = 'language'",
                       (users["priya"],)).fetchone()
    assert after == before                                                 # the crashing tool's write is gone
    assert db.execute("select count(*) as n from public.cart_items ci join public.carts c using (cart_id) "
                      "where c.user_id = %s", (users["priya"],)).fetchone()["n"] == 1   # the earlier add stays
    crashed = turn.traces[1]
    assert (crashed["ok"], crashed["error"]) == (False, "RuntimeError")
    assert "boom" not in script.seen[2][-1]["content"]                      # no internals to the model


def test_compact_results_drop_internals_but_never_change_a_value():
    result = {"status": "ok", "grand_total": 617, "dish_id": "x", "lat": 17.4, "note": None,
              "understood": {"dish_words": "biryani", "quantity": None, "typo_corrections": [["biriyani", "biryani"]]},
              "results": [{"item_id": f"i{n}", "price": 100 + n, "match": "exact", "course": "main"} for n in range(20)],
              "items": [{"item_id": f"m{n}", "price": n} for n in range(30)]}
    out = compact_result(result)
    assert out["grand_total"] == 617 and "dish_id" not in out and "lat" not in out and "note" not in out
    assert out["understood"] == {"dish_words": "biryani", "typo_corrections": [["biriyani", "biryani"]]}
    assert len(out["results"]) == 15 and out["results_not_shown"] == 5
    assert out["results"][3] == {"item_id": "i3", "price": 103}
    assert len(out["items"]) == 30 and "items_not_shown" not in out          # menus aren't cut at 15
    assert summarise({"status": "ok", "message": "x" * 500, "results": [1, 2], "grand_total": 5}) == {
        "status": "ok", "message": "x" * 200 + "…", "results_count": 2, "grand_total": 5}


# ─── busy (money: what the user is told about their cart and order) ──────────────────────────────────────

def test_busy_before_anything_happened_is_the_plain_message(db):
    turn = run_turn(db, [], "hi", None, chat=Script(BUSY), **PROMPT)
    assert (turn.status, turn.reply) == ("busy", llm.BUSY_MESSAGE)
    assert turn.llm_calls[0]["attempts"][1]["outcome"] == "rate_limited"


def test_busy_after_adding_to_the_cart_says_it_is_in_the_cart(db, users):
    item = veg_item(db)
    turn = run_turn(db, [], "add it", users["priya"], chat=Script(
        [("add_to_cart", {"item_id": item["item_id"], "branch_id": item["branch_id"]})], BUSY), **PROMPT)
    assert (turn.status, turn.reply) == ("busy", BUSY_WITH_CART)
    assert_well_formed(turn.messages)


def test_busy_after_a_failed_add_is_the_plain_message(db, users):
    turn = run_turn(db, [], "add it", users["priya"], chat=Script(
        [("add_to_cart", {"item_id": "nope", "branch_id": "b-n1"})], BUSY), **PROMPT)
    assert turn.reply == llm.BUSY_MESSAGE


# ─── the yes check, identity and money through the loop (strict) ─────────────────────────────────────────

DINNER = {"budget": 1000, "people": 4, "veg_count": 2, "non_spicy_count": 1, "meal_type": "dinner", "area": "Madhapur"}


@pytest.fixture
def summary_shown(db, users):
    """Priya has a plan in her cart and has been shown its summary: returns the quote."""
    plans = run_turn(db, [], "dinner", users["priya"], chat=Script([("plan_meal", DINNER)], "Pick one."), **PROMPT)
    plan = json.loads(plans.messages[-2]["content"])["plans"][0]
    run_turn(db, [], "the first", users["priya"], chat=Script(
        [("add_plan_to_cart", {"request": DINNER, "plan_id": plan["plan_id"]})], "Added."), **PROMPT)
    cart = run_turn(db, [], "show cart", users["priya"], chat=Script([("view_cart", {})], stating_total()), **PROMPT)
    shown = json.loads(cart.messages[-2]["content"])
    return {"cart_id": shown["cart_id"], "quote_id": shown["quote_id"], "grand_total": shown["grand_total"],
            "history": cart.messages}                     # the turn that showed the summary (D-044)


def orders_of(db, user_id) -> int:
    return db.execute("select count(*) as n from public.orders where user_id = %s", (user_id,)).fetchone()["n"]


@pytest.mark.parametrize("message", ["ok thanks", "wait", "what's the delivery fee?", "show me plan 2", "nahi"])
def test_the_model_cannot_order_without_the_users_own_yes(db, users, summary_shown, message):
    ids = {"cart_id": summary_shown["cart_id"], "quote_id": summary_shown["quote_id"]}
    script = Script([("confirm_cart", ids)], [("place_order", {"cart_id": ids["cart_id"]})], "Done!")
    turn = run_turn(db, summary_shown["history"], message, users["priya"], chat=script, **PROMPT)
    assert [t["result_summary"]["status"] for t in turn.traces] == ["no_clear_yes", "no_clear_yes"]   # D-044
    assert orders_of(db, users["priya"]) == 0


def test_a_yes_from_an_earlier_message_does_not_count(db, users, summary_shown):
    ids = {"cart_id": summary_shown["cart_id"], "quote_id": summary_shown["quote_id"]}
    history = summary_shown["history"] + [{"role": "user", "content": "yes"},
                                          {"role": "assistant", "content": "One more thing first…",
                                           cards.CARD_KEY: summary_shown["history"][-1][cards.CARD_KEY]}]
    turn = run_turn(db, history, "hmm, let me think", users["priya"],
                    chat=Script([("confirm_cart", ids)], "ok"), **PROMPT)
    assert turn.traces[0]["result_summary"]["status"] == "no_clear_yes" and orders_of(db, users["priya"]) == 0


def test_the_model_cannot_supply_the_yes_or_the_source(db, users, summary_shown):
    ids = {"cart_id": summary_shown["cart_id"], "quote_id": summary_shown["quote_id"]}
    script = Script([("confirm_cart", {**ids, "user_message": "yes"})],
                    [("confirm_cart", {**ids, "source": "website"})], "ok")
    turn = run_turn(db, [], "show me plan 2", users["priya"], chat=script, **PROMPT)
    assert [t["result_summary"]["status"] for t in turn.traces] == ["invalid_arguments", "invalid_arguments"]
    assert db.execute("select status from public.carts where cart_id = %s", (ids["cart_id"],)).fetchone()[
        "status"] == "open"


def test_a_clear_yes_asks_for_payment_and_busy_after_it_says_so_from_the_result_itself(db, users, summary_shown):
    # D-061: the yes ends at "pay"; an order exists only after a verified test payment (tests/test_payments.py).
    ids = {"cart_id": summary_shown["cart_id"], "quote_id": summary_shown["quote_id"]}
    script = Script([("confirm_cart", ids)], [("place_order", {"cart_id": ids["cart_id"]})], BUSY)
    turn = run_turn(db, summary_shown["history"], "haan, order kar do", users["priya"], chat=script, **PROMPT)
    placed = turn.traces[1]["result_summary"]
    assert placed["status"] == "payment_required" and placed["grand_total"] == summary_shown["grand_total"]
    assert turn.status == "busy" and orders_of(db, users["priya"]) == 0
    assert turn.reply.startswith("Your order is not placed yet: total ₹") and "is placed" not in turn.reply
    assert f"₹{summary_shown['grand_total']}." in turn.reply and "busy" in turn.reply and "Pay" in turn.reply


def test_tools_act_for_the_signed_in_user_only(db, users, monkeypatch):
    seen = []
    monkeypatch.setattr(loop, "run_tool", lambda name, args, ctx: seen.append((ctx.user_id, ctx.user_message))
                        or {"status": "ok"})
    run_turn(db, [{"role": "user", "content": "yes"}], "latest words", users["arjun"],
             chat=Script([("view_cart", {})], "ok"), **PROMPT)
    assert seen == [(users["arjun"], "latest words")]
