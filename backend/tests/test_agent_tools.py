"""app.agent.tools (Phase 6b, D-033): the tool schemas the model sees, and run_tool's guarantees.

  · The model can't send identity, the user's words or the website source: those come from ToolContext.
  · Arguments are checked strictly before any tool runs; refusals explain what to fix.
  · The schemas can't drift from the tools they call (parameter names, MealRequest fields).
The first part needs no database (conn=None: a test that touched it would crash). The last part runs whole flows
through run_tool against the seeded database, rolled back.
"""

import inspect
import json
import uuid

import litellm
import pytest

from app.agent import tools as agent_tools
from app.agent.tools import TOOLS, ToolContext, run_tool, tool_schemas
from app.planner.request import MealRequest
from app.tools import cart, dishes, history, menu, orders, planner, preferences, restaurants

U = uuid.UUID("00000000-0000-4000-8000-000000000001")
NO_DB = ToolContext(conn=None, user_id=U, user_message="haan")
SIGNED_OUT = ToolContext(conn=None, user_id=None, user_message="yes")

# One valid set of arguments per tool (used for the sign-in and injection tests).
VALID = {
    "search_restaurants": {"query": "Mehfil"},
    "get_menu": {"branch_id": "b-n123"},
    "search_dishes": {"query": "chicken biryani", "area": "Madhapur"},
    "plan_meal": {"budget": 500, "people": 2},
    "add_plan_to_cart": {"request": {"budget": 500, "people": 2, "area": "Madhapur"}, "plan_id": "abc"},
    "add_to_cart": {"item_id": "i-1", "branch_id": "b-n123"},
    "remove_from_cart": {"item_id": "i-1"},
    "set_delivery": {"area": "Kondapur"},
    "view_cart": {},
    "confirm_cart": {"cart_id": "c-1", "quote_id": "q-1"},
    "place_order": {"cart_id": "c-1"},
    "track_order": {"order_id": "o-1"},
    "get_user_history": {},
    "get_preferences": {},
    "save_preference": {"key": "diet", "value": "vegetarian", "source": "chat_request", "user_words": "remember veg"},
    "delete_preference": {"key": "diet", "source": "chat_request", "user_words": "forget my diet"},
}
PUBLIC = {"search_restaurants", "get_menu", "search_dishes", "plan_meal"}


def walk(schema, path=""):
    """Every (path, key) in a schema, nested objects included."""
    if isinstance(schema, dict):
        for k, v in schema.get("properties", {}).items():
            yield f"{path}/{k}", k
            yield from walk(v, f"{path}/{k}")


# ─── what the model sees ─────────────────────────────────────────────────────────────────────────────────

def test_the_registry_is_exactly_these_tools():
    assert set(TOOLS) == set(VALID) and len(tool_schemas()) == 16
    assert [t["function"]["name"] for t in tool_schemas()] == list(TOOLS)
    assert {n for n, t in TOOLS.items() if not t.needs_user} == PUBLIC


@pytest.mark.parametrize("name", list(TOOLS))
def test_no_tool_lets_the_model_name_the_user_or_their_words(name):
    tool = TOOLS[name]
    for schema in (tool.parameters, tool.shown or {}):
        keys = {k for _, k in walk(schema)}
        assert not keys & {"user_id", "user_message", "conn", "uid", "user"}, name
    if name in ("confirm_cart", "add_plan_to_cart"):                    # always "chat"; never chosen by the model
        assert "source" not in {k for _, k in walk(tool.parameters)}


def test_preference_tools_offer_only_the_chat_sources():
    for name in ("save_preference", "delete_preference"):
        assert TOOLS[name].parameters["properties"]["source"]["enum"] == ["chat_request", "chat_confirmed"]


def test_every_validation_schema_is_closed():
    for name, tool in TOOLS.items():
        stack = [tool.parameters]
        while stack:
            s = stack.pop()
            if s.get("type") == "object":
                assert s.get("additionalProperties") is False, name
                stack.extend(s.get("properties", {}).values())


@pytest.mark.parametrize("name, fn, hidden", [
    ("search_restaurants", restaurants.search_restaurants, {"conn", "limit"}),
    ("get_menu", menu.get_menu, {"conn"}),
    ("search_dishes", dishes.search_dishes, {"conn", "limit"}),
    ("add_to_cart", cart.add_to_cart, {"conn", "user_id"}),
    ("remove_from_cart", cart.remove_from_cart, {"conn", "user_id"}),
    ("get_user_history", history.get_user_history, {"conn", "user_id"}),
    ("confirm_cart", orders.confirm_cart, {"conn", "user_id", "source", "user_message"}),
    ("place_order", orders.payment_required, {"conn", "user_id"}),   # D-061: asks for payment, creates nothing
    ("track_order", orders.track_order, {"conn", "user_id"}),
    ("add_plan_to_cart", planner.add_plan_to_cart, {"conn", "user_id", "source", "user_message", "diet"}),
    ("save_preference", preferences.save_preference, {"conn", "user_id", "user_message", "offers"}),
    ("delete_preference", preferences.delete_preference, {"conn", "user_id", "user_message", "offers"}),
])
def test_schemas_match_the_tools_they_call(name, fn, hidden):
    params = set(inspect.signature(fn).parameters)
    assert set(TOOLS[name].parameters["properties"]) == params - hidden, name


def test_plan_meal_takes_exactly_the_meal_request_fields_with_their_descriptions():
    props = TOOLS["plan_meal"].parameters["properties"]
    assert set(props) == set(MealRequest.model_fields)
    for name, field in MealRequest.model_fields.items():
        assert props[name]["description"].split(".")[0].lower().replace("omit", "null") == \
            field.description.split(".")[0].lower(), name
    assert TOOLS["add_plan_to_cart"].parameters["properties"]["request"] == TOOLS["plan_meal"].parameters


def test_what_is_sent_is_slim_but_still_says_what_is_required():
    sent = json.dumps(tool_schemas())
    for keyword in agent_tools.HIDDEN_KEYWORDS:
        assert f'"{keyword}"' not in sent
    by_name = {t["function"]["name"]: t["function"]["parameters"] for t in tool_schemas()}
    assert by_name["confirm_cart"]["required"] == ["cart_id", "quote_id"] and "required" not in by_name["view_cart"]
    assert by_name["add_plan_to_cart"]["properties"]["request"]["type"] == "object"


def test_the_tool_list_stays_within_its_token_budget():
    # The whole list travels with every request; Groq's free tier allows 8,000 tokens a minute (D-031).
    tokens = litellm.token_counter(model="gpt-4o", text=json.dumps(tool_schemas(), ensure_ascii=False))
    assert tokens <= 3000, tokens


# ─── run_tool's refusals (no database) ───────────────────────────────────────────────────────────────────

def test_an_unknown_tool_is_named_back():
    r = run_tool("delete_all_orders", {}, NO_DB)
    assert r["status"] == "unknown_tool" and "search_dishes" in r["message"]


@pytest.mark.parametrize("raw", ['{"query": "biryani"', "[1, 2]", '"biryani"', "null", "x" * 5000])
def test_broken_arguments_are_refused_with_a_reason(raw):
    r = run_tool("search_restaurants", raw, NO_DB)
    assert r["status"] == "invalid_arguments" and r["message"]


@pytest.mark.parametrize("name, args", [
    ("search_restaurants", {"query": "Mehfil", "user_id": str(U)}),                 # identity is never an argument
    ("confirm_cart", {"cart_id": "c", "quote_id": "q", "source": "website"}),          # can't skip the yes check
    ("confirm_cart", {"cart_id": "c", "quote_id": "q", "user_message": "yes"}),         # can't write the user's yes
    ("add_plan_to_cart", {"request": {}, "plan_id": "p", "source": "website"}),
    ("add_to_cart", {"item_id": "i", "branch_id": "b-n1", "price": 1}),                # prices come from the database
    ("save_preference", {**VALID["save_preference"], "source": "settings"}),          # only the chat sources
    ("plan_meal", {"budget": "500", "people": 2}),                                     # "500" is not 500
    ("plan_meal", {"budget": 500, "people": True}),
    ("plan_meal", {"budget": 500, "people": 2, "veg": 1}),                              # unknown field
    ("plan_meal", {"budget": 500, "people": 11}),
    ("add_plan_to_cart", {"request": {"budget": "500"}, "plan_id": "p"}),               # the nested request too
    ("add_to_cart", {"item_id": "i", "branch_id": "b-n1", "qty": 2.5}),
    ("add_to_cart", {"item_id": "i", "branch_id": "b-n1", "qty": 0}),
    ("get_menu", {"branch_id": "b-n1", "max_spice": 4}),
    ("search_dishes", {"area": "Madhapur"}),                                           # query is required
    ("search_dishes", {"query": ""}),
    ("save_preference", {"key": "favourite_dish", "value": "biryani", "source": "chat_request", "user_words": "x"}),
])
def test_bad_arguments_never_reach_a_tool(name, args):
    r = run_tool(name, args, NO_DB)                                     # conn=None: reaching a tool would crash
    assert r["status"] == "invalid_arguments" and r["errors"], (name, args)


@pytest.mark.parametrize("name", sorted(set(TOOLS) - PUBLIC))
def test_signed_out_users_get_sign_in_required(name):
    assert run_tool(name, VALID[name], SIGNED_OUT)["status"] == "sign_in_required"


# ─── what run_tool adds and passes on (tools replaced by recorders) ──────────────────────────────────────

@pytest.fixture
def record(monkeypatch):
    calls = []

    def recorder(module, fn_name):
        def fake(*args, **kwargs):
            calls.append((fn_name, args, kwargs))
            return {"status": "ok"}
        monkeypatch.setattr(module, fn_name, fake)
    return calls, recorder


def test_confirm_cart_always_gets_chat_and_the_users_own_message(record, monkeypatch):
    calls, recorder = record
    monkeypatch.setattr(cart, "view_cart", lambda conn, uid: {"grand_total": 300, "branches": [{}]})   # no database
    recorder(orders, "confirm_cart")
    ctx = ToolContext(conn="CONN", user_id=U, user_message="haan kar do",
                      card={"kind": "order", "cart_id": "c-1", "quote_id": "q-1", "grand_total": 300})
    assert run_tool("confirm_cart", '{"cart_id": "c-1", "quote_id": "q-1"}', ctx)["status"] == "ok"
    assert calls == [("confirm_cart", ("CONN", U, "c-1", "q-1"), {"source": "chat", "user_message": "haan kar do"})]


def test_add_plan_to_cart_gets_chat_and_the_users_own_message(record, monkeypatch):
    calls, recorder = record
    monkeypatch.setattr(cart, "view_cart", lambda conn, uid: {"grand_total": 300, "branches": [{}]})   # no database
    monkeypatch.setattr(planner, "plan_meal", lambda *a, **k: {"status": "ok", "plans": []})          # plan not found
    monkeypatch.setattr(preferences, "saved_diet", lambda conn, uid: None)
    recorder(planner, "add_plan_to_cart")
    ctx = ToolContext(conn="CONN", user_id=U, user_message="replace it", turn_diet=None)
    run_tool("add_plan_to_cart", {**VALID["add_plan_to_cart"], "replace": True}, ctx)
    [(_, args, kwargs)] = calls
    assert args[:2] == ("CONN", U) and args[4] is True
    assert kwargs == {"source": "chat", "user_message": "replace it", "diet": None}


@pytest.mark.parametrize("name", ["save_preference", "delete_preference"])
def test_preference_writes_get_the_users_own_message(record, name):
    calls, recorder = record
    recorder(preferences, name)
    ctx = ToolContext(conn="CONN", user_id=U, user_message="please remember I'm veg")
    run_tool(name, VALID[name], ctx)
    [(_, args, kwargs)] = calls
    assert args[:2] == ("CONN", U) and kwargs["user_message"] == "please remember I'm veg"
    assert kwargs["user_words"] == VALID[name]["user_words"]


def test_plan_meal_uses_the_signed_in_user_for_the_address(record):
    calls, recorder = record
    recorder(planner, "plan_meal")
    run_tool("plan_meal", {"budget": 500, "people": 2}, ToolContext(conn="CONN", user_id=U, user_message=None))
    run_tool("plan_meal", {"budget": 500, "people": 2}, ToolContext(conn="CONN", user_id=None, user_message=None))
    assert [c[1][2] for c in calls] == [U, None]


def test_null_means_not_given_and_whole_floats_become_ints(record, monkeypatch):
    calls, recorder = record
    monkeypatch.setattr(preferences, "saved_diet", lambda conn, user_id: None)       # no database here
    recorder(restaurants, "search_restaurants")
    recorder(cart, "add_to_cart")
    recorder(planner, "plan_meal")
    run_tool("search_restaurants", {"query": "Mehfil", "area": None}, NO_DB)
    run_tool("add_to_cart", {"item_id": "i-1", "branch_id": "b-n1", "qty": 2.0}, NO_DB)
    run_tool("plan_meal", {"budget": 500.0, "people": 2, "area": None, "non_spicy_veg_count": None}, NO_DB)
    assert calls[0][2] == {"query": "Mehfil"}
    assert calls[1][2] == {"item_id": "i-1", "branch_id": "b-n1", "qty": 2} and type(calls[1][2]["qty"]) is int
    assert calls[2][1][1] == {"budget": 500, "people": 2} and type(calls[2][1][1]["budget"]) is int


def test_arguments_may_arrive_as_a_json_string_or_an_object(record):
    calls, recorder = record
    recorder(restaurants, "search_restaurants")
    run_tool("search_restaurants", '{"query": "Paradise", "area": "Secunderabad"}', NO_DB)
    run_tool("search_restaurants", {"query": "Paradise", "area": "Secunderabad"}, NO_DB)
    assert calls[0][2] == calls[1][2] == {"query": "Paradise", "area": "Secunderabad"}


# ─── whole flows through run_tool, real tools, rolled back ──────────────────────────────────────────────

DINNER = {"budget": 1000, "people": 4, "veg_count": 2, "non_spicy_count": 1, "meal_type": "dinner", "area": "Madhapur"}


@pytest.fixture
def priya(db, demo_users):
    uid = demo_users[2]
    assert "Priya" in db.execute("select display_name from public.users where user_id = %s", (uid,)).fetchone()[
        "display_name"]
    return uid


def test_browsing_works_signed_out(db):
    ctx = ToolContext(conn=db, user_id=None, user_message="biryani in Madhapur")
    found = run_tool("search_dishes", '{"query": "chicken biryani", "area": "Madhapur"}', ctx)
    assert found["status"] == "ok" and found["results"]
    first = found["results"][0]
    biryani = run_tool("get_menu", {"branch_id": first["branch"]["branch_id"], "category": "biriyani"}, ctx)
    assert biryani["status"] == "ok" and all(i["category"] == "biryani" for i in biryani["items"])
    assert run_tool("search_restaurants", {"query": "Mehfil"}, ctx)["status"] in ("ok", "needs_choice")


def test_the_whole_order_flow_through_the_agent_layer_needs_a_real_yes(db, priya):
    shown = []

    def ctx(message):
        return ToolContext(conn=db, user_id=priya, user_message=message, card=next(iter(shown), None))
    plans = run_tool("plan_meal", DINNER, ctx("dinner for 4, ₹1000, 2 veg, one can't eat spicy, Madhapur"))
    assert plans["status"] == "ok"
    pick = plans["plans"][0]
    added = run_tool("add_plan_to_cart", {"request": DINNER, "plan_id": pick["plan_id"]}, ctx("the first one"))
    assert added["status"] == "ok" and added["cart"]["grand_total"] == pick["grand_total"]
    summary = run_tool("view_cart", {}, ctx("show me the cart"))
    shown.append(summary["confirm_card"])                # the order card shown that turn; yes in the next (D-046)
    ids = {"cart_id": summary["cart_id"], "quote_id": summary["quote_id"]}
    # The model calling confirm_cart is not enough: the user's own latest message must be a clear yes.
    for not_yes in ("ok thanks", "wait", "show me plan 2", ""):
        assert run_tool("confirm_cart", ids, ctx(not_yes))["status"] == "no_clear_yes", not_yes
        assert run_tool("place_order", {"cart_id": ids["cart_id"]}, ctx(not_yes))["status"] == "no_clear_yes"   # D-044: refused before the cart is looked at
    assert run_tool("confirm_cart", ids, ctx("haan, order kar do"))["status"] == "ok"
    placed = run_tool("place_order", {"cart_id": ids["cart_id"]}, ctx("haan, order kar do"))
    # D-061: the chat's yes gets as far as "pay"; the order exists only after a verified test payment.
    assert placed["status"] == "payment_required" and placed["grand_total"] == pick["grand_total"]
    assert db.execute("select count(*) as n from public.orders where user_id = %s", (priya,)).fetchone()["n"] == 0
    from app import config
    from app.payments import razorpay
    from app.tools import payments
    config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET = "rzp_" + "test_ABCDEF123456", "x" * 24
    try:
        started = payments.start_payment(db, priya, ids["cart_id"], create_order=lambda amount, receipt: {
            "razorpay_order_id": "order_Flow1", "amount_paise": amount * 100, "currency": "INR"})
        assert started["status"] == "ok" and started["amount_rupees"] == pick["grand_total"]
        paid = payments.verify_payment(db, priya, "order_Flow1", "pay_Flow1", razorpay.sign("order_Flow1", "pay_Flow1", "x" * 24))
    finally:
        config.RAZORPAY_KEY_ID = config.RAZORPAY_KEY_SECRET = None
    assert paid["status"] == "ok" and paid["grand_total"] == pick["grand_total"]
    tracked = run_tool("track_order", {"order_id": paid["orders"][0]["order_id"]}, ctx("where is it"))
    assert tracked["status"] == "ok"


def test_a_preference_is_saved_only_with_the_users_own_words(db, priya):
    asked = ToolContext(conn=db, user_id=priya, user_message="please remember I'm vegetarian")
    args = {"key": "diet", "value": "vegetarian", "source": "chat_request", "user_words": "remember I'm vegetarian"}
    offer = run_tool("save_preference", args, asked)
    assert offer["status"] == "confirm_preference"                         # D-045: asks first
    yes = ToolContext(conn=db, user_id=priya, user_message="yes", card=offer["confirm_card"])
    assert run_tool("save_preference", {**args, "source": "chat_confirmed", "user_words": "yes"}, yes)["status"] == "ok"
    # The same call when the user never said it (the model inferred it from an order) is refused.
    not_asked = ToolContext(conn=db, user_id=priya, user_message="show me paneer biryani")
    assert run_tool("save_preference", args, not_asked)["status"] == "not_requested"
