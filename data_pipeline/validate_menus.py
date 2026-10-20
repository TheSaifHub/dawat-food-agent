"""Phase 3, module 3c: validate data/processed/menus.json before anything is loaded into the database (D-019).

Independent of generate_menus.py: it imports nothing from it and re-derives every expectation from the
reviewed inputs (dish catalogue, templates, restaurants.csv). The run FAILS on any error.

Checks
  coverage   every restaurant in restaurants.csv has exactly one menu, and nothing else does;
             the menu was built from the current input files (sha256 in its meta)
  items      every CLAUDE.md field present with the right type; unique item ids; no dish twice on a menu;
             name / veg / spice / serves / category / course / aliases identical to the catalogue
             (no drift), price an integer inside the dish's price range
  veg        every restaurant has ≥1 veg item; a veg-only restaurant has ONLY veg items
  meals      a meal-capable restaurant has a main and a side (bread, rice, curry side, starter…),
             and a veg main unless it is a veg-free format by design (reported, not failed)
  prices     all prices on one menu sit near the restaurant's own price level (consistent within a
             restaurant); a full plate costs more than its half plate and at most 2.2× as much;
             chains are in the 0.55–0.75 band; budget/premium names are in their bands
  promises   a restaurant whose name promises a dish type (biryani, pizza, mandi, dosa…) has one
  sizes      8–40 items per menu

Output: results/menus/validation_report.json

Run from the project root:
    .venv\\Scripts\\python data_pipeline\\validate_menus.py
"""

import csv
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
MENUS = ROOT / "data" / "processed" / "menus.json"
CATALOGUE = REF / "dish_catalogue.csv"
TEMPLATES = REF / "menu_templates.json"
RESTAURANTS = ROOT / "data" / "processed" / "restaurants.csv"
BRANCHES = ROOT / "data" / "processed" / "branches.csv"
OUT = ROOT / "results" / "menus" / "validation_report.json"

FIELDS = {"item_id": str, "dish_id": str, "name": str, "price": int, "is_veg": bool, "spice_level": int, "serves": int,
          "category": str, "course": str, "aliases": list}
MENU_SIZE = (8, 40)
LEVEL_TOLERANCE = 0.06  # jitter (0.05) + float slack; half a rounding step is added per item
BANDS = {"chain": (0.55, 0.75), "budget": (0.0, 0.30), "premium": (0.70, 1.0)}
FULL_OF = {"chicken-dum-biryani-full": "chicken-dum-biryani", "mutton-dum-biryani-full": "mutton-dum-biryani",
           "chicken-mandi-full": "chicken-mandi", "mutton-mandi-full": "mutton-mandi",
           "tandoori-chicken-full": "tandoori-chicken-half", "fried-chicken-bucket": "fried-chicken-2pc"}
# a name word → at least one item of these categories must be on the menu
PROMISES = {r"biryani|biriyani|briyani|biriani": {"biryani"}, r"pizza": {"pizza"}, r"mandi": {"mandi"},
            r"burger": {"burger"}, r"dosa|tiffins?|idli": {"tiffin"}, r"shawarma": {"shawarma"},
            r"kebab|kabab": {"kebab"}, r"juice|lassi": {"drink"}, r"bakery|bakers": {"bakery"}, r"chinese": {"noodles", "rice", "starter"}}
SIDE_CATEGORIES_OK = {"side"}


def read_csv(p: Path) -> list[dict]:
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    errors, notes = [], []

    def err(msg):
        errors.append(msg)

    data = json.loads(MENUS.read_text(encoding="utf-8"))
    menus = data["menus"]
    dishes = {d["dish_id"]: d for d in read_csv(CATALOGUE)}
    templates = json.loads(TEMPLATES.read_text(encoding="utf-8"))["templates"]
    restaurants = {r["restaurant_id"]: r for r in read_csv(RESTAURANTS)}

    # coverage + freshness
    for rid in sorted(set(restaurants) - set(menus)):
        err(f"{rid}: restaurant has no menu")
    for rid in sorted(set(menus) - set(restaurants)):
        err(f"{rid}: menu for an unknown restaurant")
    for p in (CATALOGUE, TEMPLATES, RESTAURANTS, BRANCHES):
        if data["meta"]["inputs_sha256"].get(p.name) != hashlib.sha256(p.read_bytes()).hexdigest():
            err(f"menus.json is stale: {p.name} changed since it was generated (rerun generate_menus.py)")

    item_ids, veg_free_meal = Counter(), []
    stats = Counter()
    for rid, m in menus.items():
        r = restaurants.get(rid)
        if r is None:
            continue
        items = m["items"]
        stats["items"] += len(items)
        if not MENU_SIZE[0] <= len(items) <= MENU_SIZE[1]:
            err(f"{rid}: {len(items)} items, outside {MENU_SIZE}")
        seen = Counter(it.get("dish_id") for it in items)
        for d, n in seen.items():
            if n > 1:
                err(f"{rid}: dish {d} appears {n} times")
        positions = []
        for it in items:
            for f, typ in FIELDS.items():
                if f not in it or not isinstance(it[f], typ) or (typ is int and isinstance(it[f], bool)):
                    err(f"{rid}: item {it.get('item_id')} field '{f}' missing or not {typ.__name__}")
            item_ids[it.get("item_id")] += 1
            d = dishes.get(it.get("dish_id"))
            if d is None:
                err(f"{rid}: unknown dish {it.get('dish_id')}")
                continue
            expect = {"name": d["name"], "is_veg": d["is_veg"] == "true", "spice_level": int(d["spice_level"]),
                      "serves": int(d["serves"]), "category": d["category"], "course": d["course"],
                      "aliases": [a.strip() for a in d["aliases"].split(";") if a.strip()]}
            for f, v in expect.items():
                if it.get(f) != v:
                    err(f"{rid}: {it['dish_id']} field '{f}' = {it.get(f)!r}, catalogue says {v!r}")
            lo, hi = int(d["price_low"]), int(d["price_high"])
            p = it.get("price")
            if not isinstance(p, int) or isinstance(p, bool) or not lo <= p <= hi:
                err(f"{rid}: {it['dish_id']} price {p} outside its range ₹{lo}–₹{hi}")
            elif hi > lo and it["dish_id"] not in FULL_OF:
                # allowed drift = the generator's documented jitter (±0.05) + half a rounding step (₹10, or ₹5 under ₹50)
                half_step = 5 if p >= 50 else 2.5
                positions.append((it["dish_id"], (p - lo) / (hi - lo), LEVEL_TOLERANCE + half_step / (hi - lo)))

        # veg
        if not any(it.get("is_veg") for it in items):
            err(f"{rid}: no veg item")
        if r["veg_only"] == "True":
            stats["veg_only_menus"] += 1
            bad = [it["name"] for it in items if not it.get("is_veg")]
            if bad:
                err(f"{rid} ({r['name']}) is veg-only but lists non-veg: {bad}")

        # meals
        primary = r["cuisines"].split(";")[0]
        if templates.get(primary, {}).get("meal_capable"):
            stats["meal_capable_menus"] += 1
            if not any(it.get("course") == "main" for it in items):
                err(f"{rid}: meal-capable but no main")
            if not any(it.get("course") in SIDE_CATEGORIES_OK for it in items):
                err(f"{rid}: meal-capable but no side, bread or rice")
            if not any(it.get("course") == "main" and it.get("is_veg") for it in items):
                veg_free_meal.append(f"{r['name']} ({r['cuisines']})")

        # prices: consistent within the restaurant, full > half, bands
        level = m.get("price_level")
        if not isinstance(level, (int, float)) or not 0 <= level <= 1:
            err(f"{rid}: price_level {level!r} not in [0, 1]")
        else:
            off = [(d, round(pos, 2)) for d, pos, tol in positions if abs(pos - level) > tol + 1e-9]
            if off:
                err(f"{rid}: prices inconsistent with its level {level}: {off[:3]}")
            band = m.get("price_band", "").split(" (")[0]
            if band in BANDS and not BANDS[band][0] <= level <= BANDS[band][1]:
                err(f"{rid}: price_level {level} outside the {band} band {BANDS[band]}")
            if r["is_chain"] == "True" and band != "chain":
                err(f"{rid}: chain but price band '{band}'")
        price = {it["dish_id"]: it["price"] for it in items if "dish_id" in it and isinstance(it.get("price"), int)}
        for full, half in FULL_OF.items():
            if full in price and half in price and not price[half] < price[full] <= 2.2 * price[half]:
                err(f"{rid}: {full} ₹{price[full]} vs {half} ₹{price[half]} (need half < full ≤ 2.2× half)")

        # name promises
        name = re.sub(r"[^\w\s]", " ", r["name"].lower())
        cats = {it.get("category") for it in items}
        for pattern, need in PROMISES.items():
            if re.search(rf"\b({pattern})\b", name) and not cats & need:
                err(f"{rid} ({r['name']}): name promises {sorted(need)} but the menu has none")

    errors += [f"item_id {i} used {n} times" for i, n in item_ids.items() if n > 1]
    if veg_free_meal:
        notes.append(f"{len(veg_free_meal)} meal-capable menus have no veg main (the planner must look elsewhere for a vegetarian): "
                     + "; ".join(veg_free_meal[:10]) + (" …" if len(veg_free_meal) > 10 else ""))

    report = {"menus": len(menus), "items": stats["items"], "veg_only_menus_checked": stats["veg_only_menus"],
              "meal_capable_menus_checked": stats["meal_capable_menus"], "meal_capable_without_veg_main": len(veg_free_meal),
              "meal_capable_without_veg_main_list": veg_free_meal, "checks": [
                  "coverage", "freshness", "fields and types", "catalogue match", "price in range", "unique ids",
                  "no duplicate dish", "≥1 veg item", "veg-only = all veg", "meal = main + side", "price consistency",
                  "full > half", "price bands", "name promises", "menu size"],
              "errors": errors, "notes": notes, "passed": not errors}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Checked {len(menus)} menus, {stats['items']} items ({stats['veg_only_menus']} veg-only, "
          f"{stats['meal_capable_menus']} meal-capable)")
    for n in notes:
        print("  note:", n)
    for e in errors[:25]:
        print("  ERROR:", e)
    if len(errors) > 25:
        print(f"  … and {len(errors) - 25} more")
    print(("PASSED" if not errors else f"FAILED with {len(errors)} error(s)") + f". Saved {OUT.relative_to(ROOT)}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
