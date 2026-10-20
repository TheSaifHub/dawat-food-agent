"""Dish categories and the words users type for them ("biriyani", "starters", "sweets"): shared by get_menu
(D-023) and search_dishes (D-024)."""

from app.text import compact

# Same list and order as the dishes.category CHECK constraint (0001_reference_data.sql).
CATEGORIES = ["biryani", "mandi", "kebab", "starter", "curry", "bread", "rice", "noodles", "soup", "salad", "pizza",
              "pasta", "burger", "sandwich", "roll", "shawarma", "fried_chicken", "mexican", "continental", "breakfast",
              "tiffin", "meals", "snack", "bakery", "dessert", "drink"]
CATEGORY_ALIASES = {
    "biriyani": "biryani", "briyani": "biryani", "biriani": "biryani", "biryanis": "biryani", "kebabs": "kebab",
    "kabab": "kebab", "kababs": "kebab", "starters": "starter", "appetizers": "starter", "curries": "curry",
    "gravy": "curry", "breads": "bread", "roti": "bread", "rotis": "bread", "naan": "bread", "soups": "soup",
    "salads": "salad", "pizzas": "pizza", "burgers": "burger", "sandwiches": "sandwich", "rolls": "roll",
    "wraps": "roll", "shawarmas": "shawarma", "shawerma": "shawarma", "friedchicken": "fried_chicken",
    "tiffins": "tiffin", "snacks": "snack", "desserts": "dessert", "sweets": "dessert", "drinks": "drink",
    "beverages": "drink", "juices": "drink", "meal": "meals", "cakes": "bakery", "pastries": "bakery",
}
CATEGORY_ORDER = {c: i for i, c in enumerate(CATEGORIES)}


def normalise_category(value: str) -> str | None:
    key = compact(value)
    if key in CATEGORY_ORDER:
        return key
    if key.replace("_", "") in {c.replace("_", "") for c in CATEGORIES}:
        return next(c for c in CATEGORIES if c.replace("_", "") == key.replace("_", ""))
    return CATEGORY_ALIASES.get(key)
