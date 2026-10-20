"""Confirmation cards (Saif, Session 16, D-046): the only questions a "yes" can answer.

The third rule-breaker run showed that code can't check what the model writes: a model can ask "want a drink?" while
the tools hold an order, or hide a diet question and ask about something else. So every question that needs the
user's yes is shown by CODE, as a card built from the tool result itself:

    order       "Place this order? Veg Dum Biryani ×1 ₹270 · deliver to Madhapur · total ₹341 …"
    plan        a meal plan going into the cart: its items and total, whether it replaces the cart, any non-veg
                items for a saved vegetarian
    diet        a non-veg item for a saved vegetarian ("…is it for someone else?")
    preference  saving or forgetting a saved preference, with the exact value
    remove      taking items out of the cart (always a card from chat, D-046 after the fourth run)
    delivery    moving where the cart delivers (always a card from chat)

At the end of a turn there is at most ONE card (from_results): the latest one from this turn's tool results (diet
cards in a row merge into one). A later change to the cart drops an order card, so a card never shows a stale cart.
Code attaches it to the reply message (CARD_KEY), the chat shows it under the reply (a card with buttons in the
web app, Phase 7; one line in the terminal), and the next message's yes can act ONLY on it (pending). Busy and
step-cap turns show no card. The model never writes a card: it only sees, in its history, that one was shown.
"""

import hashlib
import json

CARD_KEY = "dawat_card"          # on the reply message: the card shown under it
RESULT_KEY = "confirm_card"      # in a tool result: the card this result asks the user about
KINDS = ("order", "plan", "diet", "preference", "remove", "delivery")
# The fields each kind must have: a card stored in the history without them is ignored, never trusted or crashed on.
REQUIRED = {"order": ("cart_id", "quote_id", "grand_total", "lines"), "plan": ("plan_id", "request", "grand_total", "lines"),
            "diet": ("items",), "preference": ("offer",), "remove": ("items",), "delivery": ("area_id", "area")}
MERGING = ("diet", "remove")             # several in one turn become one card
CART_CHANGES = ("add_to_cart", "remove_from_cart", "set_delivery", "add_plan_to_cart", "confirm_cart", "place_order")


def _with_id(card: dict) -> dict:
    body = json.dumps(card, sort_keys=True, ensure_ascii=False, default=str)
    return {**card, "card_id": hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]}


def _lines(branches) -> list[dict]:
    return [{"name": it["name"], "qty": it["qty"], "line_total": it.get("line_total"), "is_veg": it.get("is_veg"),
             "restaurant": b.get("restaurant")} for b in branches or [] for it in b.get("items", [])]


def _where(delivery) -> str | None:
    if not isinstance(delivery, dict):
        return None
    label = delivery.get("address_label")
    return f"{label}, {delivery.get('area')}" if label else delivery.get("area")


def order_card(view: dict) -> dict | None:
    """From a view_cart result that can be confirmed; None otherwise."""
    if not isinstance(view, dict) or view.get("status") != "ok" or not view.get("can_confirm") or not view.get("quote_id"):
        return None
    return _with_id({"kind": "order", "cart_id": view["cart_id"], "quote_id": view["quote_id"],
                     "grand_total": view["grand_total"], "deliver_to": _where(view.get("delivery")),
                     "lines": _lines(view.get("branches"))})


def plan_card(plan: dict, request: dict, replace: bool, nonveg: list[str], saved_diet, delivery=None) -> dict:
    return _with_id({"kind": "plan", "plan_id": plan["plan_id"], "request": request, "label": plan.get("label"),
                     "grand_total": plan["grand_total"], "lines": _lines(plan.get("restaurants")),
                     "deliver_to": _where(delivery), "replace": bool(replace), "nonveg": list(nonveg),
                     "saved_diet": saved_diet if nonveg else None})


def diet_card(items: list[dict], saved_diet) -> dict:
    """items: [{item_id, branch_id, qty, name}]"""
    return _with_id({"kind": "diet", "items": items, "saved_diet": saved_diet})


def preference_card(offer: dict, label: str) -> dict:
    return _with_id({"kind": "preference", "offer": offer, "label": label})


def remove_card(items: list[dict]) -> dict:
    """items: [{item_id, branch_id, qty (None = all of it), name}]"""
    return _with_id({"kind": "remove", "items": items})


def delivery_card(area_id: str, area: str) -> dict:
    return _with_id({"kind": "delivery", "area_id": area_id, "area": area})


def _money(n) -> str:
    return f"₹{n:,}" if isinstance(n, int) else "₹?"


def _items(lines) -> str:
    return " · ".join(f"{ln['name']} ×{ln['qty']}" + (f" {_money(ln['line_total'])}" if ln.get("line_total") else "")
                      for ln in lines)


def text(card: dict) -> str:
    """The card as one line of plain text (the terminal chat, and the model's note in its history)."""
    kind = card.get("kind")
    if kind == "order":
        where = f" · deliver to {card['deliver_to']}" if card.get("deliver_to") else ""
        return (f"Place this order? {_items(card['lines'])}{where} · total {_money(card['grand_total'])} "
                "(with delivery and GST). Reply yes to place it.")
    if kind == "plan":
        extra = f" Delivers to {card['deliver_to']}." if card.get("deliver_to") else ""
        extra += " This replaces everything in your cart." if card.get("replace") else ""
        if card.get("nonveg"):
            extra += (f" Non-veg: {', '.join(card['nonveg'])} (your saved diet is {card.get('saved_diet')}).")
        return (f"Add the plan “{card.get('label')}”? {_items(card['lines'])} · total "
                f"{_money(card['grand_total'])}.{extra} Reply yes to add it.")
    if kind == "diet":
        what = ", ".join(f"{it['name']} ×{it['qty']}" for it in card["items"])
        return (f"Add {what}? Non-veg, and your saved diet is {card.get('saved_diet')}. Reply yes if it's for "
                "someone else.")
    if kind == "preference":
        o = card["offer"]
        if o.get("action") == "delete":
            return f"Forget {card.get('label')}? Reply yes to forget it."
        return f"Save to your preferences: {card.get('label')}? Reply yes to save it."
    if kind == "remove":
        what = ", ".join(f"{it['name']}" + (f" ×{it['qty']}" if it.get("qty") else " (all of it)") for it in card["items"])
        return f"Remove {what} from your cart? Reply yes to remove it."
    if kind == "delivery":
        return (f"Deliver to {card['area']} instead? Prices, fees and what's available may change. Reply yes to "
                "change it.")
    return ""


def plan_options(result: dict) -> list[dict] | None:
    """The plans of an ok plan_meal result, as the chat shows them: selectable cards under the reply (Phase 7f,
    D-058). Built by code from the tool result, so every item, quantity and price is the planner's own. Picking one
    sends a message naming its label; the model then calls add_plan_to_cart with that plan_id, as in the terminal."""
    if not isinstance(result, dict) or result.get("status") != "ok" or not isinstance(result.get("plans"), list):
        return None
    out = []
    for p in result["plans"]:
        if not isinstance(p, dict) or not p.get("plan_id"):
            continue
        out.append({"plan_id": p["plan_id"], "label": p.get("label"), "grand_total": p.get("grand_total"),
                    "items_total": p.get("items_total"), "delivery_total": p.get("delivery_total"),
                    "taxes_total": p.get("taxes_total"), "diet_note": p.get("diet_note"),
                    "budget_left": p.get("budget_left"),
                    "restaurants": [{"restaurant": r.get("restaurant"), "branch_id": r.get("branch_id"),
                                     "branch_label": r.get("branch_label"), "distance_km": r.get("distance_km"),
                                     "delivery_fee": r.get("delivery_fee"), "free_delivery": r.get("free_delivery"),
                                     "taxes": r.get("taxes"), "total": r.get("total"),
                                     "items": [{"name": it.get("name"), "qty": it.get("qty"),
                                                "line_total": it.get("line_total"), "is_veg": it.get("is_veg"),
                                                "spice_level": it.get("spice_level"), "role": it.get("role")}
                                               for it in r.get("items") or []]}
                                    for r in p.get("restaurants") or []]})
    return out or None


def _valid(card) -> bool:
    return isinstance(card, dict) and card.get("kind") in KINDS and all(k in card for k in REQUIRED[card["kind"]])


def from_results(results: list[tuple[str, dict]]) -> dict | None:
    """The one card to show at the end of a turn, from (tool name, result) pairs in the order they ran."""
    card = None
    for name, result in results:
        if not isinstance(result, dict):
            continue
        changed = (name in CART_CHANGES and result.get("status") == "ok") or "delivery_set_to" in result
        if changed and card and card["kind"] == "order":
            card = None                                       # the cart (or its delivery) changed after that summary
        if name == "place_order" and result.get("status") == "payment_required" and card and card["kind"] == "order":
            card = None                                       # the yes was given; the app shows Pay now, not the question again
        if result.get("status") == "diet_declined" and card and card["kind"] == "diet":
            items = [it for it in card["items"] if it["item_id"] != result.get("item_id")]
            card = diet_card(items, card.get("saved_diet")) if items else None    # a no takes it off the card
        new = result.get(RESULT_KEY)
        if not _valid(new):
            continue
        if card and card["kind"] == new["kind"] and new["kind"] in MERGING:
            seen = {(it["item_id"], it.get("branch_id")) for it in new["items"]}
            items = [it for it in card["items"] if (it["item_id"], it.get("branch_id")) not in seen] + new["items"]
            new = diet_card(items, new.get("saved_diet")) if new["kind"] == "diet" else remove_card(items)
        card = new
    return card


def pending(history: list[dict]) -> dict | None:
    """The card shown under the previous reply: the only thing this message's yes can act on."""
    if not history:
        return None
    last = history[-1]
    card = last.get(CARD_KEY) if last.get("role") == "assistant" else None
    return card if _valid(card) else None


def for_model(messages: list[dict]) -> list[dict]:
    """The history as the model sees it: the card key removed (providers refuse unknown fields), and a note of the
    card the app showed added to that reply's text."""
    out = []
    for m in messages:
        if CARD_KEY in m:
            card = m[CARD_KEY]
            m = {k: v for k, v in m.items() if k != CARD_KEY}
            if _valid(card):
                m["content"] = (m.get("content") or "") + f"\n\n[The app showed this card under your reply: {text(card)}]"
        out.append(m)
    return out
