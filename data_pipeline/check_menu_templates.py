"""Phase 3, module 3a: validate the hand-written menu inputs BEFORE any menu is generated (D-016, D-017).

Checks (the run FAILS on any error; warnings are printed but allowed):
  dish_catalogue.csv
    - every field present; ids unique slugs; names unique; category / course from the fixed lists
    - is_veg true/false, spice 0–3, serves 1 or 2, 0 < price_low ≤ price_high ≤ 1,500, high ≤ 3.5 × low
    - veg flag vs the dish NAME: a veg dish may not be named with a meat/egg word, and a non-veg dish
      must either have one in its name or say why in `notes` (e.g. "contains egg")
    - aliases: ≥2 per dish; only Latin or Telugu script; no alias shared by two dishes or equal to
      another dish's name (after normalising case and punctuation)
  menu_templates.json
    - a template for every cuisine used in data/processed/restaurants.csv; every dish id exists
    - no dish both core and optional; the size range fits; each template has a veg dish
    - meal_capable ⇒ a main plus a side/bread/rice in core, and a veg main somewhere in the template
    - every name_hints regex compiles and points at real dishes
  veg-only restaurants: their cuisines together offer ≥ 8 veg dishes, including a veg main
  food_lexicon.csv: terms unique, meanings filled

Output: results/menus/template_check.json (all counts; cited by DECISIONS.md D-017)

Run from the project root:
    .venv\\Scripts\\python data_pipeline\\check_menu_templates.py
"""

import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
CATALOGUE = REF / "dish_catalogue.csv"
TEMPLATES = REF / "menu_templates.json"
LEXICON = REF / "food_lexicon.csv"
RESTAURANTS = ROOT / "data" / "processed" / "restaurants.csv"
OUT = ROOT / "results" / "menus" / "template_check.json"

CATEGORIES = {"biryani", "mandi", "kebab", "starter", "curry", "bread", "rice", "noodles", "soup", "salad", "pizza",
              "pasta", "burger", "sandwich", "roll", "shawarma", "fried_chicken", "mexican", "continental",
              "breakfast", "tiffin", "meals", "snack", "bakery", "dessert", "drink"}
COURSES = {"main", "side", "dessert", "drink"}
MEAL_SIDES = {"side"}  # a meal = a main + a side (starters, breads, rice sides, curries served as sides)
MEAL_SIDE_CATEGORIES = {"bread", "rice", "curry", "starter", "kebab", "salad", "soup", "snack", "mexican", "continental"}
NON_VEG_WORDS = re.compile(r"\b(chicken|mutton|egg|eggs|fish|prawns?|shrimp|salmon|gosht|keema|lukhmi|kodi|murgh|"
                           r"pepperoni|haleem|marag|paya|omelette|lamb|meat)\b")
MAX_PRICE, MAX_SPREAD = 1500, 3.5
MIN_VEG_DISHES_FOR_VEG_ONLY = 8


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower().replace("&", " and ")
    s = re.sub(r"[^\w\s]", " ", s)  # \w keeps Telugu letters; Telugu vowel signs are \w-adjacent marks, kept below
    return re.sub(r"\s+", " ", s).strip()


def norm_alias(s: str) -> str:
    # Keep Telugu combining marks (category M*), which [^\w\s] would strip.
    s = unicodedata.normalize("NFKC", s).lower().replace("&", " and ")
    s = "".join(c if (c.isalnum() or c.isspace() or unicodedata.category(c).startswith("M") or c in "‌‍")
                else " " for c in s)
    return re.sub(r"\s+", " ", s).strip()


def script_ok(s: str) -> bool:
    for c in s:
        if c.isascii() or c in "‌‍":
            continue
        if "ఀ" <= c <= "౿":  # Telugu block
            continue
        return False
    return True


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    errors, warnings = [], []
    with CATALOGUE.open(encoding="utf-8-sig", newline="") as f:
        dishes = list(csv.DictReader(f))
    by_id = {}

    # ── catalogue ──
    for d in dishes:
        did = d["dish_id"]
        for k in ("dish_id", "name", "category", "course", "is_veg", "spice_level", "serves", "price_low", "price_high", "aliases"):
            if not d.get(k, "").strip():
                errors.append(f"{did}: empty field {k}")
        if did in by_id:
            errors.append(f"duplicate dish_id {did}")
        by_id[did] = d
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", did):
            errors.append(f"{did}: id is not a lowercase slug")
        if d["category"] not in CATEGORIES:
            errors.append(f"{did}: unknown category {d['category']}")
        if d["course"] not in COURSES:
            errors.append(f"{did}: unknown course {d['course']}")
        if d["is_veg"] not in ("true", "false"):
            errors.append(f"{did}: is_veg must be true/false")
        try:
            spice, serves, lo, hi = int(d["spice_level"]), int(d["serves"]), int(d["price_low"]), int(d["price_high"])
        except ValueError:
            errors.append(f"{did}: spice/serves/prices must be integers")
            continue
        if not 0 <= spice <= 3:
            errors.append(f"{did}: spice_level {spice} outside 0–3")
        if serves not in (1, 2):
            errors.append(f"{did}: serves {serves} not 1 or 2")
        if not (0 < lo <= hi <= MAX_PRICE):
            errors.append(f"{did}: prices {lo}–{hi} not in 0 < low ≤ high ≤ {MAX_PRICE}")
        elif hi > MAX_SPREAD * lo:
            errors.append(f"{did}: price spread {lo}–{hi} wider than {MAX_SPREAD}×")
        # veg flag vs name
        meaty = NON_VEG_WORDS.search(norm(d["name"]))
        if d["is_veg"] == "true" and meaty:
            errors.append(f"{did}: marked veg but the name says '{meaty.group()}'")
        if d["is_veg"] == "false" and not meaty and not re.search(r"egg|non-veg", d.get("notes", "")):
            errors.append(f"{did}: marked non-veg but neither the name nor notes say why")
    names = Counter(norm(d["name"]) for d in dishes)
    errors += [f"duplicate dish name '{n}'" for n, c in names.items() if c > 1]

    # aliases
    owner: dict[str, str] = {norm_alias(d["name"]): d["dish_id"] for d in dishes}
    alias_count, telugu_dishes, latin_aliases, telugu_aliases = 0, set(), 0, 0
    for d in dishes:
        aliases = [a.strip() for a in d["aliases"].split(";") if a.strip()]
        if len(aliases) < 2:
            errors.append(f"{d['dish_id']}: fewer than 2 aliases")
        seen = set()
        for a in aliases:
            if not script_ok(a):
                errors.append(f"{d['dish_id']}: alias '{a}' has characters outside Latin/Telugu script")
            n = norm_alias(a)
            if n in seen:
                warnings.append(f"{d['dish_id']}: alias '{a}' repeated")
                continue
            seen.add(n)
            other = owner.get(n)
            if other and other != d["dish_id"]:
                errors.append(f"alias '{a}' of {d['dish_id']} collides with {other}")
            owner.setdefault(n, d["dish_id"])
            alias_count += 1
            if any("ఀ" <= c <= "౿" for c in a):
                telugu_dishes.add(d["dish_id"])
                telugu_aliases += 1
            else:
                latin_aliases += 1
    no_telugu = sorted(set(by_id) - telugu_dishes)

    # ── templates ──
    tj = json.loads(TEMPLATES.read_text(encoding="utf-8"))
    templates = tj["templates"]
    with RESTAURANTS.open(encoding="utf-8-sig", newline="") as f:
        restaurants = list(csv.DictReader(f))
    used = Counter(c for r in restaurants for c in r["cuisines"].split(";"))
    missing_t = sorted(set(used) - set(templates))
    errors += [f"no template for cuisine '{c}' (used by {used[c]} restaurants)" for c in missing_t]
    unused_t = sorted(set(templates) - set(used))
    warnings += [f"template '{c}' is not used by any restaurant" for c in unused_t]

    def veg(i): return by_id[i]["is_veg"] == "true"
    template_stats = {}
    for c, t in templates.items():
        core, opt = t["core"], t["optional"]
        for i in core + opt:
            if i not in by_id:
                errors.append(f"{c}: unknown dish '{i}'")
        if set(core) & set(opt):
            errors.append(f"{c}: in both core and optional: {sorted(set(core) & set(opt))}")
        if len(core) != len(set(core)) or len(opt) != len(set(opt)):
            errors.append(f"{c}: repeated dish in core or optional")
        lo, hi = t["size"]
        if not (len(core) <= hi and lo <= len(core) + len(opt) and lo <= hi):
            errors.append(f"{c}: size {t['size']} does not fit core {len(core)} + optional {len(opt)}")
        known = [i for i in core + opt if i in by_id]
        if not any(veg(i) for i in known):
            errors.append(f"{c}: no veg dish at all")
        if t["meal_capable"]:
            core_k = [i for i in core if i in by_id]
            if not any(by_id[i]["course"] == "main" for i in core_k):
                errors.append(f"{c}: meal_capable but no main in core")
            if not any(by_id[i]["course"] in MEAL_SIDES for i in core_k):
                errors.append(f"{c}: meal_capable but no side/bread/rice in core")
            if not any(veg(i) and by_id[i]["course"] == "main" for i in known):
                errors.append(f"{c}: meal_capable but no veg main in the template")
        template_stats[c] = {"core": len(core), "optional": len(opt), "size": t["size"],
                             "veg_dishes": sum(veg(i) for i in known), "restaurants": used.get(c, 0)}
    for pattern, ids in tj["name_hints"].items():
        try:
            re.compile(pattern)
        except re.error as e:
            errors.append(f"name_hints '{pattern}': bad regex ({e})")
        errors += [f"name_hints '{pattern}': unknown dish '{i}'" for i in ids if i not in by_id]

    # ── veg-only feasibility ──
    veg_only = []
    for r in (r for r in restaurants if r["veg_only"] == "True"):
        pool = {i for c in r["cuisines"].split(";") if c in templates
                for i in templates[c]["core"] + templates[c]["optional"] if i in by_id and veg(i)}
        has_main = any(by_id[i]["course"] == "main" for i in pool)
        veg_only.append({"restaurant": r["name"], "cuisines": r["cuisines"], "veg_dishes_available": len(pool), "veg_main": has_main})
        if len(pool) < MIN_VEG_DISHES_FOR_VEG_ONLY or not has_main:
            errors.append(f"veg-only '{r['name']}' ({r['cuisines']}): only {len(pool)} veg dishes, veg main={has_main}")

    # ── lexicon ──
    with LEXICON.open(encoding="utf-8-sig", newline="") as f:
        lex = list(csv.DictReader(f))
    lt = Counter(norm_alias(x["term"]) for x in lex)
    errors += [f"lexicon: term '{t}' repeated" for t, n in lt.items() if n > 1]
    errors += [f"lexicon: '{x['term']}' has no meaning" for x in lex if not x["means"].strip()]
    errors += [f"lexicon: '{x['term']}' has characters outside Latin/Telugu script" for x in lex if not script_ok(x["term"])]
    # the same rules as the food_terms table (0005_food_terms.sql), checked before loading (D-024)
    kinds = {"ingredient", "dish word", "diet", "spice", "number", "portion"}
    errors += [f"lexicon: '{x['term']}' has unknown kind '{x['kind']}'" for x in lex if x["kind"] not in kinds]
    errors += [f"lexicon: number '{x['term']}' must mean a whole number" for x in lex
               if x["kind"] == "number" and not x["means"].strip().isdigit()]

    report = {
        "dishes": len(dishes), "veg_dishes": sum(d["is_veg"] == "true" for d in dishes),
        "by_category": dict(Counter(d["category"] for d in dishes).most_common()),
        "by_course": dict(Counter(d["course"] for d in dishes).most_common()),
        "by_spice_level": dict(sorted(Counter(d["spice_level"] for d in dishes).items())),
        "serves_2": sum(d["serves"] == "2" for d in dishes),
        "aliases": {"total_unique": alias_count, "latin": latin_aliases, "telugu_script": telugu_aliases,
                    "per_dish_avg": round(alias_count / len(dishes), 1),
                    "dishes_with_telugu_script_alias": len(telugu_dishes), "dishes_without_telugu_script_alias": no_telugu},
        "templates": template_stats, "cuisines_used_without_template": missing_t, "templates_unused": unused_t,
        "name_hints": len(tj["name_hints"]),
        "veg_only_restaurants": {"count": len(veg_only), "min_veg_dishes_available": min((v["veg_dishes_available"] for v in veg_only), default=0),
                                 "details": veg_only},
        "lexicon": {"terms": len(lex), "by_kind": dict(Counter(x["kind"] for x in lex).most_common())},
        "errors": errors, "warnings": warnings, "passed": not errors,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Dishes: {len(dishes)} ({report['veg_dishes']} veg), {alias_count} aliases "
          f"({telugu_aliases} Telugu script, {latin_aliases} Latin), avg {report['aliases']['per_dish_avg']} per dish")
    print(f"Telugu-script alias on {len(telugu_dishes)}/{len(dishes)} dishes")
    print(f"Templates: {len(templates)} for {len(used)} cuisines in use; name hints: {len(tj['name_hints'])}")
    print(f"Veg-only restaurants: {len(veg_only)}, fewest veg dishes available: {report['veg_only_restaurants']['min_veg_dishes_available']}")
    print(f"Lexicon: {len(lex)} terms")
    for w in warnings:
        print("  warning:", w)
    for e in errors:
        print("  ERROR:", e)
    print(("PASSED" if not errors else f"FAILED with {len(errors)} error(s)") + f". Saved {OUT.relative_to(ROOT)}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
