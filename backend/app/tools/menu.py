"""get_menu(branch_id, category?, is_veg?, max_spice?, max_price?) → the branch's menu, filtered, as plain JSON (D-023).

Every item, price and flag comes from the database (menu_items + dishes), through the in-memory reference copy
(D-053), which reloads whenever the database's reference version changes; nothing is computed or invented here. Filters are validated: a bad value returns status "invalid_input" (with the allowed values)
instead of silently returning the whole menu. A chain's branches share one menu (D-015), so the menu is
looked up by the branch's restaurant.
"""

import re

from psycopg import Connection

from app.tools.categories import CATEGORIES, CATEGORY_ORDER, normalise_category  # noqa: F401 (re-exported)
from app.tools.reference import get_reference

BRANCH_ID = re.compile(r"^b-[nwr][0-9]{1,15}$")
MAX_PRICE_LIMIT = 100_000
ITEM_FIELDS = ("item_id", "name", "price", "is_veg", "spice_level", "serves", "category", "course")


def _invalid(message: str, **extra) -> dict:
    return {"status": "invalid_input", "message": message, **extra}


def get_menu(conn: Connection, branch_id: str, category: str | None = None, is_veg: bool | None = None,
             max_spice: int | None = None, max_price: int | None = None) -> dict:
    if not isinstance(branch_id, str) or not BRANCH_ID.match(branch_id):
        return _invalid("branch_id must look like 'b-n123456' (from search_restaurants)")
    cat = None
    if category is not None:
        if not isinstance(category, str) or not (cat := normalise_category(category)):
            return _invalid(f"unknown category {category!r}", allowed_categories=CATEGORIES)
    if is_veg is not None and not isinstance(is_veg, bool):
        return _invalid("is_veg must be true, false or omitted")
    if max_spice is not None and (isinstance(max_spice, bool) or not isinstance(max_spice, int) or not 0 <= max_spice <= 3):
        return _invalid("max_spice must be a whole number from 0 (not spicy) to 3 (very spicy)")
    if max_price is not None and (isinstance(max_price, bool) or not isinstance(max_price, int)
                                  or not 1 <= max_price <= MAX_PRICE_LIMIT):
        return _invalid(f"max_price must be a whole number of rupees from 1 to {MAX_PRICE_LIMIT}")

    ref = get_reference(conn)
    branch = ref.branches.get(branch_id)
    if branch is None:
        return {"status": "unknown_branch", "branch_id": branch_id,
                "message": "No open Dawat branch has this id. Use search_restaurants to find the branch first."}
    r = ref.restaurants[branch["restaurant_id"]]

    rows = [{k: i[k] for k in ITEM_FIELDS} for i in ref.available(r["restaurant_id"])]
    categories_on_menu: dict[str, int] = {}
    for row in rows:
        categories_on_menu[row["category"]] = categories_on_menu.get(row["category"], 0) + 1

    def keep(row: dict) -> bool:
        return ((cat is None or row["category"] == cat) and (is_veg is None or row["is_veg"] == is_veg)
                and (max_spice is None or row["spice_level"] <= max_spice)
                and (max_price is None or row["price"] <= max_price))

    items = sorted((dict(row) for row in rows if keep(row)),
                   key=lambda i: (CATEGORY_ORDER[i["category"]], i["price"], i["name"]))
    out = {
        "status": "ok",
        "restaurant": {"restaurant_id": r["restaurant_id"], "name": r["name"], "cuisines": r["cuisines"],
                       "veg_only": r["veg_only"]},
        "branch": {"branch_id": branch_id, "label": branch["label"], "area": ref.areas[branch["area_id"]]["name"],
                   "street": branch["street"]},
        "filters": {"category": cat, "is_veg": is_veg, "max_spice": max_spice, "max_price": max_price},
        "items": items,
        "items_on_full_menu": len(rows),
        "categories_on_menu": dict(sorted(categories_on_menu.items(), key=lambda kv: CATEGORY_ORDER[kv[0]])),
    }
    if not items:
        out["message"] = ("Nothing on this menu matches these filters. Say so plainly; the full menu's categories "
                          "are in categories_on_menu.")
    return out
