"""5d · Scoring and picking three genuinely different plans (D-028 #3, #4, #7; D-029).

Score parts (each 0–1):
  spice     how well the main portions fit the spice preference; the portions the non-spicy people need are left
            out when the group asked for spicy, so a required mild dish never counts against a plan
  budget    1.0 when the total uses 75–100% of the budget, falling linearly below 75% (over budget never gets here)
  diet      the non-vegetarians get non-veg mains (they may still eat veg, so a small weight)
  variety   different main dishes, up to 3
  single    one restaurant (one delivery fee, one order) is preferred
  distance  nearer is better (fresher, cheaper delivery)
best match = 2·spice + 1.5·budget + 0.5·diet + 0.5·variety + 1·single + 0.5·distance
(A "meal" part that halved sandwiches and burgers is gone: since Session 12 they are never a lunch/dinner main.)

The three roles, picked in this order, each different from those already picked (a different set of restaurants,
or at least half the items different):
  best value  the lowest total of all, one restaurant or two (ties: one restaurant). plan.py passes it in: the
              cheapest plan within 5 km, found by a search that ignores the budget (Saif, Session 12)
  best match  the highest best-match score
  variety     the most different dishes and categories, a new restaurant counting extra
Single-restaurant plans are used for best match whenever there is one; two-restaurant plans compete for variety.
"""

from dataclasses import dataclass

from app.planner.candidates import is_main
from app.pricing import quote

SPICE_FIT = {
    None: {0: 0.5, 1: 0.5, 2: 0.5, 3: 0.5},
    "spicy": {0: 0.0, 1: 0.3, 2: 0.9, 3: 1.0},
    "medium": {0: 0.4, 1: 1.0, 2: 1.0, 3: 0.4},
    "mild": {0: 1.0, 1: 1.0, 2: 0.3, 3: 0.0},
}
TARGET_USE = 0.75
WEIGHTS = {"spice": 2.0, "budget": 1.5, "diet": 0.5, "variety": 0.5, "single": 1.0, "distance": 0.5}
FAR_KM = 5.0


def spice_fit(level: int, pref: str | None) -> float:
    return SPICE_FIT[pref][level]


@dataclass
class Scored:
    plan: object                    # build.Plan
    bill: dict
    parts: dict
    match: float
    restaurants: frozenset
    items: frozenset
    key: tuple

    @property
    def total(self) -> int:
        return self.bill["grand_total"]


def price(plan) -> dict:
    """The plan's bill from app.pricing, worked out once per plan (a plan's lines never change)."""
    if getattr(plan, "bill", None) is None:
        branches: dict[str, dict] = {}
        for b, it, q in plan.lines:
            e = branches.setdefault(b.branch_id, {"branch_id": b.branch_id, "distance_km": b.distance_km, "lines": []})
            e["lines"].append({"price": it.price, "qty": q})
        plan.bill = quote(list(branches.values()))
    return plan.bill


def score(req, plan, bill: dict) -> Scored:
    portions = []
    for _, it, q in plan.lines:
        if is_main(it, req.meal_type):
            portions += [it] * (it.serves * q)
    fits = sorted(spice_fit(it.spice_level, req.spice_preference) for it in portions)
    if req.spice_preference == "spicy":
        fits = fits[req.non_spicy_count:] or fits
    spice = sum(fits) / len(fits) if fits else 0.0
    use = bill["grand_total"] / req.budget if req.budget else TARGET_USE
    budget = 1.0 if use >= TARGET_USE else use / TARGET_USE
    non_veg_people = req.people - req.veg_count
    diet = 1.0 if non_veg_people == 0 else min(sum(1 for p in portions if not p.is_veg), non_veg_people) / non_veg_people
    variety = min(1.0, len({p.dish_id for p in portions}) / min(req.people, 3))
    restaurants = frozenset(b.restaurant_id for b, _, _ in plan.lines)
    single = 1.0 if len(restaurants) == 1 else 0.0
    distance = max(0.0, 1 - max(b.distance_km for b, _, _ in plan.lines) / FAR_KM)
    parts = {"spice": spice, "budget": budget, "diet": diet, "variety": variety, "single": single,
             "distance": distance}
    match = sum(WEIGHTS[k] * v for k, v in parts.items())
    return Scored(plan, bill, {k: round(v, 3) for k, v in parts.items()}, round(match, 4), restaurants,
                  frozenset(it.item_id for _, it, _ in plan.lines), plan.key())


def value_order(s: Scored) -> tuple:
    """Cheapest first; on a tie one restaurant, then the better match. Equal totals share the budget part, so the
    order of tied plans doesn't depend on the budget either."""
    return s.total, len(s.restaurants), -s.match, s.key


def different(a: Scored, b: Scored) -> bool:
    """A different set of restaurants, or at least half of the items different."""
    if a.restaurants != b.restaurants:
        return True
    return len(a.items & b.items) <= max(len(a.items), len(b.items)) / 2


def variety_score(s: Scored, picked: list[Scored]) -> float:
    lines = s.plan.lines
    dishes = len({it.dish_id for _, it, _ in lines})
    categories = len({it.category for _, it, _ in lines})
    new_place = 1.0 if all(not (s.restaurants & p.restaurants) for p in picked) else 0.0
    return dishes + 0.5 * categories + 1.0 * new_place


def select(scored: list[Scored], check, value: Scored | None = None) -> tuple[list[tuple[str, Scored]], int]:
    """[(role, plan)] for up to three roles, and how many candidates the checker refused (a builder bug if > 0).
    `check(scored) -> bool` is the independent rule checker; nothing it refuses is ever picked. `value`, if given,
    is the already-checked best value plan (plan.py's cheapest within 5 km); otherwise the cheapest of `scored`."""
    picked: list[tuple[str, Scored]] = []
    refused: set[tuple] = set()
    verdicts: dict[tuple, bool] = {}

    def passes(s: Scored) -> bool:
        if s.key not in verdicts:
            verdicts[s.key] = check(s)
            if not verdicts[s.key]:
                refused.add(s.key)
        return verdicts[s.key]

    if value is not None:
        picked.append(("best_value", value))
    else:
        choice = next((s for s in sorted(scored, key=value_order) if passes(s)), None)
        if choice:
            picked.append(("best_value", choice))
    singles = [s for s in scored if len(s.restaurants) == 1]
    for pool in (singles, scored):
        choice = next((s for s in sorted(pool, key=lambda s: (-s.match, s.total, s.key))
                       if all(different(s, p) for _, p in picked) and passes(s)), None)
        if choice:
            picked.append(("best_match", choice))
            break
    taken = [p for _, p in picked]
    choice = next((s for s in sorted(scored, key=lambda s: (-variety_score(s, taken), -s.match, s.total, s.key))
                   if all(different(s, p) for p in taken) and passes(s)), None)
    if choice:
        picked.append(("variety", choice))
    return picked, len(refused)
