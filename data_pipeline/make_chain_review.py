"""Phase 2, module 2c: build the chain-mapping review file for Saif, batch by batch. Merges nothing.

Candidates come from the CLEANED places (data/processed/places_clean.csv), not the Phase 1
chain_review.csv (built from raw data, so it still has unnamed places and merged duplicates).
For each chain in a batch, every name whose core name CONTAINS the chain's core name, or is a
close spelling of it (difflib ratio ≥ 0.85), becomes one row (case variants combined).

Each row carries Claude's suggestion (brand = show as a branch of that chain; separate = its
own restaurant) and a one-line reason. Saif fills saif_decision (brand / separate) and may put a
different brand name in saif_brand.

Brand grouping is a DEMO assumption made from names: OSM does not record ownership, so being
grouped under one brand is not a claim that places are officially related.

Output: data/reference/chain_mapping.csv. Rerunning keeps Saif's existing decisions and adds new batches.

Run from the project root:
    .venv\\Scripts\\python data_pipeline\\make_chain_review.py
"""

import csv
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from detect_chains import contains_tokens, core_name, normalise
from geo import metres

ROOT = Path(__file__).resolve().parent.parent
PLACES = ROOT / "data" / "processed" / "places_clean.csv"
AREAS = ROOT / "data" / "reference" / "localities.csv"
OUT = ROOT / "data" / "reference" / "chain_mapping.csv"
SPELLING_RATIO = 0.85

# batch → {chain display name: [core-name forms to search for]}
BATCHES = {
    1: {"Paradise": ["paradise"], "Mehfil": ["mehfil"], "Kritunga": ["kritunga"], "Pista House": ["pista house"]},
    2: {"Bawarchi": ["bawarchi"], "Santosh Dhaba": ["santosh dhaba", "santhosh dhaba", "santosh dabha", "santosh daba"]},
    3: {"Swagath": ["swagath"], "Sitara": ["sitara"], "Surabhi": ["surabhi"], "Minerva": ["minerva"],
        "Niloufer": ["niloufer", "nilofer"]},
    4: {"Chutneys": ["chutneys"], "Hot Chips": ["hot chips"], "Blue Fox": ["blue fox"], "Lucky": ["lucky"],
        "Bahar": ["bahar"], "Bowl O China": ["bowl o china"], "Nandini": ["nandini"], "Sarvi": ["sarvi"],
        "Chocolate Room": ["chocolate room"]},
    5: {"Abhiruchi": ["abhiruchi"], "Akshaya": ["akshaya"], "Ali": ["ali"], "Barbeque Nation": ["barbeque nation"],
        "Godavari Ruchulu": ["godavari ruchulu"], "Lassi Shop": ["lassi shop"], "Palamuru Grill": ["palamuru grill"],
        "Pizza Corner": ["pizza corner"], "Study Sip": ["study sip"], "Zam Zam": ["zam zam"]},
    # 6: every remaining two-place core name → separate by default (Saif, 2026-09-30; exact core match only)
    6: {n: [n] for n in [
        "4 seasons", "am pm", "angaara", "anupama", "arya bhavan", "astoria", "big dosa", "chick blast",
        "churrolto", "conçu", "coronation", "cream stone", "crown", "drunken monkey", "dwaraka", "flechazo",
        "frenchie", "hyderabad house", "istanbul authentic doner kebab", "laya", "madina", "mandi 36", "mumtaz",
        "ohri s", "president dhaba", "raghavendra tiffins", "rayalaseema ruchulu", "red bucket biryani",
        "reddy s tiffin center", "rumaan", "sai darshini", "seasons", "spicy hub", "swathi tiffins", "sweekar",
        "tea time", "turning point", "vibrant living", "vistari kitchen", "zeeshan"]},
    # 7: chains whose records carry an OSM brand tag (brand / brand:wikidata)
    7: {"Domino's": ["domino s"], "Cafe Coffee Day": ["coffee day"], "KFC": ["kfc"], "Subway": ["subway"],
        "McDonald's": ["mcdonald s"], "Pizza Hut": ["pizza hut"], "Burger King": ["burger king"],
        "Starbucks": ["starbucks"], "Taco Bell": ["taco bell"], "Barista": ["barista"], "Chai Point": ["chai point"],
        "Dunkin'": ["dunkin"], "Just Bake": ["just bake"], "California Burrito": ["california burrito"]},
    # 8: generic descriptors that look like chains but are not brands (exact core match only)
    8: {n: [n] for n in ["fast food", "fast food centre", "tiffin center", "canteen", "irani", "udipi"]},
}
# Batches whose rows are found by EXACT core name only (a "contains" search for "crown" or "irani"
# would pull in dozens of unrelated names), and the suggestion every such row gets.
EXACT_BATCHES = {
    6: ("separate", "", "Two-place name: separate by default under the rule of thumb (D-011)"),
    8: ("separate", "", "Generic descriptor (a kind of shop, not a business name): never a brand (D-011)"),
}

# normalised name → (suggestion, brand, reason)
SUGGESTIONS = {
    # Paradise
    "paradise": ("brand", "Paradise", "The chain's own name; 7 places spread across the city (Charminar to HITEC City)"),
    "paradise hotel": ("brand", "Paradise", "The Secunderabad flagship we kept in 2b (links to Wikipedia)"),
    "paradise secunderabad": ("brand", "Paradise", "Names the Secunderabad outlet; it's 14 m from Paradise Hotel, so the post-2c duplicate check should merge them"),
    "paradise biryani": ("brand", "Paradise", "'Paradise Biryani' is the chain's full name"),
    "paradise biriyani": ("brand", "Paradise", "Spelling variant of 'Paradise Biryani'"),
    "paradise takeaway": ("brand", "Paradise", "Takeaway outlet named after the chain"),
    "paradise take away": ("brand", "Paradise", "Same as 'Paradise Takeaway', spelled with a space"),
    "paradise restaurant": ("brand", "Paradise", "Chain name plus a generic word; lower confidence, but nothing suggests another business"),
    "hotel paradise": ("separate", "", "'Hotel X' word order is typical of independent eateries; no brand tag. Lower confidence"),
    "amrutha paradise": ("separate", "", "Different leading name ('Amrutha'); 'paradise' is just part of its name"),
    "metro paradise": ("separate", "", "Different leading name ('Metro')"),
    "hotel persis paradise": ("separate", "", "'Persis' is its own name; 30 m from Paradise, so likely named after the Paradise junction"),
    # Mehfil
    "mehfil": ("brand", "Mehfil", "The chain's own name; 6 places across the city"),
    "mehfil restaurant": ("brand", "Mehfil", "Chain name plus 'Restaurant'"),
    "mehfil mandi house": ("separate", "", "A different format ('Mandi House'); no evidence it belongs to the Mehfil chain"),
    # Kritunga
    "kritunga": ("brand", "Kritunga", "The chain's own name; 7 places"),
    "kritunga restaurant": ("brand", "Kritunga", "Chain name plus 'Restaurant'; 4 places"),
    "kritugua": ("brand", "Kritunga", "One-letter typo of Kritunga; 346 m from the nearest Kritunga, so a separate outlet, not a duplicate"),
    # Pista House
    "pista house": ("brand", "Pista House", "The chain's own name; 4 places (only case differs)"),
    # Bawarchi ("cook"): a common word, so plain-Bawarchi names are NOT treated as one chain (D-011: when unsure → separate)
    "bawarchi": ("separate", "", "'Bawarchi' means 'cook' and is used by unrelated restaurants; no brand tags; can't tell which of the 4 share an owner"),
    "bawarchi restaurant": ("separate", "", "Same reason as plain 'Bawarchi'; 2 places 2.6 km apart with different cuisine tags"),
    "bawarchi hotel": ("separate", "", "Same reason as plain 'Bawarchi'"),
    "cafe bawarchi": ("separate", "", "Same reason as plain 'Bawarchi'"),
    "bawarchi ac": ("separate", "", "Same reason. NOTE: 55–57 m from the phone-numbered Bawarchi, so it may be its A/C section; just outside the 50 m duplicate range"),
    "bawarchi resturant": ("separate", "", "Typo of 'Restaurant'. NOTE: 30 m from 'green bawarchi restaurant', so possibly the same place"),
    "bawarichi": ("separate", "", "Typo of 'Bawarchi'; same reason as plain 'Bawarchi'"),
    "green bawarchi": ("brand", "Green Bawarchi", "A distinctive two-word name repeated at 3 places in different areas → its own chain, not 'Bawarchi'"),
    "green bawarchi restaurant": ("brand", "Green Bawarchi", "'Green Bawarchi' plus 'Restaurant'"),
    "hi tech bawarchi": ("brand", "Hi-Tech Bawarchi", "A distinctive name at 2 Madhapur places 466 m apart → its own chain"),
    "hitech bawarchi": ("brand", "Hi-Tech Bawarchi", "Spelling variant; 14 m from a Hi-Tech Bawarchi, so the post-2c duplicate check should merge them"),
    "hi tech bawarchi multi cuisine restaurant": ("brand", "Hi-Tech Bawarchi", "Full name form of Hi-Tech Bawarchi (Gachibowli; has a phone number)"),
    "brothers bawarchi": ("separate", "", "Own leading name ('Brothers')"),
    "gold bawarchi": ("separate", "", "Own leading name ('Gold')"),
    "grand spicy bawarchi": ("separate", "", "Own leading name ('Grand Spicy')"),
    "madhapur bawarchi": ("separate", "", "Named after its locality; 100 m from a Hi-Tech Bawarchi but no evidence they're linked"),
    "meeraj bawarchi": ("separate", "", "Own leading name ('Meeraj')"),
    # Santosh Dhaba: spelling variants of the plain name join; "Family" and other forms are kept apart (when unsure → separate)
    "santosh dhaba": ("brand", "Santosh Dhaba", "The chain's own name; 3 places (Gachibowli, Nallakunta, Uppal)"),
    "santhosh dhaba": ("brand", "Santosh Dhaba", "Common spelling variant (Santosh/Santhosh)"),
    "santosh dabha": ("brand", "Santosh Dhaba", "'Dabha' is a transposed spelling of 'Dhaba'; 2 places 513 m apart"),
    "santosh daba": ("brand", "Santosh Dhaba", "'Daba' = 'Dhaba' missing an 'h'; 444 m from 'Santhosh Dhaba' (Abids), so a separate outlet"),
    "santosh dabba": ("separate", "", "'Dabba' means a lunch box, so it could be a different business"),
    "santhosh family dhaba": ("brand", "Santosh Family Dhaba", "'Family Dhaba' may be a different business from Santosh Dhaba → its own brand, not merged into it"),
    "santosh family dhaba": ("brand", "Santosh Family Dhaba", "Same name as the row above, spelled 'Santosh'"),
    "santosh family dabha": ("brand", "Santosh Family Dhaba", "Same name with the 'Dabha' spelling"),
    "shree santhosh family dhaba": ("separate", "", "Own prefix ('Shree'); could be a separate business"),
    # Batch 3 rule of thumb (D-011): brand only if a known Hyderabad chain (verifiable) OR a distinctive
    # name at 3+ places; common words and 2-place names stay separate.
    # Swagath
    "swagath grand": ("brand", "Swagath Grand", "Distinctive two-word name at 5 places in 4 areas (AS Rao Nagar to Kukatpally)"),
    "hotel swagath grand": ("brand", "Swagath Grand", "Same name with a 'Hotel' prefix; 1.3 km from the nearest Swagath Grand"),
    "swagath": ("separate", "", "Plain 'Swagath' ('welcome') is a common word; nothing links it to Swagath Grand"),
    "swagath restaurant": ("separate", "", "Same reason as plain 'Swagath'"),
    # Sitara ("star")
    "sitara": ("separate", "", "'Sitara' ('star') is a common name; 2 places 2.8 km apart with nothing linking them"),
    "sitara grand": ("separate", "", "'Sitara Grand' appears at only 2 places (with the 'Hotel' row) ~20 km apart; under 3, so separate"),
    "hotel sitara grand": ("separate", "", "Same as the row above"),
    "sitara cafe": ("separate", "", "Common name plus 'Cafe'; nothing links it to the others"),
    "sitara foods": ("separate", "", "Common name plus 'Foods'"),
    # Surabhi
    "surabhi restaurant": ("separate", "", "'Surabhi' is a common name; 2 places far apart"),
    "hotel surabhi": ("separate", "", "Common name"),
    "hotel surabhi udupi veg": ("separate", "", "'Surabhi Udupi Veg' is at only 2 places (Uppal, Secunderabad); under 3, so separate"),
    "surabhi udupi veg restaurant": ("separate", "", "Same as the row above"),
    "surabhi bar and restaurant": ("separate", "", "A bar-restaurant: a different format from the Udupi veg places"),
    "surabhi tiffin center": ("separate", "", "A tiffin centre: a different format"),
    # Minerva
    "minerva coffee shop": ("brand", "Minerva Coffee Shop", "Known Hyderabad restaurant chain (general knowledge; please verify like Paradise Uppal)"),
    "minerva coffee house": ("brand", "Minerva Coffee Shop", "'Coffee House' vs 'Coffee Shop'; the same chain name with one word changed (verify)"),
    "minerva": ("separate", "", "Plain 'Minerva' (a café and a restaurant, 2 places); could be the chain or unrelated → unsure"),
    "grand minerva": ("separate", "", "Own leading name ('Grand')"),
    # Niloufer
    "niloufer bakery": ("brand", "Cafe Niloufer", "The original Niloufer café/bakery near Lakdikapul (AC Guards), known in Hyderabad (verify)"),
    "cafe niloufer": ("brand", "Cafe Niloufer", "The chain's own name"),
    "niloufer": ("brand", "Cafe Niloufer", "The chain's name without 'Cafe' (Madhapur)"),
    "nilofer cafe": ("brand", "Cafe Niloufer", "Spelling variant (Nilofer). NOTE: 112 m from Niloufer Bakery, so possibly the same café; outside the 50 m re-run range"),
    "new nilofer": ("separate", "", "'New' usually marks a different business (also kept separate in dedupe review #9)"),
    # Batch 4 (rule of thumb: known chain OR distinctive name at 3+ places)
    "chutneys": ("brand", "Chutneys", "Distinctive name, identical spelling at 7 places (Begumpet to KPHB); south-Indian cuisine tags"),
    "hot chips": ("brand", "Hot Chips", "6 places, all fast food. 'Hot Chips' is a known snack-shop chain name, but it could also be a plain description ⚠ verify"),
    "blue fox": ("brand", "Blue Fox", "Distinctive name at 4 places in 4 areas"),
    "blue fox restaurant": ("brand", "Blue Fox", "'Blue Fox' plus 'Restaurant' (5th place, Himayat Nagar)"),
    "lucky restaurant": ("separate", "", "'Lucky' is a common word; 3 places far apart with nothing linking them"),
    "lucky": ("separate", "", "Common word. NOTE: 27 m from 'Lucky Arabian Mandi', so possibly the same place"),
    "lucky arabian mandi": ("separate", "", "Own format ('Arabian Mandi'); see the note on plain 'lucky'"),
    "lucky chicken mutton shop": ("separate", "", "A meat/chicken shop, a different format"),
    "lucky hotel": ("separate", "", "Common word"),
    "lucky resturant": ("separate", "", "Common word ('Resturant' typo)"),
    "luckys": ("separate", "", "Common word"),
    "cafe bahar": ("brand", "Cafe Bahar", "Known Hyderabad restaurant (Hyderguda) with another outlet in Ameerpet ⚠ verify"),
    "bahar cafe": ("separate", "", "Word order reversed ('Bahar Cafe'), and 'Bahar' ('spring') is a common name → unsure"),
    "bahar café": ("separate", "", "Same as 'Bahar Cafe' (accented é)"),
    "bowl o china": ("brand", "Bowl O China", "Distinctive name at 4 places (only punctuation differs); Chinese cuisine"),
    "cafe nandini": ("brand", "Cafe Nandini", "Distinctive name at 4 places (Banjara Hills, Begumpet, Gachibowli, Jubilee Hills)"),
    "sarvi restaurant": ("brand", "Sarvi", "'Sarvi' is a distinctive name at 4 places, all around Masab Tank / Mehdipatnam / Khairatabad"),
    "sarvi cafe": ("brand", "Sarvi", "Same Sarvi cluster (Masab Tank; 884 m from Sarvi Restaurant)"),
    "cafe sarvi": ("brand", "Sarvi", "Same Sarvi cluster (Khairatabad)"),
    "sarvi hotel": ("brand", "Sarvi", "Same Sarvi cluster (Mehdipatnam)"),
    "chocolate room": ("brand", "The Chocolate Room", "Dessert-café name at 4 places together with the 'The' rows; cuisine chocolate/waffles"),
    "the chocolate room": ("brand", "The Chocolate Room", "Same name with 'The'"),
    # Batch 5 (3-place local chains)
    "abhiruchi": ("separate", "", "'Abhiruchi' ('taste') is a common restaurant word; nothing links the places"),
    "abhiruchi restaurant": ("separate", "", "Same reason (966 m from an 'Abhiruchi')"),
    "hotel akshaya": ("separate", "", "'Akshaya' is a common name; 2 places 1.9 km apart"),
    "akshaya": ("separate", "", "Common name"),
    "ali cafe": ("separate", "", "'Ali' is a very common name; nothing links the places"),
    "ali star hotel": ("separate", "", "Own full name; 'Ali' is common"),
    "new ali cafe": ("separate", "", "'New' plus a common name"),
    "yaqoob ali cafe": ("separate", "", "Own full name ('Yaqoob Ali')"),
    "barbeque nation": ("brand", "Barbeque Nation", "National barbecue chain; one record carries its official brand tag"),
    "barbeque nation banjara hills": ("brand", "Barbeque Nation", "Chain name plus its outlet area"),
    "godavari ruchulu": ("separate", "", "Descriptive name ('flavours of Godavari') used by unrelated Andhra eateries → unsure"),
    "krishna godavari ruchulu": ("separate", "", "Same descriptive pattern with its own name"),
    "lassi shop": ("brand", "Lassi Shop", "One record has an official 'Lassi Shop' brand tag, so it's a chain name; could also be a plain description ⚠ verify"),
    "palamuru grill": ("brand", "Palamuru Grill", "Distinctive name at 3 places (Attapur, Izzat Nagar, LB Nagar); grill/kebab cuisine"),
    "palamuri grill": ("brand", "Palamuru Grill", "One-letter spelling variant; 2.8 km from the nearest, so a separate outlet"),
    "pizza corner": ("brand", "Pizza Corner", "Known Indian pizza chain name at 3 places, all tagged pizza; could also be a plain description ⚠ verify"),
    "the study sip": ("separate", "", "NOT a chain: all 4 records say 'Near SIT building', door 99, same description → one café mapped 4 times (manual-dedupe candidate)"),
    "zam zam": ("separate", "", "'Zam Zam' is a very common name; nothing links the places"),
    "zam zam cafe": ("separate", "", "Same reason"),
    "zam zam hotel": ("separate", "", "Same reason"),
    # Batch 7 (brand-tagged chains: OSM brand / brand:wikidata tags confirm the chain)
    "domino s": ("brand", "Domino's", "The chain's own name; brand-tagged in OSM"),
    "domino s pizza": ("brand", "Domino's", "'Domino's Pizza' is the chain's full name"),
    "mc domino s": ("separate", "", "Mixes two chain names ('Mc' + 'Domino's'), no brand tag → unsure which, if either"),
    "cafe coffee day": ("brand", "Cafe Coffee Day", "The chain's own name; brand-tagged in OSM"),
    "cafe coffe day": ("brand", "Cafe Coffee Day", "One-letter typo ('Coffe') of the chain's name"),
    "coffee day": ("brand", "Cafe Coffee Day", "The chain's name without 'Cafe'"),
    "kfc": ("brand", "KFC", "The chain's own name; brand-tagged in OSM"),
    "kfc lb nagar": ("brand", "KFC", "Chain name plus its outlet area"),
    "kfc next galleria mall": ("brand", "KFC", "Chain name plus its outlet (brand-tagged)"),
    "kfc sindhi colony": ("brand", "KFC", "Chain name plus its outlet (brand-tagged)"),
    "subway": ("brand", "Subway", "The chain's own name; brand-tagged in OSM"),
    "mcdonald s": ("brand", "McDonald's", "The chain's own name; brand-tagged in OSM"),
    "mc donalds": ("brand", "McDonald's", "Spelling variant of McDonald's"),
    "pizza hut": ("brand", "Pizza Hut", "The chain's own name; brand-tagged in OSM"),
    "burger king": ("brand", "Burger King", "The chain's own name; brand-tagged in OSM"),
    "starbucks": ("brand", "Starbucks", "The chain's own name; brand-tagged in OSM"),
    "taco bell": ("brand", "Taco Bell", "The chain's own name; brand-tagged in OSM"),
    "barista": ("brand", "Barista", "The chain's own name; brand-tagged in OSM"),
    "barista lavazza": ("brand", "Barista", "The chain's former name (it was 'Barista Lavazza' under Lavazza ownership)"),
    "chai point": ("brand", "Chai Point", "The chain's own name; brand-tagged in OSM"),
    "dunkin": ("brand", "Dunkin'", "The chain's own name; brand-tagged in OSM"),
    "just bake": ("brand", "Just Bake", "The chain's own name; one record brand-tagged in OSM"),
    "california burrito": ("brand", "California Burrito", "The chain's own name; brand-tagged in OSM"),
    "california burrito next galleria mall": ("brand", "California Burrito", "Chain name plus its outlet (brand-tagged)"),
}

FIELDS = ["batch", "chain", "row", "name_normalised", "names_as_written", "places", "nearest_areas", "match",
          "suggestion", "brand", "reason", "saif_decision", "saif_brand", "reviewed_by", "saif_note"]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    with PLACES.open(encoding="utf-8-sig", newline="") as f:
        places = list(csv.DictReader(f))
    with AREAS.open(encoding="utf-8-sig", newline="") as f:
        areas = list(csv.DictReader(f))

    def nearest_area(p: dict) -> str:
        pt = (float(p["lat"]), float(p["lon"]))
        return min(areas, key=lambda a: metres(pt, (float(a["lat"]), float(a["lon"]))))["display_name"]

    by_norm = defaultdict(list)
    for p in places:
        by_norm[normalise(p["name"])].append(p)

    existing = {}
    if OUT.exists():
        with OUT.open(encoding="utf-8-sig", newline="") as f:
            existing = {(r["chain"], r["name_normalised"]): r for r in csv.DictReader(f)}

    rows, missing = [], []
    for batch, chains in BATCHES.items():
        for chain, forms in chains.items():
            found = []
            for norm, ps in by_norm.items():
                core = core_name(norm)
                if batch in EXACT_BATCHES:
                    if core not in forms:
                        continue
                    match = "exact"
                elif any(contains_tokens(core.split(), f.split()) for f in forms):
                    match = "contains"
                elif any(SequenceMatcher(None, f, core).ratio() >= SPELLING_RATIO for f in forms):
                    match = "spelling"
                else:
                    continue
                found.append((norm, ps, match))
            for norm, ps, match in sorted(found, key=lambda x: (-len(x[1]), x[0])):
                s = EXACT_BATCHES.get(batch) or SUGGESTIONS.get(norm)
                if s is None:
                    missing.append(norm)
                    continue
                old = existing.get((chain, norm), {})
                rows.append({
                    "batch": batch, "chain": chain, "row": len(rows) + 1, "name_normalised": norm,
                    "names_as_written": "; ".join(f"{n} ×{c}" for n, c in Counter(p["name"] for p in ps).most_common()),
                    "places": len(ps), "nearest_areas": "; ".join(sorted({nearest_area(p) for p in ps})), "match": match,
                    "suggestion": s[0], "brand": s[1], "reason": s[2],
                    "saif_decision": old.get("saif_decision", ""), "saif_brand": old.get("saif_brand", ""),
                    "reviewed_by": old.get("reviewed_by", ""), "saif_note": old.get("saif_note", ""),
                })
    if missing:
        print(f"No suggestion written yet for: {missing}. Nothing saved.")
        return 1

    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    for b in BATCHES:
        br = [r for r in rows if r["batch"] == b]
        print(f"Batch {b}: {len(br)} rows ({sum(r['suggestion'] == 'brand' for r in br)} brand, "
              f"{sum(r['suggestion'] == 'separate' for r in br)} separate), "
              f"{sum(1 for r in br if r['saif_decision'])} already decided")
    print(f"Saved {OUT.relative_to(ROOT)}. Nothing merged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
