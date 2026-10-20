"""Phase 1, module 3: chain detection. COUNTING ONLY: nothing is merged or changed.

A "chain" here is a core name that appears at 2+ food places. Steps:
  1. normalise names (case, punctuation, "&" → "and")                → exact-name counts
  2. core name = normalised name minus generic words (hotel, restaurant, cafe, …)
  3. chains = core names with 2+ places
  4. ambiguous names = names that CONTAIN a chain's core name plus other words
     ("Hotel Persis Paradise" vs chain "paradise"). Listed for Saif's review, NOT counted.
  5. possible spelling variants between core names (stdlib difflib; rapidfuzz comes in Phase 2)
  6. same-spot pairs: two places of one chain within 50 m, a possible double-mapping

The reviewed merge decisions are Phase 2's job (a reviewed mapping in data/reference/).

Outputs:
  results/eda/chains.json        all numbers (cited by docs/data_insights.md)
  results/eda/chain_review.csv   ambiguous names + spelling variants, for review in Phase 2

Run from the project root:
    .venv\\Scripts\\python data_pipeline\\detect_chains.py
"""

import csv
import hashlib
import json
import math
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT_JSON = ROOT / "results" / "eda" / "chains.json"
OUT_REVIEW = ROOT / "results" / "eda" / "chain_review.csv"

FOOD_TYPES = {"restaurant", "fast_food", "cafe"}
# Words that describe the kind of place, not the brand. Deliberately short and reviewable;
# cuisine words like "biryani" are NOT stripped ("Paradise Biryani" is flagged for review instead).
GENERIC_WORDS = {
    "hotel", "restaurant", "restaurants", "restro", "cafe", "café", "the", "family",
    "takeaway", "take", "away", "and", "n", "pvt", "ltd", "new",
}
SAME_SPOT_METRES = 50
VARIANT_SIMILARITY = 0.85
TOP_N = 25


# ─── load (same integrity check as profile_osm.py) ─────────────────────
def load_food_places() -> tuple[list[dict], dict]:
    snapshots = sorted(p for p in RAW_DIR.glob("overpass_hyderabad_*.json") if not p.name.endswith(".meta.json"))
    if len(snapshots) != 1:
        sys.exit(f"Expected exactly one raw snapshot in data/raw/, found {len(snapshots)}.")
    path = snapshots[0]
    meta = json.loads(path.with_name(path.stem + ".meta.json").read_bytes())
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != meta["sha256"]:
        sys.exit(f"{path.name} does not match its .meta.json sha256. Refusing to run.")
    places = []
    for e in json.loads(raw)["elements"]:
        tags = e.get("tags", {})
        if tags.get("amenity") not in FOOD_TYPES:
            continue
        places.append({
            "osm": f"{e['type']}/{e['id']}",
            "name": str(tags.get("name", "")).strip(),
            "brand": str(tags.get("brand", "")).strip(),
            "amenity": tags["amenity"],
            "lat": e.get("lat", e.get("center", {}).get("lat")),
            "lon": e.get("lon", e.get("center", {}).get("lon")),
        })
    return places, meta


# ─── names ─────────────────────────────────────────────────────────────
def normalise(name: str) -> str:
    s = unicodedata.normalize("NFKC", name).lower().replace("&", " and ")
    s = re.sub(r"[^\w\s]", " ", s)  # \w keeps letters in any script (Telugu too)
    return re.sub(r"\s+", " ", s).strip()


def core_name(normalised: str) -> str:
    tokens = [t for t in normalised.split() if t not in GENERIC_WORDS]
    return " ".join(tokens) if tokens else normalised  # "Hotel Restaurant" stays as-is


def contains_tokens(haystack: list[str], needle: list[str]) -> bool:
    n = len(needle)
    return any(haystack[i:i + n] == needle for i in range(len(haystack) - n + 1))


def metres(a: dict, b: dict) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


# ─── detect ────────────────────────────────────────────────────────────
def detect(places: list[dict], meta: dict) -> tuple[dict, list[dict]]:
    named = [p for p in places if p["name"]]
    for p in named:
        p["normalised"] = normalise(p["name"])
        p["core"] = core_name(p["normalised"])

    exact_counts = Counter(p["normalised"] for p in named)
    by_core: dict[str, list[dict]] = defaultdict(list)
    for p in named:
        by_core[p["core"]].append(p)

    chains = {core: ps for core, ps in by_core.items() if len(ps) >= 2}
    ranked = sorted(chains.items(), key=lambda kv: (-len(kv[1]), kv[0]))

    close_pair_types: Counter = Counter()
    close_pair_distances: list[float] = []
    chain_rows = []
    for core, ps in ranked:
        for a, b in combinations(ps, 2):
            d = metres(a, b)
            if d <= SAME_SPOT_METRES:
                close_pair_types["+".join(sorted((a["osm"].split("/")[0], b["osm"].split("/")[0])))] += 1
                close_pair_distances.append(d)
        close_pairs = sum(1 for a, b in combinations(ps, 2) if metres(a, b) <= SAME_SPOT_METRES)
        chain_rows.append({
            "core_name": core,
            "places": len(ps),
            "name_variants": [{"name": n, "count": c} for n, c in Counter(p["name"] for p in ps).most_common()],
            "by_amenity": dict(Counter(p["amenity"] for p in ps).most_common()),
            "with_brand_tag": sum(1 for p in ps if p["brand"]),
            "same_spot_pairs_within_50m": close_pairs,
        })

    # Ambiguous: a DIFFERENT core name that contains a chain's core name as whole words.
    review: list[dict] = []
    chain_tokens = {core: core.split() for core in chains}
    for core, ps in sorted(by_core.items()):
        tokens = core.split()
        for chain, ctoks in chain_tokens.items():
            if core != chain and contains_tokens(tokens, ctoks):
                for p in ps:
                    review.append({"kind": "ambiguous_contains_chain_name", "chain_core_name": chain,
                                   "name": p["name"], "core_name": core, "amenity": p["amenity"],
                                   "osm": p["osm"], "lat": p["lat"], "lon": p["lon"], "similarity": ""})

    # Possible spelling variants between a chain's core name and any other core name.
    for chain in chains:
        for core, ps in by_core.items():
            if core == chain or contains_tokens(core.split(), chain.split()):
                continue
            ratio = SequenceMatcher(None, chain, core).ratio()
            if ratio >= VARIANT_SIMILARITY:
                for p in ps:
                    review.append({"kind": "possible_spelling_variant", "chain_core_name": chain,
                                   "name": p["name"], "core_name": core, "amenity": p["amenity"],
                                   "osm": p["osm"], "lat": p["lat"], "lon": p["lon"], "similarity": round(ratio, 2)})

    places_in_chains = sum(len(ps) for ps in chains.values())
    stats = {
        "snapshot": {"file": meta["file"], "sha256": meta["sha256"], "osm_data_timestamp": meta["osm_data_timestamp"]},
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": {
            "normalise": "NFKC, lower case, & → and, punctuation removed, spaces collapsed",
            "generic_words_ignored_in_core_name": sorted(GENERIC_WORDS),
            "chain_definition": "core name shared by 2+ named food places",
            "same_spot_threshold_m": SAME_SPOT_METRES,
            "spelling_variant_similarity": VARIANT_SIMILARITY,
            "merging": "none. Counting only; merges are reviewed in Phase 2",
        },
        "summary": {
            "food_places": len(places),
            "named_food_places": len(named),
            "distinct_exact_names": len(exact_counts),
            "exact_names_repeated_2plus": sum(1 for c in exact_counts.values() if c >= 2),
            "distinct_core_names": len(by_core),
            "chains_core_name_2plus": len(chains),
            "places_in_chains": places_in_chains,
            "places_in_chains_pct_of_named": round(100 * places_in_chains / len(named), 1),
            "single_location_names": len(by_core) - len(chains),
            "chains_by_size": dict(sorted(Counter(len(ps) for ps in chains.values()).items(), reverse=True)),
            "chains_with_same_spot_pairs": sum(1 for r in chain_rows if r["same_spot_pairs_within_50m"]),
            "same_spot_pairs_total": len(close_pair_distances),
            "same_spot_pairs_by_element_types": dict(close_pair_types.most_common()),
            "same_spot_pair_distance_m": {
                "min": round(min(close_pair_distances), 1) if close_pair_distances else None,
                "median": round(sorted(close_pair_distances)[len(close_pair_distances) // 2], 1)
                if close_pair_distances else None,
            },
            "review_rows_ambiguous": sum(1 for r in review if r["kind"] == "ambiguous_contains_chain_name"),
            "review_rows_spelling": sum(1 for r in review if r["kind"] == "possible_spelling_variant"),
        },
        "top_chains": chain_rows[:TOP_N],
        "all_chains": chain_rows,
    }
    return stats, review


# ─── report ────────────────────────────────────────────────────────────
def print_report(stats: dict, review: list[dict]) -> None:
    s = stats["summary"]
    print(f"Named food places: {s['named_food_places']} of {s['food_places']}")
    print(f"Distinct exact names: {s['distinct_exact_names']} ({s['exact_names_repeated_2plus']} appear 2+ times)")
    print(f"Distinct core names:  {s['distinct_core_names']} → chains (2+ places): {s['chains_core_name_2plus']}, "
          f"covering {s['places_in_chains']} places ({s['places_in_chains_pct_of_named']}% of named)")
    print(f"Chains by size (places: how many chains): {s['chains_by_size']}")
    print(f"Chains with a same-spot pair (≤{SAME_SPOT_METRES} m): {s['chains_with_same_spot_pairs']}\n")

    print(f"Top {TOP_N} chains (core name, places, brand tags, same-spot pairs, name variants):")
    for i, r in enumerate(stats["top_chains"], 1):
        variants = "; ".join(f"{v['name']}×{v['count']}" for v in r["name_variants"])
        print(f"{i:>3}. {r['core_name']:<24} {r['places']:>3}  brand {r['with_brand_tag']:>2}  "
              f"close {r['same_spot_pairs_within_50m']:>2}  | {variants}")

    print(f"\nFor review in Phase 2: {s['review_rows_ambiguous']} ambiguous names, "
          f"{s['review_rows_spelling']} possible spelling variants")
    for kind, title in (("ambiguous_contains_chain_name", "Ambiguous (contains a chain's name)"),
                        ("possible_spelling_variant", "Possible spelling variants")):
        rows = [r for r in review if r["kind"] == kind]
        print(f"\n  {title}:")
        for chain in sorted({r["chain_core_name"] for r in rows}):
            names = Counter(r["name"] for r in rows if r["chain_core_name"] == chain)
            listed = "; ".join(f"{n}×{c}" if c > 1 else n for n, c in names.most_common())
            print(f"    [{chain}] {listed}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    places, meta = load_food_places()
    stats, review = detect(places, meta)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with OUT_REVIEW.open("w", newline="", encoding="utf-8-sig") as f:  # -sig so Excel shows Telugu correctly
        writer = csv.DictWriter(f, fieldnames=["kind", "chain_core_name", "name", "core_name", "amenity",
                                               "osm", "lat", "lon", "similarity"])
        writer.writeheader()
        writer.writerows(sorted(review, key=lambda r: (r["kind"], r["chain_core_name"], r["name"])))
    print_report(stats, review)
    print(f"\nSaved {OUT_JSON.relative_to(ROOT)} and {OUT_REVIEW.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
