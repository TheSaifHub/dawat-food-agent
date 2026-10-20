# Dawat — Session Log

Read this in full at the start of every session (on `start`).

---

## Session 1 — Phase 0 (Setup), complete
- **Start:** 2026-09-29 ~18:55 IST (approximate, taken from the first file activity)
- **End:** 2026-09-29 21:34 IST

### What was done
1. **Repo skeleton:** `backend/`, `frontend/`, `data_pipeline/`, `data/{raw,reference,processed}/`, `evals/`, `docs/`, `results/eda/`. Root `.gitignore` (secrets, Python, Node, test output, OS files), placeholder `README.md` (demo banner and OSM credit), `DECISIONS.md`. A local `.git` folder was created by `git init` *before* the no-git rule. It is untouched and left for Saif.
2. **Backend:** Python **3.11.9** venv at the root, `.venv/`, shared by backend, pipeline and evals.
   - `backend/requirements.txt` has exact pins (FastAPI 0.141.1, Uvicorn 0.54.0, …). `requirements-dev.txt` adds pytest 9.1.1 and httpx2 2.13.1.
   - `app/main.py` and `app/api/health.py` provide `GET /health`. `app/config.py` reads `ALLOWED_ORIGINS`: comma-separated, `*` refused at startup, blank means `http://localhost:3000`.
   - **14 tests pass** (`backend/tests/`).
   - Run: `cd backend` then `..\.venv\Scripts\python -m uvicorn app.main:app --reload`
3. **Frontend:** Next.js **16.3.7**, React 19.2.8, Tailwind 4, TypeScript, App Router, `src/` folder, scaffolded with `--disable-git`.
   - Exact npm pins plus `.npmrc` `save-exact=true`.
   - Brand tokens (plum, gold, ivory, night) and fonts (Cormorant Garamond, DM Sans). Demo banner and OSM attribution in the layout.
   - `BackendStatus` component calls `/health` from the browser.
   - `frontend/.gitignore` fixed so `.env.example` isn't ignored.
   - **Saif verified in his browser:** green dot, banner and fonts all showing.
   - Next 16 ships `frontend/AGENTS.md` telling agents to read `node_modules/next/dist/docs/` before writing Next code. Keep following it.
4. **`.env.example` files:**
   - Backend has 10 variables, tagged `[SECRET]` or `[CONFIG]`.
   - Frontend has 4 `NEXT_PUBLIC_*` variables, all `[PUBLIC]`, with a loud "never put a secret in NEXT_PUBLIC_" warning.
   - Blank values now fall back to defaults. Copying an example file unchanged used to crash the backend; that's fixed and tested.
5. **Guard hooks:** `.claude/hooks/guard.py` and `.claude/settings.json`.
   - Blocks git/gh, writes to `data/raw/`, secrets in files or commands, and reading or writing real `.env` files. It also adds a start-of-session reminder, and fails closed if it crashes.
   - 72 tests in `.claude/hooks/test_guard.py`. Each block was demonstrated live.
   - Run tests: `.venv\Scripts\python -m pytest .claude/hooks -q -p no:cacheprovider`

### Decided
- D-001 Python 3.11 · D-002 CORS allow-list from env, never `*` · D-003 guard hooks (see `DECISIONS.md`).
- **No git operations at all.** This is in the CLAUDE.md Session Control section. Saif does git and GitHub manually after the project is complete.
- **Supabase key names:** used the new names (`SUPABASE_SECRET_KEY`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`). Check them against Saif's dashboard in Phase 3.
- **MCP servers and sub-agents approved in principle.** Set each one up only at its phase and remind Saif then:
  - Phases 1–2: `data-auditor` sub-agent
  - Phase 3: Supabase MCP (read-only) and Context7
  - Phases 5, 6 and 10: `rule-breaker`
  - Phase 7: Playwright MCP and `ui-checker`
- **Phase 1 uses scripts, not notebooks.** When showing profiling results, **explain the output in plain words.**

### Open / next session
- **Start Phase 1 with module 1a only (approved): the boundary check.** It's one small Overpass query listing every area named "Hyderabad" (country, admin level). Nothing gets saved to `data/raw/`. Show the list and let **Saif choose the boundary** (Hyderabad district, GHMC, or both).
  - Risk 1: Hyderabad in Pakistan (Sindh) could leak in.
  - Risk 2: the district boundary may exclude Gachibowli, Madhapur, Kondapur and HITEC City.
  - The CLAUDE.md query must not be changed without his decision.
- Then modules 1b–5 as proposed: `fetch_osm.py` (write-once, then mark read-only), `profile_osm.py`, chain counting, charts in `results/eda/`, and `docs/data_insights.md` with the `data-auditor`.
- Pipeline dependencies go in a separate pinned `data_pipeline/requirements.txt`.
- Load the `dataviz` skill before writing any chart code.

### Pending for Saif
- Nothing needed for Phases 1–2.
- Accounts are listed in order of need: Supabase (before Phase 3; Mumbai region), Google AI Studio and Groq (Phase 6), Razorpay test mode (Phase 8), GitHub, Vercel and Render (Phase 10).
- Never paste keys into chat. Put them straight into the `.env` files.

---

## Session 2 — Phase 1: module 1a done, module 1b blocked by the Overpass server
- **Start:** 2026-09-29 ~21:40 IST (approximate; the first Overpass status check was 21:44 IST)
- **End:** 2026-09-29 22:08 IST

### What was done
1. **Module 1a, boundary check: done and approved by Saif.**
   - The CLAUDE.md name filter matched 2 Indian areas: relation 7255986 (Hyderabad District, admin_level 5) and relation 7868535 (Hyderabad, admin_level 8). Hyderabad, Sindh did **not** match.
   - Saif checked 7868535 on openstreetmap.org: it covers HITEC City, Gachibowli, Madhapur and Kondapur, and contains the district.
   - **Confirmed in code** with one request (`data_pipeline/check_boundaries.py`, exit 0): the 4 landmarks and Charminar are inside; the Pakistan control is outside; Secunderabad station is inside (info only). Bounding box: lat 17.292–17.561, lon 78.239–78.622.
   - **DECISIONS.md D-005:** use relation 7868535 only, selected by ID (`area(3607868535)`). The district is dropped as redundant. Caveat: not verified to equal the legal GHMC boundary exactly, so docs call it "OSM relation 7868535".
   - **CLAUDE.md query updated** to `area(3607868535)->.a;`, with notes: never match by name; check `/api/status` first; one request; never retry in a loop.
2. **Module 1b, `data_pipeline/fetch_osm.py`: written, NOT yet successful.**
   - Standard library only. It refuses to run if a snapshot exists (write-once), checks `/api/status` for a free slot, then sends **one** request.
   - It rejects responses with an Overpass `remark` (partial data) or zero elements.
   - It saves the raw bytes unchanged as `data/raw/overpass_hyderabad_<UTC date>.json`, plus `.meta.json` (query, endpoint, fetch time, OSM data timestamp, element count, bytes, sha256), using temp-file-then-rename. Both files are marked read-only (`os.chmod` S_IREAD).
   - It prints how long the request took, to tell an overloaded server from a slow query.
   - **The one attempt got HTTP 504** from overpass-api.de, even though the status page showed 2 free slots. Nothing was saved; `data/raw/` still holds only `.gitkeep`.

### Decided
- D-005 (boundary = relation 7868535, by ID).
- The public Overpass servers were unreliable all evening (504, 429, read timeouts, and the fallback `overpass.private.coffee` timed out). Rule: status check, one request, no loops.

### Open / next session
- **Retry module 1b in the MORNING** (quieter server): `.venv\Scripts\python data_pipeline\fetch_osm.py`, one attempt.
  - **If it fails, try option 3 ONCE:** a single request to a different public instance (`overpass.kumi.systems`). This needs a small change to `fetch_osm.py`: make the endpoint configurable or add a flag, and record the endpoint actually used in `.meta.json`.
- **After a successful fetch, show Saif:** total element count; counts by amenity (restaurant, fast_food, cafe); file size; **5 random sample entries with their tags** (use a fixed seed). Confirm the file is read-only (`attrib`). Explain everything in plain words. **Stop before module 2.**
- Then: module 2 (`profile_osm.py`, with pandas and friends in a pinned `data_pipeline/requirements.txt`), modules 3–5, and the `data-auditor` sub-agent at module 5. Load the `dataviz` skill before any chart.

- **Small follow-up (low priority):** the guard hook gave a false positive on a shell append to `learning.md`, because the heredoc text mentioned the raw folder plus words like "rename". Consider having the shell check ignore quoted or heredoc text, or only match raw paths that are arguments of the mutating command. Add a test for this case. Session-end logs were written with the Edit tool instead.

### Pending for Saif
- Nothing. (Accounts are only needed from Phase 3; see Session 1.)

---

## Session 3 — guard fix done; module 1b still waiting on Overpass
- **Start:** 2026-09-29 22:10 IST (verified with the clock at `start`)
- **End:** 2026-09-29 ~22:30 IST (approximate; the shell was unavailable at `end`, so the clock couldn't be read)

### What was done
1. **Guard false positive fixed** (the Session 2 follow-up is resolved). Changes are in `.claude/hooks/guard.py`:
   - A new `code_view()` removes pure-data text before the git/raw/env rules run: heredoc bodies fed to `cat`/`tee`, and quoted `echo`/`printf` arguments.
   - What stays covered: the redirect target (`cat > data/raw/x <<EOF` is still blocked), heredocs piped onward (`| bash`) or fed to interpreters (`python -`, `bash <<`), a quoted redirect target (`echo {} > "data/raw/a.json"`), and real commands chained after `echo`.
   - The **secret scan still covers the whole command**, prose included.
   - Echo-segment scanning treats quoted strings as whole units. The first run of the new tests caught a `;` inside quotes breaking it; now fixed.
   - **86 guard tests pass** (72 old and 14 new). A live check confirmed that the exact false-positive shape (a cat heredoc to a notes file mentioning the raw folder and "rename") now goes through.
2. **Fetch attempt on `overpass.kumi.systems`: not sent.**
   - Its `/api/status` connected in 0.2 s, then timed out after 30 s with 0 bytes, so no data request was sent (the status-check-first rule).
   - DNS showed `overpass.kumi.systems` is an **alias of `overpass.private.coffee`** (193.219.97.30), the same server as the 1a fallback that timed out.
   - **DECISIONS.md D-006:** treat them as one server, never as independent fallbacks; check DNS before relying on any other public instance.
   - `fetch_osm.py` is unchanged; it targets `overpass-api.de` only.
   - `data/raw/` still holds only `.gitkeep`.

### Decided
- D-006 (kumi = private.coffee, not independent).
- Saif: **no more Overpass requests tonight.**

### Open / next session
- **Morning: retry module 1b ONCE on the main server** (`overpass-api.de`): `.venv\Scripts\python data_pipeline\fetch_osm.py`. It checks the status page first.
- **If it succeeds, show Saif:** total element count; counts by amenity (restaurant, fast_food, cafe); counts by element type; file size; **5 random sample entries with their tags** (fixed seed); confirm both files are read-only. Explain in plain words. **Stop before module 2.**
- **If it fails:** stop and propose alternatives. Check any candidate instance's DNS first (D-006); truly independent public Overpass servers are scarce. Don't try an alternative without Saif's OK.
- After that: modules 2–5 as planned (pinned `data_pipeline/requirements.txt`, the `dataviz` skill before charts, the `data-auditor` at module 5).

### Pending for Saif
- Nothing.

---

## Session 4 — Phase 1 COMPLETE (modules 1b–5)
- **Start:** 2026-09-30 09:45 IST (verified with the clock at `start`)
- **End:** 2026-09-30 12:47 IST

### What was done
1. **Module 1b, restaurant fetch: succeeded on the first request** (main server, 6 s response).
   - Saved `data/raw/overpass_hyderabad_2026-09-30.json` (1,553 elements, 392,012 bytes, OSM data as of 2026-09-30T04:20:45Z) plus `.meta.json`. Both read-only, and the sha256 was verified.
   - Found **15 `internet_cafe`** elements, caught by the unanchored regex.
2. **D-007 (Saif):** keep the snapshot as is; remove the internet cafés in Phase 2 with the count logged; the query is now the exact match `^(restaurant|fast_food|cafe)$` in both CLAUDE.md and `fetch_osm.py`. No re-fetch.
3. **Module 2, `data_pipeline/profile_osm.py` → `results/eda/stats.json`.**
   - `data_pipeline/requirements.txt`: 14 exact pins (pandas 3.0.6, numpy 2.4.6, matplotlib 3.11.2, seaborn 0.13.2, plus dependencies, including `packaging` 26.3, which was already installed for pytest).
   - Key numbers (1,538 food places):
     - name 89.5%, cuisine 37.8%, any address 18.7%, **addr:suburb 0%**, any area tag 2.0% (district or state level only)
     - postcodes: 54 raw values → 51 without spaces → 50 valid PINs
     - `addr:city` has 23 values, a few of them locality names
4. **Module 3, `data_pipeline/detect_chains.py` → `results/eda/chains.json` and `chain_review.csv`.** Counting only.
   - **113 chains** (a core name at 2+ places) covering **446 places** (32.4% of named).
   - Top: Domino's 34, Cafe Coffee Day 26, KFC 23, Paradise 15, Subway 15, McDonald's 14, Kritunga 11, Pizza Hut 11, Bawarchi 9, Mehfil 9. Pista House 4, Shah Ghouse 1.
   - 120 ambiguous and 42 spelling-variant rows for Saif's Phase 2 review.
   - **39 same-name pairs within 50 m** (26 pin+pin, 12 pin+outline, 1 outline+outline; median 13.3 m) across 31 chains. Unconfirmed duplicates.
5. **Module 4, `data_pipeline/fetch_boundary.py` and `plot_eda.py` → 5 PNGs in `results/eda/`.**
   - The boundary outline was fetched in 1 request (`data/raw/osm_relation_7868535_2026-09-30.json`, read-only).
   - The palette was validated with the dataviz script (PASS; worst colour-blind ΔE 9.2; café aqua at 2.74:1 contrast, so types are always labelled in text). The result is recorded in the `plot_eda.py` docstring.
   - All charts were viewed; I fixed the legend covering points and the lowercase chain labels.
6. **Module 5: `docs/data_insights.md` written and audited.**
   - Created `.claude/agents/data-auditor.md` (read-only; traces every number to JSON and recomputes independently from raw). The new agent type loads **next session**; this time a general-purpose agent ran with that file's instructions.
   - **Audit 1:** all 46 numbers correct but FAIL on 8 overclaims (PIN count, "international chains clean", "local chains no brand tags", the double-mapping stated as fact, Telangana as a district, `addr:city` locality names missed, the finding-5 heading, the colour check not recorded). All fixed; the new numbers were added to `stats.json` first.
   - **Audit 2: PASS.** The doc records both audits.
7. **`docs/phase2_backlog.md` created.** It holds Saif's localities idea (fetch `place=suburb/neighbourhood` in relation 7868535 with 1 request; not done), the removals (15 internet cafés, 161 unnamed), the dedupe rule for the 39 pairs, the chain review, generic "chains" to reject, "regional" cuisine, and postcode/city signals.

### Decided
- D-007 (exact amenity match; internet cafés removed in cleaning).
- Scripts recompute from raw, each verifying the snapshot's sha256 first. Every number in a doc must come from a saved JSON field (or be cited to its record).

### Open / next session
- **Phase 2 (Cleaning & Enrichment)** starts from `docs/phase2_backlog.md`. First decisions for Saif:
  1. Approve the localities fetch (one Overpass request, status check first, read-only snapshot, review before use).
  2. The dedupe rule for close pairs.
  3. Chain review of `results/eda/chain_review.csv`.
- **Remind Saif:** `data-auditor` is now a named agent type; use it before showing any doc with numbers (cleaning logs, Phase 2 DECISIONS entries).
- `chain_review.csv` couldn't be rewritten at the last run (PermissionError, probably open in Excel). Its contents are unchanged (the auditor confirmed 120 + 42 rows). Re-run `detect_chains.py` once it's closed.

### Pending for Saif
- Close `results/eda/chain_review.csv` in Excel before the next pipeline run.
- Start reviewing `chain_review.csv` whenever convenient (needed for Phase 2).

---

## Session 5 — Phase 2 modules 2a–2c (batches 1–4). Reconstructed; this session was never closed with `end`
- **Start:** 2026-09-30 ~12:50 IST (approximate: after Session 4 ended at 12:47)
- **End:** 2026-09-30 ~15:11 IST (approximate: last file activity; the session was cleared without `end`)
- *This entry was written at the end of Session 6 from DECISIONS.md D-008 to D-011 and file timestamps, not from notes taken live.*

### What was done
- **2a areas:**
  - One localities fetch → `data/raw/osm_places_7868535_2026-09-30.json`, and a missing-area check.
  - `build_localities.py` → `data/reference/localities.csv`: 170 areas (D-008, D-009). Saif verified the hand-added coordinates on Google Maps.
- **2b removals:** `clean.py` took 1,553 places to 1,348: −15 internet cafés, −161 unnamed, −18 auto-merges (≤15 m), −11 reviewed merges (D-010, `dedupe_review.csv`).
- **2c chain mapping:**
  - `make_chain_review.py` → `chain_mapping.csv`. Batches 1–4 were decided by Saif (D-011): when unsure → separate; brand only for a known chain or a distinctive name at 3+ places.
  - Rows 71 and 81 were left pending. `manual_dedupe.csv` got M1–M4.

---

## Session 6 — Phase 2 COMPLETE (batches 5–8, post-2c dedupe, areas, cuisine, output, audit)
- **Start:** 2026-09-30 ~16:35 IST (approximate; the first file edit was at 16:51)
- **End:** 2026-09-30 17:16 IST (clock read at `end`)

### What was done
- **Saif changed the pace:** the goal is showcasing Dawat AI, and the data is good enough. His instruction:
  - Finish Phase 2 quickly.
  - Stop only for decisions that change what users see.
  - Record everything as reviewed by Saif.
- **Chain mapping closed (D-011):**
  - Rows 71, 81, 104 and 107 → separate.
  - Batch 5 as suggested (+Barbeque Nation, +Palamuru Grill).
  - Batch 6: 40 two-place names, separate by default.
  - Batch 7: 14 brand-tagged chains accepted ("Mc Domino's" stays separate).
  - Batch 8: generic names rejected.
  - Result: 194 rows (72 brand, 122 separate) → 33 brands. One OSM tag conflict: a "KFC"-named place with Domino's tags is treated as KFC.
- **New `data_pipeline/enrich.py`** (reads `places_clean.csv` plus the reference files; never raw):
  1. **Brands.**
  2. **Post-2c dedupe (D-012):** 3 auto same-brand merges; M1, M2 and M4 merged, M3 kept both, M5 (Study Sip ×3) merged. 1,348 → 1,340.
  3. **Areas (D-013):** an address tag if it names an area within 3 km (30 branches), else the nearest area (1,310). Median distance 581.5 m.
  4. **Cuisine (D-014):** a 28-cuisine vocabulary, filled from tags, then name keywords, then an amenity default. Multi-cuisine is primary for 394 of 1,112 restaurants. **36 restaurants are veg-only.**
  5. **Output (D-015):** `data/processed/restaurants.csv` (1,112 restaurants: 33 chains with 261 branches, 1,079 standalone) and `branches.csv` (1,340). Stable OSM-based ids, numbered branch labels, 129 names re-cased, no phone numbers or emails.
- **Post-checks:** they fail on undecided or contradictory input. Broken on purpose 4 ways; all 4 were caught.
- **Reproducibility:** input and output sha256 hashes are recorded in `results/cleaning/enrich_log.json`. A full rerun from raw reproduced them.
- **Data audit** (general-purpose agent following `.claude/agents/data-auditor.md`): FAIL on minor points, all of them fixed:
  - 2 veg-only misses: "Raghavedndra Vegitarian" (a typo) and "Hotel Kamat". The keyword regex was widened, taking veg-only from 34 to 36.
  - The "6 × Hot Chips" example count (really 5 plus one "Hot chips").
  - "437 restaurants" should read "437 branches".
  - Missing M5 distances and the evidence against the M5 merge.
  - Unlogged claims about the break tests and reruns.
  - Missing limitations. DECISIONS.md was reworded to cover all of these.
- **Docs:**
  - `docs/phase2_backlog.md` is marked resolved.
  - `docs/backlog.md` gained Phase 3 notes (veg-only menus, the Multi-cuisine template, verifying Minerva) and Phase 4 notes (43/46 shared names need case-insensitive, area-labelled search; numbered labels).

### Decided
- By Saif: D-011 closed, plus the D-012 pairs (he accepted suggestions in advance). By Claude under Saif's delegation: D-013, D-014, D-015.
- Veg-only errs towards veg (a wrong "veg-only" narrows a menu; a wrong "non-veg" would misrepresent a real restaurant).

### Open / next session
- **Phase 3 (Synthetic Menus & Database).** It first needs Saif's **Supabase account** (free tier, Mumbai region). Then the keys go into `backend/.env` (never in chat). Check the Supabase key names against the dashboard (Session 1 note).
- Set up the **Supabase MCP (read-only) and Context7** at Phase 3, as approved in Session 1. Remind Saif.
- `validate_menus.py` must fail if a veg-only restaurant has a non-veg item. Multi-cuisine restaurants need a sensible generic menu. Chains share one menu.
- Optional for Saif: verify that Minerva Coffee Shop is vegetarian, and look over the veg-only list in `enrich_log.json` → `5_veg_only`.
- memory.md only gets written on `end`. If a session is cleared without it, the next session has to reconstruct (as happened with Session 5).

### Pending for Saif
- Create the Supabase account (free, Mumbai region) before Phase 3 starts. Don't paste keys into chat.
- Optional: skim the four user-visible choices in D-014/D-015 (veg-only rule, Multi-cuisine default, name re-casing, numbered branch labels) and veto any of them.

---

## Session 7 — Phase 3 COMPLETE (menus, validation, schema, seed, guard tests)
- **Start:** 2026-09-30 17:18 IST (clock read at `start`)
- **End:** 2026-09-30 21:04 IST (clock read at `end`)

### What was done
- **memory.md check:** Sessions 1–6 all have entries. Nothing was missing.
- **enrich.py fixes (D-014 addendum):**
  - The `udup[iy]` keyword makes "Udupy Ahar" veg-only; 37 veg-only in total.
  - Chain cuisines now ignore branches whose cuisine is only an amenity default. Paradise → Biryani;Indian, KFC → Fried Chicken;Fast Food.
- **3a, templates (D-016 Saif-approved: written by Claude, no Gemini call; D-017 design):**
  - `data/reference/dish_catalogue.csv`: 319 dishes (190 veg) and 1,815 aliases (372 Telugu script). Every dish has a Telugu-script alias.
  - `menu_templates.json`: 28 cuisines and 26 name hints. `food_lexicon.csv`: 202 terms (kodi, mamsam, kaaram, karam lekunda, rendu…).
  - `check_menu_templates.py` PASSES, and was broken 10 ways, all caught. Rules: egg = non-veg, the veg flag is cross-checked against the name, an alias belongs to one dish, Latin/Telugu script only.
- **Sample menus shown to Saif** (Siva Sai Biryani Point, Sri Raghavendra Udipi Veg, Paradise). He said they feel realistic.
- **3b, generation (D-018 pricing rules approved by Saif; D-019):**
  - `generate_menus.py` (seed 2026) → `data/processed/menus.json`: 1,112 menus, 23,780 items. Byte-identical on rerun.
  - Chicken Dum Biryani median: budget ₹250 < standard restaurant ₹310 < chain ₹350 < premium ₹390.
- **3c, validation:** `validate_menus.py` is independent of the generator.
  - PASSES. Broken 14 ways, all caught.
  - Its first runs caught real data problems:
    - plural name hints (Arya Tiffins had no tiffin dishes);
    - the bucket priced at 2.6× the 2-piece portion;
    - 4 Irani cafés with no veg main;
    - Chutneys with no dosas.
- **3d, database (D-020, Saif approved backend-only access and the confirmation-gate trigger):**
  - Keys walkthrough; Saif filled both `.env` files himself.
  - `check_connection.py` prints no secrets. It caught a Direct-connection string (IPv6-only); after the switch to the Session pooler, everything passed.
  - Migrations 0001–0004. `migrate.py` has plan, `--test` (rollback) and `--apply` modes.
  - `--test` caught a constraint-trigger name clash; renamed, then applied.
  - `verify_schema.py`: 19/19 tables, all with RLS, 0 browser grants, 10 triggers.
  - psycopg 3.3.6 pinned, plus `tzdata` for Windows only.
- **MCP:**
  - `.mcp.json` holds the Supabase MCP (project-scoped, read-only, database+docs, OAuth) and Context7 (no key).
  - Supabase MCP write tools are denied in `.claude/settings.json`.
- **3e, seed (D-021):**
  - `data_pipeline/load_db.py` (validates first, upserts only, never deletes) loaded everything.
  - 3 fictional demo users on example.com with no passwords, each with preferences and an address.
  - Idempotent on rerun.
  - `backend/db/test_triggers.py`: 17/17 (13 breaks refused, 4 controls ok), all rolled back. The first run exposed a harness bug (SET CONSTRAINTS persisting across savepoints), now fixed.

### Decided
- By Saif: D-016, D-018, the D-020 access model and trigger, and the dishes/dish_aliases design.
- By Claude under delegation: D-017, D-019, D-021.

### Open / next session
- **Phase 4 (Tools layer & Backend API).**
  - Tools: `search_restaurants`, `get_menu`, `search_dishes` (use dish_aliases + pg_trgm + food_lexicon), cart tools, `confirm_cart`/`place_order` (the DB trigger is the second layer), history, preferences, `track_order`.
  - Totals are server-side, in whole rupees, with taxes rounded to the rupee.
  - The backend connects as the table owner (no RLS), so **every query must be scoped to the user id from the verified Supabase JWT** (JWKS at `<SUPABASE_URL>/auth/v1/.well-known/jwks.json`). Test that.
  - Search must compare names case-insensitively and disambiguate the 43/46 shared standalone names by area; the out-of-coverage area reply (docs/backlog.md).
  - Unit tests per tool.
- The area-alias table and demo-login approach (Phase 7, Saif decides).

### Pending for Saif
- Restart Claude Code in D:\DAWAT, approve the **supabase** and **context7** project MCP servers, then `/mcp` → supabase → Authenticate (browser OAuth).
- Optional: verify Minerva Coffee Shop is vegetarian; skim the veg-only list (`results/cleaning/enrich_log.json` → `5_veg_only`).

---

## Session 8 — Phase 4 modules 4a and 4b COMPLETE (+ Minerva fix, permissions)
- **Start:** 2026-09-30 21:10 IST (clock read at `start`)
- **End:** 2026-09-30 22:49 IST (clock read at `end`)

### What was done
1. **Supabase MCP authenticated** by Saif (`/mcp`). It's read-only and was used for all schema and data checks this session.
2. **Minerva Coffee Shop (D-014 addendum 2, Saif):**
   - It was already veg-only; Saif verified it as pure vegetarian.
   - Its cuisine was "Cafe" (from the word "Coffee"), which gave it a café menu. Saif chose **South Indian + Cafe**, through a new logged `BRAND_CUISINES` override in `enrich.py`.
   - A diff proved only Minerva changed: 1 row in `restaurants.csv`, `branches.csv` identical, 1 menu in `menus.json` (22 → 26 veg items).
   - **17 stale menu rows deleted** (Saif approved) with a one-off script that refused unless the stale set was exactly those 17. Then `load_db.py`: SEED OK, 23,784 menu items.
3. **4a: sign-in and database (D-022).**
   - `app/auth.py`: the user id comes ONLY from a verified Supabase token.
     - ES256, checked against the project's public JWKS keys, so there's no shared secret.
     - Checks issuer, audience, `exp`/`iat`/`sub`, `role=authenticated`; anonymous sign-ins are refused for now.
     - Key re-fetches are throttled to 1 per minute; a bad token gets 401 with a generic message; unreachable keys get 503.
   - `app/db.py`: psycopg pool (1–4, lazy, no prepared statements).
   - `app/tools/users.py` `ensure_user`: creates the profile only if the account exists in `auth.users`; never renames.
   - `GET /me`.
   - Tests use a throwaway ES256 key. The `db` fixture = one transaction, always rolled back, plus a row-count leftovers check (one query).
   - **7/7 planted security bugs caught.** Honest note: with HS256 allowed, PyJWT itself blocked the confusion attack, but with a 500 (TypeError).
   - Pins: PyJWT 2.15.1, cryptography 50.0.2, cffi 2.1.1, pycparser 3.0, psycopg-pool 3.3.3.
4. **Permissions (Saif's request, confirmed by him because it arrived as pasted text):**
   - `.claude/settings.json` has **31 allow** rules (read-only commands, pytest, pinned pip installs, 12 pipeline scripts, `backend/dev_server.py`) and **42 ask** rules (`migrate.py --apply`, `load_db.py`, `db_write_*`, SQL DELETE/TRUNCATE/DROP, all file deletes). The 20 deny rules and the hooks are unchanged.
   - Tested: pytest ran with no prompt, and `migrate.py --apply` prompted (Saif confirmed).
   - New `backend/dev_server.py start|status|stop` stops only the PID it started (`.dev_server.pid` gitignored).
   - **Convention:** any one-off script that writes to the database is named `db_write_*.py`, so it always asks.
5. **4b: areas, restaurant search, menus (D-023).**
   - `app/text.py`: the normaliser, identical to the pipeline's; tested on 2,000+ aliases.
   - `app/tools/reference.py`: in-memory cache of areas, restaurants and branches, refreshed hourly.
   - `areas.py` `resolve_area`, in order:
     - city words → `needs_area`
     - Manikonda/Bowenpally → `outside_coverage`
     - exact match → `ok`
     - rapidfuzz 88+ with a 10-point lead → `ok` with a note
     - 80–87 with the lead → `confirm_area` ("Did you mean…?")
     - anything else → `unknown_area` + suggestions
     - The probe found that the first rule (80+) would have mapped **Shamirpet → Shaikpet** and **Serilingampally → Lingampally**, hence the split.
   - `restaurants.py` `search_restaurants`:
     - compares distinctive words (generic and food words stripped), compact (no spaces or apostrophes);
     - tiers: exact / contains / fuzzy / fuzzy_word;
     - `needs_choice` + `choices` (chain branches and shared names like 6 × Hot Chips); `selected_branch_id`;
     - area filter at 3 km; `not_near_area`; food-only queries → `dish_query`;
     - an unresolved area stops the search.
   - `menu.py` `get_menu`: category (with spelling and plural aliases), veg, spice and price filters (inclusive); every bad filter is refused; items come from the database.
   - **194 backend tests pass (about 19 s)**; 15/15 planted bugs caught after 4 test gaps were fixed.
   - RapidFuzz 3.14.6 pinned.

### Decided
- **By Saif:** Minerva cuisine + deletion, the user-id-from-token rule, the rollback test strategy, the permissions, and the **typo behaviour**: mild typos ask "Did you mean Madhapur?"; close typos resolve with a short note. 4a and 4b approved.
- **By Claude under delegation:** D-022 details and D-023 details.

### Open / next session
- **4c `search_dishes`:**
  - dish aliases (Hinglish, Telugu script), `food_lexicon.csv` (kodi, mamsam, kaaram…), rapidfuzz/pg_trgm;
  - across branches in or near an area; reuse `resolve_area` and the area-stops-search rule;
  - veg/spice/price filters; it answers `search_restaurants`' `dish_query` status (e.g. "biryani in Madhapur").
  - Probe real scores before choosing thresholds (as in 4b), and plant bugs afterwards.
- Then **4d** (cart and totals). **Show Saif the fee and tax options with example totals before building.**
- Then 4e (confirm/place/track; cross-user tests: a user can't read or change another user's cart or orders), 4f (history/preferences), 4g (API routes).
- Run tests: `.venv\Scripts\python -m pytest -q -p no:cacheprovider backend/tests` (no prompt).

### Pending for Saif
- Nothing required. Optional: skim D-022/D-023 in DECISIONS.md.
- Remember at the end of the project: `backend/.dev_server.pid` and `.log` are gitignored; don't commit `.env` files.

---

## Session 9 — Phase 4 modules 4c and 4d COMPLETE (dish search, cart, fees, 8 km range)
- **Start:** 2026-10-01 20:09 IST (clock read at `start`)
- **End:** 2026-10-01 23:04 IST (clock read at `end`)

### What was done
1. **4c `search_dishes` (D-024, approved by Saif).**
   - **Probe first.** Whole-query fuzzy matching was rejected:
     - "keema samosa" → the veg Samosa;
     - "karam kam" → Ghee Karam Idli;
     - word by word, "karam kam" / "karam lekunda" read as SPICY.
     - Chat words score like typos (andar→anda = egg 89, panir→pani 89).
   - **`app/tools/dish_query.py`** (pure parser), in this order:
     - whole-name match first;
     - price and area;
     - chat words removed;
     - name again, then group size and quantity;
     - diet/spice phrases with negations;
     - per-word typos (88+ auto, 80–87 or a tie → `confirm_dish`; a veg/egg tie → veg);
     - every word in one dish's name or alias (lexicon-translated);
     - category words only via category or name;
     - diet words → the `is_veg` filter, never name words.
   - **`app/tools/dishes.py`:**
     - area required (`needs_area`, no prices);
     - filters only get stricter;
     - ≤ 3 km, ≤ 2 per restaurant, 10 results;
     - honest empty answers: `no_match_with_filters`, `none_near_area`, `no_dish_match`, `unmatched_words`.
   - **Migration 0005 `food_terms`** (203 terms; panir→paneer added) and `load_db.py` update. Category lists moved to `app/tools/categories.py`.
   - **273 tests.** All 1,815 aliases and 319 names find their own dish; a 40-query SQL cross-check. **Planted bugs 18/18** after fixing two real bugs the planted-bug test exposed ("2 pc chicken please", "chicken biryani 2 persons").
   - **Saif approved all 5 user-visible choices:** dish typos like area typos; no area → ask first; "pork biryani" flagged rather than "no match"; 10 results / 2 per restaurant / 3 km; "something veg" = mains only.
2. **Permissions (Saif):** `load_db.py` and `db_write_` ask rules narrowed to `*python* *load_db.py*` and `*python* *db_write_*` (Bash and PowerShell). Grep/cat on those files no longer prompts (verified). A python run of a `db_write_` script still prompts (verified; Saif rejected the no-op run). The load_db run prompt was not re-tested, at Saif's request (same pattern).
3. **4d fees (D-025, Saif chose Option B of three, priced on real carts):**
   - ₹25 delivery up to 2 km, plus ₹10 per extra km started; free when a restaurant's items are ≥ ₹499; one fee per restaurant.
   - 5% GST on food, 18% on delivery; whole rupees.
   - GST is rounded per restaurant (each restaurant becomes one order), so the two-restaurant example is ₹617, not ₹616. Saif: fine.
4. **4d build:**
   - `app/pricing.py` (pure, integer maths, distance in whole metres).
   - **Migration 0006:** `carts.delivery_area_id` + `address_id`, and the `carts_delivery_guard` trigger (the address must be the user's and in that area; a confirmed cart's delivery point can't change).
   - **`app/tools/cart.py`:**
     - one active cart per user, found by user id only;
     - prices live; unavailable / closed / too-far items flagged and not billed;
     - any change to a confirmed cart reopens it (`confirmation_cleared`);
     - default delivery point: default address → `default_area` preference → `needs_delivery_area`.
   - `migrate.py --test` table count fixed (it counted views). Hypothesis 6.168.3 + sortedcontainers 2.4.0 pinned in `requirements-dev.txt`.
5. **8 km delivery range (Saif, chosen over 5 km and no cap).** Without it, the median branch-to-area distance of 11 km meant about ₹115 in delivery, and the longest (42.6 km) ₹435.
   - `add_to_cart` refuses beyond 8 km (`too_far`).
   - Items that end up too far after a delivery change are flagged in `unavailable` with `reason: too_far`, like unavailable items.
6. **Tests: backend suite 561 passing** (194 → 561 this session). 4d planted bugs: 18/18 plus 3/3 for the range. The first 4d miss was "distance from the area centre instead of the address", because demo addresses sit on their area centres.

### Decided
- **By Saif:** D-024's 5 user-visible choices; Option B fees; ₹617 rounding; the 8 km cap; narrowed permission rules.
- **By Claude under delegation:** the parser design and thresholds (D-024), per-restaurant rounding, the delivery-point model, the confirmed-cart reopen rule, the reason labels.

### Open / next session
- **4e:**
  - `confirm_cart` only after an explicit "yes"; it must refuse when `can_confirm` is false or `needs_delivery_area`.
  - Store the confirmed total. `place_order` recomputes and refuses if anything changed.
  - One order per branch sharing a `checkout_id`; `order_items` snapshot; `track_order`.
  - Cross-user tests on orders. The DB trigger is the second layer.
- Then 4f (history/preferences), 4g (API routes).
- Phase 6 notes are in `docs/backlog.md` (act on `typo_corrections`, `unmatched_words`, `quantity`, `people`, `confirm_*`). Also: search results should say whether a "nearest elsewhere" place is within 8 km.
- **Phase 5 reminder:** set up the `rule-breaker` sub-agent (approved in Session 1); remind Saif.
- Run tests: `.venv\Scripts\python -m pytest -q -p no:cacheprovider backend/tests` (~100 s).

### Pending for Saif
- Nothing required. Optional: skim D-024 / D-025 in DECISIONS.md.


## Session 10 — Phase 4 COMPLETE (4e gate + orders, 4f history + preferences, 4g API routes); rule-breaker set up
- **Start:** 2026-10-02 14:30 IST (clock read at `start`)
- **End:** 2026-10-02 17:37 IST (clock read at `end`)

### What was done
1. **4e: the confirmation gate, orders and tracking (D-026; Saif approved the plan and "a price that changed after the yes → ask again").**
   - `view_cart` gives a `quote_id`: a sha256 fingerprint of every line and price, the fees, the GST, the delivery point and the total.
   - `confirm_cart(cart_id, quote_id)` confirms exactly that quote (`stale_quote` if the cart changed; `cannot_confirm` if it can't be confirmed).
   - `place_order` recomputes the fingerprint. If anything changed → `quote_changed`, the cart reopens and nothing is ordered. Otherwise one order per restaurant under one `checkout_id`, with an item snapshot and the delivery point. Placing twice is harmless.
   - `track_order` gives the status timeline and says there's no ETA.
   - **Migration 0007:** `confirmed_total` / `confirmed_quote` plus the `carts_confirmation_recorded` check; `orders.delivery_area_id/lat/lon`.
   - 27 tests. Planted bugs 13/13: the first run missed "fingerprint ignores prices / delivery point", which became the same-total price-swap and 50 m address tests.
2. **4f: preferences and history (D-027).**
   - **Saif's rule:** a preference is saved only when the user explicitly asks, confirms an offer, or uses the settings screen; never inferred. View and delete are included, and users can't touch each other's.
   - `app/tools/preferences.py` (`get_preferences`, `save_preference`, `delete_preference`): every write has a `source` (chat_request / chat_confirmed / settings). A chat write must quote the user's words, and they must appear as whole words in `user_message`, the latest message, which the Phase 6 runtime fills in, not the LLM. Values are normalised; areas go through `resolve_area`, and only a clear match is saved.
   - **Honest limit (logged):** the quote check proves whose words they are, not intent ("I'm vegetarian, show me biryani"). That becomes a Phase 10 eval case.
   - A source-scan test checks only `preferences.py` writes `user_preferences`. A whole-flow test checks nothing else saves one.
   - **Migration 0008** (non-destructive): `user_preferences.source` NOT NULL with no default (12 demo rows → `seed`); language limited to en / hinglish / te. `load_db.py` writes `source='seed'`; the `test_triggers.py` case was updated (17/17).
   - `app/tools/history.py` `get_user_history`: checkouts newest first, at the prices paid. "Order my usual" is left to Phase 9 (user-visible).
   - 78 tests. Planted bugs 17/17.
3. **4g: website routes (D-027).**
   - **Files:** `app/api/deps.py` (Conn, CurrentUser, `respond` status→HTTP map), `catalog.py` (public browsing), `cart.py` (cart, confirm, orders, history, track), `preferences.py` (`/me/preferences`). `me.py` was refactored to use the shared dependency.
   - **Request bodies** use `extra="forbid"` plus strict qty and values, so a price, user id or source can't be sent.
   - **Commit before the response:** FastAPI 0.141 runs dependency cleanup *after* sending unless `Depends(get_conn, scope="function")` is used. A test makes the commit fail and expects a 500.
   - 63 tests. The private-route list is taken from OpenAPI. Planted bugs 14/14. A smoke run with the real pool works.
4. **Backend suite: 729 passing** (588 at 4e end → 729). Schema: 20 tables, 11 triggers, SCHEMA OK; migrations 0007 and 0008 applied.
5. **`rule-breaker` sub-agent created** at `.claude/agents/rule-breaker.md` (Saif asked, at the Phase 5 start).
   - Tools: Read, Grep, Glob, Bash. It must never write files, and the database is read-only with forced rollback.
   - It attacks the four rules Saif named: over budget, non-veg for a vegetarian, spicy for a non-spicy person, not enough food. It judges with its own SQL and fee maths, never the planner's checkers.
   - It returns BROKEN/HELD, the breaks with repro scripts, an attack log and weak spots.
   - **It loads at the next session start.** It hasn't been run yet, because the planner doesn't exist.

### Decided
- **By Saif:** 4e as proposed plus "ask again on price change"; the preference rule (explicit only, view/delete, cross-user isolation); Phase 4 approved; the rule-breaker scope.
- **By Claude under delegation (D-026/D-027):**
  - the fingerprint contents;
  - sources plus the quote check;
  - the normalisations;
  - public browsing routes;
  - the status→HTTP map (409 returned, not raised);
  - function-scoped connections.

### Open / next session
- **Phase 5 plan proposed, not built.** Saif must approve the plan and its user-visible choices first:
  - overlap when unclear;
  - what a "meal" contains;
  - budget-use target;
  - the 3 scenario types;
  - the impossible-request answer;
  - search radius;
  - the 2-restaurant maximum.
- **Proposed modules:**
  - 5a `MealRequest` schema;
  - 5b candidate pool;
  - 5c combo builder plus an independent `check_plan`;
  - 5d scoring and diversity;
  - 5e impossible requests;
  - 5f `plan_meal` tool plus a `POST /plans` route plus plan → cart consistency;
  - 5g Hypothesis property tests plus planted bugs plus a rule-breaker run.
- Phase 6 / 7 / 10 notes in `docs/backlog.md`: preference runtime rules and eval cases; website route flow.
- Run tests: `.venv\Scripts\python -m pytest -q -p no:cacheprovider backend/tests` (~3 min now).

### Pending for Saif
- Answer the Phase 5 decisions above, then say go.
- Optional: skim D-026 / D-027.

---

## Session 11 — Phase 5 (Meal Planner) built and attacked. Reconstructed; this session was never closed with `end`
- **Start:** 2026-10-02 ~17:40 IST (approximate: Session 10 ended 17:37; the first planner file is from 17:46)
- **End:** 2026-10-02 ~19:50 IST (approximate: the last write to DECISIONS.md)
- *This entry was written in Session 12 (2026-10-03) from DECISIONS.md D-028/D-029 and file timestamps, not from notes taken live. learning.md and interview-prep.md got no Session 11 entry; Session 12's entries cover the planner.*

### What was done
- **Saif approved all 7 user-visible planner rules "as recommended" (D-028):**
  1. Unclear overlap: don't ask; the plan works whoever the non-spicy people are.
  2. What a meal is: the mains serve the whole group, and a full meal needs bread/rice/side. Biryani, mandi and meals are complete on their own.
  3. The budget covers the whole bill; 75–100% use is preferred, never padded.
  4. Three plans: Best match / Best value / Variety, genuinely different.
  5. Impossible request: say why, and give the real cheapest price or the largest group the budget covers.
  6. Search 3 km first, then 5 km.
  7. At most 2 restaurants.
- **Built (D-029):**
  - `app/planner/` modules:
    - `request.py` (strict `MealRequest`, `needs_info`);
    - `candidates.py`;
    - `rules.py` (the independent checker, Hall's condition for every overlap);
    - `build.py` (portion mixes, 4 fill styles, trim, meal completion with paired sides, two-restaurant plans);
    - `score.py`;
    - `plan.py`.
  - `app/tools/planner.py`: `plan_meal`; `add_plan_to_cart` re-plans by `plan_id` and never trusts items from the caller.
  - `app/api/plans.py`: `POST /plans` (public, optional token) and `POST /cart/plan`.
- **Proof:**
  - 113 new tests, 842 in the backend suite.
  - Synthetic Hypothesis tests: greedy and Hall agree on 3,000 cases; the builder was tested on 1,000 random menus.
  - Real-data oracle with its own SQL, fee/GST maths and brute-force matching; a 120-request property test.
  - 36 of 36 effective planted bugs caught.
- **Rule-breaker run (first use of the sub-agent):**
  - It found no hard-rule break.
  - It did find 2 honesty breaks: the over-budget price was quoted too high (₹903 vs ₹882), and so was the smaller-group price.
  - Fixed with an X − 1 re-search loop and side costs in the value knapsack.
  - Weak spots fixed: live open-branch check; a curry's bread must come from the same restaurant; per-line price check.
  - Re-attack: HELD.
- **3 weak spots flagged to Saif:**
  - "best value" meant the cheapest within 3 km only;
  - snack plans made of snack sides;
  - burger/sandwich dinners.
  - Per Saif in Session 12, he decided these in Session 11 just before it ended, but they were never built.

### Open at the end (picked up in Session 12)
- Build the weak-spot decisions; Phase 6 (keys were already in `backend/.env`, added Oct 2 17:49).

---

## Session 12 — planner follow-ups, the yes check (D-030), LLM models (D-031). Reconstructed; this session was never closed with `end`
- **Start:** 2026-10-03 ~09:00 IST (approximate: the first planner file change was at 09:02)
- **End:** 2026-10-03 ~11:10 IST (approximate: last file activity at 11:09)
- *Written at the end of Session 13 from DECISIONS.md (the D-029 Session 12 addendum, D-030, D-031), docs/backlog.md and file timestamps, not from notes taken live.*

### What was done
- **Planner weak spots (Saif: fix the causes, not an exact optimiser):**
  - "Best value" is the cheapest checked plan from every search.
  - Value plans take the cheapest matching side, and the shortlist estimate runs the real meal completion.
  - Free-delivery variants (≥ ₹499).
  - Over-budget is worded "the cheapest I found".
  - Speed went from 29 s to about 0.5–5 s with a per-group build cache.
  - Suite: 1,084 passing.
- **D-030 (Saif): `confirm_cart` from chat needs a clear yes in the user's latest message, checked in code.**
  - `app/tools/consent.py` gives yes / no / unclear for English, Hinglish, Telugu and Hindi.
  - `source` (chat / website) has no default.
  - 170 tests; 8 of 8 planted bugs caught.
- **D-031 (Saif):** Gemini 3.5 Flash-Lite primary, Groq gpt-oss-120b fallback. Measured with 4 tiny calls; Gemini 3.8 Flash returned a 503.
- **Rule-breaker run 2 was stopped early** (usage limit). The yes check held against about 380 messages; the planner sweeps never ran.

### Open at the end (picked up in Session 13)
- "yeah yeah" / "ok thanks" / "Ha!"; replacing the cart needed the yes check; Phase 6a.

---

## Session 13 — yes-check rules settled, replace-cart gate, Phase 6a (LLM client) and 6b (agent tools) COMPLETE
- **Start:** 2026-10-03 16:12 IST (clock read at `start`)
- **End:** 2026-10-04 21:32 IST (clock read at `end`; the session ran across two days)

### What was done
1. **Reconstructed where things stood:** Session 12 had no memory entry, and learning.md / interview-prep.md stopped at Session 10. Both gaps are filled at this `end`.
2. **Yes-check rules (D-030 addendum, Saif).** The final rules:
   - "yeah yeah" = yes; "ha" / "Ha!" = yes; "ha ha" = unclear.
   - A thank-you word makes a message unclear only when every yes in it is weak. `WEAK_YES` is the "ok / fine" family, including "theek hai" and "sare" (Saif approved).
   - So "ok thanks" is unclear, while "yes thanks" and "haan thanks" are yes.
   - The first version (thanks always unclear, lone "ha" unclear) was revised by Saif. His revision arrived as pasted text, so I confirmed it with him first.
   - 220 consent tests; planted bugs 11/11, then 6/6.
3. **Replacing the cart needs a clear yes (Saif).**
   - `add_plan_to_cart(..., *, source, user_message)`; the check runs only when replace=true would remove items. `POST /cart/plan` passes `website`.
   - The replace-only yes phrases (`REPLACE_YES`: "replace it", "replace kar do") count only for that question.
   - 13 database tests, plus route tests.
4. **6a, the LLM client (D-032):**
   - **Pinned:** LiteLLM 1.103.1 plus 41 dependencies, nothing upgraded, `pip check` clean.
   - **`app/agent/llm.py` `chat()`:** the primary model ONCE, then the fallback ONCE, then `LLMUnavailable` → "Dawat AI is busy right now. Please try again in a minute."
   - **Settings:** `max_retries=0`, 20 s timeout, 1,024 max output tokens; no cost-map download on import; no message logging.
   - **Secrets:** errors are scrubbed of keys.
   - **Tests:** 26, against a fake local provider server that counts HTTP requests.
   - **Planted bugs:** 9/10. The miss ("retries left on") is honest: this LiteLLM doesn't retry these providers anyway, so the explicit 0 is insurance.
   - **Live:** 3 requests. Gemini's tool call and its follow-up (raw_message round trip) worked, and so did Groq.
5. **6b, the agent tools (D-033):**
   - `app/agent/tools.py`: 16 tools, `ToolContext(conn, user_id, user_message)` and `run_tool()`.
   - Identity, the user's message and the chat source come from the runtime, never the model. Closed schemas: extra arguments are refused. Strict types; null means not given; 2.0 becomes 2. Signed-out users get `sign_in_required` on the cart, order and preference tools.
   - The schemas sent to the model were slimmed from about 3,760 to about 2,780 tokens (a test caps it at 3,000).
   - 79 tests, including a full plan → cart → "ok thanks" refused → "haan, order kar do" → order → track flow through `run_tool`. Planted bugs 12/12.
   - **Live:** both providers accepted all 16 schemas and called `plan_meal` correctly for the ₹500 demo request.
6. **Backend suite: 1,254 passing** (18.5 min).

### Decided
- **By Saif:**
  - the yes-rule revisions ("ha" yes, thanks only weakens a weak yes);
  - "theek hai" / "sare" as weak yeses;
  - the replace-cart gate;
  - the rule-breaker will run once at the end of Phase 6, narrowly scoped (planner + agent);
  - 6b approved.
- **By Claude under delegation:** `REPLACE_YES`, D-032 and D-033 (all details).

### Open / next session
- **Phase 6c, the agent loop:**
  - `run_tool` doesn't commit, so the loop owns transactions: commit after each successful write tool, and rollback plus a generic error on an exception (e.g. `PlanCartMismatch`).
  - A tool-call step cap per turn.
  - Malformed arguments go back to the model as a correction.
  - Keep tool results compact (the token budget).
  - Send `raw_message` back unchanged; test a Gemini → Groq switch mid-conversation.
  - Log every call to `agent_traces` (attempts are already scrubbed).
- Then 6d (the system prompt, from docs/backlog.md's Phase 6 rules), 6e (conversations, messages, streaming endpoint), 6f (scripted conversations; revisit Flash-Lite for Hinglish/Telugu).
- **At the end of Phase 6:** one rule-breaker run, planner + agent only.
- Run tests: `.venv\Scripts\python -m pytest -q -p no:cacheprovider backend/tests` (~18 min now). The planner tests dominate, so run single files while iterating.

### Pending for Saif
- Check the per-model requests/day for Gemini 3.5 Flash-Lite in your Google AI Studio dashboard (needed by Phase 10 eval runs).

---

## Session 14 — Phase 6c (agent loop) COMPLETE; testing made proportionate
- **Start:** 2026-10-04 21:40 IST (clock read at `start`)
- **End:** 2026-10-04 22:27 IST (clock read at `end`)

### What was done
1. **Saif's working rules (saved to auto-memory as `proportionate-testing`):**
   - **Full rigour** (planted bugs, independent checks) only on money, consent, identity and security. Lighter tests elsewhere.
   - **Full test suite only at the end of each phase.** During a module, run the related test files only.
2. **6c, the agent loop (D-034):** `app/agent/loop.py` `run_turn(conn, history, user_message, user_id, system_prompt=, prompt_version=)` returns a `Turn`: reply, status ok/step_cap/busy, messages, traces, llm_calls.
   - **Saif approved:**
     - **The step cap:** 8 tool calls per turn, then "That took more steps than I can manage in one go. Could you say it again, a bit more simply?"
     - **Busy after something was added to the cart:** "Dawat AI is busy right now. Anything already added is in your cart. Please try again in a minute."
     - **Busy after an order was placed:** the reply is built by code from the order: "Your order is placed: total ₹X. Dawat AI is busy right now, so I can't say more. You can track it from your orders."
   - **Transactions:** each tool runs in `with conn.transaction()`. On an autocommit connection that commits per tool; in tests it's a savepoint. A crash rolls back only that tool, the model gets a generic `tool_error`, and the details go to the log.
   - **Compact results:** internal fields and nulls are dropped, lists are capped at 15 (menus at 60) with a `_not_shown` count, and no value ever changes.
   - Traces match the `agent_traces` columns; 6e will write them.
3. **A bug found live and fixed:** Groq refused Gemini's tool-call message ("property 'images' is unsupported"). `llm.for_provider` now trims assistant messages for non-Gemini providers, and Gemini still gets them whole. The live switch now works in both directions.
4. **Tests:** `test_agent_loop.py` has 20 tests (strict on the yes check, identity and the order total). Planted bugs 9/9. `test_llm.py` +1 (27). Live: 4 turns, and every ₹ in the replies came from tool results.
5. **Full suite:** started, but **killed by Claude Code for low system memory** (not a test failure). The last full run was 1,254 passed, before 6c. Since then, only the loop, its tests and `llm.for_provider` changed (47 related tests pass).

### Decided
- **By Saif:** the step cap and its message, the busy-with-cart message, the order-placed message, proportionate testing, and the full suite only at phase end. 6c approved.
- **By Claude under delegation:** D-034 details (compaction, traces, per-tool transactions, `for_provider`).

### Open / next session
- **First: rerun the full backend suite** (Saif's instruction): `.venv\Scripts\python -m pytest -q -p no:cacheprovider backend/tests` (about 18 min; close other heavy apps first).
- **Then 6d, the system prompt** (`backend/app/agent/prompts/`, versioned). It comes from docs/backlog.md's Phase 6 rules, plus the language/script fix seen live:
  - Gemini answered English questions in Telugu or Hinglish;
  - Groq slipped into Devanagari.
- **Then:**
  - 6e: conversations, messages and traces persisted; a streaming chat endpoint; an autocommit connection for `run_turn`; whether signed-out chat is allowed (a user-visible decision, tied to the Phase 7 demo login).
  - 6f: scripted conversations plus a stricter price-grounding check (numbers next to dishes, not just "₹N").
  - Then the end-of-Phase-6 rule-breaker run (planner + agent).

### Pending for Saif
- Gemini 3.5 Flash-Lite requests/day from your AI Studio dashboard (for Phase 10).

---

## Session 15 — Phase 6d, 6e and 6f COMPLETE; Saif tested the chat himself and found 4 issues (to fix first next session)
- **Start:** 2026-10-04 22:32 IST (clock read at `start`)
- **End:** 2026-10-05 10:24 IST (clock read at `end`; there was a long gap overnight while Saif tested)

### What was done
1. **Full suite rerun (Saif's instruction):** 1,275 passed (17.5 min). Everything up to 6c is verified.
2. **6d, the system prompt (D-035):** `app/agent/prompts/system_v1.md` plus a loader with versions; the version goes in every trace.
   - Rule 1 = mirror the user's language AND script (Saif's top rule). Rule 2 = every fact comes from a tool.
   - The rest: how to help (branch, then menu; budget/group → `plan_meal`); ordering (summary → yes → confirm → place); preferences; style (Saif approved: warm and brief, short lists, no tables, ₹N).
   - Live 7 turns: all four languages/scripts mirrored, every number grounded.
   - **Finding:** every Groq free chat model is capped at 8,000 tokens a minute (read from response headers), so Groq alone can't finish a turn that uses a tool.
3. **D-036 (Saif):**
   - **Fallback chain:** Flash-Lite → Gemini 3.8 Flash (reasoning_effort low) → Groq; `LLM_FALLBACK_2_MODEL` added.
   - **A stated spice preference is a hard rule** for everyone who can eat spicy food. Ranges approved by Saif: spicy 2–3, medium exactly 2 (nothing at 3), mild 0–1 for everyone.
     - The checker (Hall's `can_eat`) and builder (greedy) both apply it, and the agreement test covers it.
     - The ₹500 demo is now spicy in all 3 plans: Best value ₹230 Ghee Karam Idli; Best match ₹419; Variety ₹471.
   - **Diet notes always shown:** they now state the preference, and the model copies them word for word.
4. **6e, chat endpoint (D-037; Saif: sign-in required, live steps then the reply, 30 messages an hour):**
   - Migration **0009 applied** (`messages.payload jsonb` + index; additive only).
   - `app/agent/store.py`: conversations scoped by user; 40-message history replay; messages + traces saved per turn; the hourly count.
   - `POST /chat` = a server-sent event stream (start / step / reply / done / error) on its own autocommit connection, run in a worker thread.
   - 14 tests, planted bugs 7/7.
   - **Live in-process Hinglish order, rolled back:** search → add the ₹240 one → cart ₹240 + ₹25 + ₹17 = ₹282 → "haan, order kar do" placed one order of ₹282.
5. **Terminal chat for Saif:** `backend/chat_cli.py`. Run from `D:\DAWAT` with `.venv\Scripts\python backend\chat_cli.py --user priya|arjun|family`. Live steps; everything is rolled back on quit.
6. **6f, eval kit (D-038):** `evals/checks.py` (numbers grounded, names spelled, diet notes copied, language/script, tool expectations, orders) and `test_checks.py` (7 tests; each check is proven to fail). Also `phase6_cases.json` (20 conversations / 31 turns), `run_evals.py` (rolled back, paced, `--only`, `--repeat`, saved results) and `failure_cases.md`.
   - **Results:**
     - v1: 15/16 cases, with 2 real failures. F-1 an English question answered in Hinglish. F-2 `confirm_cart` called on "ok thanks"; the code gate refused it.
     - **Prompt v2 (CURRENT; v1 frozen):** two lines fix them. v2 is 31/32 case runs, 324/325 checks.
     - **F-3 open:** Flash-Lite misspells "Annapurna" as "Annapura" (2 of about 8 mentions).
   - The near-perfect score was treated as a warning: replies were read by hand; 4 harder cases and 3× repeats were added.

### Decided
- **By Saif:** prompt tone/format; the fallback chain; spice as a rule plus its ranges; diet notes always shown; sign-in-only chat; live steps; 30 messages an hour; the terminal chat; 6d/6e approved.
- **Session 16 orders (Saif's pasted message, confirmed by him before acting):** fix the 4 issues below and build **option 3 for names**, then the Phase 6 close-out.
- **By Claude under delegation:** D-035–D-038 details (prompt versioning, chat store and streaming design, eval checks and prompt v2).

### Open / next session (in this order)
1. **Saved diet in planning and ordering (brought forward from Phase 9, Saif).** Priya (saved diet = vegetarian) got Mutton Biryani added and later ordered Butter Chicken with no check.
   - `plan_meal` must count the user as vegetarian from their saved diet.
   - When a vegetarian user asks for a non-veg dish, Dawat AI asks once ("You've saved vegetarian, is this for someone else?") before adding it. Decide how that's enforced in code, not just the prompt (e.g. `add_to_cart` answers `confirm_diet` for a non-veg item when diet = vegetarian, unless the user's latest message confirms).
   - Add 6f eval cases.
2. **Consent typos (Saif):** "haan saudi arebian rest wala order palce kardo." was refused as no clear yes. A "haan" plus an order phrase with typos ("palce", "kardo") must be a clear yes.
   - Add it and similar typo cases to the consent tests. Keep "no always wins" and the strict-by-default stance; this is consent code, so full rigour (planted bugs).
3. **An honest reply after "no" (Saif):** after he said "no" to placing the order, the reply said "Order cancel kardiya hai" while the item was still in the cart. It must say the order wasn't placed and the cart still has the items.
   - Fix in the prompt (v3) and/or the `no_clear_yes` message.
   - Add an eval case.
4. **Option 3 for misspelled names (Saif):** code corrects near-miss restaurant names in the reply against that turn's tool results before it's shown. Use a fuzzy match to the exact tool spelling; never touch numbers. Log each correction in the trace.
5. **Phase 7 note (recorded in docs/backlog.md):** short order numbers like #DW1042, never the full UUID.
6. **Then the Phase 6 close-out:** the full backend suite (about 18 min), then the rule-breaker run (planner + agent, narrow scope), then Phase 6 approval.

### Pending for Saif
- Gemini per-model requests/day from AI Studio (for Phase 10 eval sizing).

---

## Session 16 — Phase 6 fixes and close-out: saved diet, typos, honest "no", names, the LLM intent check, four rule-breaker runs, confirmation cards (D-039 to D-046). Phase 6 NOT yet approved.
- **Start:** 2026-10-05 10:25 IST
- **End:** 2026-10-05 ~23:57 IST (approximate; corrected by Saif in Session 17)

### What was done
1. **Session 15's four issues, built as modules 1–4:**
   - **D-039, saved diet:** plans count a saved vegetarian (eggetarian counts as vegetarian); a chat add of non-veg asks "You've saved vegetarian, is this for someone else?"; only a clear yes adds it (Saif).
   - **D-040, consent typos:** "palce", "kardo" and other common misspellings are repaired from an explicit list.
   - **Prompt v3:** an honest reply after a "no": the order was NOT placed and the items are still in the cart.
   - **D-041, names:** near-miss restaurant names are corrected in the reply against the turn's tool results, with a trace.
2. **D-042:** the chat's delivery area follows the area the user named, and a saved vegetarian sees veg dishes by default.
3. **D-043 (Saif approved the design):** an LLM intent check (`app/agent/intent.py`) at the order, replace and diet moments.
   - The model quotes the user's words, and code checks the quote.
   - For order and replace it can only add one natural question, never a yes.
   - For the diet question, a verified yes adds directly (Saif's decision 4).
4. **Close-out:** full suite 1,578 passed. Then four rule-breaker runs plus a verification run, each found breaks, and each was fixed with every break as a test plus planted bugs:
   - **Run 1 → D-044:** 8 breaks (retractions read as yes, a confirmation carried over turns, an unshown quote, the replace bypass, a same-turn diet change). Fixed with word lists; 10/10 planted bugs caught.
   - **Run 2 → D-045 (Saif approved five redesigns):** 8 new breaks showed that word lists hide changes.
     - Only unambiguous yeses; Saif's typo message now gets one question.
     - A confirmation lasts one turn.
     - Removals and replacements need asking.
     - The diet question is per item.
     - Preferences take two steps.
     - Prompt v4; 20/20 planted bugs caught; full suite 1,644 passed, 1 failed (an unmapped status, fixed).
   - **Run 3 → D-046:** 8 breaks, all with a model that lies in its own reply.
     - **Saif chose option A: confirmation cards.** Code shows each question (order, plan, diet, preference; then remove and delivery too), and a yes acts only on the card under the previous reply.
     - **Saif also chose:** a plan with meat for a saved vegetarian shows the plan card first.
     - **All the fixes:** NO words are heard in questions; acknowledgements ("ok cool") and a trailing "…" are not a yes; a preference value must be in the user's words; forgetting needs a forget word; busy replies show no card.
     - Prompt v5 (4,199/4,200 tokens). 22/22 planted bugs caught.
   - **Run 4 (focused on cards):** every card-gated action held. 5 breaks were where free-text checks still decided an action:
     - removal by words;
     - a remove card used 3×;
     - delivery moved on "don't deliver to Kondapur";
     - the diet classifier reached on questions and hesitation;
     - meat added in the turn that saved "vegetarian".

     Fixed: removals and delivery moves from chat always show a card, each card item is used once with its branch enforced, and the stricter of the start-of-turn and live diet applies. Weak spots also fixed: stale order card, plan card delivery, malformed cards ignored, and one chat turn at a time per user via an advisory lock. 13/13 planted bugs caught, after adding a two-branch test for the one miss.
   - **Verification run:** all structural fixes held. 2 breaks from word checks:
     - "ok. . ." read as yes (now `TRAILING_OFF`: any ellipsis, a trailing comma or dash);
     - hesitation sounds in other scripts ("umm ok", "हम्म ठीक है", "హ్మ్ సరే"), now hesitation.

     2/2 planted bugs caught.
5. **Also changed:**
   - **New files:** `app/agent/cards.py`; the chat stream's `reply` event carries `card` and `card_text`; `chat_cli.py` prints the card.
   - **Eval cases updated:** the typo yes gets one question, then "haan" orders; a preference request gets the card, then "Yes" saves.
   - **Backlog:** a Phase 8 note on website checkout vs the chat's re-opening.
   - **DECISIONS correction:** the turn lock needs the Session pooler.
6. **Tests:**
   - 1,752 collected;
   - break files: 85 + 69 + 73;
   - the last related runs all passed.
   - **The full suite was NOT run on the final code** (Saif stopped it at session end).

### Decided (Saif)
- **D-039:**
  - ask once, then per item (D-045);
  - eggetarian counts as vegetarian;
  - only a clear yes adds meat;
  - "hmm", "kya?" and "wait" ask again.
- **D-043 design and its decisions 1–4:** the diet question proceeds on a verified LLM yes.
- The D-044 fixes, the five D-045 redesigns, option A cards plus the plan diet question plus all fixes (D-046).
- **Acceptance rule:** "if the only remaining breaks are ones where dawat asks again rather than acting without a yes, we approve phase 6 and move to phase 7."

### Open / next session (in this order)
1. **Rerun the FULL suite first** (about 30 min, 1,752 tests) before approving Phase 6 (Saif's instruction). The final code has never had a full run.
2. **Saif decides on decision 4 (D-043) with the verification results.** At the diet card, a clean message that isn't a plain yes reaches the classifier; if it wrongly says yes, the meat item is added, and the order card shows it before any order.
   - Option (a): keep it.
   - Option (b), Claude's recommendation: the diet card asks once more, like order and replace. Then every action needs a plain yes, and the acceptance rule is met cleanly.
3. **If both are clear, Phase 6 is approved and Phase 7 starts.** Phase 7 notes in the backlog:
   - a demo login;
   - SSE handling, now including the card;
   - card buttons;
   - short order numbers.
4. **Logged but not done:**
   - `chat_cli.py` runs without the turn lock (a dev tool);
   - the transaction pooler would need a different lock;
   - card text doesn't name the branch;
   - re-run the live 6f evals with prompt v5 (cards change replies).

### Pending for Saif
- Gemini per-model requests/day from AI Studio (for Phase 10 eval sizing).

---

## Session 17 — Phase 6 APPROVED (D-047, full suite green); Phase 7 decisions (D-048 to D-050); 7a built (D-051), ui-checker run pending
- **Start:** 2026-10-06 10:05 IST (clock read at `start`)
- **End:** 2026-10-06 10:57 IST (clock read at `end`)

### What was done
1. **D-047, the diet card (Saif chose option b):** `intent.decide` now gives `ask_confirm` for "rules unclear + classifier yes" at every moment, order, replace and diet. A classifier yes at the diet card only asks once more (the user's words echoed, the card shown again); a plain yes then adds the item.
   - **Tests updated:** the decision table; the safety property now covers diet too (600+ messages × 3 moments); the boyfriend wiring test (ask, then "yes" adds); the fourth-run test flipped.
   - Planted bugs 3/3; 155 related tests pass.
2. **Full suite on the final Phase 6 code: 1,752 passed, 0 failed** (19 min 56 s; 1 third-party Pydantic warning). **Phase 6 APPROVED by Saif.**
3. **Session 16 end time corrected** to ~23:57 IST (Saif).
4. **Phase 7 decisions (Saif; his pasted message was confirmed as his before acting):**
   - **D-048:**
     - per-visitor demo accounts: "Try as Priya / Arjun" → anonymous sign-in → `POST /demo/start` seeds preferences, an address and 2–3 sample orders built through the real tools;
     - a D-022 addendum to accept anonymous tokens (in 7b);
     - a global daily chat cap (`chat_daily_usage`, migration 0010, atomic count, IST day, `CHAT_DAILY_CAP` 150 until the Gemini number arrives);
     - demo-account cleanup deferred to Phase 10 (needs approval).
   - **D-049:** no delivery-time filter (distance / fee instead); "chains near you" plus cuisine shortcuts instead of top picks; email signup kept, the demo login is the main way in.
5. **D-050, tooling:**
   - `.mcp.json` → `playwright` (`@playwright/mcp@0.0.83`, `cmd /c npx`, `--isolated --headless --browser chrome --output-dir .playwright-mcp`, gitignored). Smoke-tested with the exact command: it loaded the page and measured DM Sans for body text and Cormorant Garamond for the h1.
   - `.claude/agents/ui-checker.md` created (read-only; its own WCAG maths).
6. **7a, frontend foundations (D-051):**
   - shadcn/ui 4.21.2 (Base UI). The Geist font it swapped in was reverted; `shadcn` moved to devDependencies; `cn` kept (shadcn's own package).
   - Brand theme in `globals.css` (light only; veg/nonveg/plum-deep tokens; input borders ≥ 3:1; plum focus ring, gold in the header).
   - `frontend/scripts/check_contrast.mjs`: 24/24 pairs pass AA.
   - `src/lib/api.ts`: a result object and never throws; `onSlow` 4 s for "Waking up Dawat AI…"; 70 s timeout.
   - `src/lib/config.ts` (Supabase public values) and `src/lib/supabase.ts` (a browser-only client, `accessToken()`).
   - `components/brand/DawatLogo.tsx`, `components/layout/SiteChrome.tsx` (skip link, demo banner, header, footer with the OSM credit); `layout.tsx`, `page.tsx` and `BackendStatus` moved to the API client.
   - **Checks:** `tsc`, ESLint and `next build` OK. The page serves the banner, credit, skip link and main landmark; CORS OK. Runtime `npm audit`: 0; 9 dev-tool findings left (the suggested fixes are old-major downgrades).

### Decided
- **By Saif:** D-047 (option b), Phase 6 approval, D-048 (goal plus proposal), D-049 (as recommended), starting 7a plus Playwright.
- **By Claude under delegation:** D-050 flags, D-051 (all details).

### Open / next session
1. **First: run the `ui-checker`** on http://localhost:3000 (1280 and 360 px). Fix anything it finds before 7b.
   - Start the servers first: `.venv\Scripts\python backend\dev_server.py start`, and `npm run dev` in `frontend/`. The frontend dev server stopped with this session; the backend dev server may still be running, so check with `dev_server.py status`.
2. **Then 7b, sign-in:**
   - login/signup pages and the "Try as Priya / Arjun" buttons;
   - the D-022 anonymous addendum;
   - `POST /demo/start` (sample orders through the real tools, then backdated);
   - migration 0010 `chat_daily_usage` plus the cap in `POST /chat`;
   - `GET /me` showing the name.
   - **Needs Saif's anonymous sign-ins toggle ON first.**
3. Then 7c–7h as planned. 7c needs a new public "restaurants in an area" route.
4. **Logged but not done (from Session 16):** re-run the live 6f evals on prompt v5; card text doesn't name the branch; `chat_cli.py` has no turn lock.

### Pending for Saif
- **Restart Claude Code** in D:\DAWAT and **approve the `playwright` project MCP server.** (The `ui-checker` agent type already shows as available.)
- **Supabase → Authentication → Sign In / Providers → "Allow anonymous sign-ins" ON**, before 7b.
- Gemini 3.5 Flash-Lite requests/day from AI Studio (it sets `CHAT_DAILY_CAP` and the Phase 10 eval sizing).

---

## Session 18 — Local test database (D-052) and the in-memory menu cache (D-053); 0010 applied to Supabase
- **Start:** 2026-10-06 11:10 IST (clock read at `start`)
- **End:** 2026-10-06 12:07 IST (clock read at `end`)

### What was done
1. **Saif's new rule (D-052):** no tests, rule-breaker runs or evals against Supabase; a local database only. Saved to auto-memory (`local-db-for-testing`) and to CLAUDE.md's Engineering discipline.
   - **Saif chose** plain PostgreSQL 17 (Supabase runs 17.11) and option (a): browser checks of the dev site may use Supabase, kept light.
   - **Saif installed** PG 17 (service `postgresql-x64-17`) and added `TEST_DATABASE_URL` himself.
   - An old `C:\Program Files\PostgreSQL\18\data` folder (Feb 2026, no program files) was left untouched.
2. **Built:**
   - `app/localdb.py`: `is_local` requires all hosts to be local; `test_dsn`; `require_test_dsn`; `use_test_database`.
   - `tests/conftest.py` points `DATABASE_URL` at the local database before the app is imported (blank if unset, so database tests skip). `DAWAT_TEST_RUN=1`, under which `db.get_pool()` refuses a remote database.
   - `run_evals.py`, `chat_cli.py` and `test_triggers.py` are local only.
   - `migrate.py --local`; `--test` only with `--local`.
   - `load_db.py --local` (demo users go straight into `auth.users`, uuid5 ids).
   - `backend/db/local_bootstrap.sql` (anon / authenticated / service_role, the extensions schema, `auth.users`, `auth.uid()`).
   - `backend/db/local_setup.py`: creates `dawat_test` with ICU en-US collation (like Supabase), UTC, the search_path; bootstrap, migrate, seed.
   - The live JWKS test is deselected (`addopts = -m "not live"`); the rule-breaker instructions were updated; `.env.example` has a `TEST_DATABASE_URL` slot.
   - `tests/test_localdb.py`: 26 tests; planted bugs 3/3.
3. **The local database is ready:**
   - 0001–0010 applied, 21 tables, all with RLS. The seed counts equal Supabase's (23,784 menu items, 3 demo users). 0001–0009 checksums are identical to Supabase's ledger.
   - `test_triggers.py` 17/17.
   - **The refusal shown:** a Supabase-shaped host (made up) stopped pytest, the evals and a rehearsal before any connection.
4. **D-053, the in-memory reference cache (Saif's request):**
   - `reference.py` now also holds every menu item (about 1.5 MB on the wire) and is warmed at startup in a background thread.
   - **Migration 0010** `reference_version`: statement-level triggers on the 8 reference tables stamp a random uuid. The backend reads it at most every `REFERENCE_CHECK_S` (60 s; 0 in tests) and reloads only on change; a daily safety reload; before 0010, the old hourly reload.
   - **Switched to the cache:** `get_menu`, `search_dishes`, the planner's candidates.
   - **Kept live:** cart, quotes, orders, the planner checker `rules.load_facts`, the open-branch check.
   - `tests/test_reference_cache.py`: 8 tests (incl. "the copy equals the DB row for row in order" and "cart prices are live while the copy is frozen"); planted bugs 3/3.
5. **Full suite, once, locally: 1,783 passed, 2 failed** (15 min).
   - **Both were test bugs:** `limit 1` with no ORDER BY picked Egg Biryani for vegetarian Priya. Fixed with `veg_item()`; that file passes 20/20. The full suite was not rerun.
6. **0010 applied to Supabase (Saif approved):**
   - **Apply output:** 21 tables, none without RLS.
   - **Read-only check:** 1 version row, 8 triggers, RLS on; counts unchanged.
   - **Dev backend check:** a menu is served from memory in 4–5 ms.
7. **Saif stopped one command** because it contained the word "truncate" (it only appended to DECISIONS.md). He said: explain any such command first, and never run TRUNCATE against Supabase. The 0010 triggers fire *on* a table being emptied; they never empty one.
8. **Dev server:** Saif's own `uvicorn --reload` (PID 3236, started 10:56) exited on its own during the check; I only sent it requests. My `dev_server.py` instance is running (PID 6880). A start attempt that failed to bind was stopped with `dev_server.py stop`.

### Decided
- **By Saif:** the local-only rule; PG 17; browser checks (a) kept light; the cache goal; applying 0010 to Supabase.
- **By Claude under delegation:** the D-052 enforcement design; the D-053 design (version stamp, what stays live); 0011 is now the chat daily cap.

### Open / next session
1. **Restart Claude Code** (the Playwright MCP isn't loaded yet), then run the `ui-checker` on 7a (1280 and 360 px) and fix what it finds.
2. **Then 7b:**
   - sign-in pages and the "Try as Priya / Arjun" buttons (anonymous sign-ins are ON per Saif);
   - the D-022 anonymous addendum;
   - `POST /demo/start`;
   - **migration 0011** `chat_daily_usage` plus the cap;
   - `GET /me`.
   - **Test locally first:** `migrate.py --local --test`, then `--local --apply`, then the tests, then Supabase `--apply` with Saif's OK.
3. Phase 10: measure real egress on the live app (D-053 numbers are estimates).
4. Still logged (Session 16): re-run the 6f evals on prompt v5 (now on the local DB); card text doesn't name the branch; `chat_cli` has no turn lock.

### Pending for Saif
- Restart Claude Code and approve the `playwright` MCP server.
- The Gemini 3.5 Flash-Lite requests/day number (sets `CHAT_DAILY_CAP`).
- The dev backend on port 8000 is my `dev_server.py` instance. Stop it with `.venv\Scripts\python backend\dev_server.py stop` if you want to run your own.

---

## Session 19 — Phase 7a checked, guard ask-rules moved into the hook (D-054), 7b–7f built (D-055 to D-058); 0011–0013 applied to Supabase. Reconstructed; this session was never closed with `end`
- **Start:** 2026-10-06 ~12:15 IST (approximate: the first file change after Session 18, `.claude/settings.local.json`, likely the Playwright MCP approval after the restart)
- **End:** 2026-10-07 ~00:18 IST (approximate: the last activity was order #DW1028 on Supabase; the last file write was DECISIONS.md at 00:15)
- *Written at the start of Session 20 (2026-10-07) from DECISIONS.md D-054 to D-058, file timestamps, both migration ledgers and read-only Supabase queries, not from notes taken live. learning.md and interview-prep.md got no Session 19 entry; fill both at the next `end`.*

### What was done
1. **ui-checker on 7a:** failures fixed (inline status dot, a 28 px OSM link target, `main` tabIndex −1, a gold skip-link ring), re-check PASS (recorded in D-055).
2. **D-054, guard hook (Saif: "only fire when a command actually runs against a database"):**
   - The 24 database ask rules were removed from `.claude/settings.json`. `guard.py` now asks itself, on a "database view" of the command with note text removed (Add-Content/Set-Content/Out-File/Tee-Object text, here-strings, search-command arguments).
   - It asks for: `migrate … --apply` without `--local`, `load_db`, `db_write_*`, and SQL DELETE FROM / TRUNCATE / DROP TABLE|SCHEMA|DATABASE. Deny still wins. The 18 file-delete ask rules stay.
   - 122 guard tests; planted bugs 7/7; fails closed. Live: a note mentioning TRUNCATE passed with no prompt; a Python print of "TRUNCATE" prompted.
3. **7b, sign-in and demo accounts (D-055):**
   - Anonymous tokens accepted (D-022 addendum; only JSON `true`); `GET /me` carries `is_anonymous` and `demo_persona`.
   - **Migration 0011** `chat_daily_usage`: atomic daily slot, IST day, cap from `CHAT_DAILY_CAP` (blank → 150), HTTP 429 `daily_limit`.
   - **Migration 0012:** `users.demo_persona`, `orders.is_sample`.
   - `POST /demo/start {persona}`: anonymous accounts only, once per account, seeds the name, preferences, an address and 3 sample orders through the real tools (then backdated).
   - Frontend: `session.tsx`, `demo.ts` (`tryAs`), `/login` (persona cards first, then email), `AccountNav`.
   - Tests: 22 demo + 10 daily-cap (an 8-connection race on the local DB). Planted bugs 6/6 and 9/9.
4. **7c, browsing by area (D-056; Claude under delegation, 7 user-visible choices listed for veto):**
   - `app/tools/browse.py`; public `GET /areas/{id}/home` and `GET /areas/{id}/restaurants`. Only restaurants with an open branch within 8 km; one card per restaurant; distance, fee, price for one, mild-friendly; filters in the URL.
   - Frontend `/` (`HomeBrowse`) and `/restaurants` (`RestaurantListing`), area memory in `lib/area.ts`. 24 tests (no planted bugs: public read-only).
5. **7d/7e, restaurant page, cart, checkout, order numbers (D-057; Saif approved all five user-visible choices):**
   - `/restaurant/<branch_id>`: `GET /branches/{id}?area=`, a Leaflet 1.9.4 map, the menu by category, a Veg-only toggle, spice words.
   - **Migration 0013** `orders.order_no` (identity from 1001), shown as `DW1042`; `track_order` accepts DW/#DW/plain numbers, scoped to the user. 18 tests, planted bugs 3/3.
   - `GET /me/addresses`; `CartProvider` (the one site-wide cart); `/cart` with a bill per restaurant; "Place order · ₹X" confirms exactly the quote shown, then places it.
   - ui-checker runs on 7c, 7d and the signed-in cart; all failures fixed (the last five fixes passed tsc/ESLint only).
6. **Migrations on Supabase (Saif approved):** 0011 + 0012 applied 2026-10-06 16:07 IST; 0013 at 23:28 IST. **Verified this session (Session 20):** both the Supabase and local ledgers hold 0001–0013 with hashes equal to the files.
7. **Saif's checkout test:** order **#DW1026** (₹277) placed from the website at 23:50 IST.
8. **7f, the Dawat AI chat widget (D-058), built 23:53–00:15. Saif hadn't recorded it as done:**
   - `ChatWidget.tsx`, `ChatParts.tsx`, `AskDawatAI.tsx`, `lib/chat.ts` (fetch-based SSE reader), `lib/chat-context.tsx`; the launcher on every page; a home "Just ask Dawat AI" section.
   - Cart sync: `CartProvider.refresh()` after every successful cart-changing step and after the turn.
   - A thinking panel of live steps, folded into "How Dawat AI got this · N steps".
   - Confirmation cards drawn from the backend's `card`; **new backend field `plans`** on the `reply` event (`cards.plan_options()`), rendered as selectable plan cards. `test_chat_api.py` +4, with 1 planted bug caught.
   - The conversation is kept in sessionStorage, keyed by user. Dev preview at `/dev/chat-preview` (404 in production), with real plans from the local DB (`backend/chat_preview_fixture.py`).
   - ui-checker: two runs, fixes applied (non-modal on wide screens, modal below 640 px, focus/Escape, one live region, a two-tone launcher ring, the plum skip-link ring).
   - **Seen in Supabase:** order **#DW1027** (₹303, 00:05 IST) was placed through the chat on the web channel (Priya demo account, prompt v5: plan_meal ×2 → search_dishes → add_to_cart → view_cart → confirm_cart → place_order). **#DW1028** (₹268, 00:18 IST) has no conversation, so it came from website checkout. Who ran these isn't recorded.
9. **Supabase state (read-only, Session 20):** 12 users (8 visitor demo accounts), 28 orders (24 sample), 1 conversation.

### Decided
- **By Saif:** D-054's goal; the D-057 five choices; the 0011/0012/0013 applies.
- **By Claude under delegation:** D-055, D-056, D-057 and D-058 details. The D-056 (7) and D-058 (7) user-visible choices are listed for Saif to veto; no veto is recorded.

### Open at the end (picked up in Session 20)
- D-058 status: "Saif's signed-in browser test pending"; the D-058 veto list.
- No full backend suite this session (Phase 7 isn't finished; related files only).
- Still logged: re-run the 6f evals on prompt v5 (local DB); card text doesn't name the branch; `chat_cli` has no turn lock; the Gemini requests/day number.

---

## Session 20 — Session 19 reconstructed; 7f accepted; local dev mode with a dev login (D-059); 7g built (D-060). Full suite stopped for low memory
- **Start:** 2026-10-07 12:34 IST (clock read at `start`)
- **End:** 2026-10-11 10:07 IST (clock read at `end`; there was a long idle gap after the last work on 2026-10-07)

### What was done
1. **Session 19 reconstructed** (Saif's request, nothing rebuilt), from DECISIONS.md D-054–D-058, file timestamps, both migration ledgers and read-only Supabase queries.
   - Found that Session 19 had also built **7f** (D-058), not only up to 7e.
   - #DW1027 was placed through the chat; #DW1028 came from website checkout.
   - Both ledgers hold 0001–0013 with hashes equal to the files.
2. **Saif tested 7f in his browser ("the chat works")** and accepted D-058's and D-056's choices.
3. **Saif: avoid Supabase in daily work** (egress warning).
   - I compared a local dev-login mode against the Supabase CLI stack and recommended A: the machine had 3.2/15.7 GB RAM free, and the CLI's local auth signs ES256 only with configured keys.
   - **Saif approved option A with all five locks**, plus "re-check Supabase sign-in once before deploy", which is now on the backlog's new Phase 10 deploy checklist.
4. **L1–L3, local dev mode (D-059):**
   - **`dawat_dev`:** built by `local_setup.py --dev` from `localdb.dev_dsn()`, with identical seed counts.
   - **Backend:** `app/devauth.py` (an ES256 key in gitignored `backend/.dev_login/`, issuer `dawat-dev-login`, the same `TokenVerifier`) and `app/api/devauth.py` (`/dev/auth/anonymous`, `/users`, `/seed-user`).
   - **Launcher:** `dev_server.py start` is LOCAL by default; `--supabase` is explicit.
   - **Frontend:** `lib/auth.ts` (one sign-in layer), `lib/devauth.ts`, `components/auth/DevSignIn.tsx`, `scripts/dev-local.mjs` (`npm run dev:local`), `next.config.ts` phase guard, `scripts/check_no_dev_auth.mjs` (part of `npm run build`), and a banner line in local mode.
   - **Locks proven:**
     - backend: 41 tests in `test_devauth.py` (including real subprocess start-up refusals), planted bugs 9/9;
     - frontend: a build with the flag, a plain `next dev` with it and a Vercel build were all refused; the scan caught both mutations that really leak; one mutation (a same-module const) didn't leak, because the bundler folds it.
   - **Live:** "Try as Priya" worked with **zero requests leaving localhost**.
   - Also updated: the `.env.example` notes (no slot for either flag), the ui-checker agent (local data only), CLAUDE.md Engineering discipline, and the `local-db-for-testing` memory.
5. **7g (D-060):**
   - **Pages:** `/orders`, `/orders/[orderNo]`, `/profile` (preferences save straight away with source settings; addresses read-only; Sign out).
   - **Links:** `#DW` links in chat replies and in the cart's placed panel.
   - **Backend:** `track_order` also returns `branch_id` and `is_sample` (test updated).
   - **Header:** Cart, Orders, name→Profile, Sign out on wider screens. **Phones: Cart and Profile only** (it overflowed with the cart count), listed for Saif's veto.
   - Bug found and fixed: a shared `inline-flex` class beat `hidden`.
   - **ui-checker:** FAIL on 1 item (the default-area form lost focus because AreaPicker's select is disabled while loading; fixed with `focusWhenReady`, re-checked live). 5 advisories taken.
   - **Production build:** 10 routes; `check:no-dev-auth OK` on 289 files.
6. **Tests:** related files pass (155 for sign-in/demo/local DB/chat, 97 for order numbers + agent tools). **The full backend suite was started but stopped by Claude Code for low system memory at about 63%, with no failures up to then. Not rerun, per the instruction.**

### Decided
- **By Saif:** 7f/D-058 and D-056 accepted; avoid Supabase daily; option A + the five locks; the Phase 10 sign-in re-check; the 7g plan and its 7 choices; "only stop if something affects what users see".
- **By Claude under delegation:** D-059 details (separate dawat_dev, the env-file refusal, inline build-time conditions, source maps excluded from the scan), D-060 details, and the phone header adjustment (for veto).

### Open / next session
1. **Saif's answers:** veto or keep the phone header (Cart + Profile); his 7g browser test; whether #DW1027 was him or the ui-checker (his note read "[me / the ui-checker]").
2. **Phase 7 close-out:**
   - rerun the FULL backend suite with nothing else running (stop the dev servers first, close heavy apps);
   - a ui-checker sweep of every page (local mode);
   - Saif's Phase 7 sign-off.
3. **Then Phase 8** (Razorpay test mode, simulated status progression, rider map). The backlog's D-045 note: a website confirmation must survive a chat message during payment.
4. **Still logged:** re-run the 6f evals on prompt v5 (local DB); card text doesn't name the branch; `chat_cli` has no turn lock; Gemini requests/day.

### Pending for Saif
- A `next dev` process I started is still listening on port 3000 (PID 25548). Its shell was stopped, and the process outlived it. Stop it with `Stop-Process -Id 25548`, or tell me to next session. The backend dev server is no longer running.
- Answer the three items under "Open" 1.
- The Gemini 3.5 Flash-Lite requests/day number (sets `CHAT_DAILY_CAP`).


## Session 21 — Phase 8 (payments, tracking) and the simulated gateway
**Start:** 2026-10-11 (after Session 20). **End:** 2026-10-11 22:50 IST.

### Done
- **Work split in force:** Gemini owns `frontend/`; `frontend_old/` is read-only; Claude owns backend, DB, tests and deployment. Supabase is blocked until 30 Oct, so everything is local. Skipped on Saif's instruction: the phone-header decision, the 7g browser test, the ui-checker sweep and Phase 7 sign-off. #DW1027 is logged as unknown. The Gemini requests/day number is still pending.
- **Docs written:** `docs/API_CONTRACT.md` and `docs/FRONTEND_RULES.md` (for Gemini). The leftover process on port 3000 was already gone.
- **Phase 8 (D-061), local only:** payment-first ordering. `payment_attempts` (migration 0014, applied to `dawat_test` and `dawat_dev` only), `/payments/start` and `/payments/verify`, HMAC signature check, the quote re-check with a simulated refund (`needs_refund`), simulated progress (about 6 minutes) and the rider position on `GET /orders/{id}`. `POST /orders` and the chat `place_order` create nothing, and the chat reply carries a `payment` field. Prompt v6. Planted bugs: 33 of 34 caught, and the one miss (M08) is an equivalent mutant.
- **Token cap raised to 4,250 and logged** (D-061).
- **D-062:** Razorpay test keys need PAN onboarding, which Saif declined. Payments now run through a local simulated gateway by default (`PAYMENT_GATEWAY=simulated`). New `POST /payments/simulate`, `pay_TEST_…` ids, same HMAC check with a local secret. Failure gives 402, no order, and the cart stays confirmed. Only fixed test cards and UPI ids are accepted, and CVV and expiry are never accepted. The Razorpay path stays behind `PAYMENT_GATEWAY=razorpay`. 41 new tests; 6 of 6 planted bugs caught. `API_CONTRACT.md` has the exact flow and the test values for Gemini.
- **Final full suite: 2,079 passed, 0 failed** (about 11 min, local DB).

### Decided
- By Saif: payment is required for every order; a changed quote after payment means no order plus a simulated refund; progress takes about 6 minutes with no ETA; no webhooks; token cap 4,250; simulated gateway instead of Razorpay.

### Open / next session
1. Gemini builds the checkout sheet from `API_CONTRACT.md` §Payments; then wire and test it end to end.
2. Apply migration 0014 to Supabase after 30 Oct, with Saif's approval.
3. Re-run the 6f live evals on prompt v6 (five eval turns were updated; not run).
4. Never called live: the real Razorpay path. Refunds are only recorded.
5. Still logged: card text doesn't name the branch; `chat_cli` has no turn lock and doesn't print `payment`; the Gemini requests/day number (sets `CHAT_DAILY_CAP`).

### Pending for Saif
- Phase 8 and Phase 7 sign-offs once the Gemini frontend is wired.
- Optionally set `PAYMENT_SIM_SECRET` in `backend/.env` (any long random string).


## Session 22 — Gemini-design login fixed (D-063); Google-only sign-in and "Confirm your name" (D-064)
- **Start:** 2026-10-12 (clock not read at `start`; roughly 17:00 IST, approximate)
- **End:** 2026-10-12 21:24 IST (clock read at `end`)

### What was done
1. **Both tasks arrived as pasted text; I confirmed each with Saif ("yes") before acting.** For both, Saif temporarily allowed editing `frontend/` (Gemini out of quota until about 15 Oct). Never `frontend_old/`, never Supabase, local DBs only.
2. **Task 1 (D-063): "Try as Priya" failed in `frontend/`.** The lib and login code were already ported; what was missing was the switch. `NEXT_PUBLIC_DAWAT_DEV_LOGIN=1` is set only by `npm run dev:local`, which `frontend/` lacked. Without it, sign-in went to Supabase anonymous sign-in and failed. Ported `scripts/dev-local.mjs`, `scripts/check_no_dev_auth.mjs`, the `next.config.ts` flag guard and the package scripts. `lib/servercart.ts` feeds the header's real cart count and area list; the header's name comes from `GET /me`. The flag must not go in `.env.local`; I never opened any `.env` file.
3. **Task 2 (D-064): Google is the only sign-in.**
   - **Backend (full rigour):**
     - Migration **0015** `users.name_confirmed`, applied to `dawat_test` and `dawat_dev` only.
     - Anonymous tokens are a 401. `POST /demo/start` and `api/demo.py` are removed; `tools/demo.py` stays as a library for `test_order_numbers`.
     - `GET /me` now returns `{user_id, display_name, is_demo, name_confirmed, account_name}`.
     - New `POST /me/name`: null/omitted keeps the name from the verified token; a string is validated (trimmed, 1–60 chars, no control or invisible characters, no `<`, `>` or HTML entities; the ZWJ/ZWNJ joiners are allowed).
     - Dev login: `POST /dev/auth/google` signs in a fake "Local Tester"; the five D-059 locks are unchanged.
     - New `test_google_auth.py`, plus updates to 5 other test files. **21/21 planted bugs caught** (one harness no-op fixed first).
     - **Full backend suite: 2,152 passed, 0 failed** (15 min 47 s).
   - **Frontend:**
     - `/login` has one "Continue with Google" button (production: `signInWithOAuth` back to `/login`; local mode: the fake user).
     - New `/confirm-name` page and an `AuthGate` in the layout. Header: real name, Sign out added, persona switcher removed.
     - Deleted `lib/demo.ts` and `DevSignIn.tsx`.
     - `tsc` clean and `npm run build` OK (dev-login scan: 326 files). Lint still shows 7 old errors in Gemini's files.
   - **Docs:** `docs/GOOGLE_AUTH_SETUP.md` (new) and `docs/API_CONTRACT.md` (§3 and the dev routes).

### Decided
- By Saif: Google only; fake Google user in local mode; name confirm screen with the name taken from the token; backend never requires the flag; migration 0015 locally only; the Google Cloud, Supabase dashboard and Supabase apply steps are his.
- By Claude under delegation (listed in D-064 for veto): the validation rules, "keep = token name", the `new_user` dev option and its dev-only link, the Sign out placement, "Sign in" labels, `tools/demo.py` kept as a library, anonymous tokens refused in code.

### Open / next session
1. **Saif's browser test** of the flow (backend `dev_server.py start`, frontend `npm run dev:local`) and his veto/keep on the small visible changes.
2. After 30 Oct (Saif, in order, per `docs/GOOGLE_AUTH_SETUP.md`): approve applying **0014 and 0015** to Supabase, then the Google Cloud client, the Supabase Google provider, redirect URLs, anonymous sign-ins and Email off, then one light sign-in check.
3. Gemini (about 15 Oct): the real pages. The cart, menu add buttons, orders, restaurants, home, profile and chat panel still run on mock data; `activePersona` still feeds profile, chat panel and restaurants. The checkout sheet is still to build from `API_CONTRACT.md` Payments.
4. Still logged: re-run the 6f live evals on prompt v6 (local DB); card text doesn't name the branch; `chat_cli` has no turn lock and doesn't print `payment`; the Gemini requests/day number (`CHAT_DAILY_CAP`). Phase 10: clean up old anonymous visitor accounts (needs approval); `tools/demo.py` and the unused `demo_persona`/`is_sample` columns could be retired.
5. Phase 7 and 8 sign-offs once Gemini's frontend is wired.

### Pending for Saif
- Test the flow above; reply with anything to veto.
- The Gemini requests/day number. Optionally `PAYMENT_SIM_SECRET` in `backend/.env`.


## Session 23 - Phase 9 started: the MCP server (D-065, D-066, D-067)
- **Start:** 2026-10-14 12:24 IST (taken from the session's first message timestamp; the clock was not read at `start`)
- **End:** 2026-10-14 22:53 IST (clock read at `end`)

### What was done
1. **Saif's Phase 9 order:** (1) the MCP server, (2) multi-restaurant orders in one conversation, (3) "order my usual" and saved-preference use, (4) a Hinglish and Telugu test set. Plan approved as recommended. Only item 1 was worked on this session; M0-M2 of it are done.
2. **M0 (D-065):** pinned `mcp==2.3.0` and its dependencies in `backend/requirements.txt` (mcp-types, opentelemetry-api, python-multipart, sse-starlette, pywin32 on Windows only); `pip check` clean. Design is additive-only: the MCP caller is a model, not the user, so it can never give the "yes". If Claude Desktop cannot do elicitation (unconfirmed), the MCP confirms nothing and hands off to the website.
3. **M1 (D-066):** `backend/app/mcp_server.py` (stdio server, token from env `DAWAT_MCP_TOKEN` verified on EVERY call, `user_message=None`, no card, closed schemas, identical generic sign-in reply for any token failure) and `backend/mcp_run.py` (local launcher: `--as priya|arjun|family`, local dawat_dev DB, 12 h dev token, no Supabase path). Real stdio run verified. Identity planted bugs: 11/11 caught after adding a test that captures the ToolContext.
4. **M2 (D-067):** `backend/app/mcp_cart.py`, two additive tools `add_to_cart` and `add_plan_to_cart` (10 tools exposed in total). Limits (Saif asked for them): max 10 of one item, max 30 items per cart; confirmed cart never touched; non-veg refused for a saved vegetarian/eggetarian; plans only into an empty cart, no `replace` argument; replies carry no cart_id, quote_id or confirm card. Cart row locked during checks. Tests: 56 passing (`test_mcp_cart.py` 26 + `test_mcp_server.py` 30). Planted bugs: 14 single, 12 caught, 2 equivalent (other locks still refuse); combined mutants checked.
5. **Not run:** the full backend suite (no existing code changed; last full run was Session 22, 2,152 passed). No git, no Supabase.

### Decided
- By Saif: additive-only list as written; limits per item/cart over MCP; token lifetime for the deployed app deferred to Phase 10; file name `app/mcp_server.py`; local only until 30 Oct.
- By Claude (logged in D-065..D-067): per-call token verification, tool descriptions rewritten for MCP, limits' exact numbers (10 / 30), refusal codes.

### Open / next session
1. **M3 (ordering hand-off), proposed, awaiting Saif's "go":** an order-ready cart summary, a "continue on the website" link (needs `DAWAT_SITE_URL`, local default `http://localhost:3000` - Saif to confirm), a one-call-at-a-time lock per user, and a log of every MCP call.
2. **M4/M5:** consent/identity tests for M3 and a real client run; `docs/MCP_SETUP.md` (Claude Desktop config: command `.venv\Scripts\python`, args `backend\mcp_run.py --as priya`) and Saif's own test.
3. Then Phase 9 items 2 (multi-restaurant orders), 3 ("order my usual", needs confirmation), 4 (Hinglish/Telugu test set).
4. Still logged: re-run 6f live evals on prompt v6 (local DB); card text doesn't name the branch; `chat_cli` has no turn lock and doesn't print `payment`; Gemini requests/day number (`CHAT_DAILY_CAP`); apply migrations 0014/0015 to Supabase after 30 Oct with Saif's approval; Phase 10 cleanup of old anonymous accounts; MCP real Google sign-in/token lifetime in Phase 10.
5. Tooling note (CLAUDE.md claude-code-setup): the new MCP server is itself worth a mention when it is ready for Claude Desktop; a hook/sub-agent suggestion pass is still due.

### Pending for Saif
- Reply "go" for M3 and confirm the `DAWAT_SITE_URL` name/default.
- Browser-test the Google login flow (Session 22) and report vetoes.
- Phase 7 and 8 sign-offs once Gemini's frontend is wired; the Gemini requests/day number; optionally `PAYMENT_SIM_SECRET`.


---

## Session 24 — Pivot to a native mobile app (D-068), design v2, `.claude/` guard update, device setup doc, mobile M0 built (D-069)
- **Start:** 2026-10-15 (clock not read at `start`; the session opened on 15 Oct)
- **End:** 2026-10-15 12:15 IST (clock read at `end`)

### What was done
1. **Resumed:** memory.md for Sessions 1-23 was complete. M3 of the Phase 9 MCP work stays on hold.
2. **Pivot (Saif's pasted instruction, confirmed "yes" before acting):** Dawat is now a **native iOS/Android app** (Expo React Native, TypeScript, Expo Router) in `mobile/`. Backend, DB, tools, planner, agent and tests unchanged. `frontend/` and `frontend_old/` are legacy read-only web reference; Claude owns `mobile/`.
   - **Docs:** CLAUDE.md (overview, brand, Phases 7-10, stack, file map, out-of-scope, secrets rule, claude-code-setup), `docs/MOBILE_RULES.md` (new), API_CONTRACT section 6 (mobile client), GOOGLE_AUTH_SETUP Part B (native sign-in, for Saif after 30 Oct), README rewritten, DECISIONS D-068 plus addenda, NEEDS_BACKEND mobile table (Wallet, Payment methods, bell, hearts, Cancelled, "Online", ETAs/ratings, photos, avatar), `docs/MOBILE_PLAN.md` (stack comparison, modules M0-M8, networking, distribution costs, OSM tile policy), `docs/MOBILE_DEVICE_SETUP.md`.
3. **Design v2** (`docs/design/mobile_flow_v2.png`) replaced the first palette. Legend: coral `#FF5844`, sky `#A6D3F2`, butter `#F7D78C`, sage `#AFC3A8`, surface `#DBDBE5`; sampled: page `#E8F6FD`, navy `#21364B`, ink `#050D1A`, muted `#325574`, coral tint `#FBE8EA`. **White on coral is 3.12:1 (fails)**, so primary CTAs are navy with white text; coral is icons/badges with dark text/active states only (it is under 3:1 on page 2.83 and surface 2.27); muted text fails on sage (4.17). The small white pills became navy pills. **Saif decided the tracking card is navy** (not the dark green in the image); deepGreen removed.
4. **Saif's answers:** physical Android phone over USB with Expo Go, **no Wi-Fi/LAN and no 0.0.0.0 binding** (`adb reverse`); lowercase "dawat" wordmark with "Food, your way" (arch may return as the app icon); placeholder/illustration food images; Leaflet-in-WebView map if OSM tile policy allows (checked: allowed for interactive use with attribution and a distinct User-Agent; Referer risk in a WebView, spike in M5, else static placeholder map); Android APK plus demo video only, no paid stores.
5. **`.claude/` updates (diff shown and approved first):**
   - `settings.json`: allow `npm test|run test|lint|typecheck`, `npx tsc --noEmit`, `npx jest`, `npx expo-doctor`, `adb devices|version`; ask for `npm install|ci`, `npx expo install|start|run`, `create-expo-app`, `eas`, `adb reverse`.
   - `guard.py`: new secret pattern blocking `EXPO_PUBLIC_`/`NEXT_PUBLIC_` variable **names** containing SECRET, SERVICE_ROLE, PRIVATE, PASSWORD, DATABASE, GEMINI, GROQ, LLM, PAYMENT_SIM. 47 new tests (names, secret-looking values, allowed public names, a planted-bug test, mobile `.env` paths): **169 guard tests pass**. Live proofs: a secret-looking `EXPO_PUBLIC_` write was denied, the name rule denied a short value, a `mobile/.env` read was denied (by the permission deny rule). Known gap: a long random value under an innocent public name is not blocked.
6. **adb is not at `C:\platform-tools`** (checked): Saif installs it (steps in the device doc).
7. **Mobile M0 (D-069), Saif approved the installs:** Expo **SDK 57** (npm `latest` 57.0.29; SDK 58 only on `next`). Saif's Expo Go version was never given ("[fill in]"). Scaffolded by hand from the official template tarball (not `create-expo-app`, which may run git). All dependencies pinned exactly, lockfile kept. `expo-doctor` 21/21 after moving Jest to 29.7.0 (SDK 57 expects it); `expo install --check` clean; `tsc` clean; **Jest 101 passed** (contrast table recomputed row by row); an Android bundle export compiles. Planted bugs caught (21, 1 and 15 failing tests, then restored). RNTL 14 needs `test-renderer` (docs checked); 1.2.0 chosen because 1.3.0 needs React 19.3. Non-Expo packages published within 14 days were stepped down. `npm audit`: 65 findings from 5 advisories in build-time tooling; `--force` not run (it would downgrade expo to 44). One install script (`fsevents`, macOS only).

### Decided
- By Saif: the pivot, the tracking card navy, plan and docs approved, device and logo and images and map and distribution answers, the `.claude/` diff, each npm install.
- By Claude under delegation: font choice (Plus Jakarta Sans, Outfit, Noto Sans Telugu), navy pills, test stack versions, component design, placeholder app id `com.dawat.app`.

### Open / next session
1. **Saif:** install adb at `C:\platform-tools`; tell me the Expo Go version (SDK must match, 57 assumed); enable USB debugging; then the first run per `docs/MOBILE_DEVICE_SETUP.md` (verify `expo start --localhost` and the manual `exp://localhost:8081` URL). Confirm or change the placeholder app id.
2. **Next module M1 (needs Saif's go):** Welcome screen, local dev login (`/dev/auth/google`) gated by an inline build-time condition plus a release-build scan, secure-store token, `/me`, Confirm-your-name, sign out. Full rigour on identity.
3. **Then** M2 home and browse, M3 restaurant and cart, M4 chat (SSE spike first), M5 payment and tracking (map tile spike), M6 orders and profile, M7 polish and accessibility, M8 builds.
4. Phase 9 MCP M3 (on hold); Supabase work only after 30 Oct (migrations 0014/0015 and Google setup, Parts A and B); the Gemini requests/day number; 6f evals on prompt v6 still not re-run; card text doesn't name the branch; `chat_cli` has no turn lock.
5. Not yet verified: SSE streaming with `expo/fetch`, OSM tiles inside a WebView, fonts and look on a real phone, iOS (not testable on Windows).
6. A tooling suggestion pass is due when the app grows (a `mobile-checker` agent to replace the web `ui-checker`, Maestro later).

### Pending for Saif
- adb, Expo Go version, USB debugging, app id decision, and a first on-phone look at the Home design preview (report what you see).
- Optional: `PAYMENT_SIM_SECRET`; the earlier Google login browser test is superseded by the native flow.


---

## Session 25 — Oppo set up as the test phone, M0 signed off, M1 (sign-in, token, name confirm, dev-login lock) built (D-070)
- **Start:** 2026-10-15 (clock not read at `start`; later in the day than Session 24, which ended 12:15 IST)
- **End:** 2026-10-15 19:29 IST (clock read at `end`)

### What was done
1. **Device:** Oppo K10 5G (serial `N7QW9XWGAIWCQKIZ`) is the main test phone, Samsung A56 parked. Read from the phone by adb: Android 14, Expo Go 57.0.9 = SDK 57 (no change). `docs/MOBILE_DEVICE_SETUP.md` rewritten with the device table, `adb -s <serial>` commands, ColorOS battery/auto-launch notes and a known-issues section.
2. **Metro fix:** "Failed to download remote update" was Metro listening only on IPv6 `[::1]`; `adb reverse` reaches IPv4 `127.0.0.1`. Fixed with Node `--dns-result-order=ipv4first` (now inside `npm run dev:local`). Verified on the phone.
3. **M0 sign-off fixes (Saif's 5):** active tab is a raised sky circle with a navy icon (a `View` with `borderRadius` rendered as a hard square in the tab bar on the Oppo, cause not found; now an Ionicons `ellipse` glyph); Android status bar butter with dark icons (RN `StatusBar`; expo-status-bar has no backgroundColor); `Screen` bottom padding; the "ready" text is a real `/health` check (renamed "Backend connected"); the gear is Expo Go's dev overlay. Tests 102.
4. **M1 (D-070), Saif approved plan + `expo-secure-store` 57.0.4 (published 2026-09-11, pinned exactly):** `lib/api.ts`, `tokenStore.ts`, `session.tsx` (only a real 401 signs out; network/timeout/5xx keep the sign-in; late answers can't undo a sign-out), Welcome, Confirm your name, Profile with Avatar and Sign out, `Stack.Protected` routing in `_layout.tsx`, `DevLoginPanel` (Local sign-in + New fake user) behind one inline `__DEV__ && EXPO_PUBLIC_DAWAT_DEV_LOGIN === '1'` condition, `npm run dev:local`, `npm run check:release` (production bundle scan; shown to fail when `__DEV__` is removed). Tests 144 passing; 12/12 planted identity bugs caught; no `console.*` or AsyncStorage anywhere in `src/` (test scans source).
5. **Docs:** `docs/MOBILE_PLAN.md` section 8 (native Google sign-in needs a development build, not Expo Go; Phase 10 plan, items marked to verify), D-070 in DECISIONS.md.
6. **On the Oppo (by adb taps):** Welcome, New fake user, Confirm name, Home, Profile avatar (round) all verified by screenshot. Relaunch kept the sign-in twice; **one earlier relaunch returned to Welcome and was not reproduced** (logged in the device doc).
7. **Slip:** I put a `git diff` in a command; the guard blocked it, nothing ran.

### Decided
- By Saif: M0 signed off; M1 as proposed plus the 6 extras (only-401 sign-out, no token logging, rename, fake-user link, Google plan note, round-view record).
- By Claude under delegation: gate placement in `_layout`, no client-side expiry, test harness design.

### Open / next session
1. **M2 (home and browse)** needs Saif's go. Then M3 restaurant and cart, M4 chat (SSE spike first), M5 payment/tracking (map tile spike), M6 orders/profile, M7 polish, M8 builds.
2. Ask Saif whether the relaunch-to-Welcome happened again. Tab-bar rounded-view cause still unknown.
3. Unchanged: Phase 9 MCP M3 on hold; Supabase work and Google setup only after 30 Oct; 6f evals not re-run on prompt v6; card text doesn't name the branch; `chat_cli` no turn lock; tooling pass (a `mobile-checker` agent, Maestro) still due.
4. Stopped at end: backend dev server and Metro. Restart with `.venv\Scripts\python backend\dev_server.py start`, `adb -s N7QW9XWGAIWCQKIZ reverse` for 8000 and 8081, then `npm run dev:local` in `mobile/`.

### Pending for Saif
- Set the Oppo battery option for Expo Go to Unrestricted (not confirmed done); optionally create `mobile/.env` from `.env.example`.
- Say "go" for M2.


---

## Session 26 — Mobile M2 to M5: home/browse, menu/cart, Dawat AI chat, backend turn cancellation, test payment and tracking (D-071 to D-076)
- **Start:** 2026-10-16 (clock not read at `start`)
- **End:** 2026-10-16 about 19:30 IST (phone clock showed 7:22 pm at the last check; clock not read at `end`)

### What was done
1. **M2 home/browse (D-071)** accepted; 401-notice regression tests added (Welcome shows "Please sign in again."; the dev signing key persists in `backend/.dev_login/es256.pem`).
2. **M3 menu/cart/review (D-072)** accepted. **D-073:** the first dish in an empty cart sets the delivery area to the browsed area before adding (a real bug found on the phone: the add was refused "too far"); the cart shows "Delivering to <area>" with a mismatch notice; an all-"too far" cart is no longer shown as empty; a dev-only "Seed user with address" button on Welcome.
3. **M4 chat (D-074):** SSE streaming (`expo/fetch`), `ChatProvider`, thinking panel, consent cards whose buttons send exactly "Yes"/"No", selectable plan options, cart refresh after cart steps; 34 tests, 17 of 19 planted bugs caught (2 equivalent).
4. **Backend cancellation (D-075, Saif asked):** `run_turn(..., should_stop=...)` is checked only between steps; unrun tools get "not run" answers; a cancelled turn shows no card or plan; the endpoint polls for a gone client and always closes its stream. 17 tests, 10 of 11 planted bugs caught (1 equivalent). **Full backend suite: 2,225 passed, 0 failed (8m52s).**
5. **M5 payment and tracking (D-076):** `lib/payments.ts`, `payment.tsx` (fixed test cards/UPI only, no amount sent, verify only after a successful simulate), `lib/orders.ts`, order screen with timeline, bill, rider and a Leaflet/OSM map in `react-native-webview` 13.16.1 (exact pin). 47 tests, 13 of 13 planted bugs caught. App suite 281 passed, tsc clean.
6. **On the Oppo:** OSM tile spike (tiles load with the default and the Dawat user agent, 4 ok / 0 err each; Referer and attribution confirmed; spike screen deleted); payment sheet (decline path, then paid, order DW1025, ₹93); tracking advanced Placed to On the way with a Rider marker, no ETA; diet card as Priya (cart unchanged, "No" greys the card); a real turn stopped at a step boundary (`add_to_cart` answered "Cancelled before this ran", conversation did not grow).
7. **Bug found and fixed (mine):** the seed button matched names starting with "Priya" but the seed name is "Demo Priya (vegetarian)", so it signed in as Arjun; two of four real chat turns were wasted. Now matches "Priya" anywhere.

### Decided
- By Saif: M2 and M3 vetoes (keep "Typical main ₹N", "Under 0.1 km", area in storage, "Confirmed", on-device menu Veg only, "Delivery (free) ₹0"); cancellation to be built in the backend; MCP step M3 stays on hold; eslint (dev-only, pinned exactly, flag if under 14 days old) is added before M7.
- By Claude under delegation: Stop stays labelled "Stop" with an honest notice; map falls back to a plain map; payment copy and structure.

### Open / next session
1. **Remove-confirmation card not seen on the phone** (real-turn budget used up).
2. **Before any deployed build, Saif decides** the real `MAP_BASE_URL` and a contact address in the User-Agent (`lib/osm.ts`; placeholders now).
3. M6 (orders list/profile), M7 polish (overlapping Restaurant/Rider/You labels, "Pay now" plus "Place order" both shown on a confirmed cart, eslint, accessibility), M8 builds.
4. Expo patch updates waiting (expo 57.0.30, expo-router 57.0.28), not applied. Gemini requests/day number still pending (sets `CHAT_DAILY_CAP`). 6f evals not re-run on prompt v6. Residual cancellation limits: an in-flight model call (~20 s) finishes first; a stopped turn still uses a daily slot. Supabase work (migrations 0014/0015, Google setup) only after 30 Oct. Phase 10: clean up old anonymous accounts, measure egress.
5. Stopped at end: Metro exited (code 127) just before `end`; the backend may still be running. Restart with `.venv\Scripts\python backend\dev_server.py start`, `adb -s N7QW9XWGAIWCQKIZ reverse` for 8000 and 8081, then `npm run dev:local` in `mobile/`.

### Pending for Saif
- Decide the map contact address (above); say "go" for M6.

## Session 27 — A56 as test phone, M6 (orders and profile), M7 (polish, accessibility, eslint), M8 preparation (D-077 to D-079)
- **Start:** 2026-10-17 (clock not read at `start`)
- **End:** 2026-10-17 about 13:00 IST (adb process start times read at 12:55; clock not read at `end`)

### What was done
1. **Devices:** Samsung A56 (RZGL90DPYHZ, Android 16, Expo Go 57.0.9) used as the main test phone; no-chat smoke test passed; the active tab circle is round there ("not proven, Oppo-only likely", per Saif, no comparison needed). The Oppo (N7QW9XWGAIWCQKIZ) was used last for the narrow-width check.
2. **M6 (D-077):** Orders list (newest first, #DW numbers, server status and total, tap opens tracking, empty state) and Profile (name, Google note, four saved preferences with Edit and Forget, read-only addresses, Sign out). New `lib/account.ts` and `lib/userload.ts` (a per-user keyed loader: a late answer for another user is dropped). 20 planted bugs, 18 caught, 2 equivalent mutants; one real gap found and closed. Saif's veto applied: the line under a saved preference is plain "Saved".
3. **M7 (D-078):**
   - **Flake:** the Welcome-gate failure was jest's 5 s per-test limit on a cold transform cache (reproduced with `jest --clearCache`); `testTimeout: 20000` fixes it. My first guess (raise `waitFor` to 4 s) is recorded as "hardening based on a guess".
   - **ESLint:** `eslint` 9.39.5 and `eslint-config-expo` 57.0.2 pinned exactly; whole-project lint had 22 errors (not 10); now 0 errors and 0 warnings. The list of every disable comment and its reason was given to Saif.
   - **Map labels:** pure `placeLabels` (first free side of top, bottom, right, left), copied into the Leaflet page and kept equal by a 300-case test.
   - **Cart and payment:** a confirmed cart shows only "Pay now", an unconfirmed one only "Place order". 8 planted bugs in the payment and cart gates, all caught after two new tests; a further gap (the review screen's fresh read on open was untested) found and closed.
   - **Accessibility:** `a11y.test.ts` scans all source (roles, 44 pt targets, labels on icon buttons and inputs, no text-scaling lock except tab labels at cap 1.0, Modals close on Android back, Back falls back). The first version scanned zero files and passed; a count check now guards it.
   - **Narrow check:** A56 at 320 dp and 1.3x text; Oppo at its largest Display and Font size (set by hand, because ColorOS refuses adb changes). Fixed text touching borders (chips, pills, badge), titles running to the edge, and tab labels. A test order DW1026 (Rs128, simulated) was created on the Oppo to see real payment and tracking and is **left in the local data on Saif's instruction**.
4. **M8 preparation (D-079), nothing built or installed:** icon, adaptive and themed icons and splash from the lowercase "dawat" wordmark on navy (`scripts/make-assets.py`); splash plugin; `eas.json` with an `apk` release profile and a separate `development` profile; `version` 0.1.0 and `versionCode` 1 with auto-increment; `docs/MOBILE_BUILD.md` with Saif's exact steps; `buildconfig.test.ts`. eas-cli to be run as `npx eas-cli@24.9.0` (15 days old; 25.1.1 is one day old, official publisher).
5. **Mistakes of mine, all caught:** a Python write hit an encoding error on the rupee sign and emptied `__tests__/cart.test.tsx` (recovered exactly from the jest cache source map, then edited with the Edit tool); a stray `git -v` was blocked by the guard hook (no git ran); several Python text replaces silently did not apply, so the Edit tool was used.
6. **Shutdown:** Metro and the backend stopped; adb forwards removed; adb server stopped; nothing listens on 8000 or 8081. The two `node.exe` left are the Playwright MCP helper.

### Numbers (all run)
App suite 337 passed (from 281). `tsc` clean. `eslint` 0 errors, 0 warnings.

### Decided
- By Saif: M6 accepted with the "Saved" veto; M7 accepted; package `com.dawat.app` kept; icon and splash from the wordmark on navy; EAS cloud build; eas-cli 24.9.0; Expo patch updates left alone until the APK works; DW1026 stays; `MAP_BASE_URL` kept as a placeholder until deploy; contact address `[fill in]`.
- By Claude under delegation: the label placement rule, tab labels fixed at normal size, `testTimeout` 20000, ESLint overrides for tests only.

### Open / next session
1. **Suggested first:** Phase 9 step 3 (Hinglish and Telugu fuzzy matching and alias table, re-run the 6f evals on prompt v6) and the Phase 10 evals runner; in parallel Saif runs `eas login` and `eas init` (see `docs/MOBILE_BUILD.md`).
2. The M8 build run waits for Saif; the development build also needs `expo-dev-client` (not installed). A release APK cannot use the local backend (cleartext http is blocked); it needs the deployed https backend.
3. After 30 Oct: Supabase migrations 0014 and 0015, Google setup (Part B), SHA-1 registration, Render deploy, native Google sign-in test, MCP M3 (still on hold), final evals.
4. Phase 10: README with Mermaid diagram, failure cases, demo-video script, final interview prep.
5. If a test fails again at random, capture its output first.

### Pending for Saif
- Restore the Oppo's Display size and Font size by hand (originals: 720x1612, density 320, font 1.0).
- A real contact address for the map User-Agent; the Gemini requests-per-day number; `eas login` and `eas init`; the Edit and Forget taps on the A56 (M6), not yet done on a phone.
