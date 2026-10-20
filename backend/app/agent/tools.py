"""The tools Dawat AI can call (Phase 6b, D-033): what the model sees, and how a call reaches the tested tool.

    TOOLS                          name → Tool(description, JSON-schema parameters, runner)
    tool_schemas()                 the list sent to the LLM (OpenAI "function" format; LiteLLM converts for Gemini).
                                   A slimmer copy of `parameters`: length limits and additionalProperties are
                                   checked here but not sent, add_plan_to_cart's request is described in one line,
                                   and category is free text. The whole list travels with every request, and Groq's
                                   free tier (the fallback) allows 8,000 tokens a minute.
    run_tool(name, arguments, ctx) → the tool's plain-JSON result, or a refusal the model can read and correct

What the model can and can't say (enforced here, not asked for in the prompt):
  · It sends only the arguments in the schema. Anything else ("user_id", "price", "source" on confirm_cart,
    "user_message") is refused as invalid_arguments, never silently ignored, so the model learns it can't.
  · Who the user is (`user_id`) comes from the verified sign-in token (D-022), via ToolContext.
  · The user's latest message (`user_message`), which the yes checks (D-030) and the preference rule (D-027)
    compare against, comes from the conversation, via ToolContext. Never from the model.
  · confirm_cart and add_plan_to_cart always run with source="chat": the website's source can't be chosen here.
    save/delete_preference offer only the chat sources (chat_request / chat_confirmed), never "settings".
  · Types are strict, as in the tools themselves: "500" is not 500. Two harmless normalisations only: a null
    argument means "not given" (dropped), and a whole float (2.0) for an integer becomes 2.
  · Cart, order, history and preference tools need a signed-in user; without one they answer
    sign_in_required and nothing runs.
"""

import json
import uuid
from dataclasses import dataclass, field
from typing import Callable

from jsonschema import Draft202012Validator
from psycopg import Connection

from app.planner.request import MAX_BUDGET, MAX_PEOPLE, MIN_BUDGET, MealRequest
from app.tools import cart, dishes, history, menu, orders, planner, preferences, restaurants
from app.agent import cards, intent
from app.text import tokens
from app.tools.areas import resolve_area
from app.tools.consent import (DIET_YES, REMOVE_YES, REPLACE_YES, TRAILING_OFF, _plain, _question, consent,
                               only_hesitation)
from app.tools.reference import get_reference

MAX_ARGUMENT_CHARS = 4000


@dataclass(frozen=True)
class ToolContext:
    conn: Connection
    user_id: uuid.UUID | None       # from the verified token (None: not signed in), never from the model
    user_message: str | None        # the user's own latest message, from the conversation, never from the model
    card: dict | None = None        # the confirmation card shown under the previous reply (D-046)
    chat_area_id: str | None = None  # the latest area this conversation's tool results resolved (D-042)
    turn_diet: object = ...                 # the saved diet at the start of the turn (D-044); ... = read it now
    cart_locked: bool = False               # a replacement was refused this turn: no cart changes (D-044)
    cart_had_items: bool = False            # the cart had items when this turn began (D-045)
    spent: dict = field(default_factory=dict)  # diet-card quantities already added this turn (D-046)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    run: Callable[[ToolContext, dict], dict]
    needs_user: bool = False
    shown: dict | None = None       # what the model sees, if not derived from `parameters`


# ─── shared pieces of schema ─────────────────────────────────────────────────────────────────────────────

def _obj(properties: dict, required: tuple[str, ...] = ()) -> dict:
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


def _text(description: str, max_length: int = 200) -> dict:
    return {"type": "string", "minLength": 1, "maxLength": max_length, "description": description}


AREA = _text("Hyderabad area as the user said it, e.g. 'Madhapur'. Omit if the user hasn't said.", 80)
IS_VEG = {"type": "boolean", "description": "true: vegetarian items only. Omit otherwise."}
MAX_SPICE = {"type": "integer", "minimum": 0, "maximum": 3,
             "description": "Highest spice level allowed: 0 none, 1 mild, 2 medium, 3 very spicy."}
MAX_PRICE = {"type": "integer", "minimum": 1, "maximum": 100_000, "description": "Highest price per item, whole rupees."}
# Free text, not an enum of 26 (that cost ~110 tokens per tool, every request): the tools accept spelling variants
# ("biriyani", "starters") and refuse anything else with the allowed list.
CATEGORY = _text("Only this category, e.g. biryani, starter, curry, bread, dessert, drink.", 40)
BRANCH_ID = _text("A branch_id from search_restaurants, search_dishes or get_menu, e.g. 'b-n123456'.", 40)
ITEM_ID = _text("An item_id from get_menu, search_dishes or the cart.", 60)
CART_ID = _text("The cart_id from view_cart.", 60)
QTY = {"type": "integer", "minimum": 1, "maximum": 20, "description": "How many. Default 1."}
CHAT_SOURCE = {"type": "string", "enum": list(preferences.CHAT_SOURCES), "description": (
    "chat_request: the user asks now (nothing changes; ask the question you get). chat_confirmed: their yes to it.")}
USER_WORDS = _text("The user's own words (their request or their yes), copied exactly from their latest message.",
                   preferences.MAX_WORDS_LEN)

# plan_meal's request: the MealRequest fields (app/planner/request.py), with their own descriptions. A test checks
# the two never drift apart.
_MEAL_TYPES = {
    "budget": {"type": "integer", "minimum": MIN_BUDGET, "maximum": MAX_BUDGET},
    "people": {"type": "integer", "minimum": 1, "maximum": MAX_PEOPLE},
    "veg_count": {"type": "integer", "minimum": 0, "maximum": MAX_PEOPLE},
    "non_spicy_count": {"type": "integer", "minimum": 0, "maximum": MAX_PEOPLE},
    "non_spicy_veg_count": {"type": "integer", "minimum": 0, "maximum": MAX_PEOPLE},
    "spice_preference": {"type": "string", "enum": ["mild", "medium", "spicy"]},
    "meal_type": {"type": "string", "enum": ["breakfast", "lunch", "dinner", "meal", "snack"]},
    "area": {"type": "string", "minLength": 1, "maxLength": 80},
}
MEAL_REQUEST = _obj({name: {**_MEAL_TYPES[name], "description": field.description.replace("null if", "Omit if")
                            .replace("null when", "Omit when")}
                     for name, field in MealRequest.model_fields.items()})


# ─── runners: the model's arguments + the runtime's context → the tested tool ────────────────────────────

def _uid(ctx: ToolContext) -> uuid.UUID:
    return ctx.user_id      # needs_user tools only run when this is set


DIET_QUESTION = "You've saved vegetarian, is this for someone else?"


def _intent_fields(check: dict) -> dict:
    """The intent check, flattened so the trace summary keeps it (D-043)."""
    return {"intent_used": bool(check.get("used")), "intent": check.get("intent"),
            "intent_evidence": check.get("evidence"), "intent_fallback": check.get("fallback_reason")}


def _wants_change(check: dict, nothing_done: str) -> dict:
    what = f" ({check['change']})" if check.get("change") else ""
    return {"status": "wants_change", **_intent_fields(check),
            "message": f"{nothing_done} The user wants a change first: \"{check['evidence']}\"{what}. Make that change "
                       "with the tools, then show the new summary and ask again."}


def _card(ctx: ToolContext, kind: str) -> dict | None:
    """The card shown under the previous reply, if it is of this kind (D-046): the only thing a yes can act on."""
    return ctx.card if isinstance(ctx.card, dict) and ctx.card.get("kind") == kind else None


CARD_NOTE = ("The app shows the user a card with the exact details under your reply. Ask your question in one short "
             "line in the user's language; don't repeat the card's numbers.")


def _view_cart(ctx: ToolContext, a: dict) -> dict:
    """view_cart; a summary that can be confirmed comes with its order card (D-046)."""
    view = cart.view_cart(ctx.conn, _uid(ctx))
    card = cards.order_card(view)
    return {**view, cards.RESULT_KEY: card,
            "message": "Quote totals exactly as given; never add them up yourself. To order: ask the user to say yes, "
                       "then confirm_cart with this cart_id and quote_id. " + CARD_NOTE} if card else view


def _confirm_cart(ctx: ToolContext, a: dict) -> dict:
    """confirm_cart from chat: only the order card shown under the previous reply (D-046), on a clear yes (the
    rules, D-030), with the intent check in front (D-043). The tool's own yes check still runs inside."""
    card = _card(ctx, "order")
    if not card or card["quote_id"] != a["quote_id"] or card["cart_id"] != a["cart_id"]:
        fresh = cards.order_card(cart.view_cart(ctx.conn, ctx.user_id))
        return {"status": "not_shown", **({cards.RESULT_KEY: fresh} if fresh else {}),
                "message": "Nothing was confirmed: the user hasn't been shown this order's card. " +
                           ("The app shows it now: ask them to say yes. " + CARD_NOTE if fresh else
                            "Call view_cart.")}
    rules = consent(ctx.user_message)["consent"]
    check, verdict = {"used": False}, "rules"
    if rules != "no":
        check = intent.classify(f"Place the order for ₹{card['grand_total']}?", ctx.user_message)
        verdict = intent.decide("order", rules, check)
        if verdict == "ask_confirm":
            fresh = cards.order_card(cart.view_cart(ctx.conn, ctx.user_id))
            return {"status": "confirm_intent", "question_type": "order", "total": card["grand_total"],
                    "echo": check["evidence"], **_intent_fields(check), **({cards.RESULT_KEY: fresh} if fresh else {}),
                    "message": f"Not confirmed yet: nothing was ordered. The user seems to agree (their words: "
                               f"\"{check['evidence']}\") but didn't say a plain yes. Ask ONE short natural question, "
                               f"in the SAME language and script as the user's latest message, echoing what they told "
                               f"you: place this order? {CARD_NOTE} Do NOT call confirm_cart or place_order again in "
                               "this turn."}
        if verdict == "wants_change":
            return _wants_change(check, "Nothing was ordered and the cart is unchanged.")
    result = orders.confirm_cart(ctx.conn, _uid(ctx), a["cart_id"], a["quote_id"], source="chat",
                                 user_message=ctx.user_message)
    return {**_with_order_card(result), **_intent_fields(check)}


def _with_order_card(result: dict) -> dict:
    """A refusal that carries a fresh cart (stale_quote, quote_changed) shows that cart's order card."""
    if result.get("status") in ("stale_quote", "quote_changed") and isinstance(result.get("cart"), dict):
        card = cards.order_card(result["cart"])
        if card:
            return {**result, cards.RESULT_KEY: card}
    return result


def _place_order(ctx: ToolContext, a: dict) -> dict:
    """place_order from chat needs a clear yes in the user's LATEST message too (fix 2, D-044). A confirmation also
    lasts only for its own turn (D-045: run_turn re-opens any confirmed cart when a turn begins), so the yes that
    confirms is the yes that orders."""
    if consent(ctx.user_message)["consent"] != "yes":
        return {"status": "no_clear_yes", "message": "Nothing was ordered: the user's latest message isn't a clear yes "
                "to placing the order. Show the summary and ask; the items are still in the cart."}
    # Phase 8 (D-061): an order exists only after a verified test payment, which the user does with the Pay button.
    # This runs the same checks as placing an order always did and creates nothing.
    return _with_order_card(orders.payment_required(ctx.conn, _uid(ctx), a["cart_id"]))


def _same_request(x, y) -> bool:
    return json.dumps(x, sort_keys=True, default=str) == json.dumps(y, sort_keys=True, default=str)


def _plan_nonveg(plan: dict) -> list[str]:
    return [it["name"] for r in plan.get("restaurants", []) for it in r.get("items", []) if not it.get("is_veg")]


def _add_plan_to_cart(ctx: ToolContext, a: dict) -> dict:
    """add_plan_to_cart from chat (D-043, D-045, D-046). A plan needs the user's yes to its PLAN CARD when
    (1) the cart had items when the turn began or has items now (it replaces them), or (2) the user's saved diet is
    vegetarian and the plan has non-veg items (Saif, Session 16: the diet question for plans too). The planner's own
    yes check still runs inside for a replacement."""
    if ctx.cart_locked:
        return CART_LOCKED
    current = cart.view_cart(ctx.conn, ctx.user_id)
    needs_replace = bool(ctx.cart_had_items or current.get("branches") or current.get("unavailable"))
    diet = _diet(ctx)
    found = planner.plan_meal(ctx.conn, a["request"], ctx.user_id, ctx.turn_diet)
    plan = next((p for p in found.get("plans", []) if p.get("plan_id") == a["plan_id"]), None)
    nonveg = _plan_nonveg(plan) if plan and diet in preferences.VEG_DIETS else []
    check = {"used": False}
    if plan and (needs_replace or nonveg):
        card = _card(ctx, "plan")
        fresh = cards.plan_card(plan, a["request"], needs_replace, nonveg, diet, found.get("delivery"))
        if needs_replace and not a.get("replace"):
            return {"status": "cart_not_empty", "cart": current, cards.RESULT_KEY: fresh,
                    "message": "The cart had items when the user sent this message. Ask whether to replace them with "
                               "this plan; call again with replace=true only after their yes. " + CARD_NOTE}
        if not card or card["plan_id"] != a["plan_id"] or not _same_request(card["request"], a["request"]) \
                or (needs_replace and not card["replace"]) or (nonveg and not card["nonveg"]):
            return {"status": "cart_not_empty" if needs_replace else "confirm_plan", cards.RESULT_KEY: fresh,
                    "message": ("Not added: the user hasn't said yes to this plan's card" +
                                (" (it includes non-veg items and their saved diet is " + str(diet) + ")"
                                 if nonveg else "") + ". Ask them. " + CARD_NOTE)}
        said = consent(ctx.user_message, also_yes=REPLACE_YES if needs_replace else DIET_YES)
        rules = said["consent"]
        if rules == "no":
            return {"status": "no_clear_yes", "consent": said, "message": "The user said no or asked to wait. The "
                    "cart was left as it is; ask what they'd like to do."}
        check = intent.classify("Add this plan to your cart" + (", replacing what is in it?" if needs_replace else "?"),
                                ctx.user_message)
        verdict = intent.decide("replace", rules, check)
        if verdict == "ask_confirm":
            return {"status": "confirm_intent", "question_type": "replace", "echo": check["evidence"],
                    **_intent_fields(check), cards.RESULT_KEY: fresh,
                    "message": f"Not added yet: the cart is unchanged. The user seems to agree (their words: "
                               f"\"{check['evidence']}\") but didn't say a plain yes. Ask ONE short natural question, in "
                               f"the SAME language and script as the user's latest message, echoing what they said. "
                               f"{CARD_NOTE}"}
        if verdict == "wants_change":
            return _wants_change(check, "The cart is unchanged.")
        if rules != "yes":
            return {"status": "no_clear_yes", "consent": said, **_intent_fields(check), cards.RESULT_KEY: fresh,
                    "message": "The user's latest message isn't a clear yes to this plan. Nothing was changed. "
                               "Ask again. " + CARD_NOTE}
    result = planner.add_plan_to_cart(ctx.conn, _uid(ctx), a["request"], a["plan_id"], a.get("replace", False),
                                      source="chat", user_message=ctx.user_message, diet=ctx.turn_diet)
    if result.get("status") == "ok":
        card = cards.order_card(result.get("cart"))
        if card:
            result = {**result, cards.RESULT_KEY: card,
                      "message": "The plan is in the cart. To order: ask the user to say yes. " + CARD_NOTE}
    return {**result, **_intent_fields(check)}


def _follow_chat_area(ctx: ToolContext) -> dict | None:
    """The area the user named in chat is where the cart delivers (Saif, Session 16, D-042). If the cart delivers
    elsewhere (or nowhere yet), move it there first: to the user's saved address in that area if they have one
    (default first), else to the area itself. Returns what was set, or None if nothing changed."""
    if not ctx.chat_area_id:
        return None
    current = ctx.conn.execute("select delivery_area_id from public.carts where user_id = %s and status in "
                               "('open', 'confirmed') order by status = 'open' desc, created_at desc limit 1",
                               (ctx.user_id,)).fetchone()
    if current and current["delivery_area_id"] == ctx.chat_area_id:
        return None
    addr = ctx.conn.execute("select address_id from public.addresses where user_id = %s and area_id = %s "
                            "order by is_default desc, created_at limit 1", (ctx.user_id, ctx.chat_area_id)).fetchone()
    area = get_reference(ctx.conn).areas.get(ctx.chat_area_id)
    if addr:
        moved = cart.set_delivery(ctx.conn, ctx.user_id, address_id=str(addr["address_id"]))
    elif area:
        moved = cart.set_delivery(ctx.conn, ctx.user_id, area=area["name"])
    else:
        return None
    if moved.get("status") != "ok":
        return None
    return {"area": area["name"] if area else ctx.chat_area_id, "saved_address": bool(addr)}


def _diet(ctx: ToolContext):
    """The saved diet for the diet checks: as of the start of the turn (so changing it in the turn can't unlock
    meat, D-044), but a vegetarian diet saved during the turn counts at once (D-046, fourth run: "yes" to saving
    vegetarian, then meat added in the same turn)."""
    live = preferences.saved_diet(ctx.conn, ctx.user_id)
    if ctx.turn_diet is ... or live in preferences.VEG_DIETS:
        return live
    return ctx.turn_diet


CART_LOCKED = {"status": "cart_locked", "message": "The user hasn't agreed to replace their cart, so the cart can't be "
               "changed in this turn. Ask them what they want; don't remove or add items to get around it."}


def _remove_from_cart(ctx: ToolContext, a: dict) -> dict:
    """Removing from chat always goes through a REMOVE CARD (D-046, after the fourth rule-breaker run): every check
    on the user's own words ("named the dish", "asked to clear") let some message through ("don't remove the
    Avocado Toast", "pet khali hai"). The first call shows the card (calls in one turn merge into one card, so
    "clear my cart" is still one question); after the user's clear yes, each item on it is removed once, exactly as
    shown."""
    if ctx.cart_locked:
        return CART_LOCKED
    card = _card(ctx, "remove")
    branch = a.get("branch_id")
    on_card = next((it for it in (card or {}).get("items", []) if it["item_id"] == a["item_id"]
                    and branch in (None, it.get("branch_id")) and a.get("qty") == it.get("qty")), None)
    key = ("remove", a["item_id"], on_card.get("branch_id") if on_card else branch)
    if on_card and key not in ctx.spent and consent(ctx.user_message, also_yes=REMOVE_YES)["consent"] == "yes":
        ctx.spent[key] = 1
        args = {**a, **({"branch_id": on_card["branch_id"]} if on_card.get("branch_id") else {})}
        return cart.remove_from_cart(ctx.conn, _uid(ctx), **args)
    in_cart = cart.view_cart(ctx.conn, ctx.user_id)
    lines = [(b["branch_id"], it) for b in in_cart.get("branches", []) for it in b["items"] if it["item_id"] == a["item_id"]]
    lines += [(u["branch_id"], u) for u in in_cart.get("unavailable", []) if u["item_id"] == a["item_id"]]
    lines = [(b, it) for b, it in lines if branch in (None, b)]
    if not lines:
        return {"status": "not_in_cart", "item_id": a["item_id"], "message": "That item is not in the cart."}
    if len(lines) > 1:
        return {"status": "needs_branch", "item_id": a["item_id"], "branches": [b for b, _ in lines],
                "message": "This item is in the cart from more than one branch. Ask which one."}
    b, it = lines[0]
    return {"status": "remove_not_asked", cards.RESULT_KEY: cards.remove_card(
                [{"item_id": a["item_id"], "branch_id": b, "qty": a.get("qty"), "name": it["name"]}]),
            "message": "Nothing is removed yet. " + CARD_NOTE}


def _set_delivery(ctx: ToolContext, a: dict) -> dict:
    """Moving the delivery from chat always goes through a DELIVERY CARD (D-046, fourth run: "don't deliver to
    Kondapur" and "is Kondapur too far?" moved it). The user's clear yes to the card moves it to exactly that area."""
    if ctx.cart_locked:
        return CART_LOCKED
    resolved = resolve_area(get_reference(ctx.conn), a["area"])
    if resolved.get("status") != "ok":
        return {"status": resolved["status"], "area_resolution": resolved,
                "message": "Nothing changed. " + resolved.get("message", "")}
    area = resolved["area"]
    card = _card(ctx, "delivery")
    if card and card["area_id"] == area["area_id"] and "delivery" not in ctx.spent \
            and consent(ctx.user_message)["consent"] == "yes":
        ctx.spent["delivery"] = 1
        return cart.set_delivery(ctx.conn, _uid(ctx), area=area["name"])
    return {"status": "delivery_not_asked", cards.RESULT_KEY: cards.delivery_card(area["area_id"], area["name"]),
            "message": "Nothing changed yet. " + CARD_NOTE}


def _add_to_cart(ctx: ToolContext, a: dict) -> dict:
    if ctx.cart_locked:
        return CART_LOCKED
    refused, extra = _diet_check(ctx, a)                 # the diet check first: a refused add moves nothing
    if refused is not None:
        return refused
    moved = _follow_chat_area(ctx)
    result = cart.add_to_cart(ctx.conn, ctx.user_id, **a)
    if result.get("status") == "ok":
        result = {**result, **extra}
        if extra.get("diet_override"):
            key = (a["item_id"], a["branch_id"])
            ctx.spent[key] = ctx.spent.get(key, 0) + a.get("qty", 1)
    if moved and isinstance(result, dict):
        result = {**result, "delivery_set_to": moved,
                  "delivery_note": f"Delivery is set to {moved['area']}, the area the user named. Mention it once."}
    return result


def _search_dishes(ctx: ToolContext, a: dict) -> dict:
    """A saved vegetarian sees vegetarian dishes by default (Saif, Session 16, D-042), unless the request names only
    non-veg dishes ("chicken biryani"): that is an explicit ask, shown as asked (adding it still asks first, D-039).
    An is_veg the model passed on purpose is respected."""
    diet = _diet(ctx) if ctx.user_id else None
    if diet not in preferences.VEG_DIETS or "is_veg" in a:
        return dishes.search_dishes(ctx.conn, **a)
    plain = dishes.search_dishes(ctx.conn, **a)
    matched = plain.get("dishes_matched") or []
    if plain.get("status") not in ("ok", "no_match_with_filters", "none_near_area"):
        return plain
    if matched and not any(d.get("is_veg") for d in matched):
        return {**plain, "saved_diet": diet,
                "diet_note": f"Every dish matching this request is non-vegetarian, and the user's saved diet is {diet}. "
                             "Say so in one line before listing them; adding one will ask them first."}
    veg = dishes.search_dishes(ctx.conn, **a, is_veg=True)
    return {**veg, "preferences_applied": {"diet": diet, "is_veg": True},
            "diet_note": f"Showing vegetarian dishes only, because the user's saved diet is {diet}. Say so in one "
                         "short line; show non-veg only if they ask."}


def _diet_check(ctx: ToolContext, a: dict) -> tuple[dict | None, dict]:
    """The saved-diet check for a chat add (D-039, D-043, D-044, D-046), run before anything else: (refusal or None,
    fields to add to a successful result). A non-veg item for a user whose saved diet (as of the START of the turn,
    so changing the diet in the same turn can't unlock it) is vegetarian is added only if the DIET CARD shown under
    the previous reply lists this item, up to the quantity on the card, and the user's latest message is a clear
    yes (rules + the intent check). Otherwise the app shows a diet card for it and nothing is added. A clear no gives
    diet_declined. The website's own cart route doesn't go through here: this is how Dawat AI behaves, not a rule on
    what users may buy."""
    diet = _diet(ctx)
    if diet not in preferences.VEG_DIETS:
        return None, {}
    item = ctx.conn.execute("select d.is_veg, d.name from public.menu_items m join public.dishes d using (dish_id) "
                            "where m.item_id = %s", (a["item_id"],)).fetchone()
    if item is None or item["is_veg"]:
        return None, {}
    qty = a.get("qty", 1)
    fresh = cards.diet_card([{"item_id": a["item_id"], "branch_id": a["branch_id"], "qty": qty, "name": item["name"]}],
                            diet)
    ask = {"status": "confirm_diet", "item": item["name"], "item_id": a["item_id"], "saved_diet": diet,
           cards.RESULT_KEY: fresh}
    card = _card(ctx, "diet")
    on_card = next((it for it in (card or {}).get("items", [])
                    if it["item_id"] == a["item_id"] and it["branch_id"] == a["branch_id"]), None)
    left = on_card["qty"] - ctx.spent.get((a["item_id"], a["branch_id"]), 0) if on_card else 0
    if qty > left:
        return {**ask, "message": f"Not added. The user's saved diet is {diet} and {item['name']} is not vegetarian. "
                                  f"Ask, in the user's language, naming the item: \"{DIET_QUESTION}\" {CARD_NOTE} "
                                  "Call add_to_cart again only after they answer."}, {}
    said = consent(ctx.user_message, also_yes=DIET_YES)
    if said["consent"] == "no" and not only_hesitation(said):
        return {"status": "diet_declined", "item": item["name"], "item_id": a["item_id"],
                "message": "Not added: the user said no. Offer vegetarian options instead."}, {}
    msg = ctx.user_message or ""
    if said["consent"] == "no" or _question(msg) or not _plain(msg) or TRAILING_OFF.search(msg):
        # D-046 (fourth run): hesitation, a question or an emoji is never a yes, so the classifier isn't asked:
        # "wait, is that chicken?" added the item. (Since D-047 a classifier yes only asks once more anyway.)
        return {**ask, "asked_again": True,
                "message": f"Not added: the user hasn't said yes yet (they hesitated or asked something). Answer "
                           f"them, then ask again: \"{DIET_QUESTION}\" {CARD_NOTE}"}, {}
    rules = said["consent"]
    check = intent.classify(f"You've saved vegetarian. Is the {item['name']} for someone else, so I should "
                            "add it?", ctx.user_message)
    verdict = intent.decide("diet", rules, check)
    if verdict == "wants_change":
        return _wants_change(check, "Nothing was added."), {}
    if verdict == "ask_confirm":
        return {**ask, "asked_again": True, **_intent_fields(check),
                "message": f"Not added yet. Ask once more, naturally, in the SAME language and script as the "
                           f"user's latest message, echoing their words (\"{check['evidence']}\"): is the "
                           f"{item['name']} for someone else? {CARD_NOTE}"}, {}
    if not (verdict == "proceed" or rules == "yes"):
        return {**ask, "asked_again": True, **_intent_fields(check),
                "message": f"Not added: the user's answer wasn't a clear yes or no. Ask again, in the user's "
                           f"language: \"{DIET_QUESTION}\" {CARD_NOTE}"}, {}
    return None, {"diet_override": True, **_intent_fields(check)}


def _preference(ctx: ToolContext, a: dict, write) -> dict:
    """save/delete_preference from chat (D-045, D-046): a chat_request only offers the change (the app shows a
    preference card); chat_confirmed applies exactly the change on the card shown under the previous reply."""
    card = _card(ctx, "preference")
    result = write(offers=(card["offer"],) if card else ())
    if result.get("status") == "confirm_preference":
        result = {**result, cards.RESULT_KEY: cards.preference_card(result["offer"], result.get("label", "")),
                  "message": result["message"] + " " + CARD_NOTE}
    return result


_TOOL_LIST = [
    Tool("search_restaurants",
         "Find restaurants in Hyderabad by name ('Mehfil', 'Paradise'). Returns each restaurant with its branches "
         "and branch_ids. If status is needs_choice, ask which one or which area before showing a menu. For a dish "
         "or a kind of food ('biryani'), use search_dishes instead.",
         _obj({"query": _text("The restaurant name as the user said it."), "area": AREA}, ("query",)),
         lambda ctx, a: restaurants.search_restaurants(ctx.conn, **a)),
    Tool("get_menu",
         "The menu of one branch, optionally filtered. If the user asked for a category (biryani, shawarma), pass "
         "it and show only that category.",
         _obj({"branch_id": BRANCH_ID, "category": CATEGORY, "is_veg": IS_VEG, "max_spice": MAX_SPICE,
               "max_price": MAX_PRICE}, ("branch_id",)),
         lambda ctx, a: menu.get_menu(ctx.conn, **a)),
    Tool("search_dishes",
         "Find dishes on menus in or near an area: 'chicken biryani', 'veg starters under 200', 'karam kam'. Pass "
         "the user's own words as query, in any language. Needs an area; if none is known, ask for it.",
         _obj({"query": _text("What the user wants, in their words."), "area": AREA, "is_veg": IS_VEG,
               "max_spice": MAX_SPICE, "max_price": MAX_PRICE, "category": CATEGORY}, ("query",)),
         _search_dishes),
    Tool("plan_meal",
         "Plan a meal for a budget and/or a group ('₹500 for 2, one is vegetarian'). Use it for EVERY request with "
         "a budget, a group size or mixed diets. Fill only what the user said and omit the rest; code checks the "
         "budget, diets, spice and portions. If status is needs_info, ask for the first missing item only.",
         MEAL_REQUEST,
         lambda ctx, a: planner.plan_meal(ctx.conn, a, ctx.user_id, ctx.turn_diet)),
    Tool("add_plan_to_cart",
         "Put the plan the user picked into the cart. Pass the SAME request you gave plan_meal and that plan's "
         "plan_id. Set replace=true only after the user said yes to replacing what is already in their cart.",
         _obj({"request": MEAL_REQUEST, "plan_id": _text("The plan_id of the plan the user picked.", 64),
               "replace": {"type": "boolean", "description": "true only after the user agreed to replace their cart."}},
              ("request", "plan_id")),
         _add_plan_to_cart,
         needs_user=True,
         shown=_obj({"request": {"type": "object", "description": "Exactly the request object you passed to plan_meal."},
                     "plan_id": {"type": "string", "description": "The plan_id of the plan the user picked."},
                     "replace": {"type": "boolean", "description": "true only after the user agreed to replace their cart."}},
                    ("request", "plan_id"))),
    Tool("add_to_cart",
         "Add an item to the cart (item_id and branch_id from get_menu or search_dishes).",
         _obj({"item_id": ITEM_ID, "branch_id": BRANCH_ID, "qty": QTY}, ("item_id", "branch_id")),
         _add_to_cart, needs_user=True),
    Tool("remove_from_cart",
         "Remove an item from the cart: qty of it, or all of it if qty is omitted.",
         _obj({"item_id": ITEM_ID, "branch_id": BRANCH_ID, "qty": QTY}, ("item_id",)),
         _remove_from_cart, needs_user=True),
    Tool("set_delivery",
         "Change where the cart is delivered, to a Hyderabad area. Prices, fees and availability may change.",
         _obj({"area": _text("The delivery area as the user said it, e.g. 'Kondapur'.", 80)}, ("area",)),
         _set_delivery, needs_user=True),
    Tool("view_cart",
         "The cart with every line, delivery fee, GST and grand_total (all computed by the server), plus cart_id and "
         "quote_id. Show this summary exactly before asking the user for a yes.",
         _obj({}),
         _view_cart, needs_user=True),
    Tool("confirm_cart",
         "Confirm the cart summary the user just said yes to (cart_id and quote_id from the view_cart you showed). "
         "Code checks that their latest message is a clear yes.",
         _obj({"cart_id": CART_ID, "quote_id": _text("The quote_id of the summary the user said yes to.", 64)},
              ("cart_id", "quote_id")),
         _confirm_cart,
         needs_user=True),
    Tool("place_order",
         "Ask the user to pay for a confirmed cart. Places no order: it exists only after payment. Needs confirm_cart first.",
         _obj({"cart_id": CART_ID}, ("cart_id",)),
         _place_order, needs_user=True),
    Tool("track_order",
         "The status timeline of one of the user's orders.",
         _obj({"order_id": _text("The order number (DW1042) or order_id from place_order or get_user_history.", 60)},
              ("order_id",)),
         lambda ctx, a: orders.track_order(ctx.conn, _uid(ctx), a["order_id"]), needs_user=True),
    Tool("get_user_history",
         "The user's past orders, newest first, at the prices they paid.",
         _obj({"limit": {"type": "integer", "minimum": 1, "maximum": history.MAX_LIMIT,
                         "description": f"How many checkouts. Default {history.DEFAULT_LIMIT}."}}),
         lambda ctx, a: history.get_user_history(ctx.conn, _uid(ctx), **a), needs_user=True),
    Tool("get_preferences",
         "The preferences the user saved (diet, max_spice, default_area, language).",
         _obj({}),
         lambda ctx, a: preferences.get_preferences(ctx.conn, _uid(ctx)), needs_user=True),
    Tool("save_preference",
         "Only when the user asks you to remember something. Two steps: chat_request, then chat_confirmed after "
         "their yes in the next message.",
         _obj({"key": {"type": "string", "enum": list(preferences.KEYS)},
               "value": _text("diet: vegetarian / eggetarian / non_vegetarian; max_spice: 0-3; default_area: an "
                              "area name; language: en / hinglish / te.", 80),
               "source": CHAT_SOURCE, "user_words": USER_WORDS}, ("key", "value", "source", "user_words")),
         lambda ctx, a: _preference(ctx, a, lambda offers: preferences.save_preference(
             ctx.conn, _uid(ctx), a["key"], a["value"], a["source"], user_words=a["user_words"],
             user_message=ctx.user_message, offers=offers)),
         needs_user=True),
    Tool("delete_preference",
         "Forget a saved preference (or key 'all') only when the user asks. Same two steps as save_preference.",
         _obj({"key": {"type": "string", "enum": [*preferences.KEYS, "all"]}, "source": CHAT_SOURCE,
               "user_words": USER_WORDS}, ("key", "source", "user_words")),
         lambda ctx, a: _preference(ctx, a, lambda offers: preferences.delete_preference(
             ctx.conn, _uid(ctx), a["key"], a["source"], user_words=a["user_words"],
             user_message=ctx.user_message, offers=offers)),
         needs_user=True),
]
TOOLS = {t.name: t for t in _TOOL_LIST}
_VALIDATORS = {t.name: Draft202012Validator(t.parameters) for t in _TOOL_LIST}


HIDDEN_KEYWORDS = ("minLength", "maxLength", "additionalProperties")


def _shown(schema):
    """The schema minus what only code needs to check (it still checks it; the model just isn't told)."""
    if isinstance(schema, dict):
        return {k: _shown(v) for k, v in schema.items() if k not in HIDDEN_KEYWORDS}
    if isinstance(schema, list):
        return [_shown(v) for v in schema]
    return schema


def tool_schemas() -> list[dict]:
    """The tool list sent with every LLM request."""
    out = []
    for t in _TOOL_LIST:
        params = _shown(t.shown or t.parameters)
        if not params["required"]:
            del params["required"]
        out.append({"type": "function", "function": {"name": t.name, "description": t.description,
                                                     "parameters": params}})
    return out


# ─── running a call ──────────────────────────────────────────────────────────────────────────────────────

def _refuse(message: str, **extra) -> dict:
    return {"status": "invalid_arguments", "message": message, **extra}


def _tidy(value, schema: dict):
    """null → not given; a whole float for an integer → int. Nothing else is changed."""
    if isinstance(value, dict) and schema.get("type") == "object":
        props = schema.get("properties", {})
        return {k: _tidy(v, props.get(k, {})) for k, v in value.items() if v is not None}
    if schema.get("type") == "integer" and isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def run_tool(name: str, arguments, ctx: ToolContext) -> dict:
    """One tool call from the model. Never trusts the model for identity, the user's words or the source."""
    tool = TOOLS.get(name)
    if tool is None:
        return {"status": "unknown_tool", "message": f"There is no tool called {name!r}. Use one of: "
                                                     f"{', '.join(TOOLS)}."}
    if isinstance(arguments, str):
        if len(arguments) > MAX_ARGUMENT_CHARS:
            return _refuse(f"The arguments are too long (over {MAX_ARGUMENT_CHARS} characters).")
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError as e:
            return _refuse(f"The arguments were not valid JSON ({e.msg} at character {e.pos}). Send a JSON object.")
    if not isinstance(arguments, dict):
        return _refuse("The arguments must be a JSON object.")
    arguments = _tidy(arguments, tool.parameters)
    errors = sorted(_VALIDATORS[name].iter_errors(arguments), key=lambda e: list(e.absolute_path))
    if errors:
        return _refuse(f"Invalid arguments for {name}. Fix them and call again.",
                       errors=[(("/".join(map(str, e.absolute_path)) + ": ") if e.absolute_path else "") + e.message
                               for e in errors[:3]])
    if tool.needs_user and ctx.user_id is None:
        return {"status": "sign_in_required", "message": "The user isn't signed in. Ask them to sign in to use the "
                                                         "cart, orders, history or saved preferences."}
    return tool.run(ctx, arguments)
