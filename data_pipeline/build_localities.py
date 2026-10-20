"""Phase 2, module 2a: build data/reference/localities.csv, the ONE locality level (D-008).

Inputs (raw snapshots are sha256-verified; reference files are hand-built and reviewed by Saif):
  data/raw/osm_places_7868535_*.json               suburb/neighbourhood points
  data/raw/osm_missing_area_check_7868535_*.json   any place=* tag for 7 names missing above
  data/raw/osm_relation_7868535_*.json             boundary outline (inside/outside test)
  data/raw/overpass_hyderabad_*.json               food places (nearest-area counts)
  data/reference/areas_hand_added.csv              areas OSM doesn't have as places (source = hand-added)
  data/reference/area_overrides.csv                display-name fixes and aliases

Steps:
  1. Well-known areas = place=suburb, or a neighbourhood with a wikidata/wikipedia link
     (unless its name has a small-place word). Small neighbourhoods are NOT used (D-008).
  2. Same-name areas are merged into one (the suburb point wins over a neighbourhood point).
  3. Add OSM places tagged city/town/suburb that were missed (e.g. Secunderabad is place=city)
     if they are inside the boundary and not already present.
  4. Add hand-added areas (checked to be inside the boundary).
  5. Display names: overrides first, else the OSM name (all-lower-case names get title case).
     Aliases: overrides + the Telugu name + a no-space form ("Dilsukh Nagar" → "Dilsukhnagar").
  6. Nearest-area food counts BEFORE (the 165 draft areas) and AFTER (the final list).

Outputs:
  data/reference/localities.csv
  results/cleaning/localities_summary.json   (every number shown to Saif)

Run from the project root:
    .venv\\Scripts\\python data_pipeline\\build_localities.py
"""

import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from geo import boundary_segments, load_verified, metres, point_in_boundary

ROOT = Path(__file__).resolve().parent.parent
REF_DIR = ROOT / "data" / "reference"
OUT_CSV = REF_DIR / "localities.csv"
OUT_JSON = ROOT / "results" / "cleaning" / "localities_summary.json"

FOOD_TYPES = {"restaurant", "fast_food", "cafe"}
SMALL_NAME_WORDS = {"colony", "enclave", "phase", "layout", "apartments", "society", "block", "residency", "township"}
ADDABLE_PLACE_TYPES = {"city", "town", "suburb"}  # from the missing-area check; "locality" is a landmark, not an area


def key(name: str) -> str:
    """Comparison key: letters only, lower case ('L.B. Nagar' == 'LB Nagar')."""
    return re.sub(r"[^a-z]", "", name.lower())


def pt(e: dict) -> tuple[float, float]:
    return e.get("lat", e.get("center", {}).get("lat")), e.get("lon", e.get("center", {}).get("lon"))


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


# ─── steps ─────────────────────────────────────────────────────────────
def well_known_areas(places: dict) -> list[dict]:
    areas = []
    for e in places["elements"]:
        t = e.get("tags", {})
        name = str(t.get("name", "")).strip()
        small_word = any(w in name.lower().split() for w in SMALL_NAME_WORDS)
        if t.get("place") == "suburb":
            reason = "OSM place=suburb"
        elif (t.get("wikidata") or t.get("wikipedia")) and not small_word:
            reason = "neighbourhood with a wikidata/wikipedia link"
        else:
            continue
        lat, lon = pt(e)
        areas.append({"osm_name": name, "name_te": t.get("name:te", ""), "lat": lat, "lon": lon,
                      "source": "osm", "source_ref": f"{e['type']}/{e['id']}", "osm_place": t["place"],
                      "reason": reason})
    return areas


def merge_same_names(areas: list[dict]) -> tuple[list[dict], list[dict]]:
    kept: dict[str, dict] = {}
    dropped = []
    for a in sorted(areas, key=lambda a: a["osm_place"] != "suburb"):  # suburbs first, so they win
        k = key(a["osm_name"])
        if k in kept:
            dropped.append({**a, "merged_into": kept[k]["source_ref"],
                            "distance_m": round(metres((a["lat"], a["lon"]), (kept[k]["lat"], kept[k]["lon"])))})
        else:
            kept[k] = a
    return list(kept.values()), dropped


def add_missing(areas, check, segments, hand_rows):
    present = {key(a["osm_name"]) for a in areas}
    added, skipped = [], []
    for e in check["elements"]:
        t = e.get("tags", {})
        name, lat, lon = t.get("name", ""), *pt(e)
        record = {"name": name, "osm_place": t.get("place"), "source_ref": f"{e['type']}/{e['id']}"}
        if not point_in_boundary(lat, lon, segments):
            skipped.append({**record, "why": "outside relation 7868535"})
        elif t.get("place") not in ADDABLE_PLACE_TYPES:
            skipped.append({**record, "why": f"place={t.get('place')} is not an area-level tag (city/town/suburb)"})
        elif key(name) in present:
            skipped.append({**record, "why": "already in the list"})
        else:
            areas.append({"osm_name": name, "name_te": t.get("name:te", ""), "lat": lat, "lon": lon,
                          "source": "osm", "source_ref": record["source_ref"], "osm_place": t.get("place"),
                          "reason": f"missing-area check: OSM place={t.get('place')}"})
            present.add(key(name))
            added.append(record)
    for h in hand_rows:
        lat, lon = float(h["lat"]), float(h["lon"])
        if key(h["name"]) in present:
            skipped.append({"name": h["name"], "source_ref": "hand-added", "why": "already in the list"})
            continue
        if not point_in_boundary(lat, lon, segments):
            skipped.append({"name": h["name"], "source_ref": "hand-added", "why": "outside relation 7868535"})
            continue
        areas.append({"osm_name": h["name"], "name_te": "", "lat": lat, "lon": lon, "source": "hand-added",
                      "source_ref": h["coord_source"], "osm_place": "", "reason": h["note"]})
        present.add(key(h["name"]))
        added.append({"name": h["name"], "osm_place": "", "source_ref": "hand-added"})
    return added, skipped


def name_and_aliases(areas: list[dict], overrides: list[dict]) -> None:
    by_name = {o["osm_name"]: o for o in overrides}
    for a in areas:
        o = by_name.get(a["osm_name"])
        osm = a["osm_name"]
        display = o["display_name"] if o else (osm.title() if osm == osm.lower() else osm)
        aliases = [s.strip() for s in (o["aliases"].split(";") if o and o["aliases"] else []) if s.strip()]
        if " " in display or "-" in display:
            aliases.append(re.sub(r"[\s\-]+", "", display).capitalize())  # "Dilsukh Nagar" → "Dilsukhnagar"
        if osm != display:
            aliases.append(osm)
        if a["name_te"]:
            aliases.append(a["name_te"])
        # Drop only exact repeats (case-insensitive). Spacing/punctuation variants such as
        # "Dilsukhnagar", "L.B. Nagar" and "Hi-Tech City" are kept: they help fuzzy matching later.
        seen, unique = {display.casefold()}, []
        for al in aliases:
            k = al.casefold()
            if k not in seen:
                seen.add(k)
                unique.append(al)
        a["display_name"], a["aliases"] = display, unique
        a["area_id"] = slug(display)


def nearest_counts(areas, food_pts, id_key) -> tuple[Counter, list[float]]:
    counts, dists = Counter(), []
    for p in food_pts:
        best = min(areas, key=lambda a: metres(p, (a["lat"], a["lon"])))
        counts[best[id_key]] += 1
        dists.append(metres(p, (best["lat"], best["lon"])))
    return counts, sorted(dists)


def distance_stats(d: list[float]) -> dict:
    return {"median_m": round(d[len(d) // 2]), "p90_m": round(d[int(len(d) * 0.9)]), "max_m": round(d[-1]),
            "within_2km_pct": round(100 * sum(x <= 2000 for x in d) / len(d), 1)}


# ─── main ──────────────────────────────────────────────────────────────
def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    places, pmeta = load_verified("osm_places_7868535_")
    check, cmeta = load_verified("osm_missing_area_check_7868535_")
    boundary, _ = load_verified("osm_relation_7868535_")
    food, fmeta = load_verified("overpass_hyderabad_")
    segments = boundary_segments(boundary)
    food_pts = [pt(e) for e in food["elements"] if e.get("tags", {}).get("amenity") in FOOD_TYPES]

    draft = well_known_areas(places)
    for a in draft:
        a["draft_id"] = a["source_ref"]
    before_counts, before_d = nearest_counts(draft, food_pts, "draft_id")

    areas, merged = merge_same_names([dict(a) for a in draft])
    added, skipped = add_missing(areas, check, segments, read_csv(REF_DIR / "areas_hand_added.csv"))
    name_and_aliases(areas, read_csv(REF_DIR / "area_overrides.csv"))
    if len({a["area_id"] for a in areas}) != len(areas):
        sys.exit("Duplicate area_id after naming; fix area_overrides.csv.")
    after_counts, after_d = nearest_counts(areas, food_pts, "area_id")

    # Before/after per name: before is summed over draft points with the same name (Musheerabad had 2).
    before_by_key = Counter()
    for a in draft:
        before_by_key[key(a["osm_name"])] += before_counts.get(a["draft_id"], 0)
    for a in areas:
        a["food_places_nearest"] = after_counts.get(a["area_id"], 0)
        a["food_places_nearest_before"] = before_by_key.get(key(a["osm_name"]), 0) if a["source"] == "osm" and a["reason"].startswith(("OSM", "neighbourhood")) else ""

    # Sanity context for hand-added/new areas: the two nearest OSM areas.
    osm_areas = [a for a in areas if a["source"] == "osm"]
    new_areas = [a for a in areas if a["source"] == "hand-added" or a["reason"].startswith("missing-area")]
    neighbours = {
        a["display_name"]: [{"area": b["display_name"], "m": round(metres((a["lat"], a["lon"]), (b["lat"], b["lon"])))}
                            for b in sorted((b for b in osm_areas if b is not a),
                                            key=lambda b: metres((a["lat"], a["lon"]), (b["lat"], b["lon"])))[:2]]
        for a in new_areas
    }

    areas.sort(key=lambda a: a["display_name"].lower())
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = ["area_id", "display_name", "aliases", "name_te", "lat", "lon", "source", "source_ref",
              "osm_name", "osm_place", "reason", "food_places_nearest"]
    with OUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for a in areas:
            w.writerow({**a, "aliases": ";".join(a["aliases"])})

    summary = {
        "inputs": {"places": pmeta["file"], "missing_area_check": cmeta["file"], "food": fmeta["file"],
                   "hand_added": "data/reference/areas_hand_added.csv", "overrides": "data/reference/area_overrides.csv"},
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counts": {
            "draft_areas": len(draft),
            "merged_same_name": len(merged),
            "added_from_osm_check": sum(1 for x in added if x["source_ref"] != "hand-added"),
            "added_hand": sum(1 for x in added if x["source_ref"] == "hand-added"),
            "final_areas": len(areas),
            "final_by_source": dict(Counter(a["source"] for a in areas)),
            "areas_with_zero_food_places": sum(1 for a in areas if a["food_places_nearest"] == 0),
            "areas_with_aliases": sum(1 for a in areas if a["aliases"]),
        },
        "merged": [{"name": m["osm_name"], "dropped": m["source_ref"], "kept": m["merged_into"], "distance_m": m["distance_m"]} for m in merged],
        "added": added,
        "skipped": skipped,
        "new_area_neighbours": neighbours,
        "distance_food_to_nearest_area": {"before": distance_stats(before_d), "after": distance_stats(after_d)},
        "before_after": {
            a["display_name"]: {"before": a["food_places_nearest_before"] if a["food_places_nearest_before"] != "" else None,
                                "after": a["food_places_nearest"]}
            for a in areas
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("counts", "merged", "added", "skipped", "new_area_neighbours",
                                                 "distance_food_to_nearest_area")}, indent=2, ensure_ascii=False))
    print(f"\nSaved {OUT_CSV.relative_to(ROOT)} ({len(areas)} areas) and {OUT_JSON.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
