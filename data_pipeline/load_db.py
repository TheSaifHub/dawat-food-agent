"""Phase 3, module 3e: seed the Supabase database from the processed files (D-021). Idempotent and rerunnable.

Before loading, it runs validate_menus.py and refuses to continue unless that passes.

Loads, in dependency order, with INSERT … ON CONFLICT DO UPDATE (upserts), all in ONE transaction:
  areas + area_aliases        data/reference/localities.csv
  restaurants + branches      data/processed/restaurants.csv, branches.csv (+ price level from menus.json)
  dishes + dish_aliases       data/reference/dish_catalogue.csv (each dish and alias stored once)
  food_terms                  data/reference/food_lexicon.csv (query words: kodi, karam lekunda, rendu; D-024)
  menu_items                  data/processed/menus.json (restaurant, dish, price only)
NEVER deletes. Rows that exist in the database but no longer in the files are only REPORTED
(deleting data needs Saif's approval, CLAUDE.md).

Demo users (fictional, @example.com, D-021) are created through the Supabase Auth admin API with the secret
key, without passwords (how demo login works is decided in Phase 7), then given a users row, preferences and
one fictional address each.

Nothing secret is printed. Run from the project root:
    .venv\\Scripts\\python data_pipeline\\load_db.py             # Supabase (DATABASE_URL)
    .venv\\Scripts\\python data_pipeline\\load_db.py --local     # the LOCAL test database (TEST_DATABASE_URL, D-052)

With --local there is no Supabase Auth: the demo users are written straight into the local stand-in auth.users
(backend/db/local_bootstrap.sql), with fixed ids derived from their emails so reruns find the same users.
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from check_menu_templates import norm_alias

ROOT = Path(__file__).resolve().parent.parent
REF, PROC = ROOT / "data" / "reference", ROOT / "data" / "processed"

DEMO_USERS = [
    {"email": "demo.veg@example.com", "display_name": "Demo Priya (vegetarian)",
     "prefs": {"diet": "vegetarian", "max_spice": 1, "default_area": "madhapur", "language": "en"},
     "address": {"label": "Home", "line1": "Flat 101, Demo Residency (fictional)", "area_id": "madhapur"}},
    {"email": "demo.spicy@example.com", "display_name": "Demo Arjun (loves spicy)",
     "prefs": {"diet": "non_vegetarian", "max_spice": 3, "default_area": "gachibowli", "language": "hinglish"},
     "address": {"label": "Office", "line1": "Tower 2, Demo Tech Park (fictional)", "area_id": "gachibowli"}},
    {"email": "demo.family@example.com", "display_name": "Demo Family (Telugu)",
     "prefs": {"diet": "non_vegetarian", "max_spice": 2, "default_area": "kukatpally", "language": "te"},
     "address": {"label": "Home", "line1": "House 7, Demo Colony (fictional)", "area_id": "kukatpally"}},
]


def read_csv(p: Path) -> list[dict]:
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def script_of(s: str) -> str:
    return "telugu" if any("ఀ" <= c <= "౿" for c in s) else "latin"


def aliases(values) -> list[tuple[str, str]]:
    """(alias as written, normalised) pairs, one per distinct normalised form."""
    seen, out = set(), []
    for a in (v.strip() for v in values if v and v.strip()):
        n = norm_alias(a)
        if n and n not in seen:
            seen.add(n)
            out.append((a, n))
    return out


# ─── Supabase Auth admin API (secret key, sent as the apikey header) ─────
def auth_admin(method: str, path: str, body: dict | None = None) -> dict:
    url = os.environ["SUPABASE_URL"].rstrip("/") + "/auth/v1/admin/" + path
    key = os.environ["SUPABASE_SECRET_KEY"]
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:200].replace(key, "***")
        sys.exit(f"Auth admin API {method} {path} failed: HTTP {e.code} {detail}. Nothing committed.")


def ensure_demo_auth_users() -> dict[str, str]:
    existing = {u["email"]: u["id"] for u in auth_admin("GET", "users?page=1&per_page=1000").get("users", [])}
    ids = {}
    for d in DEMO_USERS:
        if d["email"] in existing:
            ids[d["email"]] = existing[d["email"]]
        else:
            u = auth_admin("POST", "users", {"email": d["email"], "email_confirm": True,
                                             "user_metadata": {"display_name": d["display_name"], "is_demo": True}})
            ids[d["email"]] = u["id"]
    return ids


def ensure_local_demo_auth_users(dsn: str) -> dict[str, str]:
    """The local stand-in for ensure_demo_auth_users: same emails and metadata, ids fixed by uuid5(email)."""
    ids = {d["email"]: str(uuid.uuid5(uuid.NAMESPACE_URL, "dawat-demo:" + d["email"])) for d in DEMO_USERS}
    with psycopg.connect(dsn, connect_timeout=15) as conn:
        for d in DEMO_USERS:
            conn.execute("insert into auth.users (id, email, raw_user_meta_data) values (%s, %s, %s::jsonb) "
                         "on conflict (id) do nothing",
                         (ids[d["email"]], d["email"], json.dumps({"display_name": d["display_name"], "is_demo": True})))
    return ids


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true", help="seed the LOCAL test database (TEST_DATABASE_URL)")
    args = ap.parse_args()
    load_dotenv(ROOT / "backend" / ".env")
    if args.local:
        sys.path.insert(0, str(ROOT / "backend"))
        from app.localdb import require_test_dsn
        dsn = require_test_dsn()
        print("Target: the LOCAL test database")
    else:
        dsn = os.environ["DATABASE_URL"]
        print("Target: Supabase (DATABASE_URL)")

    # 0. the menus must pass validation first
    v = subprocess.run([sys.executable, str(ROOT / "data_pipeline" / "validate_menus.py")], capture_output=True, text=True,
                       encoding="utf-8")
    if v.returncode != 0:
        print(v.stdout[-2000:])
        sys.exit("validate_menus.py failed. Nothing loaded.")
    print("validate_menus.py: PASSED")

    areas = read_csv(REF / "localities.csv")
    restaurants = read_csv(PROC / "restaurants.csv")
    branches = read_csv(PROC / "branches.csv")
    dishes = read_csv(REF / "dish_catalogue.csv")
    menus = json.loads((PROC / "menus.json").read_text(encoding="utf-8"))["menus"]

    area_rows = [(a["area_id"], a["display_name"], a["name_te"] or None, float(a["lat"]), float(a["lon"]), a["source"]) for a in areas]
    area_alias_rows = [(a["area_id"], al, n) for a in areas for al, n in aliases([a["display_name"], *a["aliases"].split(";")])]
    rest_rows = [(r["restaurant_id"], r["name"], r["is_chain"] == "True", int(r["branch_count"]), r["cuisines"].split(";"),
                  r["primary_cuisine"], r["veg_only"] == "True", menus[r["restaurant_id"]]["meal_capable"],
                  menus[r["restaurant_id"]]["price_band"], menus[r["restaurant_id"]]["price_level"]) for r in restaurants]
    bad_postcodes = sum(1 for b in branches if b["postcode"] and not re.fullmatch(r"\d{6}", b["postcode"]))
    branch_rows = [(b["branch_id"], b["restaurant_id"], b["branch_label"], b["osm"], b["osm_name"], b["amenity"], float(b["lat"]),
                    float(b["lon"]), b["area_id"], b["area_method"], int(b["area_distance_m"]), b["street"] or None,
                    b["postcode"] if re.fullmatch(r"\d{6}", b["postcode"] or "") else None) for b in branches]
    dish_rows = [(d["dish_id"], d["name"], d["category"], d["course"], d["is_veg"] == "true", int(d["spice_level"]), int(d["serves"]),
                  int(d["price_low"]), int(d["price_high"]), d["notes"] or None) for d in dishes]
    dish_alias_rows = [(d["dish_id"], al, n, script_of(al)) for d in dishes for al, n in aliases(d["aliases"].split(";"))]
    term_rows = [(norm_alias(t["term"]), t["term"], t["means"].strip(), t["kind"], t["language"])
                 for t in read_csv(REF / "food_lexicon.csv")]
    item_rows = [(it["item_id"], rid, it["dish_id"], it["price"]) for rid, m in menus.items() for it in m["items"]]

    if args.local:
        print("Creating/finding demo users in the local auth.users …")
        demo_ids = ensure_local_demo_auth_users(dsn)
    else:
        print("Creating/finding demo users in Supabase Auth …")
        demo_ids = ensure_demo_auth_users()

    upserts = [
        ("areas", "area_id", ["area_id", "name", "name_te", "lat", "lon", "source"], area_rows),
        ("area_aliases", "area_id, alias_norm", ["area_id", "alias", "alias_norm"], area_alias_rows),
        ("restaurants", "restaurant_id", ["restaurant_id", "name", "is_chain", "branch_count", "cuisines", "primary_cuisine",
                                          "veg_only", "meal_capable", "price_band", "price_level"], rest_rows),
        ("branches", "branch_id", ["branch_id", "restaurant_id", "label", "osm_ref", "osm_name", "amenity", "lat", "lon", "area_id",
                                   "area_method", "area_distance_m", "street", "postcode"], branch_rows),
        ("dishes", "dish_id", ["dish_id", "name", "category", "course", "is_veg", "spice_level", "serves", "price_low",
                               "price_high", "notes"], dish_rows),
        ("dish_aliases", "dish_id, alias_norm", ["dish_id", "alias", "alias_norm", "script"], dish_alias_rows),
        ("food_terms", "term_norm", ["term_norm", "term", "means", "kind", "language"], term_rows),
        ("menu_items", "item_id", ["item_id", "restaurant_id", "dish_id", "price"], item_rows),
    ]
    source_keys = {"areas": {r[0] for r in area_rows}, "restaurants": {r[0] for r in rest_rows},
                   "branches": {r[0] for r in branch_rows}, "dishes": {r[0] for r in dish_rows},
                   "menu_items": {r[0] for r in item_rows}, "food_terms": {r[0] for r in term_rows}}

    with psycopg.connect(dsn, connect_timeout=15) as conn:
        with conn.transaction():
            for table, key, cols, rows in upserts:
                keys = [k.strip() for k in key.split(",")]
                updates = [c for c in cols if c not in keys]
                sql = (f"insert into public.{table} ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))}) "
                       f"on conflict ({key}) do " + (f"update set {', '.join(f'{c} = excluded.{c}' for c in updates)}"
                                                     if updates else "nothing"))
                with conn.cursor() as cur:
                    cur.executemany(sql, rows)
                print(f"  {table:<14} {len(rows):>6} rows upserted")

            for d in DEMO_USERS:
                uid = demo_ids[d["email"]]
                conn.execute("insert into public.users (user_id, display_name, is_demo) values (%s, %s, true) "
                             "on conflict (user_id) do update set display_name = excluded.display_name, is_demo = true",
                             (uid, d["display_name"]))
                for k, val in d["prefs"].items():
                    conn.execute("insert into public.user_preferences (user_id, key, value, source) values (%s, %s, %s::jsonb, 'seed') "
                                 "on conflict (user_id, key) do update set value = excluded.value, source = 'seed'",
                                 (uid, k, json.dumps(val)))
                a = d["address"]
                lat, lon = next((r[3], r[4]) for r in area_rows if r[0] == a["area_id"])
                if not conn.execute("select 1 from public.addresses where user_id = %s and label = %s", (uid, a["label"])).fetchone():
                    conn.execute("insert into public.addresses (user_id, label, line1, area_id, lat, lon, is_default) "
                                 "values (%s, %s, %s, %s, %s, %s, true)", (uid, a["label"], a["line1"], a["area_id"], lat, lon))
            print(f"  demo users     {len(DEMO_USERS):>6} (users + preferences + one address each)")

        # report (never delete) rows the files no longer contain; then counts
        pk = {"areas": "area_id", "restaurants": "restaurant_id", "branches": "branch_id", "dishes": "dish_id", "menu_items": "item_id",
              "food_terms": "term_norm"}
        stale = {t: len({r[0] for r in conn.execute(f"select {k} from public.{t}").fetchall()} - source_keys[t]) for t, k in pk.items()}
        counts = {t: conn.execute(f"select count(*) from public.{t}").fetchone()[0] for t, *_ in upserts}
        counts.update({t: conn.execute(f"select count(*) from public.{t}").fetchone()[0]
                       for t in ("users", "user_preferences", "addresses")})
        veg_breach = conn.execute("""select count(*) from public.menu_items m join public.restaurants r using (restaurant_id)
                                     join public.dishes d using (dish_id) where r.veg_only and not d.is_veg""").fetchone()[0]

    print(f"\nRows now in the database: {counts}")
    print(f"Rows in the database but not in the files (reported, NOT deleted): {stale}")
    print(f"Postcodes dropped as malformed: {bad_postcodes}")
    print(f"Non-veg items on veg-only menus in the database: {veg_breach}")
    expected = {"areas": len(area_rows), "area_aliases": len(area_alias_rows), "restaurants": len(rest_rows),
                "branches": len(branch_rows), "dishes": len(dish_rows), "dish_aliases": len(dish_alias_rows),
                "menu_items": len(item_rows), "food_terms": len(term_rows)}
    mismatch = {t: (counts[t], n) for t, n in expected.items() if counts[t] != n}
    if mismatch or veg_breach or any(stale.values()):
        print(f"CHECK FAILED: count mismatches {mismatch}, veg breaches {veg_breach}, stale {stale}")
        return 1
    print("SEED OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
