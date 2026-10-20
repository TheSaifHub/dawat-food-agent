"""Phase 2, module 2b (analysis only): describe duplicate candidates and what each dedupe option would do.

NOTHING is removed here. This builds the evidence for Saif's choice of dedupe rule:
  - candidate pairs = two named food places with the same core name (detect_chains.py rules)
    within 50 m of each other
  - pairs are grouped into clusters (A~B and B~C → one cluster {A, B, C})
  - for each pair: distance, pin/outline, exact vs core-name match, amenity, tag richness
  - for each option: how many places it would remove, and which pairs it would leave alone

Outputs:
  results/cleaning/dedupe_candidates.csv    one row per pair (for review)
  results/cleaning/dedupe_options.json      every number shown to Saif

Run from the project root:
    .venv\\Scripts\\python data_pipeline\\dedupe_candidates.py
"""

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

from detect_chains import core_name, normalise
from geo import load_verified, metres

ROOT = Path(__file__).resolve().parent.parent
OUT_CSV = ROOT / "results" / "cleaning" / "dedupe_candidates.csv"
OUT_JSON = ROOT / "results" / "cleaning" / "dedupe_options.json"
FOOD_TYPES = {"restaurant", "fast_food", "cafe"}
RADIUS_M = 50
# Core names that describe a KIND of shop, not one business (docs/phase2_backlog.md). Two
# "Fast Food" places 3 m apart are likely two stalls, so these never merge automatically.
GENERIC_CORE_NAMES = {"fast food", "kabab", "kebab", "canteen", "tiffin center", "tiffin centre",
                      "irani", "udipi", "udupi", "bakery", "juice", "tea"}


def places() -> tuple[list[dict], dict]:
    data, meta = load_verified("overpass_hyderabad_")
    out = []
    for e in data["elements"]:
        t = e.get("tags", {})
        if t.get("amenity") not in FOOD_TYPES or not str(t.get("name", "")).strip():
            continue
        name = str(t["name"]).strip()
        out.append({
            "osm": f"{e['type']}/{e['id']}", "osm_type": e["type"], "name": name,
            "normalised": normalise(name), "core": core_name(normalise(name)),
            "amenity": t["amenity"], "tag_count": len(t),
            "lat": e.get("lat", e.get("center", {}).get("lat")), "lon": e.get("lon", e.get("center", {}).get("lon")),
        })
    return out, meta


def clusters(pairs: list[dict]) -> list[set[str]]:
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for p in pairs:
        parent[find(p["a"])] = find(p["b"])
    groups = defaultdict(set)
    for x in list(parent):
        groups[find(x)].add(x)
    return list(groups.values())


def removed_by(pairs: list[dict], rule) -> int:
    """Places removed if every pair matching `rule` is merged: sum over clusters of (size - 1)."""
    return sum(len(c) - 1 for c in clusters([p for p in pairs if rule(p)]))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ps, meta = places()
    by_core = defaultdict(list)
    for p in ps:
        by_core[p["core"]].append(p)

    pairs = []
    for core, group in by_core.items():
        for a, b in combinations(group, 2):
            d = metres((a["lat"], a["lon"]), (b["lat"], b["lon"]))
            if d <= RADIUS_M:
                richer = a if a["tag_count"] >= b["tag_count"] else b
                pairs.append({
                    "chain_core_name": core, "a": a["osm"], "b": b["osm"],
                    "name_a": a["name"], "name_b": b["name"], "distance_m": round(d, 1),
                    "types": "+".join(sorted((a["osm_type"], b["osm_type"]))),
                    "same_exact_name": a["normalised"] == b["normalised"],
                    "same_amenity": a["amenity"] == b["amenity"],
                    "amenities": f"{a['amenity']} / {b['amenity']}",
                    "tags_a": a["tag_count"], "tags_b": b["tag_count"], "richer": richer["osm"],
                    "generic_name": core in GENERIC_CORE_NAMES,
                })
    pairs.sort(key=lambda p: (p["distance_m"], p["chain_core_name"]))
    cl = clusters(pairs)

    # Every option: generic-name pairs are never auto-merged (they go to review), and a merge
    # keeps the record with more tags and logs the dropped one. Amenity is NOT a test: real
    # duplicates are often tagged differently (Istanbul Doner: fast_food vs restaurant).
    options = {
        "1_certain_only": {
            "rule": "auto-merge only if same exact name (case/punctuation ignored) AND ≤10 m; everything else → Saif reviews",
            "test": lambda p: not p["generic_name"] and p["same_exact_name"] and p["distance_m"] <= 10,
        },
        "2_close_means_same": {
            "rule": "auto-merge if same core name AND ≤15 m; 15–50 m → Saif reviews",
            "test": lambda p: not p["generic_name"] and p["distance_m"] <= 15,
        },
        "3_all_within_50m": {
            "rule": "auto-merge every same-core-name pair within 50 m; only generic names → Saif reviews",
            "test": lambda p: not p["generic_name"],
        },
    }
    option_results = {}
    for key_, o in options.items():
        hit = [p for p in pairs if o["test"](p)]
        option_results[key_] = {
            "rule": o["rule"],
            "pairs_matched": len(hit),
            "places_removed": removed_by(pairs, o["test"]),
            "pairs_left_for_review": len(pairs) - len(hit),
        }

    summary = {
        "snapshot": {"file": meta["file"], "sha256": meta["sha256"]},
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "candidates": {
            "named_food_places": len(ps),
            "pairs_within_50m": len(pairs),
            "clusters": len(cl),
            "cluster_sizes": sorted((len(c) for c in cl), reverse=True),
            "places_in_clusters": sum(len(c) for c in cl),
            "same_exact_name_pairs": sum(p["same_exact_name"] for p in pairs),
            "core_only_pairs": sum(not p["same_exact_name"] for p in pairs),
            "same_amenity_pairs": sum(p["same_amenity"] for p in pairs),
            "by_types": {t: sum(p["types"] == t for p in pairs) for t in ("node+node", "node+way", "way+way")},
            "generic_name_pairs": sum(p["generic_name"] for p in pairs),
            "within_10m": sum(p["distance_m"] <= 10 for p in pairs),
            "within_15m": sum(p["distance_m"] <= 15 for p in pairs),
            "exactly_0m": sum(p["distance_m"] == 0 for p in pairs),
        },
        "options": option_results,
    }

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = ["chain_core_name", "name_a", "name_b", "distance_m", "types", "same_exact_name", "same_amenity",
              "amenities", "tags_a", "tags_b", "richer", "a", "b"] + [f"option_{k}" for k in options]
    with OUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for p in pairs:
            w.writerow({**p, **{f"option_{k}": "merge" if o["test"](p) else "keep" for k, o in options.items()}})
    OUT_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps(summary["candidates"], indent=2))
    print(json.dumps(summary["options"], indent=2, ensure_ascii=False))
    print("\nAll pairs (distance, exact/core/GENERIC, decision under options 1/2/3, names):")
    for p in pairs:
        kind = "GENERIC" if p["generic_name"] else ("exact" if p["same_exact_name"] else "core")
        decisions = "/".join("M" if o["test"](p) else "r" for o in options.values())
        print(f"  {p['distance_m']:>5.1f} m  {kind:<7} {decisions}  {p['name_a']!r} ~ {p['name_b']!r}")
    print("  (M = auto-merge, r = Saif reviews)")
    print(f"\nSaved {OUT_CSV.relative_to(ROOT)} and {OUT_JSON.relative_to(ROOT)}. Nothing was removed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
