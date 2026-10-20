"""Phase 2, module 2b: removals. Rerunnable from the raw snapshot; never modifies data/raw/.

Steps (each count and every dropped OSM id is logged):
  1. keep only food places (amenity restaurant / fast_food / cafe). Drops the internet cafés
     the old unanchored query let in (D-007).
  2. drop places without a name (they can't be shown to users).
  3. auto-merge duplicates (D-010): same core name (detect_chains.py rules) within 15 m, unless the
     core name is generic ("Fast Food", "Kabab", …).
  4. apply Saif's reviewed decisions from data/reference/dedupe_review.csv (merge / keep_both).
  Merging: pairs are grouped into clusters (A~B, B~C → {A, B, C}); the record with the most tags
  is kept (ties: a pin over an outline, then the lower OSM id) and the others are dropped.

Post-checks (the run FAILS if any is violated):
  - no remaining pair matches the auto-merge rule
  - no pair Saif marked "merge" survives, and no pair he marked "keep_both" was merged away

Outputs:
  data/processed/places_clean.csv     one row per kept place (tags kept as JSON)
  results/cleaning/clean_log.json     before/after counts and every removal with its reason

Run from the project root:
    .venv\\Scripts\\python data_pipeline\\clean.py
"""

import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

from dedupe_candidates import GENERIC_CORE_NAMES, clusters
from detect_chains import core_name, normalise
from geo import load_verified, metres

ROOT = Path(__file__).resolve().parent.parent
REVIEW = ROOT / "data" / "reference" / "dedupe_review.csv"
OUT_CSV = ROOT / "data" / "processed" / "places_clean.csv"
OUT_LOG = ROOT / "results" / "cleaning" / "clean_log.json"

FOOD_TYPES = {"restaurant", "fast_food", "cafe"}
AUTO_MERGE_M = 15  # D-010


def to_place(e: dict) -> dict:
    t = e.get("tags", {})
    name = str(t.get("name", "")).strip()
    return {"osm": f"{e['type']}/{e['id']}", "osm_type": e["type"], "osm_id": e["id"], "name": name,
            "core": core_name(normalise(name)) if name else "", "amenity": t.get("amenity"),
            "lat": e.get("lat", e.get("center", {}).get("lat")), "lon": e.get("lon", e.get("center", {}).get("lon")),
            "tags": t}


def auto_merge_pairs(places: list[dict]) -> list[dict]:
    by_core = defaultdict(list)
    for p in places:
        by_core[p["core"]].append(p)
    pairs = []
    for core, group in by_core.items():
        if core in GENERIC_CORE_NAMES:
            continue
        for a, b in combinations(group, 2):
            d = metres((a["lat"], a["lon"]), (b["lat"], b["lon"]))
            if d <= AUTO_MERGE_M:
                pairs.append({"a": a["osm"], "b": b["osm"], "distance_m": round(d, 1), "why": f"auto: same core name '{core}' ≤{AUTO_MERGE_M} m"})
    return pairs


def read_review() -> list[dict]:
    with REVIEW.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    undecided = [r["pair"] for r in rows if r.get("saif_decision") not in ("merge", "keep_both")]
    if undecided:
        sys.exit(f"dedupe_review.csv has rows without a valid saif_decision: {undecided}. Nothing written.")
    return rows


def keep_order(p: dict) -> tuple:
    """Best record first: most tags, then a pin (exact point) over an outline centre, then lower id."""
    return (-len(p["tags"]), p["osm_type"] != "node", p["osm_id"])


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    raw, meta = load_verified("overpass_hyderabad_")
    all_places = [to_place(e) for e in raw["elements"]]
    removed: list[dict] = []
    steps = [{"step": "raw snapshot", "places": len(all_places),
              "by_amenity": dict(Counter(p["amenity"] for p in all_places).most_common())}]

    # 1. food places only
    food = [p for p in all_places if p["amenity"] in FOOD_TYPES]
    removed += [{"osm": p["osm"], "name": p["name"], "reason": f"not a food place (amenity={p['amenity']})"}
                for p in all_places if p["amenity"] not in FOOD_TYPES]
    steps.append({"step": "1. keep food places only", "removed": len(all_places) - len(food), "places": len(food)})

    # 2. named only
    named = [p for p in food if p["name"]]
    removed += [{"osm": p["osm"], "name": "", "reason": "no name"} for p in food if not p["name"]]
    steps.append({"step": "2. drop unnamed places", "removed": len(food) - len(named), "places": len(named)})

    # 3 + 4. merges (auto rule + Saif's review), resolved together so overlapping clusters stay consistent
    by_osm = {p["osm"]: p for p in named}
    auto = auto_merge_pairs(named)
    review = read_review()
    missing = [r["pair"] for r in review if r["osm_a"] not in by_osm or r["osm_b"] not in by_osm]
    if missing:
        sys.exit(f"Review pairs refer to places not in the cleaned set: {missing}. Nothing written.")
    reviewed_merges = [{"a": r["osm_a"], "b": r["osm_b"], "distance_m": float(r["distance_m"]),
                        "why": f"Saif review pair {r['pair']}: merge"} for r in review if r["saif_decision"] == "merge"]

    def apply(pairs: list[dict], survivors: list[dict], label: str) -> list[dict]:
        alive = {p["osm"] for p in survivors}
        drop: dict[str, dict] = {}
        for cluster in clusters([p for p in pairs if p["a"] in alive and p["b"] in alive]):
            members = sorted((by_osm[o] for o in cluster), key=keep_order)
            keeper = members[0]
            for m in members[1:]:
                drop[m["osm"]] = {"osm": m["osm"], "name": m["name"], "reason": label, "merged_into": keeper["osm"],
                                  "merged_into_name": keeper["name"]}
        removed.extend(drop.values())
        return [p for p in survivors if p["osm"] not in drop]

    after_auto = apply(auto, named, f"duplicate: auto-merge (D-010, same core name ≤{AUTO_MERGE_M} m)")
    steps.append({"step": f"3. auto-merge duplicates (≤{AUTO_MERGE_M} m, D-010)", "pairs": len(auto),
                  "removed": len(named) - len(after_auto), "places": len(after_auto)})
    final = apply(reviewed_merges, after_auto, "duplicate: merged after Saif's review (data/reference/dedupe_review.csv)")
    steps.append({"step": "4. reviewed merges (Saif)", "pairs_marked_merge": len(reviewed_merges),
                  "pairs_marked_keep_both": sum(r["saif_decision"] == "keep_both" for r in review),
                  "removed": len(after_auto) - len(final), "places": len(final)})

    # Post-checks: these must be able to fail.
    # "Where did this record end up?" = itself if kept, else follow merged_into. A keep_both pair
    # means "don't merge these two TOGETHER"; one side may still be merged into a third record
    # (Bawarchi: #20 merges the two phone-numbered records, #19 keeps the bare one separate).
    merged_into = {r["osm"]: r["merged_into"] for r in removed if "merged_into" in r}

    def ends_up(osm: str) -> str:
        while osm in merged_into:
            osm = merged_into[osm]
        return osm

    leftover_auto = auto_merge_pairs(final)
    surviving_merges = [r["pair"] for r in review if r["saif_decision"] == "merge" and ends_up(r["osm_a"]) != ends_up(r["osm_b"])]
    broken_keeps = [r["pair"] for r in review if r["saif_decision"] == "keep_both" and ends_up(r["osm_a"]) == ends_up(r["osm_b"])]
    problems = {"pairs_still_matching_auto_rule": len(leftover_auto), "merge_pairs_not_merged": surviving_merges,
                "keep_both_pairs_merged": broken_keeps}
    if leftover_auto or surviving_merges or broken_keeps:
        print(json.dumps(problems, indent=2))
        sys.exit("Post-checks FAILED. Nothing written.")

    final.sort(key=lambda p: (p["name"].lower(), p["osm"]))
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["osm", "name", "amenity", "lat", "lon", "tags_json"])
        w.writeheader()
        for p in final:
            w.writerow({"osm": p["osm"], "name": p["name"], "amenity": p["amenity"], "lat": p["lat"], "lon": p["lon"],
                        "tags_json": json.dumps(p["tags"], ensure_ascii=False, sort_keys=True)})

    log = {
        "snapshot": {"file": meta["file"], "sha256": meta["sha256"]},
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rules": {"food_types": sorted(FOOD_TYPES), "auto_merge_m": AUTO_MERGE_M,
                  "generic_core_names_never_auto_merged": sorted(GENERIC_CORE_NAMES),
                  "keep_rule": "most tags, then pin over outline, then lower OSM id",
                  "decisions": ["D-007", "D-010"]},
        "steps": steps,
        "before_after": {
            "before": {"places": len(all_places), "by_amenity": dict(Counter(p["amenity"] for p in all_places).most_common())},
            "after": {"places": len(final), "by_amenity": dict(Counter(p["amenity"] for p in final).most_common()),
                      "by_osm_type": dict(Counter(p["osm_type"] for p in final).most_common())},
        },
        "removed_by_reason": dict(Counter(
            "not a food place" if r["reason"].startswith("not a food") else r["reason"] for r in removed).most_common()),
        "post_checks": {**problems, "passed": True},
        "removed": removed,
    }
    OUT_LOG.parent.mkdir(parents=True, exist_ok=True)
    OUT_LOG.write_text(json.dumps(log, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("Before → after")
    for s in steps:
        extra = "" if "removed" not in s else f"  (−{s['removed']})"
        print(f"  {s['step']:<48} {s['places']:>5}{extra}")
    print(f"\nBy amenity: before {log['before_after']['before']['by_amenity']}")
    print(f"            after  {log['before_after']['after']['by_amenity']}")
    print(f"Post-checks passed: 0 pairs still match the auto rule; all {len(reviewed_merges)} reviewed merges applied; "
          f"all {steps[-1]['pairs_marked_keep_both']} keep_both pairs intact.")
    print(f"\nSaved {OUT_CSV.relative_to(ROOT)} and {OUT_LOG.relative_to(ROOT)}. data/raw/ untouched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
