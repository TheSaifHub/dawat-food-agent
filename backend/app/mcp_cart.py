"""The two cart-changing tools the MCP server exposes (Phase 9 M2, D-067), with the rules of an ADDITIVE-ONLY caller.

Over MCP there is no user message and no confirmation card, so nothing here may depend on the user saying yes. The
approved list (Saif, D-065) is therefore only things that add and can be undone on the website:

  add_to_cart       one item, any amount up to MAX_ITEM_QTY in total per line
  add_plan_to_cart  one of plan_meal's plans, into an EMPTY cart only

and these refusals, all decided by code from the database and the verified token, never from anything the model says:

  · cart_confirmed   a cart that is confirmed (the user said yes on the website, maybe mid-payment) is never touched;
                     adding would silently reopen it and undo that yes (D-045, D-061)
  · qty_limit        more than MAX_ITEM_QTY of one item in the cart (the website's own cap is 20)
  · cart_limit       more than MAX_CART_UNITS items in the cart in total
  · diet_blocked     a non-veg item for a saved vegetarian or eggetarian; Dawat AI asks them first on the website's
                     chat, and here nobody can be asked
  · cart_not_empty   a plan never replaces what is in the cart; replacing is the website's job

The schemas are closed and have no `replace` field. Removing, replacing, changing delivery and saving preferences are
not offered at all. The reply never carries cart_id, quote_id or a confirmation card.
"""

import json
from dataclasses import dataclass

from jsonschema import Draft202012Validator

from app.agent.tools import BRANCH_ID, ITEM_ID, MEAL_REQUEST, ToolContext, _obj, _refuse, _tidy, _text
from app.tools import cart, planner, preferences

MAX_ITEM_QTY = 10             # of one item in the cart, over MCP (the website allows 20)
MAX_CART_UNITS = 30           # items in the whole cart, over MCP (the biggest plan, 10 people, has about 20)
WEBSITE = "Do it on the Dawat website."

QTY = {"type": "integer", "minimum": 1, "maximum": MAX_ITEM_QTY, "description": "How many. Default 1."}
ADD_TO_CART = _obj({"item_id": ITEM_ID, "branch_id": BRANCH_ID, "qty": QTY}, ("item_id", "branch_id"))
ADD_PLAN = _obj({"request": MEAL_REQUEST, "plan_id": _text("The plan_id of the plan the user picked.", 64)},
                ("request", "plan_id"))


@dataclass(frozen=True)
class CartTool:
    name: str
    description: str
    parameters: dict


CART_TOOLS = {
    "add_to_cart": CartTool(
        "add_to_cart",
        "Add an item to the user's cart (item_id and branch_id from get_menu or search_dishes). It only adds: it can't "
        f"remove anything, and it never touches a cart the user has already confirmed. At most {MAX_ITEM_QTY} of one "
        f"item and {MAX_CART_UNITS} items in total from here. Nothing is ordered: the user reviews the cart and "
        "orders on the Dawat website.", ADD_TO_CART),
    "add_plan_to_cart": CartTool(
        "add_plan_to_cart",
        "Put the plan the user picked into their cart. Pass the SAME request you gave plan_meal and that plan's "
        "plan_id. Only into an empty cart: it never replaces anything. Nothing is ordered: the user reviews the cart "
        "and orders on the Dawat website.", ADD_PLAN),
}
_VALIDATORS = {name: Draft202012Validator(t.parameters) for name, t in CART_TOOLS.items()}


def _refusal(status: str, message: str, **extra) -> dict:
    return {"status": status, "message": message, **extra}


def public_cart(view) -> dict | None:
    """A cart view as the MCP client may see it: no ids to confirm with, no confirmation card, no instructions
    meant for the website's chat."""
    if not isinstance(view, dict):
        return None
    return {k: v for k, v in view.items() if k not in ("cart_id", "quote_id", "can_confirm", "confirm_card", "message")}


def _state(ctx: ToolContext):
    """(status, units, {(item_id, branch_id): qty}) of the user's open or confirmed cart, row-locked for this
    transaction so two calls at once can't both pass the limits."""
    active = cart._active_cart(ctx.conn, ctx.user_id)
    if active is None:
        return None, 0, {}
    lines = {(r["item_id"], r["branch_id"]): r["qty"] for r in ctx.conn.execute(
        "select item_id, branch_id, qty from public.cart_items where cart_id = %s", (active["cart_id"],)).fetchall()}
    return active["status"], sum(lines.values()), lines


def _vegetarian_only(ctx: ToolContext) -> bool:
    """The saved diet NOW (a card or a yes can't exist here, so there is no 'diet at the start of the turn')."""
    return preferences.saved_diet(ctx.conn, ctx.user_id) in preferences.VEG_DIETS


def check_additions(ctx: ToolContext, additions: list[dict], *, empty_only: bool = False) -> dict | None:
    """additions: [{item_id, branch_id, qty, name, is_veg}]. A refusal, or None when all of them may be added."""
    status, units, lines = _state(ctx)
    if status == "confirmed":
        return _refusal("cart_confirmed", "Nothing was added: the user's cart is already confirmed on the website. "
                        "Changing it from here would undo that. They can finish that order, or change the cart on the "
                        "Dawat website.")
    if empty_only and units:
        return _refusal("cart_not_empty", "Nothing was added: the cart already has items, and a plan never replaces "
                        "them. Replacing a cart is something the user does on the Dawat website.")
    added: dict = {}
    for a in additions:
        key = (a["item_id"], a["branch_id"])
        added[key] = added.get(key, 0) + a["qty"]
    for key, qty in added.items():
        if lines.get(key, 0) + qty > MAX_ITEM_QTY:
            return _refusal("qty_limit", f"Nothing was added: at most {MAX_ITEM_QTY} of one item can be in the cart "
                            f"from here ({lines.get(key, 0)} already). For more, use the Dawat website.",
                            max_qty=MAX_ITEM_QTY, in_cart=lines.get(key, 0))
    if units + sum(added.values()) > MAX_CART_UNITS:
        return _refusal("cart_limit", f"Nothing was added: at most {MAX_CART_UNITS} items in total can be in the cart "
                        f"from here ({units} already). For more, use the Dawat website.",
                        max_items=MAX_CART_UNITS, in_cart=units)
    if _vegetarian_only(ctx):
        meat = sorted({a["name"] for a in additions if not a["is_veg"]})
        if meat:
            return _refusal("diet_blocked", f"Nothing was added: the user's saved diet is vegetarian and {', '.join(meat)} "
                            f"is not. Dawat can't ask them from here: offer vegetarian options, or tell them to add it "
                            "on the Dawat website where they can confirm.", items=meat)
    return None


def _add_to_cart(ctx: ToolContext, a: dict) -> dict:
    item = ctx.conn.execute("select d.name, d.is_veg from public.menu_items m join public.dishes d using (dish_id) "
                            "where m.item_id = %s", (a["item_id"],)).fetchone()
    qty = a.get("qty", 1)
    if item is not None:               # an unknown item gets cart.add_to_cart's own answer
        refused = check_additions(ctx, [{**a, "qty": qty, "name": item["name"], "is_veg": item["is_veg"]}])
        if refused:
            return refused
    result = cart.add_to_cart(ctx.conn, ctx.user_id, a["item_id"], a["branch_id"], qty)
    if result.get("status") != "ok":
        return {k: v for k, v in result.items() if k != "cart"}
    return {"status": "ok", "added": result["added"], "cart": public_cart(result.get("cart")),
            "message": "Added to the user's cart. Nothing is ordered: the user reviews the cart and orders on the "
                       "Dawat website."}


def _add_plan_to_cart(ctx: ToolContext, a: dict) -> dict:
    found = planner.plan_meal(ctx.conn, a["request"], ctx.user_id, preferences.saved_diet(ctx.conn, ctx.user_id))
    plan = next((p for p in found.get("plans", []) if p.get("plan_id") == a["plan_id"]), None)
    if plan is None:
        if found.get("status") in ("ok", "over_budget", "no_valid_plan"):
            return _refusal("plan_changed", "Nothing was added: that plan is no longer available as it was. Plan again "
                            "with plan_meal and let the user choose.")
        return {k: v for k, v in found.items() if k != "plans"}
    additions = [{"item_id": it["item_id"], "branch_id": r["branch_id"], "qty": it["qty"], "name": it["name"],
                  "is_veg": bool(it.get("is_veg"))} for r in plan["restaurants"] for it in r["items"]]
    refused = check_additions(ctx, additions, empty_only=True)
    if refused:
        return refused
    # replace is fixed to False: even if the cart filled up between the check and now, the planner refuses.
    result = planner.add_plan_to_cart(ctx.conn, ctx.user_id, a["request"], a["plan_id"], False, source="chat",
                                      user_message=None, diet=preferences.saved_diet(ctx.conn, ctx.user_id))
    if result.get("status") != "ok":
        return {k: v for k, v in result.items() if k not in ("cart", "planner")}
    return {"status": "ok", "plan_id": result["plan_id"], "plan_label": result["plan_label"],
            "cart": public_cart(result.get("cart")),
            "message": "The plan is in the user's cart. Nothing is ordered: the user reviews the cart and orders on "
                       "the Dawat website."}


_RUN = {"add_to_cart": _add_to_cart, "add_plan_to_cart": _add_plan_to_cart}


def run_cart_tool(name: str, arguments, ctx: ToolContext) -> dict:
    """Validate against the MCP schema (stricter than the agent's), then run. Same argument rules as run_tool."""
    if not isinstance(arguments, dict):
        return _refuse("The arguments must be a JSON object.")
    if len(json.dumps(arguments, default=str)) > 4000:
        return _refuse("The arguments are too long.")
    arguments = _tidy(arguments, CART_TOOLS[name].parameters)
    errors = sorted(_VALIDATORS[name].iter_errors(arguments), key=lambda e: list(e.absolute_path))
    if errors:
        return _refuse(f"Invalid arguments for {name}. Fix them and call again.",
                       errors=[(("/".join(map(str, e.absolute_path)) + ": ") if e.absolute_path else "") + e.message
                               for e in errors[:3]])
    return _RUN[name](ctx, arguments)
