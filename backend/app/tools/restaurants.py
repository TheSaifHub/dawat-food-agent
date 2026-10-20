"""search_restaurants(query, area?) → matching restaurants and their branches, as plain JSON (D-023).

Matching, on the distinctive words of the name ("Hotel Mehfil" and "mehfil restaurant" → "mehfil"),
compared without spaces or apostrophes (so "mc donalds" = "McDonald's"), in tiers:
  exact     the distinctive words are the same
  contains  every distinctive word of the query is a word of the name ("paradise" → "Hotel Persis Paradise")
  fuzzy       a typo of the whole distinctive part: rapidfuzz ratio ≥ FUZZY_MIN ("paradice" → Paradise)
  fuzzy_word  a typo of each query word inside a longer name ("paradice" → Hotel Persis Paradise); ranked
              below fuzzy, because a typo of the whole name is stronger evidence
A query made only of food words ("biryani", "chinese") is a dish question → status "dish_query".

The agent's rules are supported by fields, not prose:
  needs_choice + choices  more than one branch/place fits the best match → the agent must ask which one
                          (a chain's branches AND separate restaurants that share a name, e.g. 5 × "Hot Chips")
  selected_branch_id      exactly one fits → safe to show its menu
With an area, only branches in it or within NEAR_KM are returned; matches with no branch nearby are listed
in not_near_area (with their nearest branches) instead of being dropped silently. An area we can't resolve
stops the search: results from somewhere else would be a silent guess.
"""

from rapidfuzz import fuzz

from psycopg import Connection

from app.text import compact, tokens
from app.tools.areas import resolve_area
from app.tools.reference import FOOD_WORDS, GENERIC_WORDS, Reference, get_reference, km

FUZZY_MIN = 85
WORD_FUZZY_MIN_LEN = 4
NEAR_KM = 3.0
MAX_RESULTS, MAX_BRANCHES, MAX_CHOICES = 8, 12, 12
MAX_QUERY_LEN = 100
TIER = {"exact": 0, "contains": 1, "fuzzy": 2, "fuzzy_word": 3}


def _match(core: list[str], core_c: str, r: dict) -> tuple[str, float] | None:
    if r["core_compact"] == core_c:
        return "exact", 100.0
    if set(core) <= r["words"]:
        return "contains", 100.0
    whole = fuzz.ratio(core_c, r["core_compact"])
    if whole >= FUZZY_MIN:
        return "fuzzy", whole
    per_word = [max((fuzz.ratio(w, n) for n in r["words"]), default=0) for w in core if len(w) >= WORD_FUZZY_MIN_LEN]
    if per_word and len(per_word) == len(core) and min(per_word) >= FUZZY_MIN:
        return "fuzzy_word", min(per_word)
    return None


def _branch_json(ref: Reference, b: dict, area: dict | None) -> dict:
    out = {"branch_id": b["branch_id"], "label": b["label"], "area": ref.areas[b["area_id"]]["name"], "street": b["street"]}
    if area is not None:
        out["distance_km"] = round(km(b["lat"], b["lon"], area["lat"], area["lon"]), 1)
    return out


def search_restaurants(conn: Connection, query: str, area: str | None = None, limit: int = MAX_RESULTS) -> dict:
    query = (query or "").strip()
    if not query or len(query) > MAX_QUERY_LEN:
        return {"status": "invalid_input", "message": f"query must be 1–{MAX_QUERY_LEN} characters"}
    limit = max(1, min(int(limit), MAX_RESULTS))
    ref = get_reference(conn)

    area_row, area_info = None, None
    if area is not None and area.strip():
        resolved = resolve_area(ref, area)
        if resolved["status"] != "ok":
            return {"status": resolved["status"], "query": query, "area_resolution": resolved,
                    "message": resolved["message"]}
        area_row, area_info = ref.areas[resolved["area"]["area_id"]], resolved

    words = tokens(query)
    core = [w for w in words if w not in GENERIC_WORDS and w not in FOOD_WORDS]
    food = [w for w in words if w in FOOD_WORDS]
    if not core:
        if food:
            return {"status": "dish_query", "query": query, "food_words": food,
                    "message": "This names food, not a restaurant: use search_dishes for it."}
        return {"status": "no_match", "query": query, "results": [],
                "message": "Ask the user for the restaurant's name."}
    core_c = compact(core)

    matches, not_near = [], []
    for r in ref.restaurants.values():
        m = _match(core, core_c, r)
        if not m:
            continue
        branches = ref.branches_by_restaurant.get(r["restaurant_id"], [])
        if not branches:
            continue
        if area_row is not None:
            dist = {b["branch_id"]: km(b["lat"], b["lon"], area_row["lat"], area_row["lon"]) for b in branches}
            ordered = sorted(branches, key=lambda b: (b["area_id"] != area_row["area_id"], dist[b["branch_id"]]))
            near = [b for b in ordered if b["area_id"] == area_row["area_id"] or dist[b["branch_id"]] <= NEAR_KM]
            if not near:
                not_near.append({"restaurant_id": r["restaurant_id"], "name": r["name"], "match": m[0],
                                 "nearest_branches": [_branch_json(ref, b, area_row) for b in ordered[:3]]})
                continue
            branches = near
        matches.append((m, r, branches))

    matches.sort(key=lambda x: (TIER[x[0][0]], -x[0][1], not x[1]["is_chain"], -len(x[2]), x[1]["name"].lower()))
    results = [{
        "restaurant_id": r["restaurant_id"], "name": r["name"], "cuisines": r["cuisines"], "veg_only": r["veg_only"],
        "is_chain": r["is_chain"], "match": m[0],
        "branches": [_branch_json(ref, b, area_row) for b in branches[:MAX_BRANCHES]],
        "branches_matching": len(branches), "branches_in_city": r["branch_count"],
    } for m, r, branches in matches[:limit]]

    out: dict = {"status": "ok" if results else ("none_near_area" if not_near else "no_match"), "query": query,
                 "area": {"area_id": area_row["area_id"], "name": area_row["name"]} if area_row else None,
                 "results": results}
    if area_info and area_info["matched_by"] == "fuzzy":
        out["area_note"] = area_info["message"]
    if not_near:
        not_near.sort(key=lambda x: (TIER[x["match"]], x["name"].lower()))
        out["not_near_area"] = not_near[:limit]
    if food:
        out["food_words"] = food          # e.g. "paradise biryani": filter the menu by category next

    if results:
        best_tier = results[0]["match"]
        best = [(m, r, b) for m, r, b in matches if m[0] == best_tier]
        options = [(r, br) for _, r, bs in best for br in bs]
        if len(options) == 1:
            out["needs_choice"], out["selected_branch_id"] = False, options[0][1]["branch_id"]
        else:
            out["needs_choice"] = True
            out["choices"] = [{"restaurant_id": r["restaurant_id"], "restaurant_name": r["name"],
                               **_branch_json(ref, br, area_row)} for r, br in options[:MAX_CHOICES]]
            out["choices_total"] = len(options)
            out["message"] = ("Several branches or places match. Ask the user which one (by area) before showing a "
                              "menu." + (" Asking for their area will narrow it down." if area_row is None else ""))
    elif not_near:
        out["message"] = "No matching branch near this area. Tell the user and offer the nearest branches listed."
    else:
        out["message"] = "No restaurant by that name in Dawat. Say so; do not guess one."
    return out
