"""In-memory copy of the reference data: areas, area aliases, restaurants, branches (D-023), the dish index built
from dishes, dish_aliases and food_terms (D-024), and every menu item with its price and availability (D-053).

It changes only when data_pipeline/load_db.py reseeds (or an admin edits a row), so each server process loads it
once, at startup, and reuses it. To notice a change it reads ONE row, public.reference_version (migration 0010),
at most every REFERENCE_CHECK_S seconds; triggers stamp a new random version on any change to a reference table, so
the copy is reloaded only when something really changed (plus once a day as a safety net). Before migration 0010
exists the copy simply reloads hourly, as it did before D-053.

What reads the copy: browsing (get_menu), dish search, restaurant search and the planner's search for candidates.
What never does (always live from the database): cart prices, quotes and orders (money), the planner's own
independent checker (rules.load_facts: a stale copy must not be able to fool both the builder and the checker),
the live open-branch check, and everything user-owned.
"""

import math
import threading
import time
from dataclasses import dataclass, field

from psycopg import Connection

from app import config
from app.text import compact, tokens
from app.tools.dish_query import DishIndex

TTL_S = 3600                   # without migration 0010: reload hourly, as before D-053
MAX_AGE_S = 24 * 3600          # with it: reload at least daily anyway (a safety net, ~2 MB)

# Words that say what kind of place it is, not which place. Stripped from BOTH the query and the names,
# so "Hotel Mehfil", "mehfil restaurant" and "Mehfil" all compare as "mehfil".
GENERIC_WORDS = {
    "hotel", "hotels", "restaurant", "restaurants", "resturant", "restraunt", "restarant", "restro", "the", "family",
    "new", "cafe", "café", "and", "of", "n", "point", "house", "corner", "centre", "center", "food", "foods", "joint",
    "dhaba", "mess",
}
# Words that name food rather than a place. A query made only of these is a dish/cuisine query (search_dishes).
FOOD_WORDS = {
    "biryani", "biriyani", "briyani", "biriani", "mandi", "kebab", "kebabs", "kabab", "grill", "bbq", "pizza", "pizzas",
    "burger", "burgers", "shawarma", "shawarmas", "chinese", "noodles", "momos", "dosa", "dosas", "idli", "tiffin",
    "tiffins", "meals", "chicken", "mutton", "fish", "seafood", "tea", "chai", "coffee", "juice", "juices", "shake",
    "shakes", "icecream", "ice", "cream", "dessert", "desserts", "sweets", "bakery", "bakers", "cake", "cakes",
    "sandwich", "sandwiches", "rolls", "roll", "haleem", "andhra", "hyderabadi", "arabian", "mughlai", "punjabi",
    "veg", "nonveg", "non", "pure", "vegetarian", "fried", "snacks", "chaat", "chat", "lassi", "falooda", "tandoori",
}


def core_words(words: list[str]) -> list[str]:
    """The distinctive words of a name; falls back to all words if everything is generic/food ("House of Dosas")."""
    core = [w for w in words if w not in GENERIC_WORDS and w not in FOOD_WORDS]
    return core or words


def km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


@dataclass
class Reference:
    areas: dict[str, dict]                              # area_id → {area_id, name, name_te, lat, lon}
    area_keys: list[tuple[str, str]]                    # (area_id, compact alias), incl. the display name
    restaurants: dict[str, dict]                        # restaurant_id → row + "words", "core", "core_compact"
    branches: dict[str, dict]                           # branch_id → row (open_for_demo branches only)
    branches_by_restaurant: dict[str, list[dict]] = field(default_factory=dict)
    dish_index: DishIndex | None = None
    # D-053: restaurant_id → its menu items (available or not), each with the dish's facts, sorted by (price, item_id)
    menus: dict[str, list[dict]] = field(default_factory=dict)
    items_by_dish: dict[str, list[dict]] = field(default_factory=dict)
    version: str | None = None                          # reference_version when loaded; None before migration 0010
    loaded_at: float = 0.0
    checked_at: float = 0.0

    def available(self, restaurant_id: str) -> list[dict]:
        """The restaurant's available menu items, cheapest first (ties by item_id), as copies callers may change."""
        return [dict(i) for i in self.menus.get(restaurant_id, ()) if i["is_available"]]


def current_version(conn: Connection) -> str | None:
    """The reference data's version stamp, or None while migration 0010 isn't applied."""
    if conn.execute("select to_regclass('public.reference_version') is not null as ok").fetchone()["ok"]:
        row = conn.execute("select version::text as v from public.reference_version where id = 1").fetchone()
        return row["v"] if row else None
    return None


def load_reference(conn: Connection) -> Reference:
    version = current_version(conn)          # read BEFORE the data: a change in between only causes one extra reload
    areas = {r["area_id"]: r for r in conn.execute("select area_id, name, name_te, lat, lon from public.areas")}
    keys = {(a, compact(r["name"])) for a, r in areas.items()}
    keys |= {(r["area_id"], compact(r["alias"])) for r in conn.execute("select area_id, alias from public.area_aliases")}
    restaurants = {}
    for r in conn.execute("select restaurant_id, name, is_chain, branch_count, cuisines, primary_cuisine, veg_only, "
                          "meal_capable from public.restaurants"):
        words = tokens(r["name"])
        core = core_words(words)
        restaurants[r["restaurant_id"]] = {**r, "words": set(words), "core": core, "core_compact": compact(core)}
    branches, by_restaurant = {}, {}
    for b in conn.execute("select branch_id, restaurant_id, label, area_id, street, lat, lon from public.branches "
                          "where open_for_demo order by restaurant_id, label"):
        branches[b["branch_id"]] = b
        by_restaurant.setdefault(b["restaurant_id"], []).append(b)
    dish_rows = conn.execute("select dish_id, name, category, course, is_veg, spice_level, serves "
                             "from public.dishes").fetchall()
    dish_index = DishIndex(
        dish_rows,
        conn.execute("select dish_id, alias_norm from public.dish_aliases order by dish_id, alias_norm").fetchall(),
        conn.execute("select term_norm, means, kind from public.food_terms").fetchall())
    # Menus: only the menu_items columns go over the wire (~1.5 MB for 23,784 rows); the dish facts are joined here.
    dish_facts = {d["dish_id"]: {k: d[k] for k in ("name", "is_veg", "spice_level", "serves", "category", "course")}
                  for d in dish_rows}
    menus: dict[str, list[dict]] = {}
    items_by_dish: dict[str, list[dict]] = {}
    for m in conn.execute("select item_id, restaurant_id, dish_id, price, is_available from public.menu_items"):
        item = {"item_id": m["item_id"], "restaurant_id": m["restaurant_id"], "dish_id": m["dish_id"],
                "price": m["price"], "is_available": m["is_available"], **dish_facts[m["dish_id"]]}
        menus.setdefault(m["restaurant_id"], []).append(item)
        items_by_dish.setdefault(m["dish_id"], []).append(item)
    for items in menus.values():
        items.sort(key=lambda i: (i["price"], i["item_id"]))
    now = time.monotonic()
    return Reference(areas, sorted(k for k in keys if k[1]), restaurants, branches, by_restaurant, dish_index,
                     menus, items_by_dish, version, now, now)


_ref: Reference | None = None
_lock = threading.Lock()


def get_reference(conn: Connection) -> Reference:
    """The cached copy. Loads it on first use; then, at most every REFERENCE_CHECK_S seconds, reads the one-row
    version stamp and reloads only if it changed (or the copy is a day old). Tests set the interval to 0, so a test
    that changes a menu row inside its rolled-back transaction sees the change, and the next test sees it undone."""
    global _ref
    with _lock:
        now = time.monotonic()
        if _ref is None:
            _ref = load_reference(conn)
        elif _ref.version is None:                      # migration 0010 not applied yet: the old hourly reload
            if now - _ref.loaded_at > TTL_S:
                _ref = load_reference(conn)
        elif now - _ref.checked_at >= config.REFERENCE_CHECK_S:
            if current_version(conn) != _ref.version or now - _ref.loaded_at > MAX_AGE_S:
                _ref = load_reference(conn)
            else:
                _ref.checked_at = now
        return _ref


def warm_reference() -> None:
    """Load the copy at server startup (in a background thread, so /health answers at once on a cold start).
    Any failure is only logged: the first request that needs the copy loads it instead."""
    import logging

    from app.db import get_pool
    try:
        with get_pool().connection() as conn:
            get_reference(conn)
    except Exception:
        logging.getLogger("dawat.reference").exception("warming the reference cache failed; it will load on demand")


def clear_reference_cache() -> None:
    global _ref
    with _lock:
        _ref = None
