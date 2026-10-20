"""5c · check_plan: the independent checker every plan must pass before anyone sees it (D-028, D-029).

It deliberately shares NOTHING with the builder (build.py) except the request schema and app.pricing, the one
place totals come from (tested on its own, and re-derived without it by the tests and the rule-breaker). It has
its own idea of what a portion is, and its own diet check: Hall's marriage condition over the four kinds of eater,
for EVERY possible overlap, where the builder uses a greedy count. A bug in one is caught by the other.

Hard rules (a plan breaking any of them is never returned):
  places   every line: item available, on that branch's restaurant's menu, branch open for the demo, branch within
           the search radius (≤ 5 km ≤ the 8 km delivery range); at most 2 restaurants; qty 1–20; no repeated line
  budget   the whole bill (items + delivery + GST, from app.pricing) ≤ budget
  food     main portions (qty × serves) ≥ people
  diet     whoever the non-spicy people are, every person can be given a main portion they can eat:
           vegetarians a veg main, non-spicy people a main with spice ≤ 1
  group    a whole-vegetarian group gets no non-veg line at all; a whole-non-spicy group no line above spice 1
  spice    a stated preference (Saif, Session 15, D-036): everyone who can eat spicy food gets a main inside
           MealRequest.spice_range() (spicy 2–3, medium 2, mild 0–1), checked inside the Hall condition above;
           and no line at all above the range's top (no very spicy item for "medium", nothing above 1 for "mild")
  meal     lunch/dinner/meal: every main is a proper meal main (PROPER_MEAL_MAINS: no burgers, sandwiches, rolls,
           shawarma, snack, bakery or bread mains; Saif, Session 12); a biryani/mandi/meals main, or a side, bread
           or rice line; any curry main comes with bread or rice from the same restaurant
  padding  no main can be taken away (one unit) with the food and diet rules still holding: never padded
  extras   no dessert or drink lines (never required, so never added)
"""

from dataclasses import dataclass
from itertools import combinations

from psycopg import Connection

from app.pricing import MAX_QTY, quote
from app.planner.request import MealRequest
from app.tools.reference import km

MAX_RESTAURANTS = 2
FULL_MEALS = {"lunch", "dinner", "meal"}
COMPLETE = {"biryani", "mandi", "meals"}                   # a complete plate of rice + curry (D-028 #2)
# What a lunch, dinner or plain "meal" may be built on (Saif, Session 12). An allow-list on purpose: the builder
# keeps a deny-list (candidates.NOT_MEAL_MAINS), so a category missing from either is refused here, never let through.
PROPER_MEAL_MAINS = frozenset({"biryani", "mandi", "meals", "curry", "rice", "noodles", "kebab", "pizza", "pasta",
                               "fried_chicken", "continental", "mexican", "tiffin"})
SNACK_PORTION_SIDES = {"snack", "bakery", "starter", "fried_chicken", "kebab"}
EXTRAS = {"dessert", "drink"}

# The four kinds of eater and the four kinds of main portion. An eater can eat a portion if it is veg when they
# are vegetarian, and spice ≤ 1 when they are non-spicy.
EATERS = ("veg_mild", "veg_any", "nonveg_mild", "nonveg_any")
CAN_EAT = {"veg_mild": {"veg_mild"}, "veg_any": {"veg_mild", "veg_spicy"},
           "nonveg_mild": {"veg_mild", "nonveg_mild"},
           "nonveg_any": {"veg_mild", "veg_spicy", "nonveg_mild", "nonveg_spicy"}}


def can_eat(req: MealRequest) -> dict[str, set[str]]:
    """CAN_EAT narrowed by a stated preference: with "spicy" or "medium" the spice-eaters ("_any") need a spicy
    portion (spice ≥ 2); with "mild" they need a mild one. Non-spicy eaters are unchanged."""
    low, high = req.spice_range()
    out = {k: set(v) for k, v in CAN_EAT.items()}
    for eater in ("veg_any", "nonveg_any"):
        if low >= 2:
            out[eater] = {p for p in out[eater] if p.endswith("spicy")}
        if high <= 1:
            out[eater] = {p for p in out[eater] if p.endswith("mild")}
    return out


@dataclass(frozen=True)
class LineFacts:
    """Everything the checker needs about one plan line, loaded fresh by load_facts (or given by a test)."""
    item_id: str
    branch_id: str
    qty: int
    price: int
    is_veg: bool
    spice_level: int
    serves: int
    category: str
    course: str
    available: bool
    on_menu: bool               # the item belongs to the branch's restaurant
    branch_open: bool
    restaurant_id: str
    distance_km: float


def is_portion(f: LineFacts, meal_type: str) -> bool:
    if meal_type in FULL_MEALS:
        return f.course == "main" and f.category in PROPER_MEAL_MAINS
    return f.course == "main" or (meal_type == "snack" and f.course == "side" and f.category in SNACK_PORTION_SIDES)


def portion_kinds(lines: list[LineFacts], meal_type: str) -> dict[str, int]:
    kinds = dict.fromkeys(("veg_mild", "veg_spicy", "nonveg_mild", "nonveg_spicy"), 0)
    for f in lines:
        if is_portion(f, meal_type):
            kinds[("veg_" if f.is_veg else "nonveg_") + ("mild" if f.spice_level <= 1 else "spicy")] += f.qty * f.serves
    return kinds


def eaters(req: MealRequest, overlap: int) -> dict[str, int]:
    """How many of each kind of eater, if `overlap` of the non-spicy people are vegetarian."""
    return {"veg_mild": overlap, "veg_any": req.veg_count - overlap, "nonveg_mild": req.non_spicy_count - overlap,
            "nonveg_any": req.people - req.veg_count - req.non_spicy_count + overlap}


def everyone_fed(req: MealRequest, kinds: dict[str, int]) -> bool:
    """Hall's condition: for every set of eater kinds, there are at least as many portions any of them can eat as
    there are people in the set; checked for every possible overlap."""
    edible_for = can_eat(req)
    for k in req.overlaps():
        people = eaters(req, k)
        for size in range(1, 5):
            for group in combinations(EATERS, size):
                need = sum(people[e] for e in group)
                edible = set().union(*(edible_for[e] for e in group))
                if need > sum(kinds[p] for p in edible):
                    return False
    return True


def _qty_ok(qty) -> bool:
    return not isinstance(qty, bool) and isinstance(qty, int) and 1 <= qty <= MAX_QTY


def check_plan(req: MealRequest, lines: list[LineFacts], radius_km: float) -> dict:
    """{"ok": bool, "violations": [{"rule", "detail"}], "bill": quote or None, "portions": {...}}."""
    v: list[dict] = []

    def bad(rule: str, detail: str):
        v.append({"rule": rule, "detail": detail})

    if req.people is None or req.budget is None:
        raise ValueError("check_plan needs people and budget")
    if not lines:
        bad("food", "the plan is empty")
        return {"ok": False, "violations": v, "bill": None, "portions": {}}

    seen = set()
    for f in lines:
        key = (f.item_id, f.branch_id)
        if key in seen:
            bad("places", f"{f.item_id} at {f.branch_id} is listed twice")
        seen.add(key)
        if not _qty_ok(f.qty):
            bad("places", f"{f.item_id}: qty {f.qty!r} is not 1–{MAX_QTY}")
        if not f.available:
            bad("places", f"{f.item_id} is not available")
        if not f.on_menu:
            bad("places", f"{f.item_id} is not on the menu of {f.branch_id}")
        if not f.branch_open:
            bad("places", f"{f.branch_id} is not open for orders")
        if round(f.distance_km * 1000) > round(radius_km * 1000):
            bad("places", f"{f.branch_id} is {f.distance_km:.2f} km away, beyond {radius_km:g} km")
        if f.category in EXTRAS or f.course in EXTRAS:
            bad("extras", f"{f.item_id} is a {f.category}; desserts and drinks are never added")
    restaurants = {f.restaurant_id for f in lines}
    if len(restaurants) > MAX_RESTAURANTS:
        bad("places", f"{len(restaurants)} restaurants; at most {MAX_RESTAURANTS}")
    if len({f.branch_id for f in lines}) != len(restaurants):
        bad("places", "two branches of the same restaurant")

    # budget: the whole bill, from the one pricing function
    bill = None
    if all(_qty_ok(f.qty) and f.price > 0 for f in lines):
        branches: dict[str, dict] = {}
        for f in lines:
            b = branches.setdefault(f.branch_id, {"branch_id": f.branch_id, "distance_km": f.distance_km, "lines": []})
            b["lines"].append({"price": f.price, "qty": f.qty})
        bill = quote(list(branches.values()))
        if bill["grand_total"] > req.budget:
            bad("budget", f"total ₹{bill['grand_total']} is over the ₹{req.budget} budget")

    # food and diet
    kinds = portion_kinds(lines, req.meal_type)
    total = sum(kinds.values())
    if total < req.people:
        bad("food", f"{total} main portions for {req.people} people")
    if not everyone_fed(req, kinds):
        bad("diet", f"portions {kinds} can't feed every eater for overlaps {list(req.overlaps())}")
    if req.veg_count == req.people and any(not f.is_veg for f in lines):
        bad("group", "the whole group is vegetarian but the plan has a non-veg item")
    if req.non_spicy_count == req.people and any(f.spice_level > 1 for f in lines):
        bad("group", "nobody eats spicy food but the plan has an item above spice 1")
    top = req.spice_range()[1]
    for f in lines:
        if f.spice_level > top:
            bad("spice", f"{f.item_id} is spice {f.spice_level}; '{req.spice_preference}' allows at most {top}")

    # a proper meal
    if req.meal_type in FULL_MEALS:
        mains = [f for f in lines if f.course == "main"]
        for f in mains:
            if f.category not in PROPER_MEAL_MAINS:
                bad("meal", f"{f.item_id} is a {f.category}, not a proper {req.meal_type} main")
        complete = any(f.category in COMPLETE for f in mains)
        accompaniment = any(f.course == "side" and f.category not in EXTRAS for f in lines)
        if not complete and not accompaniment:
            bad("meal", f"a {req.meal_type} needs a side, bread or rice (or a biryani/mandi/meals main)")
        for rid in {f.restaurant_id for f in mains if f.category == "curry"}:
            if not any(f.category in ("bread", "rice") and f.restaurant_id == rid for f in lines):
                bad("meal", f"a curry from {rid} needs bread or rice from the same restaurant")

    # never padded: taking one unit of any main away must break the food or diet rule
    if not v:
        for i, f in enumerate(lines):
            if not is_portion(f, req.meal_type):
                continue
            fewer = lines[:i] + ([LineFacts(**{**f.__dict__, "qty": f.qty - 1})] if f.qty > 1 else []) + lines[i + 1:]
            k = portion_kinds(fewer, req.meal_type)
            if sum(k.values()) >= req.people and everyone_fed(req, k):
                bad("padding", f"one {f.item_id} less still feeds everyone")
                break

    return {"ok": not v, "violations": v, "bill": bill, "portions": kinds}


def load_facts(conn: Connection, lines: list[dict], point: tuple[float, float]) -> list[LineFacts] | None:
    """Fresh facts for [{"item_id", "branch_id", "qty"}] with the checker's own query; None if an id is unknown."""
    if not lines:
        return []
    rows = conn.execute("""
        select m.item_id, b.branch_id, m.price, m.is_available, d.is_veg, d.spice_level, d.serves, d.category,
               d.course, m.restaurant_id = b.restaurant_id as on_menu, b.open_for_demo, b.restaurant_id, b.lat, b.lon
        from public.menu_items m join public.dishes d using (dish_id)
             join public.branches b on (m.item_id, b.branch_id) in (select * from unnest(%s::text[], %s::text[]))""",
                        ([ln["item_id"] for ln in lines], [ln["branch_id"] for ln in lines])).fetchall()
    facts = {(r["item_id"], r["branch_id"]): r for r in rows}
    out = []
    for ln in lines:
        r = facts.get((ln["item_id"], ln["branch_id"]))
        if r is None:
            return None
        out.append(LineFacts(ln["item_id"], ln["branch_id"], ln["qty"], r["price"], r["is_veg"], r["spice_level"],
                             r["serves"], r["category"], r["course"], r["is_available"], r["on_menu"],
                             r["open_for_demo"], r["restaurant_id"], km(r["lat"], r["lon"], *point)))
    return out
