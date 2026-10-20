"""Phase 2, modules 2c–2f: enrichment. Rerunnable; reads only data/processed/places_clean.csv (clean.py
output) and the reviewed files in data/reference/. Never touches data/raw/.

Steps (every count, merge and fallback is logged):
  1. brands (2c, D-011): data/reference/chain_mapping.csv decides whether a place is a branch of a
     brand. Every other place is its own restaurant.
  2. brand duplicates (post-2c, D-012): same brand ≤15 m → auto-merge (the D-010 rule applied to mapped
     brands); same brand 15–50 m → must have a decision in data/reference/manual_dedupe.csv; plus
     the cross-name pairs Saif decided there (M1–M5).
  3. areas (2d, D-013): an address tag naming a known area, if that area is within 3 km of the place;
     otherwise the nearest area in data/reference/localities.csv.
  4. cuisine + veg-only (2e, D-014): OSM cuisine tags mapped to one fixed vocabulary; else name keywords;
     else a default by amenity. Veg-only from diet tags and name keywords, decided per restaurant.
  5. output (2f): restaurants.csv (one row per brand or standalone place) and branches.csv (one row per place).

Post-checks (the run FAILS if any is violated): no same-brand pair ≤15 m survives; every reviewed merge
applied; every keep_both intact; every branch has an area and ≥1 cuisine; ids are unique.

Outputs:
  data/processed/restaurants.csv, data/processed/branches.csv
  results/cleaning/enrich_log.json

Run from the project root:
    .venv\\Scripts\\python data_pipeline\\enrich.py
"""

import csv
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path
from statistics import median

from clean import keep_order
from dedupe_candidates import clusters
from detect_chains import normalise
from geo import metres

ROOT = Path(__file__).resolve().parent.parent
PLACES = ROOT / "data" / "processed" / "places_clean.csv"
CHAINS = ROOT / "data" / "reference" / "chain_mapping.csv"
MANUAL = ROOT / "data" / "reference" / "manual_dedupe.csv"
AREAS = ROOT / "data" / "reference" / "localities.csv"
OUT_RESTAURANTS = ROOT / "data" / "processed" / "restaurants.csv"
OUT_BRANCHES = ROOT / "data" / "processed" / "branches.csv"
OUT_LOG = ROOT / "results" / "cleaning" / "enrich_log.json"

AUTO_MERGE_M, REVIEW_M = 15, 50  # D-010, applied to mapped brands
AREA_TAG_KEYS = ("addr:suburb", "addr:neighbourhood", "addr:quarter", "addr:city")
AREA_TAG_MAX_M = 3000  # an address tag is trusted only if the named area is this close to the pin
AREA_TAG_SIMILARITY = 0.85
CITY_WORDS = {"hyderabad", "hyderbad", "hyderavad", "telangana", "india"}

# ─── cuisine vocabulary (D-014) ────────────────────────────────────────
# OSM cuisine value → one display cuisine. Values mapped to None carry no usable signal.
CUISINE_MAP = {
    "biryani": "Biryani", "biryanis": "Biryani", "kalyani biryani": "Biryani", "regional,_biriyani,_mughlai, indian, bakery": "Biryani",
    "hyderabadi": "Hyderabadi", "mughlai": "Mughlai",
    "indian": "Indian", "curry": "Indian", "chicken_curry": "Indian", "currie": "Indian", "meals": "Indian", "roti": "Indian", "chapathi": "Indian",
    "north_indian": "North Indian", "north-indian": "North Indian",
    "south_indian": "South Indian", "dosa": "South Indian", "idly": "South Indian", "tiffins": "South Indian", "pure_veg": "South Indian",
    "parota": "South Indian", "egg_parota": "South Indian",
    "chinese": "Chinese", "noodle": "Chinese", "noodles": "Chinese",
    "asian": "Asian", "thai": "Asian", "japanese": "Asian", "korean": "Asian", "sushi": "Asian", "vietnamese": "Asian",
    "indonesian": "Asian", "nepalese": "Asian", "rice_bowls": "Asian",
    "pizza": "Pizza", "italian_pizza": "Pizza", "italian": "Italian", "pasta": "Italian",
    "burger": "Burgers", "american": "Burgers", "diner": "Burgers",
    "sandwich": "Sandwiches", "wraps": "Rolls & Wraps", "rolls": "Rolls & Wraps", "frankie": "Rolls & Wraps",
    "chicken": "Fried Chicken", "fried_chicken": "Fried Chicken", "fry_chicken": "Fried Chicken",
    "kebab": "Kebab & Grill", "barbecue": "Kebab & Grill", "grill": "Kebab & Grill", "steak_house": "Kebab & Grill", "shawarma": "Kebab & Grill",
    "arab": "Arabian", "arabian_mandi": "Arabian", "mutton_mandi": "Arabian", "fish_mandi": "Arabian", "chucken_fry_mandi": "Arabian",
    "persian": "Arabian", "mediterranean": "Arabian",
    "fish": "Seafood", "seafood": "Seafood", "fish_and_chips": "Seafood",
    "mexican": "Mexican", "tex-mex": "Mexican", "latin_american": "Mexican",
    "international": "Continental", "continental": "Continental", "french": "Continental", "spanish": "Continental",
    "swedish": "Continental", "world": "Continental", "fine_dining": "Continental", "salad": "Continental", "soup": "Continental",
    "breakfast": "Breakfast", "brunch": "Breakfast", "pancake": "Breakfast",
    "coffee_shop": "Cafe", "coffee": "Cafe", "cafe": "Cafe",
    "tea": "Tea", "bubble_tea": "Tea",
    "cake": "Bakery", "pastry": "Bakery", "bakery": "Bakery", "donut": "Bakery", "sweets_and_bakery, fast food": "Bakery",
    "ice_cream": "Desserts", "dessert": "Desserts", "desserts": "Desserts", "sweets": "Desserts", "chocolate": "Desserts",
    "waffles": "Desserts", "waffle": "Desserts", "falooda": "Desserts",
    "juice": "Juices & Shakes", "smoothie": "Juices & Shakes", "smoothies": "Juices & Shakes", "lassi": "Juices & Shakes",
    "milkshake": "Juices & Shakes", "milk_shakes": "Juices & Shakes", "thickshakes": "Juices & Shakes", "thick_shakes": "Juices & Shakes",
    "mojitos": "Juices & Shakes", "drinks": "Juices & Shakes", "colldrins": "Juices & Shakes",
    "fast_food": "Fast Food", "fried_food": "Fast Food", "fries": "Fast Food", "chips": "Fast Food", "maggi": "Fast Food",
    "fried_maggi": "Fast Food", "quick_bites": "Fast Food", "staters": "Fast Food", "takeaway": "Fast Food",
    "multi-cuisine": "Multi-cuisine",
    # no usable signal: "regional" says a region but not which one (D-014); the rest are noise
    "regional": None, "local": None, "c": None, "etc": None,
}
# Name keyword → cuisine, checked in this order (the first matches become the cuisine; word boundaries).
NAME_KEYWORDS = [
    (r"biryani|biriyani|briyani|biriani", "Biryani"),
    (r"mandi|arabian|shawarma|shawerma", "Arabian"),
    (r"kebab|kabab|grill|bbq|barbe?que|tandoor", "Kebab & Grill"),
    (r"hyderabadi|nawab|nizam", "Hyderabadi"),
    (r"irani", "Irani Cafe"),
    (r"dhaba|punjabi", "North Indian"),
    (r"ruchulu|andhra|rayalaseema|godavari|military|telangana|telugu", "Andhra"),
    (r"udup[iy]|udipi|tiffins?|idli|idly|dosa|darshini|bhavan|mess|meals", "South Indian"),
    (r"chinese|china|wok|noodles?|momos?", "Chinese"),
    (r"pizza|pizzeria", "Pizza"),
    (r"burgers?", "Burgers"),
    (r"sandwich(es)?", "Sandwiches"),
    (r"chicken|chick", "Fried Chicken"),
    (r"fish|sea ?food|prawns?", "Seafood"),
    (r"bakery|bakers|bake|cakes?", "Bakery"),
    (r"ice ?cream|creamery|desserts?|sweets|waffles?|chocolate|falooda", "Desserts"),
    (r"juices?|shakes?|lassi|smoothies?", "Juices & Shakes"),
    (r"chai|tea", "Tea"),
    (r"coffee|cafe|café", "Cafe"),
    (r"fast ?food", "Fast Food"),
]
AMENITY_DEFAULT = {"restaurant": "Multi-cuisine", "fast_food": "Fast Food", "cafe": "Cafe"}
MAX_CUISINES = 3

# ─── veg-only (D-014) ──────────────────────────────────────────────────
# A restaurant is veg-only if any of its branches has diet:vegetarian=only or a veg name keyword, and
# no branch says diet:non-vegetarian=yes. Erring towards veg-only is the safe direction: a synthetic
# menu with chicken on a real vegetarian restaurant misrepresents it; the reverse only narrows a menu.
# "veg[ei]t[ae]rian" also catches common typos ("Vegitarian", "Vegeterian"); Kamat/Kamath is a vegetarian
# chain name (general knowledge; one "Kamath Hotel" record is tagged diet:vegetarian=only).
VEG_NAME = re.compile(r"\b(pure veg|veg restaurant|veg[ei]t[ae]rian|veggie|udup[iy]|udipi|darshini|bhavan|kamath?)\b|\bveg$")
SMALL_WORDS = {"and", "of", "the", "n", "in", "on", "at"}
NON_VEG_NAME = re.compile(r"\bnon ?veg\b")
VEG_ONLY_BRANDS = {"Minerva Coffee Shop": "verified by Saif 2026-09-30: pure vegetarian"}
# Reviewed brand cuisines that override the computed ones (D-014 addendum 2). "Coffee" in the name made
# Minerva "Cafe"; it is a South Indian vegetarian restaurant with a coffee counter (Saif, 2026-09-30).
BRAND_CUISINES = {"Minerva Coffee Shop": (["South Indian", "Cafe"], "Saif 2026-09-30: South Indian first, Cafe second")}


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "x"


def display_name(name: str) -> str:
    """All-lowercase names, and all-caps names with a word of 4+ letters, get title case; others are kept as written."""
    letters = [c for c in name if c.isalpha()]
    if not letters or not all(c.isascii() for c in letters):
        return name
    lower, upper = name == name.lower(), name == name.upper()
    if not (lower or (upper and any(len(re.sub(r"[^A-Za-z]", "", w)) >= 4 for w in name.split()))):
        return name

    def word(w: str, first: bool) -> str:
        if not re.search(r"[aeiouy]", w, re.I) and w.isalpha():
            return w.upper()  # no vowels → an acronym: GHMC, KS, RV
        if not first and w.lower() in SMALL_WORDS:
            return w.lower()
        return w[:1].upper() + w[1:].lower()

    # split on spaces, hyphens and commas but keep them, so "al-madini" → "Al-Madini"
    parts = re.split(r"([\s,\-]+)", name)
    return "".join(p if re.fullmatch(r"[\s,\-]+", p) or not p else word(p, i == 0) for i, p in enumerate(parts))


def dist(a: dict, b: dict) -> float:
    return metres((a["lat"], a["lon"]), (b["lat"], b["lon"]))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    log: dict = {"generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "inputs": [p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else str(p)
                            for p in (PLACES, CHAINS, MANUAL, AREAS)],
                 "decisions": ["D-010", "D-011", "D-012", "D-013", "D-014"]}
    places = []
    for p in read_csv(PLACES):
        t = json.loads(p["tags_json"])
        otype, oid = p["osm"].split("/")
        places.append({"osm": p["osm"], "osm_type": otype, "osm_id": int(oid), "name": p["name"], "norm": normalise(p["name"]),
                       "amenity": p["amenity"], "lat": float(p["lat"]), "lon": float(p["lon"]), "tags": t})
    log["places_in"] = len(places)

    # ── 1. brands ──────────────────────────────────────────────────────
    chain_rows = read_csv(CHAINS)
    undecided = [r["row"] for r in chain_rows if r["saif_decision"] not in ("brand", "separate")]
    if undecided or any(r["saif_decision"] == "brand" and not r["saif_brand"] for r in chain_rows):
        sys.exit(f"chain_mapping.csv has undecided or brand-less rows: {undecided}. Nothing written.")
    decision = {r["name_normalised"]: r for r in chain_rows}
    for p in places:
        r = decision.get(p["norm"])
        p["brand"] = r["saif_brand"] if r and r["saif_decision"] == "brand" else None
    tag_conflicts = [{"osm": p["osm"], "name": p["name"], "osm_brand_tag": p["tags"]["brand"], "assigned": p["brand"]}
                     for p in places if p["brand"] and p["tags"].get("brand") and p["tags"]["brand"] != p["brand"]]
    log["1_brands"] = {
        "mapping_rows": len(chain_rows), "mapping_rows_by_decision": dict(Counter(r["saif_decision"] for r in chain_rows)),
        "places_in_a_brand": sum(1 for p in places if p["brand"]), "brands": len({p["brand"] for p in places if p["brand"]}),
        "osm_brand_tag_conflicts": tag_conflicts,
        "conflict_rule": "the reviewed mapping (by name) wins over a conflicting OSM brand tag; conflicts are listed here",
    }

    # ── 2. brand duplicates + reviewed cross-name pairs ─────────────────
    by_osm = {p["osm"]: p for p in places}
    manual = read_csv(MANUAL)
    bad = [r["pair"] for r in manual if r["saif_decision"] not in ("merge", "keep_both")]
    missing = [r["pair"] for r in manual if r["osm_a"] not in by_osm or r["osm_b"] not in by_osm]
    if bad or missing:
        sys.exit(f"manual_dedupe.csv: undecided {bad}, unknown places {missing}. Nothing written.")
    reviewed = {frozenset((r["osm_a"], r["osm_b"])): r for r in manual}

    by_brand = defaultdict(list)
    for p in places:
        if p["brand"]:
            by_brand[p["brand"]].append(p)
    auto, needs_review = [], []
    for brand, group in by_brand.items():
        for a, b in combinations(group, 2):
            d = dist(a, b)
            if d <= AUTO_MERGE_M:
                auto.append({"a": a["osm"], "b": b["osm"], "names": [a["name"], b["name"]], "distance_m": round(d, 1),
                             "why": f"auto: same brand '{brand}' ≤{AUTO_MERGE_M} m"})
            elif d <= REVIEW_M and frozenset((a["osm"], b["osm"])) not in reviewed:
                needs_review.append({"brand": brand, "a": a["osm"], "b": b["osm"], "distance_m": round(d, 1)})
    if needs_review:
        print(json.dumps(needs_review, indent=2, ensure_ascii=False))
        sys.exit("Same-brand pairs 15–50 m apart need a decision in manual_dedupe.csv. Nothing written.")
    manual_merges = [{"a": r["osm_a"], "b": r["osm_b"], "names": [r["name_a"], r["name_b"]],
                      "distance_m": round(dist(by_osm[r["osm_a"]], by_osm[r["osm_b"]]), 1),
                      "why": f"Saif review {r['pair']}: merge"} for r in manual if r["saif_decision"] == "merge"]

    merged_into, merge_log = {}, []
    for cluster in clusters(auto + manual_merges):
        members = sorted((by_osm[o] for o in cluster), key=keep_order)
        keeper = members[0]
        keeper["brand"] = keeper["brand"] or next((m["brand"] for m in members if m["brand"]), None)
        for m in members[1:]:
            merged_into[m["osm"]] = keeper["osm"]
            merge_log.append({"dropped": m["osm"], "dropped_name": m["name"], "kept": keeper["osm"], "kept_name": keeper["name"]})
    places = [p for p in places if p["osm"] not in merged_into]

    def ends_up(o: str) -> str:
        while o in merged_into:
            o = merged_into[o]
        return o

    leftover = [(a["osm"], b["osm"]) for grp in [[p for p in places if p["brand"] == br] for br in by_brand]
                for a, b in combinations(grp, 2) if dist(a, b) <= AUTO_MERGE_M]
    not_merged = [r["pair"] for r in manual if r["saif_decision"] == "merge" and ends_up(r["osm_a"]) != ends_up(r["osm_b"])]
    broken_keep = [r["pair"] for r in manual if r["saif_decision"] == "keep_both" and ends_up(r["osm_a"]) == ends_up(r["osm_b"])]
    if leftover or not_merged or broken_keep:
        sys.exit(f"Post-checks FAILED: leftover {leftover}, not merged {not_merged}, keep_both broken {broken_keep}")
    log["2_duplicates"] = {"auto_pairs": auto, "manual_merge_pairs": manual_merges,
                           "manual_keep_both": [r["pair"] for r in manual if r["saif_decision"] == "keep_both"],
                           "pairs_15_to_50_m_needing_review": 0, "removed": len(merge_log), "merges": merge_log,
                           "places_after": len(places)}

    # ── 3. areas ───────────────────────────────────────────────────────
    areas = read_csv(AREAS)
    for a in areas:
        a["lat"], a["lon"] = float(a["lat"]), float(a["lon"])
    key = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())  # noqa: E731
    area_keys = [(key(n), a) for a in areas for n in [a["display_name"], *a["aliases"].split(";")] if n and key(n)]

    def area_from_tags(p: dict):
        for k in AREA_TAG_KEYS:
            for part in str(p["tags"].get(k, "")).replace("hyderabad", ",").replace("Hyderabad", ",").split(","):
                pk = key(part)
                if not pk or pk in CITY_WORDS or len(pk) < 4:
                    continue
                score, i = max((1.0 if ak == pk else SequenceMatcher(None, ak, pk).ratio(), i)
                               for i, (ak, _) in enumerate(area_keys))
                if score >= AREA_TAG_SIMILARITY:
                    return area_keys[i][1], k, part.strip(), score
        return None

    methods, tag_rejected, tag_used = Counter(), [], []
    for p in places:
        nearest = min(areas, key=lambda a: dist(p, a))
        hit = area_from_tags(p)
        if hit and dist(p, hit[0]) <= AREA_TAG_MAX_M:
            area, method = hit[0], "address tag"
            tag_used.append({"osm": p["osm"], "tag": f"{hit[1]}={p['tags'][hit[1]]}", "area": area["display_name"],
                             "nearest_would_be": nearest["display_name"], "distance_m": round(dist(p, area))})
        else:
            if hit:
                tag_rejected.append({"osm": p["osm"], "tag": f"{hit[1]}={p['tags'][hit[1]]}", "matched": hit[0]["display_name"],
                                     "distance_m": round(dist(p, hit[0])), "used_nearest": nearest["display_name"]})
            area, method = nearest, "nearest area"
        p["area"], p["area_method"], p["area_distance_m"] = area, method, round(dist(p, area))
        methods[method] += 1
    ds = sorted(p["area_distance_m"] for p in places)
    log["3_areas"] = {
        "rule": f"address tag naming a known area (similarity ≥{AREA_TAG_SIMILARITY}) if that area is ≤{AREA_TAG_MAX_M} m away; else nearest area",
        "by_method": dict(methods), "tag_used": tag_used, "tag_rejected_too_far": tag_rejected,
        "tag_agrees_with_nearest": sum(1 for t in tag_used if t["area"] == t["nearest_would_be"]),
        "distance_to_area_m": {"median": median(ds), "p90": ds[int(0.9 * (len(ds) - 1))], "max": ds[-1],
                               "over_2km": sum(1 for d in ds if d > 2000)},
        "areas_with_places": len({p["area"]["area_id"] for p in places}), "areas_total": len(areas),
    }

    # ── 4. cuisine + veg signals (per place) ────────────────────────────
    unmapped = Counter()
    for p in places:
        found, source = [], None
        for v in str(p["tags"].get("cuisine", "")).split(";"):
            v = v.strip().lower()
            if not v:
                continue
            if v not in CUISINE_MAP:
                unmapped[v] += 1
            elif CUISINE_MAP[v] and CUISINE_MAP[v] not in found:
                found.append(CUISINE_MAP[v])
        if found:
            source = "osm cuisine tag"
        name_hits = [c for pat, c in NAME_KEYWORDS if re.search(rf"\b({pat})\b", p["norm"])]
        if not found and name_hits:
            found, source = name_hits, "name keyword"
        elif name_hits and name_hits[0] in ("Biryani", "Arabian"):
            # a dish-type name leads: "X Biryani House" tagged only 'indian' is a biryani place first
            found = [name_hits[0]] + [c for c in found if c != name_hits[0]]
        if not found:
            found, source = [AMENITY_DEFAULT[p["amenity"]]], f"default for amenity={p['amenity']}"
        p["cuisines"], p["cuisine_source"] = found[:MAX_CUISINES], source
        diet = p["tags"].get("diet:vegetarian")
        p["veg_signal"] = ("diet:vegetarian=only" if diet == "only" else
                           "name keyword" if VEG_NAME.search(p["norm"]) and not NON_VEG_NAME.search(p["norm"]) else None)
        p["nonveg_tag"] = p["tags"].get("diet:non-vegetarian") == "yes"
    if unmapped:
        sys.exit(f"Cuisine values with no mapping: {dict(unmapped)}. Add them to CUISINE_MAP. Nothing written.")

    # ── 5. restaurants + branches ──────────────────────────────────────
    groups = defaultdict(list)
    for p in places:
        groups[("brand", p["brand"]) if p["brand"] else ("own", p["osm"])].append(p)
    restaurants, branches, veg_log, cuisine_overrides = [], [], [], []
    for (kind, k), ps in sorted(groups.items(), key=lambda kv: (kv[0][0], str(kv[0][1]).lower())):
        name = k if kind == "brand" else display_name(ps[0]["name"])
        rid = f"r-{slug(name)}" if kind == "brand" else f"r-{slug(name)}-{ps[0]['osm_type'][0]}{ps[0]['osm_id']}"
        # A branch whose cuisine is only an amenity default says nothing about the brand, so defaults count
        # only when no branch has a real signal (Paradise: Biryani from tagged branches, not "Multi-cuisine").
        informed = [p for p in ps if not p["cuisine_source"].startswith("default")] or ps
        counts, first = Counter(), {}
        for p in informed:
            for i, c in enumerate(p["cuisines"]):
                counts[c] += 1
                first.setdefault(c, (i, len(first)))
        cuisines = sorted(counts, key=lambda c: (-counts[c], first[c]))[:MAX_CUISINES]
        if name in BRAND_CUISINES:
            override, why = BRAND_CUISINES[name]
            cuisine_overrides.append({"restaurant": name, "computed": cuisines, "used": override, "why": why})
            cuisines = override
        signals = sorted({p["veg_signal"] for p in ps if p["veg_signal"]})
        if name in VEG_ONLY_BRANDS:
            signals.append(VEG_ONLY_BRANDS[name])
        nonveg = any(p["nonveg_tag"] for p in ps)
        veg_only = bool(signals) and not nonveg
        if signals:
            veg_log.append({"restaurant": name, "veg_only": veg_only, "signals": signals, "blocked_by_non_veg_tag": nonveg})
        restaurants.append({"restaurant_id": rid, "name": name, "is_chain": len(ps) >= 2, "branch_count": len(ps),
                            "cuisines": ";".join(cuisines), "primary_cuisine": cuisines[0], "veg_only": veg_only,
                            "grouping": "reviewed brand (chain_mapping.csv)" if kind == "brand" else "own name"})
        per_area = Counter(p["area"]["area_id"] for p in ps)
        seen = Counter()
        for p in sorted(ps, key=lambda p: (p["area"]["display_name"], -len(p["tags"]), p["osm"])):
            # Several branches of one restaurant in one area are numbered ("Madhapur 1", "Madhapur 2"), richest
            # record first. OSM branch/street tags are too inconsistent for labels; the street stays in its own column.
            label = p["area"]["display_name"]
            if per_area[p["area"]["area_id"]] > 1:
                seen[p["area"]["area_id"]] += 1
                label = f"{label} {seen[p['area']['area_id']]}"
            branches.append({"branch_id": f"b-{p['osm_type'][0]}{p['osm_id']}", "restaurant_id": rid, "restaurant_name": name,
                             "branch_label": label, "osm": p["osm"], "osm_name": p["name"], "amenity": p["amenity"],
                             "lat": p["lat"], "lon": p["lon"], "area_id": p["area"]["area_id"], "area_name": p["area"]["display_name"],
                             "area_method": p["area_method"], "area_distance_m": p["area_distance_m"],
                             "cuisines": ";".join(p["cuisines"]), "cuisine_source": p["cuisine_source"],
                             "street": p["tags"].get("addr:street", ""), "postcode": re.sub(r"\s", "", p["tags"].get("addr:postcode", ""))})

    # post-checks
    problems = []
    if len({r["restaurant_id"] for r in restaurants}) != len(restaurants):
        problems.append("duplicate restaurant_id")
    if len({b["branch_id"] for b in branches}) != len(branches) or len(branches) != len(places):
        problems.append("branch ids not unique / branch count != place count")
    labels = Counter((b["restaurant_id"], b["branch_label"]) for b in branches)
    if any(v > 1 for v in labels.values()):
        problems.append(f"duplicate branch labels: {[k for k, v in labels.items() if v > 1]}")
    if any(not b["area_id"] or not b["cuisines"] for b in branches):
        problems.append("branch without area or cuisine")
    vocab = {c for c in CUISINE_MAP.values() if c} | {c for _, c in NAME_KEYWORDS}
    if len(cuisine_overrides) != len(BRAND_CUISINES) or any(c not in vocab for o in cuisine_overrides for c in o["used"]):
        problems.append(f"brand cuisine override for an unknown brand or outside the vocabulary: {BRAND_CUISINES}")
    if problems:
        sys.exit(f"Post-checks FAILED: {problems}. Nothing written.")

    renamed = [{"from": ps[0]["name"], "to": display_name(ps[0]["name"])} for (kind, _), ps in groups.items()
               if kind == "own" and display_name(ps[0]["name"]) != ps[0]["name"]]
    log["4_cuisine"] = {
        "rule": "OSM cuisine tags → fixed vocabulary; else name keywords; else default by amenity; max 3 per place/restaurant",
        "branches_by_source": dict(Counter(b["cuisine_source"] for b in branches)),
        "restaurants_by_primary_cuisine": dict(Counter(r["primary_cuisine"] for r in restaurants).most_common()),
        "regional_only_places": sum(1 for p in places if {v.strip().lower() for v in p["tags"].get("cuisine", "").split(";") if v.strip()} == {"regional"}),
        "vocabulary": sorted({c for c in CUISINE_MAP.values() if c} | {c for _, c in NAME_KEYWORDS}),
        "reviewed_brand_overrides": cuisine_overrides,
    }
    log["5_veg_only"] = {"restaurants_veg_only": sum(r["veg_only"] for r in restaurants), "details": veg_log}
    log["6_output"] = {
        "restaurants": len(restaurants), "chains": sum(r["is_chain"] for r in restaurants),
        "standalone": sum(not r["is_chain"] for r in restaurants), "branches": len(branches),
        "branches_in_chains": sum(r["branch_count"] for r in restaurants if r["is_chain"]),
        "branch_labels_disambiguated": sum(1 for b in branches if b["branch_label"] != b["area_name"]),
        # separate restaurants that share a display name ("Hot Chips" ×6): search must tell them apart by area
        "standalone_names_shared": (lambda c: {"names": sum(1 for v in c.values() if v > 1),
                                               "restaurants": sum(v for v in c.values() if v > 1)})(
            Counter(r["name"] for r in restaurants if not r["is_chain"])),
        "names_recased": {"count": len(renamed), "rule": "all-lowercase, or all-caps with a 4+ letter word → title case", "list": renamed},
        "post_checks": "passed",
    }

    for path, rows in ((OUT_RESTAURANTS, restaurants), (OUT_BRANCHES, branches)):
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    # hashes let a later rerun prove it reproduces the same outputs byte for byte
    log["output_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (OUT_RESTAURANTS, OUT_BRANCHES)}
    log["input_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (PLACES, CHAINS, MANUAL, AREAS)}
    OUT_LOG.write_text(json.dumps(log, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    o = log["6_output"]
    print(f"1. brands: {log['1_brands']['places_in_a_brand']} places in {log['1_brands']['brands']} brands; "
          f"{len(tag_conflicts)} OSM brand-tag conflict(s)")
    print(f"2. duplicates: {len(auto)} auto pair(s), {len(manual_merges)} reviewed merge pair(s) → −{len(merge_log)}; "
          f"{log['places_in']} → {len(places)} places")
    print(f"3. areas: {dict(methods)}; {len(tag_rejected)} tag(s) rejected as too far; median {median(ds)} m, max {ds[-1]} m")
    print(f"4. cuisine sources: {log['4_cuisine']['branches_by_source']}")
    print(f"5. veg-only restaurants: {log['5_veg_only']['restaurants_veg_only']}")
    print(f"6. {o['restaurants']} restaurants ({o['chains']} chains with {o['branches_in_chains']} branches, {o['standalone']} standalone); "
          f"{o['branches']} branches; {o['names_recased']['count']} names re-cased")
    print(f"Saved {OUT_RESTAURANTS.relative_to(ROOT)}, {OUT_BRANCHES.relative_to(ROOT)}, {OUT_LOG.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
