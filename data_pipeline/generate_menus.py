"""Phase 3, module 3b: build one synthetic menu per restaurant from the reviewed 3a templates (D-016 to D-018).

Deterministic: a fixed global seed plus the restaurant id seed every random choice, so a rerun gives
byte-identical output. No network, no LLM. Chains share one menu across all their branches.

Per restaurant:
  1. price level t in [0, 1] (0 = the dish's price_low, 1 = its price_high), D-018:
       chains                         → a seeded value in the mid-to-upper band 0.55–0.75
       budget words in the name       → 0.00–0.30   (point, centre, tiffins, mess, dhaba, bandi, stall, canteen…)
       premium words in the name      → 0.70–1.00   (grand, palace, lounge, bistro, fine dining…)
       otherwise, by amenity          → fast_food 0.05–0.45, cafe 0.25–0.75, restaurant 0.20–0.70
  2. dishes: the primary cuisine's core, up to 3 core dishes from each secondary cuisine, dishes the
     restaurant's name promises (name_hints), then seeded optional dishes (primary first) until the
     menu reaches its size (chains: the template's maximum size). Veg-only restaurants: veg dishes only.
  3. price per dish: price_low + (price_high − price_low) × (t ± 0.05), rounded to ₹10 (₹5 under ₹50),
     kept inside the dish's range. A "(Full)" dish is kept above its half-plate version.

Outputs:
  data/processed/menus.json          every menu item with all CLAUDE.md fields (compact JSON)
  results/menus/generate_log.json    counts, price summaries by restaurant type, input/output hashes

Run from the project root:
    .venv\\Scripts\\python data_pipeline\\generate_menus.py
"""

import csv
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
CATALOGUE = REF / "dish_catalogue.csv"
TEMPLATES = REF / "menu_templates.json"
RESTAURANTS = ROOT / "data" / "processed" / "restaurants.csv"
BRANCHES = ROOT / "data" / "processed" / "branches.csv"
OUT = ROOT / "data" / "processed" / "menus.json"
OUT_LOG = ROOT / "results" / "menus" / "generate_log.json"

GLOBAL_SEED = 2026
GENERATOR_VERSION = "3b-1"
CHAIN_BAND = (0.55, 0.75)
BUDGET_BAND, PREMIUM_BAND = (0.00, 0.30), (0.70, 1.00)
AMENITY_BAND = {"fast_food": (0.05, 0.45), "cafe": (0.25, 0.75), "restaurant": (0.20, 0.70)}
BUDGET_WORDS = re.compile(r"\b(point|centre|center|tiffins?|tiffen|mess|dhaba|dabha|daba|bandi|stall|canteen|corner|"
                          r"annapurna|chai|tea stall|fast food|chat|chaat)\b")
PREMIUM_WORDS = re.compile(r"\b(grand(?! ?ma\b)|palace|lounge|bistro|fine dine|fine dining|brasserie|resto bar|kitchen and bar|"
                           r"bar and kitchen|rooftop|terrace|luxe|boutique)\b")
JITTER = 0.05
SECONDARY_CORE_PICKS = 3
MAX_OVER_SIZE = 6  # core + name hints may push a menu past the template size, but only this far
# serves-2 dishes and the serves-1 dish they are the bigger portion of (kept more expensive)
FULL_OF = {"chicken-dum-biryani-full": "chicken-dum-biryani", "mutton-dum-biryani-full": "mutton-dum-biryani",
           "chicken-mandi-full": "chicken-mandi", "mutton-mandi-full": "mutton-mandi",
           "tandoori-chicken-full": "tandoori-chicken-half", "fried-chicken-bucket": "fried-chicken-2pc"}
CATEGORY_ORDER = ["biryani", "mandi", "meals", "tiffin", "starter", "kebab", "curry", "bread", "rice", "noodles", "soup",
                  "salad", "pizza", "pasta", "burger", "sandwich", "roll", "shawarma", "fried_chicken", "mexican",
                  "continental", "breakfast", "snack", "bakery", "dessert", "drink"]


def read_csv(p: Path) -> list[dict]:
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def price_band(r: dict, amenity: str) -> tuple[str, tuple[float, float]]:
    if r["is_chain"] == "True":
        return "chain", CHAIN_BAND
    name = re.sub(r"[^\w\s]", " ", r["name"].lower())
    if BUDGET_WORDS.search(name):
        return "budget (name)", BUDGET_BAND
    if PREMIUM_WORDS.search(name):
        return "premium (name)", PREMIUM_BAND
    return f"standard ({amenity})", AMENITY_BAND[amenity]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    dishes = {d["dish_id"]: d for d in read_csv(CATALOGUE)}
    tj = json.loads(TEMPLATES.read_text(encoding="utf-8"))
    templates, hints = tj["templates"], [(re.compile(rf"\b({p})\b"), ids) for p, ids in tj["name_hints"].items()]
    restaurants = read_csv(RESTAURANTS)
    amenities = defaultdict(Counter)
    for b in read_csv(BRANCHES):
        amenities[b["restaurant_id"]][b["amenity"]] += 1

    menus, log_rows = {}, []
    for r in restaurants:
        rid = r["restaurant_id"]
        rng = random.Random(GLOBAL_SEED ^ int(hashlib.sha256(rid.encode()).hexdigest()[:16], 16))
        amenity = sorted(amenities[rid].items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        band_name, band = price_band(r, amenity)
        t = round(rng.uniform(*band), 3)
        cuisines = [c for c in r["cuisines"].split(";") if c in templates]
        if not cuisines:
            sys.exit(f"{rid}: none of its cuisines {r['cuisines']} has a template. Nothing written.")
        veg_only = r["veg_only"] == "True"
        allowed = (lambda i: dishes[i]["is_veg"] == "true") if veg_only else (lambda i: True)
        primary = templates[cuisines[0]]
        size = primary["size"][1] if r["is_chain"] == "True" else rng.randint(*primary["size"])

        chosen: list[str] = []

        def add(ids):
            for i in ids:
                if i not in chosen and allowed(i):
                    chosen.append(i)

        add(primary["core"])
        for c in cuisines[1:]:
            core = templates[c]["core"]
            add(rng.sample(core, min(SECONDARY_CORE_PICKS, len(core))))
        name = re.sub(r"[^\w\s]", " ", r["name"].lower())
        for pattern, ids in hints:
            if pattern.search(name):
                add(ids)
        chosen = chosen[:size + MAX_OVER_SIZE]
        pools = []
        for c in cuisines:
            pool = [i for i in templates[c]["optional"] if allowed(i)]
            rng.shuffle(pool)
            pools += pool
        for i in pools:
            if len(chosen) >= size:
                break
            add([i])

        items = {}
        for i in chosen:
            d = dishes[i]
            lo, hi = int(d["price_low"]), int(d["price_high"])
            raw = lo + (hi - lo) * min(1.0, max(0.0, t + rng.uniform(-JITTER, JITTER)))
            step = 10 if raw >= 50 else 5
            items[i] = min(hi, max(lo, int(round(raw / step) * step)))
        for full, half in FULL_OF.items():
            if full in items and half in items and items[full] <= items[half]:
                items[full] = min(int(dishes[full]["price_high"]), items[half] + 10 * round(items[half] * 0.7 / 10))

        menu = []
        for i in sorted(chosen, key=lambda i: (CATEGORY_ORDER.index(dishes[i]["category"]), items[i], i)):
            d = dishes[i]
            menu.append({"item_id": f"{rid}__{i}", "dish_id": i, "name": d["name"], "price": items[i],
                         "is_veg": d["is_veg"] == "true", "spice_level": int(d["spice_level"]), "serves": int(d["serves"]),
                         "category": d["category"], "course": d["course"],
                         "aliases": [a.strip() for a in d["aliases"].split(";") if a.strip()]})
        menus[rid] = {"restaurant_id": rid, "name": r["name"], "is_chain": r["is_chain"] == "True",
                      "cuisines": cuisines, "veg_only": veg_only, "price_band": band_name, "price_level": t,
                      "meal_capable": primary["meal_capable"], "items": menu}
        log_rows.append({"rid": rid, "band": band_name.split(" (")[0], "amenity": amenity, "chain": r["is_chain"] == "True",
                         "items": menu})

    out = {"meta": {"generator_version": GENERATOR_VERSION, "global_seed": GLOBAL_SEED,
                    "inputs_sha256": {p.name: sha(p) for p in (CATALOGUE, TEMPLATES, RESTAURANTS, BRANCHES)},
                    "restaurants": len(menus), "items": sum(len(m["items"]) for m in menus.values())},
           "menus": menus}
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":"), sort_keys=True), encoding="utf-8")

    # ── summary log ──
    def price_summary(rows):
        prices = sorted(it["price"] for row in rows for it in row["items"])
        cdb = sorted(it["price"] for row in rows for it in row["items"] if it["dish_id"] == "chicken-dum-biryani")
        sizes = sorted(len(row["items"]) for row in rows)
        return {"restaurants": len(rows), "items": len(prices),
                "item_price_min": prices[0], "item_price_median": median(prices), "item_price_max": prices[-1],
                "menu_size_min": sizes[0], "menu_size_median": median(sizes), "menu_size_max": sizes[-1],
                "chicken_dum_biryani_price": ({"on_menus": len(cdb), "min": cdb[0], "median": median(cdb), "max": cdb[-1]}
                                              if cdb else None)}
    by_band = defaultdict(list)
    for row in log_rows:
        by_band[row["band"] if row["band"] != "standard" else f"standard ({row['amenity']})"].append(row)
    all_items = [it for m in menus.values() for it in m["items"]]
    log = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator_version": GENERATOR_VERSION, "global_seed": GLOBAL_SEED, "decisions": ["D-016", "D-017", "D-018"],
        "restaurants": len(menus), "items": len(all_items),
        "items_veg": sum(it["is_veg"] for it in all_items), "distinct_dishes_used": len({it["dish_id"] for it in all_items}),
        "restaurants_by_price_band": dict(Counter(m["price_band"] for m in menus.values()).most_common()),
        "price_summary_by_band": {k: price_summary(v) for k, v in sorted(by_band.items())},
        "price_summary_all": price_summary(log_rows),
        "inputs_sha256": out["meta"]["inputs_sha256"], "output_sha256": {OUT.name: sha(OUT)},
    }
    OUT_LOG.parent.mkdir(parents=True, exist_ok=True)
    OUT_LOG.write_text(json.dumps(log, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"{len(menus)} menus, {len(all_items)} items ({log['items_veg']} veg), {log['distinct_dishes_used']} distinct dishes used")
    print(f"Price bands: {log['restaurants_by_price_band']}")
    for k, v in log["price_summary_by_band"].items():
        c = v["chicken_dum_biryani_price"]
        print(f"  {k:<24} {v['restaurants']:>4} rest. | items ₹{v['item_price_min']}–₹{v['item_price_max']} (median ₹{v['item_price_median']}) "
              f"| menu {v['menu_size_min']}–{v['menu_size_max']} | chicken biryani " + (f"₹{c['min']}–₹{c['max']} (median ₹{c['median']})" if c else "—"))
    print(f"Saved {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB) and {OUT_LOG.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
