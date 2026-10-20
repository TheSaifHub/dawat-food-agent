"""search_dishes(query, area?, is_veg?, max_spice?, max_price?, category?) → dishes on menus in or near an area,
as plain JSON (D-024).

The query is understood by app.tools.dish_query (English, Hinglish, Telugu, typos, "karam kam", "under 200",
"in Madhapur", "rendu"); every item, price and flag in the answer comes from the database.

Rules the agent relies on, enforced here in code:
  · An area is required, and one that doesn't resolve stops the search (the same rule as search_restaurants):
    needs_area / confirm_area / unknown_area / outside_coverage, with what was understood so far.
  · Filters can only get stricter: an explicit filter and one read from the text are combined, never
    loosened (is_veg=True from either side wins; the lower max_spice and max_price win).
  · A borderline typo returns confirm_dish ("did you mean mutton?"); nothing is snapped silently.
  · Words that matched no dish are listed in unmatched_words, so "pork biryani" is never presented as if we
    had it.
  · Only open_for_demo branches in the area or within NEAR_KM, and only available items.
"""

from collections import Counter

from psycopg import Connection

from app.tools.areas import resolve_area
from app.tools.categories import CATEGORIES, normalise_category
from app.tools.dish_query import EXACT, NAME, ALIAS, understand
from app.tools.reference import Reference, get_reference, km
from app.tools.restaurants import NEAR_KM

MAX_QUERY_LEN = 200
DEFAULT_LIMIT, MAX_LIMIT, PER_RESTAURANT, MAX_DISH_SUMMARY = 10, 20, 2, 8
MAX_PRICE_LIMIT = 100_000
AREA_STOP = ("needs_area", "confirm_area", "unknown_area", "outside_coverage")


def _match_label(tier: int) -> str:
    return "exact" if tier == EXACT else "name" if tier <= NAME else "alias" if tier <= ALIAS else "loose"


def _invalid(message: str, **extra) -> dict:
    return {"status": "invalid_input", "message": message, **extra}


def _check(is_veg, max_spice, max_price, category, limit) -> dict | None:
    if is_veg is not None and not isinstance(is_veg, bool):
        return _invalid("is_veg must be true, false or omitted")
    if max_spice is not None and (isinstance(max_spice, bool) or not isinstance(max_spice, int) or not 0 <= max_spice <= 3):
        return _invalid("max_spice must be a whole number from 0 (not spicy) to 3 (very spicy)")
    if max_price is not None and (isinstance(max_price, bool) or not isinstance(max_price, int)
                                  or not 1 <= max_price <= MAX_PRICE_LIMIT):
        return _invalid(f"max_price must be a whole number of rupees from 1 to {MAX_PRICE_LIMIT}")
    if category is not None and (not isinstance(category, str) or not normalise_category(category)):
        return _invalid(f"unknown category {category!r}", allowed_categories=CATEGORIES)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        return _invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    return None


def _stricter_min(*values):
    vals = [v for v in values if v is not None]
    return min(vals) if vals else None


def _nearest_branches(ref: Reference, area: dict, restaurant_ids=None, near_only=True) -> dict[str, tuple[dict, float]]:
    """restaurant_id → (its branch nearest the area, km). With near_only, only branches in the area or within NEAR_KM."""
    out = {}
    for rid, branches in ref.branches_by_restaurant.items():
        if restaurant_ids is not None and rid not in restaurant_ids:
            continue
        best = None
        for b in branches:
            d = km(b["lat"], b["lon"], area["lat"], area["lon"])
            if near_only and not (b["area_id"] == area["area_id"] or d <= NEAR_KM):
                continue
            key = (b["area_id"] != area["area_id"], d)
            if best is None or key < best[0]:
                best = (key, b, d)
        if best:
            out[rid] = (best[1], best[2])
    return out


def search_dishes(conn: Connection, query: str, area: str | None = None, is_veg: bool | None = None,
                  max_spice: int | None = None, max_price: int | None = None, category: str | None = None,
                  limit: int = DEFAULT_LIMIT) -> dict:
    if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_LEN:
        return _invalid(f"query must be 1–{MAX_QUERY_LEN} characters")
    if area is not None and not isinstance(area, str):
        return _invalid("area must be text, e.g. 'Madhapur'")
    if bad := _check(is_veg, max_spice, max_price, category, limit):
        return bad
    query = query.strip()
    ref = get_reference(conn)
    idx = ref.dish_index

    def area_score(text: str) -> int:
        return 2 if resolve_area(ref, text)["status"] in ("ok", "confirm_area", "outside_coverage") else 0

    m = understand(query, idx, area_score)
    u = m.understood

    # ── filters: explicit and understood, combined so they only get stricter ──
    notes = list(u.notes)
    if is_veg is not None and u.is_veg is not None and is_veg != u.is_veg:
        notes.append("the is_veg filter and the request's diet words disagree; showing vegetarian only")
    veg = True if True in (is_veg, u.is_veg) else (False if False in (is_veg, u.is_veg) else None)
    spice_max = _stricter_min(max_spice, u.max_spice)
    spice_min = u.min_spice
    if spice_min is not None and spice_max is not None and spice_min > spice_max:
        notes.append("asked for spicy and not spicy at once; applying only the not-spicy limit")
        spice_min = None
    price_max = _stricter_min(max_price, u.max_price)
    cat = normalise_category(category) if category else None
    filters = {"is_veg": veg, "min_spice": spice_min, "max_spice": spice_max, "max_price": price_max, "category": cat}
    understood = {**u.as_json(), **({"notes": notes} if notes else {})}
    base = {"query": query, "understood": understood, "filters": filters}

    # ── area: required; an explicit area and one in the text must agree ──
    area_text = area.strip() if area and area.strip() else u.area_text
    if area and area.strip() and u.area_text:
        a, b = resolve_area(ref, area), resolve_area(ref, u.area_text)
        if a["status"] == b["status"] == "ok" and a["area"]["area_id"] != b["area"]["area_id"]:
            return {"status": "area_conflict", **base, "areas": [a["area"], b["area"]],
                    "message": "The area given and the area in the request differ. Ask the user which one."}
    if not area_text:
        return {"status": "needs_area", **base, **_dish_preview(m, idx),
                "message": "Ask the user which area to deliver to before searching. Do not show prices yet."}
    resolved = resolve_area(ref, area_text)
    if resolved["status"] != "ok":
        return {"status": resolved["status"], **base, "area_resolution": resolved, "message": resolved["message"]}
    area_row = ref.areas[resolved["area"]["area_id"]]
    base["area"] = {"area_id": area_row["area_id"], "name": area_row["name"]}
    if resolved["matched_by"] == "fuzzy":
        base["area_note"] = resolved["message"]

    # ── the dishes ──
    if m.status == "confirm":
        return {"status": "confirm_dish", **base, "confirm": m.confirm,
                "message": f"Ask the user: did you mean '{m.confirm['candidate']}' (for '{m.confirm['word']}')? "
                           "Search again only if they say yes."}
    if m.status == "none":
        return {"status": "no_dish_match", **base, "suggestions": m.suggestions,
                "message": "No dish on Dawat matches this. Say so; offer the suggestions if any. Never invent a dish."}
    if m.status == "any":
        tiers = {d: NAME for d, r in idx.dishes.items() if (r["category"] == cat if cat else r["course"] == "main")}
    else:
        tiers = {d: t for d, t in m.tiers.items() if cat is None or idx.dishes[d]["category"] == cat}
        if not tiers:
            return {"status": "no_dish_match", **base, "suggestions": [],
                    "message": f"None of the matching dishes is in the category '{cat}'. Say so."}

    near = _nearest_branches(ref, area_row)
    # D-053: from the in-memory menus (same rows the database query returned: available items of these dishes here)
    rows = [i for rid in near for i in ref.available(rid) if i["dish_id"] in tiers]

    def keep(r: dict) -> bool:
        return ((veg is None or r["is_veg"] == veg) and (spice_max is None or r["spice_level"] <= spice_max)
                and (spice_min is None or r["spice_level"] >= spice_min)
                and (price_max is None or r["price"] <= price_max))

    items = [r for r in rows if keep(r)]
    if not items:
        return _nothing_found(conn, ref, area_row, tiers, rows, keep, base)

    # best match first, then nearest; at one place, the dish most places nearby serve (for a plain "biryani":
    # Chicken Dum Biryani, not the cheapest Egg Biryani), then price
    served = Counter(r["dish_id"] for r in items)
    items.sort(key=lambda r: (tiers[r["dish_id"]], near[r["restaurant_id"]][1], -served[r["dish_id"]], r["price"],
                              r["name"]))
    per_restaurant: dict[str, int] = {}
    results = []
    for r in items:
        if per_restaurant.get(r["restaurant_id"], 0) >= PER_RESTAURANT:
            continue
        per_restaurant[r["restaurant_id"]] = per_restaurant.get(r["restaurant_id"], 0) + 1
        results.append(_item_json(ref, r, tiers, near, area_row))
        if len(results) == limit:
            break

    out = {"status": "ok", **base, "match": m.status, "results": results,
           "dishes_matched": _dish_summary(items, tiers),
           "totals": {"items": len(items), "restaurants": len({r["restaurant_id"] for r in items}),
                      "dishes": len({r["dish_id"] for r in items})}}
    msg = []
    if u.unmatched_words:
        msg.append(f"No dish matched the words {u.unmatched_words}: these results ignore them. Tell the user we "
                   "don't have that; never present these results as that dish.")
    if u.corrections:
        msg.append(f"Typos read as {u.corrections}; mention it.")
    if u.quantity:
        msg.append(f"The user wants {u.quantity}: use it as the quantity when adding to the cart.")
    if u.people:
        msg.append("This is a group request: use plan_meal for portions and budget.")
    if msg:
        out["message"] = " ".join(msg)
    return out


def _item_json(ref: Reference, r: dict, tiers: dict, near: dict, area_row: dict) -> dict:
    b, dist = near[r["restaurant_id"]]
    rest = ref.restaurants[r["restaurant_id"]]
    return {"item_id": r["item_id"], "dish_id": r["dish_id"], "name": r["name"], "price": r["price"],
            "is_veg": r["is_veg"], "spice_level": r["spice_level"], "serves": r["serves"], "category": r["category"],
            "course": r["course"], "match": _match_label(tiers[r["dish_id"]]),
            "restaurant": {"restaurant_id": rest["restaurant_id"], "name": rest["name"], "veg_only": rest["veg_only"]},
            "branch": {"branch_id": b["branch_id"], "label": b["label"], "area": ref.areas[b["area_id"]]["name"],
                       "street": b["street"], "distance_km": round(dist, 1)}}


def _dish_summary(items: list[dict], tiers: dict) -> list[dict]:
    by: dict[str, dict] = {}
    for r in items:
        s = by.setdefault(r["dish_id"], {"dish_id": r["dish_id"], "name": r["name"], "is_veg": r["is_veg"],
                                         "spice_level": r["spice_level"], "match": _match_label(tiers[r["dish_id"]]),
                                         "restaurants": set(), "price_from": r["price"], "price_to": r["price"]})
        s["restaurants"].add(r["restaurant_id"])
        s["price_from"], s["price_to"] = min(s["price_from"], r["price"]), max(s["price_to"], r["price"])
    ranked = sorted(by.values(), key=lambda s: (tiers[s["dish_id"]], -len(s["restaurants"]), s["name"]))
    return [{**s, "restaurants": len(s["restaurants"])} for s in ranked[:MAX_DISH_SUMMARY]]


def _dish_preview(m, idx) -> dict:
    if m.status in ("exact", "contains", "category"):
        ranked = sorted(m.tiers.items(), key=lambda kv: (kv[1], idx.names[kv[0]]))
        return {"match": m.status, "dishes_understood": [idx.names[d] for d, _ in ranked[:5]]}
    if m.status == "confirm":
        return {"match": "confirm", "confirm": m.confirm}
    return {"match": m.status, **({"suggestions": m.suggestions} if m.suggestions else {})}


def _nothing_found(conn, ref, area_row, tiers, nearby_rows, keep, base) -> dict:
    if nearby_rows:
        cheapest = min(r["price"] for r in nearby_rows)
        return {"status": "no_match_with_filters", **base, "results": [],
                "nearby_without_filters": {"items": len(nearby_rows), "cheapest_price": cheapest,
                                           "has_veg": any(r["is_veg"] for r in nearby_rows),
                                           "mildest_spice": min(r["spice_level"] for r in nearby_rows)},
                "message": "These dishes are available nearby, but none fits the filters. Say which limit rules "
                           "them out (see nearby_without_filters) and ask whether to relax it. Never relax it silently."}
    # nothing nearby: where is the nearest place that has it (filters still applied)?
    rows = [i for d in tiers for i in ref.items_by_dish.get(d, ()) if i["is_available"]]
    rids = {r["restaurant_id"] for r in rows if keep(r)}
    far = _nearest_branches(ref, area_row, rids, near_only=False)
    nearest = sorted(far.items(), key=lambda kv: kv[1][1])[:3]
    return {"status": "none_near_area", **base, "results": [], "near_km": NEAR_KM,
            "nearest_elsewhere": [{"restaurant": ref.restaurants[rid]["name"], "branch_id": b["branch_id"],
                                   "area": ref.areas[b["area_id"]]["name"], "distance_km": round(d, 1)}
                                  for rid, (b, d) in nearest],
            "message": f"No restaurant within {NEAR_KM:g} km of {area_row['name']} serves this. Say so; you may "
                       "mention the nearest places listed, with their distance."}
