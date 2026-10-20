"""Two fixes from Saif's chat test (D-042): the area named in chat is where the cart delivers, and a saved
vegetarian sees vegetarian dish results by default."""

import pytest

from app.agent.loop import latest_area, run_turn
from app.agent.tools import ToolContext, run_tool
from app.tools.cart import view_cart
from tests.test_agent_loop import PROMPT, Script


@pytest.fixture
def users(demo_users):
    arjun, family, priya = demo_users
    return {"arjun": arjun, "priya": priya}


def an_item_in(db, area_id):
    return db.execute("""select m.item_id, b.branch_id from public.branches b join public.menu_items m using (restaurant_id)
                         join public.dishes d using (dish_id)
                         where b.area_id = %s and b.open_for_demo and m.is_available and d.is_veg and d.course = 'main'
                         order by m.item_id limit 1""", (area_id,)).fetchone()


def cart_delivery(db, user):
    return db.execute("select delivery_area_id, address_id from public.carts where user_id = %s and status = 'open'",
                      (user,)).fetchone()


def tool(name, content):
    return {"role": "tool", "name": name, "content": content}


# ─── the area named in chat ──────────────────────────────────────────────────────────────────────────────

def test_latest_area_is_the_most_recent_resolved_one_from_tool_results_only():
    msgs = [tool("search_dishes", '{"status":"ok","area":{"area_id":"kondapur","name":"Kondapur"}}'),
            tool("plan_meal", '{"status":"ok","delivery":{"area_id":"gachibowli","area":"Gachibowli"}}'),
            {"role": "assistant", "content": '{"status":"ok","area":{"area_id":"uppal"}}'},          # the model's words
            tool("search_dishes", '{"status":"needs_area"}'),                                    # nothing resolved
            tool("search_dishes", "not json")]
    assert latest_area(msgs) == "gachibowli"
    assert latest_area(msgs[:1]) == "kondapur" and latest_area([]) is None


def test_adding_moves_the_cart_to_the_area_named_in_chat(db, users):
    item = an_item_in(db, "kondapur")
    ctx = ToolContext(conn=db, user_id=users["priya"], user_message="add it", chat_area_id="kondapur")
    r = run_tool("add_to_cart", {"item_id": item["item_id"], "branch_id": item["branch_id"]}, ctx)
    assert r["status"] == "ok" and r["delivery_set_to"] == {"area": "Kondapur", "saved_address": False}
    assert cart_delivery(db, users["priya"])["delivery_area_id"] == "kondapur"   # not her Madhapur home
    assert view_cart(db, users["priya"])["delivery"]["area_id"] == "kondapur"


def test_a_saved_address_in_that_area_is_used(db, users):
    db.execute("""insert into public.addresses (user_id, label, line1, area_id, lat, lon, is_default)
                  values (%s, 'Office', 'Test office (fictional)', 'kondapur', 17.462, 78.357, false)""", (users["priya"],))
    item = an_item_in(db, "kondapur")
    ctx = ToolContext(conn=db, user_id=users["priya"], user_message="add it", chat_area_id="kondapur")
    r = run_tool("add_to_cart", {"item_id": item["item_id"], "branch_id": item["branch_id"]}, ctx)
    assert r["delivery_set_to"]["saved_address"] is True
    assert cart_delivery(db, users["priya"])["address_id"] is not None


def test_no_area_named_or_the_same_area_changes_nothing(db, users):
    item = an_item_in(db, "madhapur")
    for area in (None, "madhapur"):
        ctx = ToolContext(conn=db, user_id=users["priya"], user_message="add it", chat_area_id=area)
        r = run_tool("add_to_cart", {"item_id": item["item_id"], "branch_id": item["branch_id"]}, ctx)
        assert r["status"] == "ok" and "delivery_set_to" not in r, area
    assert cart_delivery(db, users["priya"])["delivery_area_id"] == "madhapur"


def test_through_the_loop_a_search_in_kondapur_then_add_delivers_to_kondapur(db, users):
    item = an_item_in(db, "kondapur")
    script = Script([("search_dishes", {"query": "veg biryani", "area": "Kondapur"})],
                    [("add_to_cart", {"item_id": item["item_id"], "branch_id": item["branch_id"]})], "Added!")
    run_turn(db, [], "veg biryani in Kondapur, add one", users["priya"], chat=script, **PROMPT)
    assert cart_delivery(db, users["priya"])["delivery_area_id"] == "kondapur"


# ─── a saved vegetarian sees vegetarian dishes ───────────────────────────────────────────────────────────

def search(db, user, **args):
    return run_tool("search_dishes", {"area": "Madhapur", **args}, ToolContext(conn=db, user_id=user, user_message="x"))


def test_a_saved_vegetarian_gets_only_veg_dishes_by_default(db, users):
    r = search(db, users["priya"], query="biryani")
    assert r["status"] == "ok" and r["results"] and all(x["is_veg"] for x in r["results"])
    assert r["preferences_applied"] == {"diet": "vegetarian", "is_veg": True}


def test_asking_for_a_non_veg_dish_by_name_shows_it_with_a_note(db, users):
    r = search(db, users["priya"], query="chicken biryani")
    assert r["status"] == "ok" and any(not x["is_veg"] for x in r["results"])
    assert r["saved_diet"] == "vegetarian" and "preferences_applied" not in r


def test_others_and_an_explicit_filter_are_unchanged(db, users):
    assert any(not x["is_veg"] for x in search(db, users["arjun"], query="biryani")["results"])
    assert any(not x["is_veg"] for x in search(db, None, query="biryani")["results"])
    r = search(db, users["priya"], query="biryani", is_veg=False)
    assert "preferences_applied" not in r
