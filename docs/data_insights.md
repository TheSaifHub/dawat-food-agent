# Dawat — Data Insights (Phase 1)

What OpenStreetMap actually gives us for Hyderabad, measured before any cleaning.

- **Snapshot:** `data/raw/overpass_hyderabad_2026-09-30.json`, OSM data as of **2026-09-30 04:20:45 UTC**, fetched in one request (read-only; sha256 in its `.meta.json`).
- **Area:** everything inside OSM relation **7868535**, selected by ID (DECISIONS.md D-005).
- **Sources for every number below:** `results/eda/stats.json` (module 2, `profile_osm.py`) and `results/eda/chains.json` (module 3, `detect_chains.py`). Charts are in `results/eda/` (module 4, `plot_eda.py`). Two exceptions: the colour check is recorded in the `plot_eda.py` docstring, and fetch details are in DECISIONS.md D-007.
- **Audit:** every number was re-checked by the `data-auditor` sub-agent on 2026-09-30, against these files and by recomputing independently from the raw snapshot. First pass: all numbers correct, 8 wording overclaims, all fixed. Second pass: PASS.
- Percentages are of the **1,538 food places** unless stated otherwise.

Data © OpenStreetMap contributors, available under the ODbL.

---

## Top findings

1. **OSM has almost no area information, so areas must come from coordinates.**
   - `addr:suburb` is on **0** food places (0.0%).
   - Any area-like tag appears on only **31** (2.0%), and those are `addr:district` values naming districts or the state (e.g. "Hyderabad" ×17, "Rangareddy" ×5, "Telangana" ×2), not neighbourhoods.
   - A handful of `addr:city` values do contain a locality name (e.g. "Vanasthaslipuram,Hyderabad" ×5, "Uppal, Hyderabad" ×4). That's a small extra area signal for Phase 2.
   - In Phase 2, almost every branch's area will come from the nearest-locality fallback, which makes `data/reference/localities.csv` a critical input.

2. **Names are reliable; almost everything else is thin.**

   | Tag | Places | Share |
   |---|---|---|
   | name | 1,377 | 89.5% |
   | cuisine | 581 | 37.8% |
   | any address tag | 287 | 18.7% |
   | postcode | 198 | 12.9% |
   | brand | 154 | 10.0% |
   | Telugu name (`name:te`) | 90 | 5.9% |

   Most places will need their cuisine inferred from their name.

3. **About a third of named places belong to a "chain", but local chains are messy.**
   - **113** core names appear at 2+ places, covering **446** places (**32.4%** of named places).
   - **The big international chains are mostly brand-tagged:** Domino's 33 of 34 places, KFC 23 of 23, McDonald's 14 of 14, Subway 14 of 15. Pizza Hut is only 7 of 11.
   - **The local chains in the top 15 have no brand tags** (Paradise 0 of 15, Kritunga 0 of 11, Bawarchi 0 of 9, Mehfil 0 of 9) and appear under several name forms, mostly differences in case or added words like "Restaurant" or "Hotel".
   - Grouping local chains therefore depends on name matching plus human review.

4. **Some "branches" are probably the same place mapped twice.**
   - **39** pairs of same-name places sit within 50 m of each other, across **31** chains. Median distance: **13.3 m**; minimum: **0.0 m**.
   - **12** of these pairs are a map pin plus a building outline, a pattern that often means one place drawn twice. None of the pairs has been checked by hand yet.
   - Raw chain counts may therefore be inflated until Phase 2 deduplicates.

5. **Places are spread across the boundary, unevenly** (partly a visual observation).
   - All **1,538** food places have coordinates, and all fall inside the boundary's bounding box (100.0%). That check is expected to pass, since the query only asked for places inside the boundary.
   - *Visual observation from the map, not a measurement:* places look densest in the west-central area and in a central belt, and sparse in the south and the northern parts of the boundary.
   - The west-central cluster lies around the HITEC City and Madhapur coordinates checked in module 1a (D-005); no neighbourhood has been assigned to any place yet.

6. **The mix is mostly restaurants.** Restaurant **916**, fast food **332**, café **290**. A further **15** `internet_cafe` elements were caught by the original, unanchored query and are excluded here (D-007).

7. **Cuisine tags are messy but informative.**
   - **124** distinct values; **142** places list more than one (e.g. `indian;biryani`).
   - Most common: indian (173), regional (91), coffee_shop (88), chicken (83), pizza (82).
   - "regional" is vague and needs a mapping rule in Phase 2.

---

## Details

### Population (`stats.json → population`)
| | Count |
|---|---|
| All elements in the snapshot | 1,553 |
| restaurant | 916 |
| fast_food | 332 |
| cafe | 290 |
| internet_cafe (excluded, D-007) | 15 |
| **Food places** | **1,538** |
| …mapped as a single point (node) | 1,374 |
| …mapped as a shape (way; its centre point is used) | 164 |

### Tag coverage (`stats.json → coverage_of_food_places`)
| Tag | Places | Share |
|---|---|---|
| name | 1,377 | 89.5% |
| cuisine | 581 | 37.8% |
| any `addr:*` tag | 287 | 18.7% |
| addr:street | 248 | 16.1% |
| addr:postcode | 198 | 12.9% |
| addr:city | 198 | 12.9% |
| opening_hours | 160 | 10.4% |
| brand | 154 | 10.0% |
| name:te (Telugu) | 90 | 5.9% |
| name:en | 86 | 5.6% |
| any area-like tag | 31 | 2.0% |
| addr:district | 31 | 2.0% |
| addr:suburb / neighbourhood / quarter / place | 0 | 0.0% |

**Places without a name:** 1,538 − 1,377 = **161**. They're dropped in Phase 2, because an unnamed place can't be shown to a user.

**Address values** (`stats.json → address_values`):
- `addr:city` has **23** distinct values. Most places' values are spellings of Hyderabad ("Hyderabad" ×126, "hyderabad" ×28, "HYDERABAD" ×7, "Hyderbad" ×2) or Secunderabad. Several others are locality names ("Uppal, Hyderabad", "Kukatpally", "LB Nagar, Hyderabad", …), which is a small extra area signal.
- `addr:postcode` has **54** distinct values as written. That drops to **51** once spaces are removed ("500 003" = "500003"), and **50** are valid 6-digit PIN codes. Postcode could serve as a secondary area signal for the 12.9% of places that have one, after this normalisation.

### Cuisine (`stats.json → cuisine`)
**124** distinct values; **142** places list more than one. Top 15:

| Cuisine | Places | Cuisine | Places | Cuisine | Places |
|---|---|---|---|---|---|
| indian | 173 | burger | 55 | italian | 17 |
| regional | 91 | chinese | 54 | barbecue | 17 |
| coffee_shop | 88 | sandwich | 39 | juice | 16 |
| chicken | 83 | kebab | 38 | steak_house | 13 |
| pizza | 82 | ice_cream | 34 | tea | 13 |

### Chains (`chains.json → summary`, `top_chains`)
**Method:**
- Names are normalised: lower case, punctuation removed, "&" read as "and".
- A **core name** also ignores generic words (hotel, restaurant, cafe, the, family, takeaway, …).
- A **chain** is a core name shared by 2+ named food places.
- **Counting only.** Nothing was merged.

| | Count |
|---|---|
| Named food places | 1,377 |
| Distinct names, as written (case and punctuation ignored) | 1,099 (96 appear 2+ times) |
| Distinct core names | 1,044 |
| **Chains (2+ places)** | **113** |
| Places in chains | 446 (32.4% of named) |
| Chains with exactly 2 places | 66 |

**Top 15 chains** (raw counts, before review and deduplication):

| # | Chain | Places | With brand tag | Same-spot pairs (≤50 m) |
|---|---|---|---|---|
| 1 | Domino's | 34 | 33 | 1 |
| 2 | Cafe Coffee Day | 26 | 21 | 1 |
| 3 | KFC | 23 | 23 | 0 |
| 4 | Paradise | 15 | 0 | 4 |
| 5 | Subway | 15 | 14 | 0 |
| 6 | McDonald's | 14 | 14 | 0 |
| 7 | Kritunga | 11 | 0 | 0 |
| 8 | Pizza Hut | 11 | 7 | 0 |
| 9 | Bawarchi | 9 | 0 | 3 |
| 10 | Mehfil | 9 | 0 | 1 |
| 11 | Chutneys | 8 | 0 | 1 |
| 12 | Burger King | 6 | 6 | 0 |
| 13 | Hot Chips | 6 | 0 | 0 |
| 14 | Starbucks | 6 | 6 | 0 |
| 15 | Swagath Grand | 6 | 0 | 0 |

**Why name matching alone isn't enough:**
- A simple "name contains" search (`stats.json → chain_name_preview`) finds **21** places for "paradise", but only **15** share the chain's core name. The rest include names like "Hotel Persis Paradise" that are probably unrelated.
- Likewise "mehfil" finds **10** places, while the Mehfil chain has **9**.
- `results/eda/chain_review.csv` lists **120** ambiguous-name rows and **42** possible-spelling-variant rows (`chains.json → summary`) for review in Phase 2.
- Some groups are generic descriptions, not brands (e.g. "Fast Food", "canteen", "tiffin center"), and must not become brands.

**Two well-known names barely appear:** Pista House matches **4** places (1 with a brand tag); Shah Ghouse matches **1**, so it isn't a chain in this data.

### Possible double-mapping (`chains.json → summary`)
| | Count |
|---|---|
| Same-name pairs within 50 m | 39 |
| …pin + pin | 26 |
| …pin + building outline | 12 |
| …outline + outline | 1 |
| Chains affected | 31 |
| Distance: minimum / median | 0.0 m / 13.3 m |

---

## Charts (`results/eda/`)
| File | What it shows |
|---|---|
| `map_places_by_type.png` | Every food place as a dot, coloured by type, over the grey outline of relation 7868535 |
| `places_by_type.png` | Restaurants vs fast food vs cafés |
| `tag_coverage.png` | Share of places with each tag, from name (89.5%) down to suburb (0.0%) |
| `top_cuisines.png` | The 15 most common cuisine values |
| `top_chains.png` | The 15 largest chains by raw place count |

Colours: restaurant blue, fast food orange, café aqua, the same in every chart.
- **Colour-blind check:** the three were checked on 2026-09-30 with the dataviz skill's palette validator (`validate_palette.js --pairs all`, light surface). All checks passed; the worst colour-blind separation was ΔE 9.2, against a target of 8 or more.
- **Contrast:** café aqua is below 3:1 contrast on the background, so every chart also names the types in text.
- The result is recorded in `data_pipeline/plot_eda.py`.

---

## Limitations
- **OSM only knows what volunteers have mapped.**
  - Absence in this data does not mean absence in the city.
  - Pista House (4 places) and Shah Ghouse (1) are well-known local names but barely appear; their real branch counts are **not** known from this data.
  - Treat every count here as "mapped in OSM", not "exists in Hyderabad".
- **Sparse south and north:** the map shows few places in the south and the northern parts of the boundary. That is a visual observation, not a measurement, and this data cannot tell whether those areas have fewer eateries or have simply been mapped less.
- **No area tags:** `addr:suburb` is 0.0%. Every area in the app will be *derived* (nearest locality), not taken from OSM, and its accuracy depends on `localities.csv`.
- **Chain counts are raw:**
  - They come before the Phase 2 review and deduplication.
  - They may include double-mapped places (39 pairs within 50 m).
  - They may include unrelated places sharing a generic name, and miss branches written differently ("Paradise Biryani" is flagged for review, not counted).
- **Double-mapping is unconfirmed:** the 39 close pairs are candidates only. None has been checked by hand, so some may be genuinely adjacent outlets.
- **Thin attributes:** cuisine is known for only 37.8% of places; the rest will be inferred, which is less reliable.
- **Messy address values:** postcodes and city names need normalising before use (spaces inside PINs, one malformed value, locality names inside `addr:city`).
- **One point in time:** a single snapshot, with OSM data as of 2026-09-30 04:20:45 UTC. OSM changes daily; this data will not.
- **Boundary:** relation 7868535 is used as "Hyderabad". It has not been verified to match the legal GHMC limits exactly (D-005).
- **Tags as given:** categories reflect mappers' choices. For example, some places named "Hotel" are tagged as cafés; no tag was corrected in Phase 1.

## What this means for Phase 2
See `docs/phase2_backlog.md`. In short:
1. Build `localities.csv` (idea: fetch `place=suburb/neighbourhood` points inside relation 7868535 in one request).
2. Drop the 15 internet cafés and the 161 unnamed places.
3. Agree a dedupe rule for the 39 close pairs.
4. Review the chain names.
5. Map "regional" and infer missing cuisines.

## Reproduce
From the project root, with the pinned `data_pipeline/requirements.txt` installed:
```
.venv\Scripts\python data_pipeline\profile_osm.py     # → results/eda/stats.json
.venv\Scripts\python data_pipeline\detect_chains.py   # → results/eda/chains.json, chain_review.csv
.venv\Scripts\python data_pipeline\plot_eda.py        # → results/eda/*.png
```
All three verify the raw snapshot's sha256 before reading it, and none of them modify `data/raw/`.
