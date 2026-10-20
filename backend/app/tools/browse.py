"""Browsing by area (Phase 7c, D-049, D-056): the restaurant listing and the home page's shortcuts.

    restaurants_near(conn, area_id, cuisine?, veg_only?, mild?, max_km?, max_price_for_one?, sort?, offset?, limit?)
    area_home(conn, area_id) → cuisine shortcuts + chains near you
    branch_info(conn, branch_id, area?) → a restaurant page's header and map (7d): the branch, its sibling
                                          branches, and, for an area, whether it delivers there and the fee

Only restaurants that can deliver to the area are listed: a branch within MAX_DELIVERY_KM (8 km, Saif, Session 9) of
the area centre, the same rule the cart enforces, so nothing shown here is refused at "add". One card per restaurant,
its nearest branch, plus how many more of its branches are in range.

Every number on a card comes from code and the database, nothing is estimated or made up (no ratings, no ETAs):
  distance_km     branch → area centre, as the cart measures it
  delivery_fee    pricing.delivery_fee for a small order at that distance; free from ₹499 of items (pricing)
  price_for_one   the median price of the restaurant's available single-serving mains (₹, whole rupees)
  mild_mains      how many available mains are spice level 0–1; "mild-friendly" means at least MILD_FRIENDLY_MIN
"""

import statistics

from psycopg import Connection

from app import pricing
from app.tools.areas import area_json, resolve_area
from app.tools.reference import Reference, get_reference, km

DEFAULT_LIMIT, MAX_LIMIT = 24, 48
MILD_FRIENDLY_MIN = 3
SORTS = ("distance", "price", "name")
HOME_CUISINES, HOME_CHAINS = 12, 10
# The fallback label for restaurants with no clear cuisine (D-014): a filter in the listing, not a home shortcut.
NOT_A_SHORTCUT = {"Multi-cuisine"}

_stats: tuple[Reference, dict[str, dict]] | None = None   # (the copy it was built from, restaurant_id → stats)


def _invalid(message: str) -> dict:
    return {"status": "invalid_input", "message": message}


def _restaurant_stats(ref: Reference) -> dict[str, dict]:
    """Per-restaurant figures, rebuilt whenever the reference copy is reloaded (a new object)."""
    global _stats
    if _stats is None or _stats[0] is not ref:
        out = {}
        for rid, items in ref.menus.items():
            available = [i for i in items if i["is_available"]]
            mains = [i for i in available if i["course"] == "main"]
            single = [i["price"] for i in mains if i["serves"] == 1] or [i["price"] for i in mains] \
                or [i["price"] for i in available]
            out[rid] = {"price_for_one": statistics.median_low(single) if single else None,
                        "mild_mains": sum(1 for i in mains if i["spice_level"] <= 1)}
        _stats = (ref, out)
    return _stats[1]


def cuisine_vocabulary(ref: Reference) -> dict[str, str]:
    """lower-case → display spelling, from the restaurants themselves."""
    return {c.lower(): c for r in ref.restaurants.values() for c in (r["cuisines"] or [])}


def _area(ref: Reference, area_id) -> tuple[dict | None, dict | None]:
    """The area row, or an answer to return. The website's picker sends ids; a name still works (same resolver as
    the chat), so a typed or shared link with "Madhapur" isn't refused."""
    if not isinstance(area_id, str) or not area_id.strip() or len(area_id) > 80:
        return None, _invalid("area must be an area id from GET /areas, e.g. 'madhapur'")
    if area_id in ref.areas:
        return ref.areas[area_id], None
    resolved = resolve_area(ref, area_id)
    if resolved["status"] != "ok":
        return None, {**resolved, "area_resolution": resolved}
    return ref.areas[resolved["area"]["area_id"]], None


def _in_range(ref: Reference, area: dict, max_km: float) -> list[dict]:
    """Every restaurant with a branch in range: its nearest branch and how many in range, nearest first."""
    best: dict[str, dict] = {}
    for b in ref.branches.values():
        d = km(b["lat"], b["lon"], area["lat"], area["lon"])
        if not pricing.within_delivery_range(d) or round(d * 1000) > round(max_km * 1000):
            continue
        rid = b["restaurant_id"]
        if rid not in ref.restaurants:
            continue
        cur = best.get(rid)
        if cur is None:
            best[rid] = {"branch": b, "distance": d, "in_range": 1}
        else:
            cur["in_range"] += 1
            if (d, b["branch_id"]) < (cur["distance"], cur["branch"]["branch_id"]):
                cur["branch"], cur["distance"] = b, d
    return sorted(({"restaurant_id": rid, **v} for rid, v in best.items()),
                  key=lambda x: (x["distance"], x["restaurant_id"]))


def _card(ref: Reference, stats: dict, hit: dict) -> dict:
    r, b, d = ref.restaurants[hit["restaurant_id"]], hit["branch"], hit["distance"]
    s = stats.get(r["restaurant_id"], {"price_for_one": None, "mild_mains": 0})
    return {
        "restaurant_id": r["restaurant_id"], "name": r["name"], "cuisines": list(r["cuisines"] or []),
        "veg_only": r["veg_only"], "is_chain": r["is_chain"],
        "branch": {"branch_id": b["branch_id"], "label": b["label"], "area": ref.areas[b["area_id"]]["name"],
                   "street": b["street"], "distance_km": round(d, 1)},
        "more_branches_in_range": hit["in_range"] - 1,
        "delivery_fee": pricing.delivery_fee(0, d),
        "price_for_one": s["price_for_one"], "mild_mains": s["mild_mains"],
        "mild_friendly": s["mild_mains"] >= MILD_FRIENDLY_MIN,
    }


def restaurants_near(conn: Connection, area_id: str, cuisine: str | None = None, veg_only: bool | None = None,
                     mild: bool | None = None, max_km: float | None = None, max_price_for_one: int | None = None,
                     sort: str = "distance", offset: int = 0, limit: int = DEFAULT_LIMIT) -> dict:
    ref = get_reference(conn)
    area, answer = _area(ref, area_id)
    if answer:
        return answer
    if max_km is not None and not (isinstance(max_km, (int, float)) and 0 < max_km <= pricing.MAX_DELIVERY_KM):
        return _invalid(f"max_km must be more than 0 and at most {pricing.MAX_DELIVERY_KM}")
    if max_price_for_one is not None and (not isinstance(max_price_for_one, int) or max_price_for_one < 1):
        return _invalid("max_price_for_one must be a whole number of rupees")
    if sort not in SORTS:
        return _invalid(f"sort must be one of {', '.join(SORTS)}")
    if not (isinstance(offset, int) and offset >= 0 and isinstance(limit, int) and 1 <= limit <= MAX_LIMIT):
        return _invalid(f"offset must be ≥ 0 and limit 1–{MAX_LIMIT}")
    vocab = cuisine_vocabulary(ref)
    if cuisine is not None and cuisine.strip().lower() not in vocab:
        return _invalid("cuisine must be one of the cuisines from this listing's facets")

    stats = _restaurant_stats(ref)
    cards = [_card(ref, stats, h) for h in _in_range(ref, area, max_km or pricing.MAX_DELIVERY_KM)]
    if veg_only:
        cards = [c for c in cards if c["veg_only"]]
    if mild:
        cards = [c for c in cards if c["mild_friendly"]]
    if max_price_for_one is not None:
        cards = [c for c in cards if c["price_for_one"] is not None and c["price_for_one"] <= max_price_for_one]
    facets = _cuisine_counts(cards)                          # before the cuisine filter: the chips show what's there
    if cuisine is not None:
        want = cuisine.strip().lower()
        cards = [c for c in cards if want in (x.lower() for x in c["cuisines"])]
    if sort == "price":
        cards.sort(key=lambda c: (c["price_for_one"] is None, c["price_for_one"] or 0, c["branch"]["distance_km"],
                                  c["restaurant_id"]))
    elif sort == "name":
        cards.sort(key=lambda c: (c["name"].lower(), c["restaurant_id"]))
    return {"status": "ok" if cards else "empty", "area": area_json(area),
            "filters": {"cuisine": vocab[cuisine.strip().lower()] if cuisine else None, "veg_only": bool(veg_only),
                        "mild": bool(mild), "max_km": max_km or pricing.MAX_DELIVERY_KM,
                        "max_price_for_one": max_price_for_one, "sort": sort},
            "total": len(cards), "offset": offset, "restaurants": cards[offset:offset + limit],
            "cuisine_facets": facets,
            "free_delivery_from": pricing.FREE_DELIVERY_FROM, "max_delivery_km": pricing.MAX_DELIVERY_KM,
            **({} if cards else {"message": "No restaurants match these filters in this area. Try removing a filter."})}


def _cuisine_counts(cards: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for c in cards:
        for x in c["cuisines"]:
            counts[x] = counts.get(x, 0) + 1
    return [{"cuisine": k, "restaurants": n} for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def area_home(conn: Connection, area_id: str) -> dict:
    """The home page for an area: the most common cuisines in range (shortcuts) and the chains in range, most branches
    in range first (D-049: real branch counts, never ratings)."""
    ref = get_reference(conn)
    area, answer = _area(ref, area_id)
    if answer:
        return answer
    stats = _restaurant_stats(ref)
    cards = [_card(ref, stats, h) for h in _in_range(ref, area, pricing.MAX_DELIVERY_KM)]
    chains = sorted((c for c in cards if c["is_chain"]),
                    key=lambda c: (-c["more_branches_in_range"], c["branch"]["distance_km"], c["restaurant_id"]))
    return {"status": "ok" if cards else "empty", "area": area_json(area), "restaurants_in_range": len(cards),
            "cuisines": [c for c in _cuisine_counts(cards) if c["cuisine"] not in NOT_A_SHORTCUT][:HOME_CUISINES], "chains": chains[:HOME_CHAINS],
            "max_delivery_km": pricing.MAX_DELIVERY_KM, "free_delivery_from": pricing.FREE_DELIVERY_FROM,
            **({} if cards else {"message": "No restaurants deliver to this area yet."})}

def branch_info(conn: Connection, branch_id: str, area: str | None = None) -> dict:
    """Everything the restaurant page shows above the menu. The menu itself is GET /branches/{id}/menu (get_menu).
    Coordinates are the OpenStreetMap position (for the map); delivery is judged exactly as the cart judges it."""
    ref = get_reference(conn)
    if not isinstance(branch_id, str) or branch_id not in ref.branches:
        return {"status": "unknown_branch", "branch_id": branch_id if isinstance(branch_id, str) else None,
                "message": "No open Dawat branch has this id."}
    b = ref.branches[branch_id]
    r = ref.restaurants[b["restaurant_id"]]
    stats = _restaurant_stats(ref).get(r["restaurant_id"], {"price_for_one": None, "mild_mains": 0})
    out = {
        "status": "ok",
        "restaurant": {"restaurant_id": r["restaurant_id"], "name": r["name"], "cuisines": list(r["cuisines"] or []),
                       "veg_only": r["veg_only"], "is_chain": r["is_chain"], "price_for_one": stats["price_for_one"],
                       "mild_friendly": stats["mild_mains"] >= MILD_FRIENDLY_MIN},
        "branch": {"branch_id": branch_id, "label": b["label"], "area_id": b["area_id"],
                   "area": ref.areas[b["area_id"]]["name"], "street": b["street"], "lat": b["lat"], "lon": b["lon"]},
        "other_branches": [{"branch_id": o["branch_id"], "label": o["label"], "area": ref.areas[o["area_id"]]["name"]}
                           for o in ref.branches_by_restaurant.get(r["restaurant_id"], []) if o["branch_id"] != branch_id],
        "free_delivery_from": pricing.FREE_DELIVERY_FROM, "max_delivery_km": pricing.MAX_DELIVERY_KM,
    }
    if area is not None:
        area_row, answer = _area(ref, area)
        if answer:
            out["delivery"] = {"status": answer["status"], "message": answer.get("message")}
        else:
            d = km(b["lat"], b["lon"], area_row["lat"], area_row["lon"])
            ok = pricing.within_delivery_range(d)
            out["delivery"] = {"status": "ok" if ok else "too_far", "area": area_json(area_row),
                               "distance_km": round(d, 1), "delivery_fee": pricing.delivery_fee(0, d) if ok else None}
    return out
