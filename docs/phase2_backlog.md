# Phase 2 backlog (Cleaning & Enrichment)

> **Status 2026-09-30: all items below are resolved. Phase 2 is complete.** See DECISIONS.md D-008 to D-015, `results/cleaning/clean_log.json` and `results/cleaning/enrich_log.json`. Items for later phases moved to `docs/backlog.md`. The text below is kept as the original Phase 1 hand-off.

Items found during Phase 1 to handle in Phase 2. Each needs Saif's review or approval where noted. Numbers come from `results/eda/stats.json` and `results/eda/chains.json` (snapshot `overpass_hyderabad_2026-09-30.json`).

## Areas / localities
- **Idea (Saif, 2026-09-30):** build `data/reference/localities.csv` by fetching neighbourhood points (`place=suburb` / `place=neighbourhood`) inside relation 7868535 from OSM, instead of typing coordinates by hand.
  - One Overpass request, following the fetch rules: status check first, no retries (CLAUDE.md, D-005, D-006).
  - Save it as its own read-only raw snapshot with a `.meta.json`, like the restaurant fetch.
  - Review the result before using it: missing major areas, duplicate names, spelling.
  - **Not done yet. Needs Saif's go-ahead.**
- **Why it matters:** `addr:suburb` is present on **0** food places, and `any_area_tag` on only 31 (2.0%, and those are district-level values like "Hyderabad" or "Rangareddy"). So almost every branch's area will come from the nearest-locality fallback, which makes `localities.csv` a critical input.
- **Possible secondary signals:**
  - `addr:postcode` is present on 198 places (12.9%). It has 54 distinct raw values, 51 after removing spaces, and 50 valid 6-digit PINs. Normalise before use.
  - A few `addr:city` values contain a locality name ("Uppal, Hyderabad", "Kukatpally", "Vanasthaslipuram,Hyderabad", …). These could cross-check the nearest-locality result. (Found by the data-auditor, 2026-09-30.)

## Rows to remove (log each count)
- `amenity=internet_cafe`: **15** rows (D-007).
- Places with no `name`: **161** (1,538 − 1,377).
- Exact duplicates: define "exact" first. Chain detection found **39 close pairs (≤50 m)** within same-name groups:
  - 12 node+way pairs, likely one place mapped both as a pin and as a building
  - 26 node+node pairs
  - 1 way+way pair
  - median distance 13 m, minimum 0 m
  
  The dedupe rule needs Saif's approval (e.g. same core name and ≤ X m).

## Dedupe follow-up (Saif, 2026-09-30, D-010)
- **Manual-dedupe list:** `data/reference/manual_dedupe.csv` holds cross-name pairs the brand-based re-run can't compare (M1 Bawarchi Ac ~ Bawarchi 56.7 m, M2 Bawarchi Resturant ~ green bawarchi restaurant 30.1 m). Saif decides these together with whatever the re-run finds.
- **After module 2c (chain mapping), re-run the duplicate check on the mapped brand names**, not just the raw core names, so alias duplicates like "CCD" / "Cafe Coffee Day" at the same spot are caught too. Same rules apply: ≤15 m auto-merge, 15–50 m or generic names to Saif's review.

## Chain mapping (reviewed, not blind merging)
- Review file: `results/eda/chain_review.csv`. It has 120 "ambiguous: contains a chain's name" rows (e.g. "Hotel Persis Paradise", "Mehfil Mandi House", "Paradise Biryani") and 42 "possible spelling variant" rows (e.g. "Kritugua", "Bawarichi", Santosh/Santhosh Dhaba). Saif decides each; the decisions go into `data/reference/chain_mapping.csv`.
- **Generic "chains" to reject:** some 2+ groups are generic descriptors, not brands (e.g. "fast food", "canteen", "tiffin center", "kabab", "irani", "udipi"). They must not become brands.
- The generic-word list used for core names is in `detect_chains.py` (`GENERIC_WORDS`). Review it too.

## Cuisine
- Coverage is 37.8%. The rest is classified from name keywords (biryani, bakery, dhaba, …), otherwise "multi-cuisine" (CLAUDE.md Phase 2).
- **"regional"** (91 places) is vague in OSM. Decide what it maps to.
- Cuisine values can be lists (`indian;biryani`; 142 places) and need normalising.

## Tag noise (low priority)
- `addr:city` has 23 spellings of mostly the same city (Hyderabad/hyderabad/HYDERABAD/Hyderbad…). Probably just ignore it; it isn't needed for areas.
