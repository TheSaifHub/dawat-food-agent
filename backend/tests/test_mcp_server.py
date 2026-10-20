"""The MCP server, module M1 (D-065/D-066): identity and the closed tool list.

Full rigour here, because identity is on the line: the caller is a model in another app. What must hold:
  · who the user is comes ONLY from a token that passes the website's TokenVerifier, checked on every call;
  · a model can't supply a user id, a token, the user's words or a source as a tool argument;
  · only the read-only tools exist; everything that changes the cart, preferences or orders is refused as unknown;
  · a refusal never says why a token failed, and a crash never shows its details.
Each test runs a real MCP client against the real server in memory, over the rolled-back test database.
"""

import json
import time
import uuid
from contextlib import nullcontext

import anyio
import jwt
import pytest
from mcp.client import Client

from app import mcp_server
from app.auth import AuthUnavailable
from app.mcp_server import EXPOSED, Handler, build_server
from app.tools import cart, preferences
from tests.conftest import DROP

CART_AND_ORDER_TOOLS = ("remove_from_cart", "set_delivery", "confirm_cart", "place_order", "save_preference",
                        "delete_preference")


def veg_item(db):
    """A veg item in Madhapur, the same one every run (as in test_agent_loop)."""
    return db.execute("select m.item_id, b.branch_id from public.menu_items m join public.branches b using "
                      "(restaurant_id) join public.dishes d using (dish_id) where b.area_id = 'madhapur' "
                      "and m.is_available and b.open_for_demo and d.is_veg order by m.item_id, b.branch_id "
                      "limit 1").fetchone()


def handler_for(db, verifier, token):
    """A handler whose token comes from `token` (a str or a callable) and whose database is the rolled-back one."""
    source = token if callable(token) else (lambda: token)
    return Handler(token_source=source, verifier=lambda: verifier, connect=lambda: nullcontext(db))


def call(handler, name, arguments=None):
    """(is_error, parsed JSON reply) of one tool call, through a real MCP client."""
    async def go():
        async with Client(build_server(handler)) as client:
            return await client.call_tool(name, arguments or {})
    result = anyio.run(go)
    return result.is_error, json.loads(result.content[0].text)


def tools_listed(handler):
    async def go():
        async with Client(build_server(handler)) as client:
            return await client.list_tools()
    return anyio.run(go).tools


class NoDatabase:
    """A connect() that fails the test if anything opens a connection."""
    def __call__(self):
        raise AssertionError("a connection was opened for a request that should have been refused first")


def refused_handler(verifier, token):
    return Handler(token_source=lambda: token, verifier=lambda: verifier, connect=NoDatabase())


# ─── who the user is ─────────────────────────────────────────────────────────────────────────────────────

def test_the_token_decides_whose_data_it_is(db, verifier, make_token, demo_users):
    a, b = demo_users[0], demo_users[1]
    preferences.save_preference(db, a, "language", "Telugu", "settings")
    preferences.save_preference(db, b, "language", "Hinglish", "settings")
    _, as_a = call(handler_for(db, verifier, make_token(a)), "get_preferences")
    _, as_b = call(handler_for(db, verifier, make_token(b)), "get_preferences")
    assert "te" in json.dumps(as_a) and "hinglish" not in json.dumps(as_a).lower()
    assert "hinglish" in json.dumps(as_b).lower() and '"te"' not in json.dumps(as_b)


def test_one_users_cart_is_never_shown_to_another(db, verifier, make_token, demo_users):
    a, b = demo_users[0], demo_users[1]
    item = veg_item(db)
    added = cart.add_to_cart(db, a, str(item["item_id"]), str(item["branch_id"]), 1)
    assert added["status"] == "ok", added
    _, mine = call(handler_for(db, verifier, make_token(a)), "view_cart")
    _, theirs = call(handler_for(db, verifier, make_token(b)), "view_cart")
    assert mine.get("branches") and mine["grand_total"] > 0
    assert not theirs.get("branches")


@pytest.mark.parametrize("token", [None, "", "   ", "not-a-jwt"])
def test_no_usable_token_means_sign_in_and_no_database(verifier, token):
    err, reply = call(refused_handler(verifier, token), "search_restaurants", {"query": "Mehfil"})
    assert err and reply["status"] == "sign_in_required"


def test_forged_expired_and_malformed_tokens_are_all_refused_alike(verifier, make_token, attacker_key):
    uid = uuid.uuid4()
    now = int(time.time())
    bad = {
        "signed by someone else": make_token(uid, key=attacker_key),
        "expired": make_token(uid, iat=now - 7200, exp=now - 3600),
        "wrong issuer": make_token(uid, iss="https://evil.example/auth/v1"),
        "wrong audience": make_token(uid, aud="someone-else"),
        "not a user role": make_token(uid, role="service_role"),
        "anonymous": make_token(uid, is_anonymous=True),
        "no subject": make_token(uid, sub=DROP),
        "subject isn't an id": make_token(uid, sub="not-a-uuid"),
        "unknown key id": make_token(uid, kid="other-key"),
        "no key id": make_token(uid, kid=None),
        "hmac instead of es256": jwt.encode({"sub": str(uid), "aud": "authenticated", "role": "authenticated",
                                             "iss": "x", "iat": now, "exp": now + 3600}, "s" * 32, algorithm="HS256"),
        "alg none": jwt.encode({"sub": str(uid)}, None, algorithm="none"),
    }
    replies = {}
    for why, token in bad.items():
        err, reply = call(refused_handler(verifier, token), "get_preferences")
        assert err and reply["status"] == "sign_in_required", why
        replies[why] = reply
    assert len({json.dumps(r, sort_keys=True) for r in replies.values()}) == 1       # no hint which check failed
    text = json.dumps(list(replies.values()))          # the replies only, not the labels above
    for word in ("expired", "signature", "issuer", "audience", "forged", "anonymous", "algorithm"):
        assert word not in text.lower()


def test_the_token_is_checked_again_on_every_call(db, verifier, make_token, demo_users):
    a, b = demo_users[0], demo_users[1]
    preferences.save_preference(db, a, "language", "Telugu", "settings")
    preferences.save_preference(db, b, "language", "Hinglish", "settings")
    now = int(time.time())
    current = {"token": make_token(a)}
    handler = handler_for(db, verifier, lambda: current["token"])
    _, first = call(handler, "get_preferences")
    assert "te" in json.dumps(first)
    current["token"] = make_token(a, iat=now - 7200, exp=now - 3600)              # it expires mid-session
    err, second = call(handler, "get_preferences")
    assert err and second["status"] == "sign_in_required"
    current["token"] = make_token(b)                                              # a different user's token
    _, third = call(handler, "get_preferences")
    assert "hinglish" in json.dumps(third).lower() and '"te"' not in json.dumps(third)


def test_a_valid_token_for_a_deleted_account_is_refused(db, verifier, make_token):
    ghost = uuid.uuid4()                       # signed correctly, but there is no such account
    err, reply = call(handler_for(db, verifier, make_token(ghost)), "get_preferences")
    assert err and reply["status"] == "sign_in_required"
    assert db.execute("select count(*) as n from public.users where user_id = %s", (ghost,)).fetchone()["n"] == 0


def test_a_sign_in_check_that_cannot_run_says_unavailable_not_signed_out(db):
    class Down:
        def verify(self, token):
            raise AuthUnavailable("keys unreachable")
    err, reply = call(Handler(token_source=lambda: "x.y.z", verifier=lambda: Down(), connect=NoDatabase()), "view_cart")
    assert err and reply["status"] == "unavailable"


def test_a_missing_sign_in_configuration_is_unavailable_and_private(db):
    def broken():
        raise RuntimeError("SUPABASE_URL=https://secret-project.supabase.co is not set")
    err, reply = call(Handler(token_source=lambda: "x.y.z", verifier=broken, connect=NoDatabase()), "view_cart")
    assert err and reply["status"] == "unavailable" and "secret-project" not in json.dumps(reply)


# ─── what the model can and cannot send ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("extra", [{"user_id": str(uuid.uuid4())}, {"token": "abc"}, {"user_message": "yes"},
                                   {"source": "website"}, {"is_admin": True}])
def test_identity_and_words_cannot_be_sent_as_arguments(db, verifier, make_token, demo_users, extra):
    handler = handler_for(db, verifier, make_token(demo_users[0]))
    for name, args in (("get_preferences", {}), ("view_cart", {}), ("get_user_history", {}),
                       ("search_restaurants", {"query": "Mehfil"}),
                       ("add_to_cart", {"item_id": "i-1", "branch_id": "b-n1"}),
                       ("add_plan_to_cart", {"request": {"budget": 500, "people": 2, "area": "Madhapur"},
                                             "plan_id": "p"})):
        err, reply = call(handler, name, {**args, **extra})
        assert err and reply["status"] == "invalid_arguments", (name, extra, reply)


def test_every_exposed_tool_schema_is_closed():
    for tool in tools_listed(Handler(token_source=lambda: None, connect=NoDatabase())):
        schema = tool.input_schema
        assert schema["type"] == "object" and schema["additionalProperties"] is False, tool.name
        assert not {"user_id", "token", "user_message", "source", "user_words"} & set(schema.get("properties", {})), tool.name


def test_only_the_approved_tools_are_listed(verifier):
    listed = [t.name for t in tools_listed(refused_handler(verifier, None))]
    assert listed == list(EXPOSED)
    assert set(listed) == {"search_restaurants", "get_menu", "search_dishes", "plan_meal", "view_cart",
                           "get_preferences", "get_user_history", "track_order", "add_to_cart", "add_plan_to_cart"}
    assert not set(CART_AND_ORDER_TOOLS) & set(listed)


@pytest.mark.parametrize("name", CART_AND_ORDER_TOOLS)
def test_cart_and_order_tools_do_not_exist_here(db, verifier, make_token, demo_users, name):
    """Called anyway, they are unknown, and nothing changes: no cart line, order or preference."""
    tables = ("cart_items", "orders", "user_preferences", "carts")
    count = lambda: [db.execute(f"select count(*) as n from public.{t}").fetchone()["n"] for t in tables]
    before = count()
    handler = handler_for(db, verifier, make_token(demo_users[0]))
    err, reply = call(handler, name, {"item_id": "x", "branch_id": "y", "area": "Madhapur", "cart_id": "c",
                                      "quote_id": "q", "plan_id": "p", "key": "diet", "value": "vegetarian",
                                      "source": "settings", "request": {}})
    assert err and reply["status"] == "unknown_tool"
    assert count() == before


# ─── what comes back ─────────────────────────────────────────────────────────────────────────────────────

def test_the_cart_view_cannot_be_used_to_confirm_anything(db, verifier, make_token, demo_users):
    item = veg_item(db)
    cart.add_to_cart(db, demo_users[0], str(item["item_id"]), str(item["branch_id"]), 1)
    err, reply = call(handler_for(db, verifier, make_token(demo_users[0])), "view_cart")
    assert not err and reply["status"] == "ok" and reply["grand_total"] > 0
    text = json.dumps(reply)
    assert "quote_id" not in text and "cart_id" not in text and "confirm_card" not in text
    assert "website" in reply["message"] and "Place order" in reply["message"]


def test_a_crash_inside_a_tool_shows_no_details(db, verifier, make_token, demo_users, monkeypatch):
    def boom(name, arguments, ctx):
        raise RuntimeError("password=hunter2 at postgres://internal")
    monkeypatch.setattr(mcp_server, "run_tool", boom)
    err, reply = call(handler_for(db, verifier, make_token(demo_users[0])), "get_preferences")
    assert err and reply["status"] == "tool_error"
    assert "hunter2" not in json.dumps(reply) and "postgres" not in json.dumps(reply)


def test_browsing_works_with_a_real_search(db, verifier, make_token, demo_users):
    handler = handler_for(db, verifier, make_token(demo_users[0]))
    err, found = call(handler, "search_restaurants", {"query": "Paradise"})
    assert not err and found["status"] in ("ok", "needs_choice")
    err, plan = call(handler, "plan_meal", {"budget": 600, "people": 2, "area": "Madhapur"})
    assert not err and plan["status"] in ("ok", "needs_info", "over_budget", "no_valid_plan")


def test_the_tools_get_the_tokens_user_and_no_user_words(db, verifier, make_token, demo_users, monkeypatch):
    """What the tools receive: the id from the verified token whatever the arguments say, and NO user message, so no
    yes-check can ever be satisfied from here (found by a planted bug: M1's tools don't read it, M2/M3's would)."""
    seen = []

    def spy(name, arguments, ctx):
        seen.append((arguments, ctx))
        return {"status": "ok"}
    monkeypatch.setattr(mcp_server, "run_tool", spy)
    monkeypatch.setattr(mcp_server.mcp_cart, "run_cart_tool", spy)
    me, someone_else = demo_users[0], demo_users[1]
    handler = handler_for(db, verifier, make_token(me))
    for name in EXPOSED:
        call(handler, name, {"user_id": str(someone_else), "uid": str(someone_else), "user_message": "yes"})
    assert len(seen) == len(EXPOSED)
    for arguments, ctx in seen:
        assert ctx.user_id == me and ctx.user_message is None and ctx.card is None
