"""5b · The candidate pool: which branches and dishes a plan may use (D-029).

For a delivery point and a search radius (3 km first, 5 km if needed; D-028 #6):
  · one branch per restaurant: the nearest open_for_demo branch (a chain's branches share one menu, D-015, so a
    farther branch of the same chain only costs more delivery);
  · lunch / dinner / meal: only meal_capable restaurants (a main plus a side, bread or rice can be built, D-017);
  · only available menu items, read live from the database (prices and availability are never cached).

Each item is sorted into the roles the builder uses:
  mains   count as portions (what "enough food for the group" is measured in). For a lunch, dinner or plain
          "meal" only a proper meal main counts (Saif, Session 12): burgers, sandwiches, rolls, shawarma, snack,
          bakery and bread mains don't. The checker (rules.py) keeps its own list of what DOES count.
  bases   bread or rice to eat a curry with
  sides   anything that satisfies "a main plus a side, bread or rice" (bases included)
"""

from dataclasses import dataclass, field

from psycopg import Connection

from app.pricing import MAX_DELIVERY_KM
from app.tools.reference import Reference, km

NEAR_KM, WIDE_KM = 3.0, 5.0
assert WIDE_KM <= MAX_DELIVERY_KM

FULL_MEALS = ("lunch", "dinner", "meal")
# A main from these categories is a complete plate of rice + curry: it needs no separate side (D-028 #2).
COMPLETE_MAINS = frozenset({"biryani", "mandi", "meals"})
BASE_CATEGORIES = frozenset({"bread", "rice"})
NOT_A_SIDE = frozenset({"dessert", "drink"})                  # never required, never used to complete a meal
BREAKFAST_MAINS = frozenset({"breakfast", "tiffin"})
SNACK_SIDES = frozenset({"snack", "bakery", "starter", "fried_chicken", "kebab"})
# Never a lunch/dinner/meal portion (Saif, Session 12; D-028 #2). A deny-list here, an allow-list in the checker:
# test_meal_main_lists_cover_every_category proves the two split the database's main categories exactly.
NOT_MEAL_MAINS = frozenset({"burger", "sandwich", "roll", "shawarma", "snack", "bakery", "bread", "breakfast"})


@dataclass(frozen=True)
class Item:
    item_id: str
    dish_id: str
    name: str
    price: int
    is_veg: bool
    spice_level: int
    serves: int
    category: str
    course: str

    @property
    def mild(self) -> bool:
        return self.spice_level <= 1


@dataclass
class Branch:
    branch_id: str
    restaurant_id: str
    restaurant: str
    label: str
    area: str
    distance_km: float
    veg_only: bool
    mains: list[Item] = field(default_factory=list)
    bases: list[Item] = field(default_factory=list)
    sides: list[Item] = field(default_factory=list)


def is_main(item: Item, meal_type: str) -> bool:
    """Does this item count as a portion of food for this kind of meal?"""
    if meal_type == "breakfast":
        return item.course == "main" and item.category in BREAKFAST_MAINS
    if meal_type == "snack":
        return item.course == "main" or (item.course == "side" and item.category in SNACK_SIDES)
    return item.course == "main" and item.category not in NOT_MEAL_MAINS


def is_base(item: Item) -> bool:
    return item.course == "side" and item.category in BASE_CATEGORIES


def is_side(item: Item) -> bool:
    return item.course == "side" and item.category not in NOT_A_SIDE


def nearest_branches(ref: Reference, point: tuple[float, float], radius_km: float) -> list[tuple[dict, float]]:
    """(branch, km) for each restaurant's nearest open branch within radius_km, nearest first."""
    best: dict[str, tuple[dict, float]] = {}
    for b in ref.branches.values():                               # open_for_demo branches only (reference.py)
        d = km(b["lat"], b["lon"], *point)
        if round(d * 1000) > round(radius_km * 1000):
            continue
        rid = b["restaurant_id"]
        if rid not in best or (d, b["branch_id"]) < (best[rid][1], best[rid][0]["branch_id"]):
            best[rid] = (b, d)
    return sorted(best.values(), key=lambda bd: (bd[1], bd[0]["branch_id"]))


def load_candidates(conn: Connection, ref: Reference, point: tuple[float, float], radius_km: float,
                    meal_type: str) -> list[Branch]:
    found = nearest_branches(ref, point, radius_km)
    if meal_type in FULL_MEALS:
        found = [(b, d) for b, d in found if ref.restaurants[b["restaurant_id"]]["meal_capable"]]
    if not found:
        return []
    # The reference cache is refreshed hourly; whether a branch is open is checked live (rule-breaker, Session 11:
    # branches closed after the cache loaded were built into plans the checker then had to refuse).
    open_now = {r["branch_id"] for r in conn.execute(
        "select branch_id from public.branches where open_for_demo and branch_id = any(%s)",
        ([b["branch_id"] for b, _ in found],))}
    found = [(b, d) for b, d in found if b["branch_id"] in open_now]
    if not found:
        return []
    # D-053: the menus come from the in-memory reference copy (each already ordered by price, then item_id, as the
    # database query was). The plan is still checked against live database facts by rules.load_facts.
    by_restaurant: dict[str, list[Item]] = {}
    for rid in {b["restaurant_id"] for b, _ in found}:
        by_restaurant[rid] = [Item(r["item_id"], r["dish_id"], r["name"], r["price"], r["is_veg"], r["spice_level"],
                                   r["serves"], r["category"], r["course"]) for r in ref.available(rid)]

    out = []
    for b, d in found:
        rest = ref.restaurants[b["restaurant_id"]]
        items = by_restaurant.get(b["restaurant_id"], [])
        br = Branch(b["branch_id"], b["restaurant_id"], rest["name"], b["label"], ref.areas[b["area_id"]]["name"], d,
                    rest["veg_only"],
                    mains=[i for i in items if is_main(i, meal_type)],
                    bases=[i for i in items if is_base(i)],
                    sides=[i for i in items if is_side(i)])
        if br.mains:
            out.append(br)
    return out
