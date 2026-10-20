"""Meal planner tools (Phase 5f, D-029): plan_meal and add_plan_to_cart. Plain-JSON results.

plan_meal(request) → up to three checked plans (app.planner.plan). Read-only.

add_plan_to_cart(request, plan_id, replace=False, *, source, user_message=None) → puts the chosen plan in the user's cart.
  · It never takes a list of items from the caller. It re-runs the planner on the same request and finds the plan
    with that plan_id. The planner is deterministic, so the plan is found again exactly; if prices, availability
    or the delivery point changed in between, the id isn't there and the answer is plan_changed with the fresh
    plans. A list of items invented or edited by the LLM can't get into the cart this way.
  · A cart that already has items is left alone (cart_not_empty) unless the user agreed to replace them
    (replace=True), so a plan never quietly mixes with an earlier order, and its budget still means something.
    From chat, code checks that agreement itself (Saif, Session 13), exactly like confirm_cart (D-030): the
    user's latest message, passed by the agent runtime and never written by the LLM, must be a clear yes
    (app.tools.consent), or nothing is removed (no_clear_yes). From the website, the user's own click on the
    "Replace cart" dialog is the yes. `source` has no default, so a chat call can't skip the check by leaving it out.
  · The cart's delivery point is set to the plan's, then every line goes through add_to_cart (all the cart's own
    checks apply), then the cart's server-computed grand_total must equal the plan's. A mismatch is a bug: it
    raises, the whole transaction is rolled back, and nothing is left half-added.
  · It does NOT confirm the cart. The user still sees the cart summary and says yes (confirm_cart, D-026).
"""

import uuid

from psycopg import Connection

from app.planner.plan import plan_meal as _plan_meal
from app.tools import cart as cart_tools
from app.tools.consent import REPLACE_YES, consent
from app.tools.orders import SOURCES


def plan_meal(conn: Connection, request, user_id: uuid.UUID | None = None, diet=...) -> dict:
    """`diet`: the saved diet as of the start of the chat turn (D-044); ... means read it now."""
    return _plan_meal(conn, request, user_id, diet)


class PlanCartMismatch(RuntimeError):
    """The cart total differs from the plan total right after adding the plan: a bug, never shown as a result."""


def add_plan_to_cart(conn: Connection, user_id: uuid.UUID, request, plan_id: str, replace: bool = False, *,
                     source: str, user_message: str | None = None, diet=...) -> dict:
    if source not in SOURCES:
        return {"status": "invalid_input", "message": f"source must be one of {', '.join(SOURCES)}"}
    if not isinstance(plan_id, str) or not plan_id or len(plan_id) > 64:
        return {"status": "invalid_input", "message": "plan_id must be a plan_id from plan_meal"}
    if not isinstance(replace, bool):
        return {"status": "invalid_input", "message": "replace must be true or false"}
    result = _plan_meal(conn, request, user_id, diet)
    if result["status"] not in ("ok", "over_budget", "no_valid_plan"):
        return result                     # invalid request, missing info, an area to clarify: nothing is added
    plan = next((p for p in result.get("plans", []) if p["plan_id"] == plan_id), None)
    if plan is None:
        return {"status": "plan_changed", "planner": result,
                "message": "That plan is no longer available as it was (a price, an item or the delivery point "
                           "changed). Show the user the current plans from `planner` and let them choose again."}

    current = cart_tools.view_cart(conn, user_id)
    if current["branches"] or current.get("unavailable"):
        if not replace:
            return {"status": "cart_not_empty", "cart": current,
                    "message": "The cart already has items. Ask the user whether to replace them with this plan; "
                               "call again with replace=true only if they say yes."}
        if source == "chat":
            said = consent(user_message, also_yes=REPLACE_YES)          # "haan, replace kar do" is a yes here
            if said["consent"] != "yes":
                return {"status": "no_clear_yes", "consent": said, "cart": current,
                        "message": ("The user said no or asked to wait. The cart was left as it is; ask what they'd "
                                    "like to do." if said["consent"] == "no" else
                                    "The user's latest message isn't a clear yes to replacing the cart. Nothing was "
                                    "changed. Ask again: replace the current cart with this plan?")}
        cart = cart_tools._active_cart(conn, user_id)
        cart_tools.reopen(conn, cart["cart_id"])
        conn.execute("delete from public.cart_items where cart_id = %s", (cart["cart_id"],))

    d = result["delivery"]
    moved = (cart_tools.set_delivery(conn, user_id, address_id=d["address_id"]) if d["address_id"]
             else cart_tools.set_delivery(conn, user_id, area=d["area"]))
    if moved["status"] == "unknown_user":
        return moved
    if moved["status"] != "ok":
        raise PlanCartMismatch(f"could not set the plan's delivery point: {moved['status']}")
    for r in plan["restaurants"]:
        for it in r["items"]:
            added = cart_tools.add_to_cart(conn, user_id, it["item_id"], r["branch_id"], it["qty"])
            if added["status"] != "ok":
                raise PlanCartMismatch(f"adding {it['item_id']} failed: {added['status']}")

    cart = cart_tools.view_cart(conn, user_id)
    if cart["status"] != "ok" or cart["grand_total"] != plan["grand_total"]:
        raise PlanCartMismatch(f"plan total {plan['grand_total']} but cart total {cart.get('grand_total')}")
    return {"status": "ok", "plan_id": plan_id, "plan_label": plan["label"], "cart": cart,
            "message": "The plan is in the cart. Show the cart summary with its grand_total exactly as given, ask "
                       "for a clear yes, and only then call confirm_cart with the cart's quote_id."}
