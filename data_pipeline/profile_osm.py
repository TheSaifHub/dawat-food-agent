"""Phase 1, module 2: profile the raw OpenStreetMap snapshot (read-only).

Load → verify → profile → save numbers. No charts here (module 4) and no cleaning
(Phase 2): this only describes what OSM gave us.

What it measures (CLAUDE.md, Phase 1):
  - places by type (food places vs the 15 internet cafés the old query let in, D-007)
  - how many have a name, a cuisine tag, address tags, area-like tags
  - cuisine distribution (OSM cuisine values can be lists: "indian;biryani")
  - places per area, where an area tag exists
  - coordinate sanity against the boundary's bounding box (D-005)
  - a quick name preview for a few well-known chains (full chain detection is module 3)

Every number printed is also written to results/eda/stats.json, which later docs cite.

Run from the project root:
    .venv\\Scripts\\python data_pipeline\\profile_osm.py
"""

import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT_PATH = ROOT / "results" / "eda" / "stats.json"

FOOD_TYPES = ["restaurant", "fast_food", "cafe"]
# Bounding box of OSM relation 7868535 (DECISIONS.md D-005).
BBOX = {"min_lat": 17.292, "max_lat": 17.561, "min_lon": 78.239, "max_lon": 78.622}
AREA_KEYS = ["addr:suburb", "addr:neighbourhood", "addr:district", "addr:quarter", "addr:place"]
CHAIN_PREVIEW = {  # case-insensitive patterns over the `name` tag only
    "Mehfil": r"mehfil",
    "Paradise": r"paradise",
    "Pista House": r"pista\s*house",
    "Shah Ghouse": r"shah\s*gh?ouse",
}
TOP_N = 15


# ─── load ──────────────────────────────────────────────────────────────
def load_snapshot() -> tuple[list[dict], dict]:
    snapshots = sorted(p for p in RAW_DIR.glob("overpass_hyderabad_*.json") if not p.name.endswith(".meta.json"))
    if len(snapshots) != 1:
        sys.exit(f"Expected exactly one raw snapshot in data/raw/, found {len(snapshots)}.")
    data_path = snapshots[0]
    meta = json.loads(data_path.with_name(data_path.stem + ".meta.json").read_bytes())
    raw_bytes = data_path.read_bytes()
    if hashlib.sha256(raw_bytes).hexdigest() != meta["sha256"]:
        sys.exit(f"{data_path.name} does not match the sha256 in its .meta.json. Refusing to profile.")
    return json.loads(raw_bytes)["elements"], meta


def to_frame(elements: list[dict]) -> pd.DataFrame:
    rows = []
    for e in elements:
        tags = e.get("tags", {})
        rows.append({
            "osm_type": e["type"],
            "osm_id": e["id"],
            "lat": e.get("lat", e.get("center", {}).get("lat")),
            "lon": e.get("lon", e.get("center", {}).get("lon")),
            "amenity": tags.get("amenity"),
            "tags": tags,
        })
    return pd.DataFrame(rows)


# ─── helpers ───────────────────────────────────────────────────────────
def has(df: pd.DataFrame, key: str) -> pd.Series:
    return df["tags"].map(lambda t: bool(str(t.get(key, "")).strip()))


def coverage(mask: pd.Series) -> dict:
    count = int(mask.sum())
    return {"count": count, "pct": round(100 * count / len(mask), 1)}


def norm(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


# ─── profile ───────────────────────────────────────────────────────────
def profile(df_all: pd.DataFrame, meta: dict) -> dict:
    food = df_all[df_all["amenity"].isin(FOOD_TYPES)].reset_index(drop=True)
    n = len(food)

    any_addr = food["tags"].map(lambda t: any(k.startswith("addr:") for k in t))
    any_area = food["tags"].map(lambda t: any(str(t.get(k, "")).strip() for k in AREA_KEYS))

    # Cuisine: split "indian;biryani" into separate values.
    cuisine_lists = food["tags"].map(lambda t: [norm(c) for c in str(t.get("cuisine", "")).split(";") if c.strip()])
    cuisine_counts = Counter(c for cl in cuisine_lists for c in cl)

    suburb_counts = Counter(norm(t["addr:suburb"]) for t in food["tags"] if str(t.get("addr:suburb", "")).strip())

    in_bbox = food["lat"].between(BBOX["min_lat"], BBOX["max_lat"]) & food["lon"].between(BBOX["min_lon"], BBOX["max_lon"])

    names = food["tags"].map(lambda t: str(t.get("name", "")).strip())
    preview = {}
    for label, pattern in CHAIN_PREVIEW.items():
        mask = names.str.contains(pattern, case=False, regex=True)
        variants = Counter(names[mask])
        preview[label] = {
            "places": int(mask.sum()),
            "with_brand_tag": int(has(food[mask], "brand").sum()) if mask.any() else 0,
            "name_variants": [{"name": k, "count": v} for k, v in variants.most_common()],
        }

    return {
        "snapshot": {
            "file": meta["file"],
            "sha256": meta["sha256"],
            "osm_data_timestamp": meta["osm_data_timestamp"],
            "query": meta["query"],
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "population": {
            "all_elements": len(df_all),
            "by_amenity_all": dict(Counter(df_all["amenity"].fillna("(none)")).most_common()),
            "food_places": n,
            "excluded_non_food": int(len(df_all) - n),
            "food_by_amenity": {a: int((food["amenity"] == a).sum()) for a in FOOD_TYPES},
            "food_by_osm_type": dict(Counter(food["osm_type"]).most_common()),
        },
        "coverage_of_food_places": {
            "name": coverage(has(food, "name")),
            "cuisine": coverage(has(food, "cuisine")),
            "any_addr_tag": coverage(any_addr),
            "addr:street": coverage(has(food, "addr:street")),
            "addr:postcode": coverage(has(food, "addr:postcode")),
            "addr:city": coverage(has(food, "addr:city")),
            "addr:suburb": coverage(has(food, "addr:suburb")),
            "any_area_tag": coverage(any_area),
            **{k: coverage(has(food, k)) for k in AREA_KEYS if k != "addr:suburb"},
            "brand": coverage(has(food, "brand")),
            "name:en": coverage(has(food, "name:en")),
            "name:te": coverage(has(food, "name:te")),
            "opening_hours": coverage(has(food, "opening_hours")),
        },
        "cuisine": {
            "places_with_multiple_values": int((cuisine_lists.map(len) > 1).sum()),
            "distinct_values": len(cuisine_counts),
            "top": [{"cuisine": k, "places": v} for k, v in cuisine_counts.most_common(TOP_N)],
        },
        "address_values": {
            "addr_district_values": dict(Counter(
                str(t["addr:district"]).strip() for t in food["tags"] if str(t.get("addr:district", "")).strip()
            ).most_common()),
            "addr_city_distinct_spellings": len({str(t["addr:city"]).strip() for t in food["tags"]
                                                 if str(t.get("addr:city", "")).strip()}),
            "addr_city_values": dict(Counter(
                str(t["addr:city"]).strip() for t in food["tags"] if str(t.get("addr:city", "")).strip()
            ).most_common()),
            "addr_postcode_distinct": len({str(t["addr:postcode"]).strip() for t in food["tags"]
                                           if str(t.get("addr:postcode", "")).strip()}),
            # "500 003" and "500003" are the same PIN; Indian PINs are exactly 6 digits.
            "addr_postcode_distinct_spaces_removed": len({re.sub(r"\s+", "", str(t["addr:postcode"]))
                                                          for t in food["tags"]
                                                          if str(t.get("addr:postcode", "")).strip()}),
            "addr_postcode_valid_6_digit_distinct": len({re.sub(r"\s+", "", str(t["addr:postcode"]))
                                                         for t in food["tags"]
                                                         if re.fullmatch(r"\d{6}", re.sub(r"\s+", "", str(t.get("addr:postcode", ""))))}),
        },
        "areas_from_addr_suburb": {
            "places_with_suburb": sum(suburb_counts.values()),
            "distinct_suburbs": len(suburb_counts),
            "top": [{"suburb": k, "places": v} for k, v in suburb_counts.most_common(TOP_N)],
        },
        "coordinates": {
            "missing": int(food["lat"].isna().sum() + food["lon"].isna().sum()),
            "inside_boundary_bbox": coverage(in_bbox),
        },
        "chain_name_preview": preview,
    }


# ─── report ────────────────────────────────────────────────────────────
def print_report(s: dict) -> None:
    p, c = s["population"], s["coverage_of_food_places"]
    print(f"Snapshot {s['snapshot']['file']} (OSM data as of {s['snapshot']['osm_data_timestamp']}), sha256 verified\n")
    print(f"All elements: {p['all_elements']}  →  food places: {p['food_places']}  (set aside: {p['excluded_non_food']} non-food)")
    print("  by amenity:", ", ".join(f"{k} {v}" for k, v in p["food_by_amenity"].items()))
    print("  by OSM type:", ", ".join(f"{k} {v}" for k, v in p["food_by_osm_type"].items()))

    print("\nTag coverage (share of food places that have the tag):")
    for key, v in c.items():
        print(f"  {key:<20} {v['count']:>5}  {v['pct']:>5.1f}%")

    cu = s["cuisine"]
    print(f"\nCuisine: {cu['distinct_values']} distinct values; {cu['places_with_multiple_values']} places list more than one")
    for row in cu["top"]:
        print(f"  {row['cuisine']:<22} {row['places']:>4}")

    ar = s["areas_from_addr_suburb"]
    print(f"\nAreas (addr:suburb): {ar['places_with_suburb']} places tagged, {ar['distinct_suburbs']} distinct suburbs")
    for row in ar["top"]:
        print(f"  {row['suburb']:<26} {row['places']:>4}")

    co = s["coordinates"]
    print(f"\nCoordinates: missing {co['missing']}; inside the boundary's bounding box "
          f"{co['inside_boundary_bbox']['count']} ({co['inside_boundary_bbox']['pct']}%)")

    print("\nChain name preview (name tag, case-insensitive):")
    for label, v in s["chain_name_preview"].items():
        print(f"  {label}: {v['places']} place(s), {v['with_brand_tag']} with a brand tag")
        for var in v["name_variants"]:
            print(f"      {var['count']:>3} × {var['name']}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    elements, meta = load_snapshot()
    stats = profile(to_frame(elements), meta)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print_report(stats)
    print(f"\nAll numbers saved to {OUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
