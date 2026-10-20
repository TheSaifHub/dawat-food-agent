# CLAUDE.md — Project Brain

**User:** Saif
**Project:** Dawat (Hyderabad food ordering **native mobile app** for iOS and Android, with an agentic ordering assistant, **Dawat AI**)
**Purpose of this file:** the source of truth for how Claude Code should operate on this project. Read it in full before doing anything.

---

## Project Overview

### What this project is
A **full-stack, Zomato-style food ordering native mobile app (iOS and Android) for Hyderabad** with an **agentic AI assistant, Dawat AI**, that can take an order entirely through chat. Starting from real restaurant locations pulled from OpenStreetMap, we (1) understand and verify the data, (2) clean and enrich it (chains, branches, areas, cuisines), (3) generate realistic synthetic menus and load everything into a database, (4) build a shared tools layer and backend API, (5) build a constraint-based meal planner, (6) build the Dawat AI agent on top of the tools, (7) build the native mobile app, (8) add payments, orders and live tracking, (9) add advanced agent features, and (10) evaluate, deploy and showcase it.

The build order is fixed and must not be reshuffled: **Setup → Data Understanding → Cleaning & Enrichment → Menus & Database → Tools & Backend → Meal Planner → Dawat AI Agent → Mobile App → Payments & Tracking → Advanced Features → Evaluation, Deployment & Showcase.**

**Pivot (2026-10-15, D-068):** Dawat is a native mobile app, not a web app. Phases 7–10 changed; the backend, database, tools, planner, agent and their tests are unchanged. `frontend/` (Next.js) and `frontend_old/` are **legacy web reference, read-only**: never extended, never deployed. The new client lives in `mobile/`.

In plain words: a user opens Dawat, browses real Hyderabad restaurants in a polished mobile app, or just tells Dawat AI what they want — "order a chicken biryani from Mehfil", or "Bro, I'm hungry. I have ₹500. I want something spicy for 2 people, but one person is vegetarian." Dawat AI asks what it needs (which branch area, delivery area), searches, plans, shows options, fills the real cart in the app, and **only places the order after the user explicitly confirms.**

### Why this project exists (the actual point)
This is a **portfolio project** to show recruiters real agentic AI and full-stack engineering skill: tool calling, clarifying questions, multi-step actions, constraint solving, safe agent design, a data pipeline, and a deployed product. The deliverable is a working, deployed, honestly evaluated system with clean code and a story Saif can defend in an interview — not a real food delivery business.

**Everything customer-facing is simulated:** menus, prices, users, orders, payments (test mode), and delivery tracking. Restaurant names and locations are real (from OpenStreetMap); nothing else about them is.

### The core design idea (every phase follows it)
**The LLM understands; code decides.**
- The LLM's job: understand the user (any language or style), extract structured intent, choose which tool to call, ask clarifying questions, and present results naturally.
- Code's job: every fact (restaurants, menus, prices), every calculation (totals, budgets, portions), every hard rule (veg, spice, budget, confirmation before ordering).
- The LLM must never invent a restaurant, dish, price, total, order ID or ETA. If a tool didn't return it, Dawat AI doesn't say it.

### Who does what
Claude Code builds almost everything. Saif owns anything that needs his identity, accounts, money decisions, or judgment.

**Claude Code does:** project scaffolding, data pipeline, database schema and seeding, backend, tools layer, meal planner, agent, mobile app, payments integration (test mode), tracking, advanced features, tests, evals, docs, deployment configs, debugging.

**Stop and ask Saif (never do these yourself):**
- Installing system software (Node.js, Python, Git) on his machine — guide him instead.
- Creating any account or generating any API key (GitHub, Supabase, Render, Expo/EAS, Google Cloud, Google AI Studio, Groq, and later Apple Developer / Google Play).
- Putting real secrets into `.env` or hosting dashboards — create `.env.example` with empty slots and tell Saif exactly what goes where.
- Connecting repos in the Render / EAS dashboards and setting their environment variables.
- Anything that costs money or needs a card. **The budget is ₹0** — if a step would require a paid plan, stop and propose a free alternative. (App Store / Play Store publishing needs paid accounts: Saif decides, never Claude.)
- Destructive database operations (dropping tables, deleting data, resetting Supabase) — explain first, wait for approval.
- Product and UX decisions (feature priority, how a screen should feel, whether an agent answer is good enough) — offer options, let Saif decide.
- Testing on a real phone or emulator as a real user — tell Saif what to test and what to look for, then act on what he reports or screenshots.
- The demo video, LinkedIn post, and resume entries.

### A note on honesty and quality expectations (read this before building anything)
- **The agent's credibility is the project.** One hallucinated price or one vegetarian user shown a chicken dish destroys the demo. Hard constraints are enforced in code and tested automatically, not requested politely in the prompt.
- **Free LLM tiers have rate limits and occasional errors.** Handle them gracefully (retries, a friendly "Dawat AI is busy, try again" message, fallback provider) — never crash the chat.
- **If eval results come out perfect, the default assumption is that the eval is too easy or is testing the wrong thing** — not that the agent is flawless. Check the test cases are realistic and the checks actually fail when they should (break something on purpose and confirm the eval catches it).
- Documented failure cases (ambiguous requests, impossible budgets, unknown dishes, mixed-language typos, rate-limit outages) are a required deliverable, not an embarrassment.

### Brand
- **Name:** Dawat (means "feast" / "invitation"). **Agent:** Dawat AI. **Tagline:** "Every order, a feast."
- **Design source of truth:** `docs/design/mobile_flow_v2.png` (10 screens; v2 replaces the earlier reference). Style: a cool blue-grey base, soft flatter cards and bento tiles, big radii, round food-photo placeholders, an initial avatar (no photo), a bottom tab bar (Home, Dawat AI, Cart with badge, Orders, Profile; active tab raised).
- **Palette (legend, exact):** accent coral `#FF5844`, secondary sky `#A6D3F2`, highlight butter `#F7D78C`, success sage `#AFC3A8`, surface `#DBDBE5`. **Sampled from the image:** page `#E8F6FD`, navy `#21364B` (primary buttons, Total tile), ink `#050D1A`, muted `#325574`, coral tint `#FBE8EA`, card white. The order-tracking card is navy (Saif, 2026-10-15). Full table and ratios in `docs/MOBILE_PLAN.md` section 1; the tokens live in `mobile/src/theme`.
- **Contrast rule (computed, tested):** white text on coral is 3.12:1 and fails, so it is never used. Primary CTAs are navy with white text (12.4:1). Coral is for icons, badges with dark text, active states and large text only, never small text on a light surface (coral is also under 3:1 on `page` and `surface`). Dark `ink` on sky, butter and sage; `muted` text never on sage. Every text/fill pair is recomputed by a test.
- **Fonts:** the rounded geometric sans in the design (identified in M0 and recorded in DECISIONS.md); **Noto Sans Telugu** for Telugu script.
- **Logo:** the lowercase "dawat" wordmark with "Food, your way" under it, as in the design, as a reusable component. (The earlier Mughal-arch mark is not in the new design; Saif decides whether it comes back.)
- Never copy Zomato's, Swiggy's or any other company's name, logo, colors, layouts or assets.

### Data
**Restaurants: OpenStreetMap via the Overpass API** (free, ODbL license).
```
[out:json][timeout:120];
area(3607868535)->.a;
nwr["amenity"~"^(restaurant|fast_food|cafe)$"](area.a);
out center tags;
```
- **Exact amenity match** (`^…$`): the original unanchored regex also matched `internet_cafe` (15 cyber cafés in the 2026-09-30 snapshot). Those rows are removed in Phase 2 cleaning with the count logged; the snapshot is not re-fetched. See DECISIONS.md D-007.
- **Boundary:** OSM relation **7868535** ("Hyderabad", admin_level 8), selected **by ID**. The Overpass area id is 3600000000 + relation id = `3607868535`. It covers the old city, Secunderabad and the western IT corridor (HITEC City, Gachibowli, Madhapur, Kondapur), and it contains Hyderabad District (7255986), which is therefore not queried separately. Never match by name: "Hyderabad" is ambiguous (e.g. Hyderabad, Sindh). Decided by Saif and confirmed in code in module 1a; see DECISIONS.md D-005.
- Public Overpass servers are often busy: check `https://overpass-api.de/api/status` first, send one request, and never retry in a loop.
- Fetched **once** by a script, saved raw to `data/raw/`, never called live from the app.
- Gives names, coordinates, and (sometimes) cuisine and address tags. Chains appear as multiple entries — this powers the "which branch area?" flow.

**Areas:** from `addr:suburb` / address tags when present; otherwise map coordinates to the nearest locality from a hand-built list of Hyderabad locality centre points (`data/reference/localities.csv`). If reverse geocoding with Nominatim is ever used: max 1 request/second, a proper User-Agent, results cached, never repeated.

**Menus: synthetic.** No free source has real menus, so menus are generated per restaurant based on cuisine, once, with a fixed seed, and stored. Every menu item must have:

| Field | Example | Used for |
|---|---|---|
| `name` | Chicken Dum Biryani | Display, search |
| `price` | 280 | Budget math |
| `is_veg` | true / false | Veg constraints |
| `spice_level` | 0–3 | Spice constraints |
| `serves` | 1 or 2 | Group portion math |
| `category` | biryani, starter, curry, bread, rice, dessert, drink | Filtering |
| `course` | main, side, dessert, drink | Building complete meals |
| `aliases` | biriyani, briyani, బిర్యానీ | Fuzzy / multilingual matching |

Prices must be realistic for Hyderabad and consistent within a restaurant. Generated menus are validated by code (no missing fields, prices in sane ranges, every restaurant has at least one veg item) before loading.

**Rules:**
- **Everything under `data/raw/` is read-only.** Never modify it. All cleaning and enrichment outputs go to new locations.
- **Attribution required:** "© OpenStreetMap contributors" on every screen that shows a map or restaurant data (the demo footer line), in the Profile "About Dawat" screen, and in the README.
- **No scraping** Zomato, Swiggy or any other platform. **No Google Places API** (needs billing, restricts storage).
- **No fake ratings or reviews** attached to real restaurant names.
- A visible **demo banner** on every app screen: "Demo project. Menus, prices and orders are simulated. Not affiliated with any restaurant."

### Out of scope for v1 (do not build unless Saif explicitly asks)
- Real money payments (Razorpay **test mode only**).
- Real restaurant integration, real delivery partners, a real rider app.
- Scraping any food platform.
- A public website, PWA or web wrapper of the app (rejected in D-068), and any paid distribution unless Saif decides otherwise.
- Any paid service.

---

## The Phases

### Phase 0 — Setup
Goal: a clean monorepo and working local environment.
- Monorepo: `backend/` (FastAPI), `mobile/` (Expo React Native; originally `frontend/` Next.js, now legacy), `data_pipeline/`, `evals/`, `docs/`.
- Python venv + pinned `requirements.txt`; Node with a lockfile.
- `.env.example` files for backend and frontend listing every variable with empty values and a comment on where Saif gets it. `.env` is gitignored.
- **Stop and hand over to Saif:** list the accounts to create and keys to paste, in order.
- Confirm the backend and the client both start locally with a health check.

### Phase 1 — Data Understanding
Goal: know exactly what OpenStreetMap gives us before changing anything.
- Fetch with the Overpass query; save raw JSON to `data/raw/` with the fetch date.
- Profile: total places by type, % with a name, % with a cuisine tag, % with address/suburb tags, cuisine distribution, places per area.
- **Chain detection:** find names appearing multiple times (Mehfil, Pista House, Shah Ghouse, etc.) — how many chains, how many branches each.
- Plot restaurant locations on a map to confirm they fall inside Hyderabad.
- Save charts to `results/eda/`; write findings to `docs/data_insights.md` (top findings first, each backed by a number that was actually computed).

### Phase 2 — Cleaning & Enrichment
Goal: a trustworthy restaurant table and a record of exactly what was done.
- Drop unnamed places and exact duplicates; log counts.
- Normalise chain names ("Hotel Mehfil", "Mehfil Restaurant" → brand "Mehfil") with a reviewed mapping, not blind fuzzy merging. Log ambiguous cases for Saif.
- Assign every branch an area (tags first, nearest-locality fallback). Log how many used each method.
- Classify cuisine where missing (from name keywords like "biryani", "bakery", "dhaba"; else "multi-cuisine"). Log the rule and counts.
- Code lives in `data_pipeline/clean.py`, rerunnable from the raw file, prints a before/after summary. Decisions go in `DECISIONS.md`.

### Phase 3 — Synthetic Menus & Database
Goal: a complete, realistic, queryable database.
- Supabase Postgres schema: `restaurants`, `branches`, `menu_items`, `users`, `user_preferences`, `addresses`, `carts`, `cart_items`, `orders`, `order_items`, `order_status_events`, `conversations`, `messages`, `agent_traces`.
- Migrations as SQL files in `backend/db/migrations/`.
- Generate menus per cuisine template (LLM-assisted once, fixed seed, cached to `data/processed/menus.json`), validate with code, then load.
- Row Level Security on user-owned tables (carts, orders, conversations).
- Seed script is idempotent and rerunnable. A small set of fictional demo users.

### Phase 4 — Tools Layer & Backend API
Goal: every capability exists as a tested Python function before any AI touches it.
- Tools layer (`backend/app/tools/`), each returning **plain JSON**:
  - `search_restaurants(query, area?)` → matching brands and their branches
  - `get_menu(branch_id, category?, is_veg?, max_spice?, max_price?)` → filtered items
  - `search_dishes(query, area, filters)` → dishes across nearby branches (fuzzy + aliases)
  - `plan_meal(budget, people, constraints, area)` → valid meal scenarios (Phase 5)
  - `add_to_cart(user_id, item_id, qty)`, `remove_from_cart`, `view_cart(user_id)`
  - `confirm_cart(user_id, cart_id)` → marks the cart confirmed (only after an explicit user "yes")
  - `place_order(user_id, cart_id)` → **fails unless the cart is confirmed**
  - `get_user_history(user_id)`, `get_preferences(user_id)`, `save_preference(user_id, key, value)`
  - `track_order(order_id)`
- **All totals are computed server-side** (items + delivery fee + taxes). Never trust a price sent from the client or produced by the LLM.
- FastAPI routes for the mobile app use the same tools layer.
- Unit tests for every tool with known inputs and expected outputs.

### Phase 5 — Meal Planner (the standout feature)
Goal: handle budget and group requests with guaranteed-correct results.
- **Step 1 — the LLM extracts constraints** into a strict JSON schema, e.g. for "₹1,000, 4 people, two vegetarian, one doesn't eat spicy, a good dinner":
  `{"budget": 1000, "people": 4, "veg_count": 2, "non_spicy_count": 1, "spice_preference": null, "meal_type": "dinner", "area": null}`
  Validated with Pydantic. Missing required info (e.g. area) → Dawat AI asks.
- **Step 2 — code builds combos.** Hard rules that can never be broken:
  - total (items + delivery fee + taxes) ≤ budget
  - every vegetarian person gets at least one veg main they can eat
  - every non-spicy person gets a main with `spice_level ≤ 1`
  - total `serves` ≥ number of people
  - "dinner"/"meal" includes a main plus a side, bread or rice — not snacks only
  - only open-for-demo branches in or near the delivery area
- **Step 3 — score and diversify:** budget usage, spice match, variety, single restaurant preferred (one delivery fee). Return the **top 3 genuinely different scenarios** (e.g. best value, best match, mix-and-match / family pack), each item marked veg/non-veg and spice level.
- **Impossible requests** (e.g. ₹150 for 4 dinners): say so honestly and offer the closest valid option with its real price. Never silently break a rule.
- Property-based tests (Hypothesis) that generate random budgets/groups and assert no returned plan ever violates a hard rule.

### Phase 6 — Dawat AI Agent
Goal: a reliable, safe, conversational agent on top of the tools.
- LLM via **LiteLLM**: Gemini (free tier) as primary, Groq (free tier) as fallback, provider switchable by config.
- Agent loop with native function calling; max tool-call steps per turn to prevent loops.
- System prompt rules (in `backend/app/agent/prompts/`):
  - If a restaurant has multiple branches, ask which area before showing a menu.
  - When a category is requested (biryani, shawarma), show only that category.
  - Budget / group / dietary requests always go through `plan_meal`.
  - Never state a restaurant, dish, price, total or ETA that didn't come from a tool.
  - Always summarise the cart with the server-computed total and ask for a clear "yes" before `confirm_cart` → `place_order`.
  - Reply in the user's language/style (English, Hinglish, Telugu).
- Conversation state persisted in `conversations` / `messages`; every tool call logged to `agent_traces`.
- Streaming responses (SSE) to the client.
- Graceful handling of rate limits, timeouts and malformed tool arguments.

### Phase 7 — Mobile App (iOS + Android)
Goal: a polished native app in the Dawat design (`docs/design/mobile_flow_v2.png`), built in `mobile/` with Expo React Native, TypeScript and Expo Router.
- **Ten screens:** Welcome/Login (Google only), Home, Dawat AI chat, Confirmation card, Restaurant menu, Cart, Payment (simulated), Order tracking, Orders, Profile. Bottom tab bar: Home, Dawat AI, Cart (badge), Orders, Profile.
- **Dawat AI chat** is a tab and is reachable from Home:
  - Chat and app share one backend cart; the cart tab and badge refresh after every cart-changing step.
  - A **"Dawat AI is thinking" panel** of live tool steps (from the SSE `step` events).
  - Plan options are selectable cards; confirmation cards come from the backend. **Card buttons send exactly "Yes" or "No" through the chat** (whatever the label says); they never call confirm or place-order directly.
- **Never faked:** the app sends no price, user id or `source`; totals come from the server; no ETAs, ratings or invented features. Design elements the backend lacks (Wallet, Payment methods, notification bell, favourite hearts, Cancelled status, "Online" presence) are left out or disabled and listed in `NEEDS_BACKEND.md`.
- **Every screen:** demo banner; OpenStreetMap attribution on map screens; "Waking up Dawat AI…" for backend cold starts; loading and error states.
- **Accessibility:** 44pt touch targets, `accessibilityLabel` on icon buttons, readable contrast, dynamic text sizes, safe areas, Android back button.
- Food images: no copyrighted photos. Placeholders or illustrations; free licensed photos only with credit and Saif's decision.
- Rules: `docs/MOBILE_RULES.md`. Plan: `docs/MOBILE_PLAN.md`. Modules M0–M8.

### Phase 8 — Payments, Orders & Tracking
Goal: a checkout and tracking flow that feels real, with no real money.
- **Simulated payment (D-061, D-062):** the backend creates the payment attempt with the server-computed amount; the app shows a "Test payment (simulated). No real money." sheet (fixed test card and UPI values only; no wallet); the backend **verifies the HMAC signature** before creating the Dawat order. The Razorpay path stays behind a config switch and is not used.
- Dawat AI can trigger the same payment step after the user's clear "yes".
- One order per branch for multi-restaurant carts, with one combined summary.
- Simulated status progression (Confirmed → Preparing → Picked up → On the way → Delivered) written to `order_status_events`, with a rider marker moving on a map screen (OpenStreetMap tiles with attribution).

### Phase 9 — Advanced Features
Goal: the features that make Dawat stand out. Build in this order, each fully working before the next:
1. **Multi-restaurant orders** in one conversation ("one biryani from Mehfil and two shawarmas from Arabian Mandi").
2. **Memory:** "order my usual" (from history), saved dietary preferences applied automatically (a saved vegetarian never gets non-veg suggestions). Still requires confirmation.
3. **Hinglish and Telugu:** fuzzy dish matching (`rapidfuzz`) + alias table; a test set of mixed-language requests.
4. **MCP server:** expose the same tools via the official MCP Python SDK so Claude Desktop can browse and order from Dawat (same confirmation rules apply).
5. **Voice ordering:** on-device speech-to-text (the module is chosen then; it likely needs a development build, not Expo Go) → text → the same agent.

### Phase 10 — Evaluation, Deployment & Showcase
Goal: honest numbers, an installable app, and a strong presentation.
- **Evals** (`evals/`): 50+ scripted conversations, at least 15 budget/group planner scenarios, plus multilingual, multi-restaurant, memory and edge cases.
- **Automated hard checks:** budget never exceeded; dietary rules never violated; no order without confirmation; no restaurant/dish/price absent from the database; correct clarifying questions asked.
- Report: task completion rate, constraint-compliance rate, average tool calls per order, latency, and **documented failure cases**.
- **Deploy:** backend → Render (free), database/auth → Supabase (free), app → an installable Android APK and Expo Go / development build (free). **App Store / TestFlight and Google Play need paid accounts** (Apple about US$99/year, Google Play about US$25 once; confirm current prices): Saif decides. Saif connects dashboards and sets env vars; Claude Code prepares configs and exact instructions.
- **README:** what it is, how to install the app (APK / Expo Go link), architecture diagram (Mermaid), key design decisions, eval results, failure cases, limitations, how to run locally, attributions.
- Supply Saif a demo-video script (screen recording from a phone or emulator): ₹500 spicy + veg request, a Hinglish order, multi-restaurant order, "order my usual", and ordering via Claude Desktop (MCP).

---

## Stack
| Layer | Tool |
|---|---|
| Mobile app | Expo React Native, TypeScript, Expo Router (see `docs/MOBILE_PLAN.md` for the module choices); builds via EAS or local Android Studio |
| Maps | OpenStreetMap tiles in a native map view (library chosen in the plan) with attribution |
| Backend | FastAPI (Python), Pydantic |
| Database + Auth | Supabase (Postgres, Auth, Row Level Security) |
| LLM | LiteLLM → Gemini (primary, free tier), Groq (fallback, free tier) |
| Data pipeline | requests, pandas, numpy, rapidfuzz |
| Charts | matplotlib, seaborn |
| Payments | Local simulated gateway (default, D-062); Razorpay Test Mode code kept behind a switch |
| MCP | Official MCP Python SDK |
| Testing | pytest, Hypothesis (backend); Jest + React Native Testing Library (app); Maestro (device flows, later) |
| Deployment | Render (backend), Supabase (DB), EAS or local build (APK; stores only if Saif pays) |
| Environment | Python venv + pinned `requirements.txt`; Node with `package-lock.json` and exact pins |

## Definition of done
The project is complete when we have: a data insights document with real charts; a cleaning and enrichment pipeline reproducible from the raw OpenStreetMap file; a seeded database with validated synthetic menus; a fully tested tools layer; a meal planner whose hard rules are proven by property-based tests; Dawat AI ordering end to end with confirmation enforced in code; a polished Dawat native mobile app (iOS and Android) with the Dawat AI chat, cart sync and thinking panel; simulated test payment with signature verification; simulated live tracking; multi-restaurant orders, memory, Hinglish/Telugu, MCP and voice working; an eval suite with honest numbers and documented failure cases; a deployed backend plus an installable app build; and a README a recruiter can understand in two minutes.

---

## Session Control (non-negotiable)
- Do not begin any work until Saif types exactly `start`.
- Do not end a session until Saif types exactly `end`.
- Never push code to git/GitHub unless explicitly instructed to do so in that specific turn. Assume no push authority by default.
- **No git operations at all.** No commits, no staging, no branches, no `git` commands of any kind (including read-only ones like `git status`), and no tools that run git implicitly (e.g. pass `--disable-git` to scaffolders). Saif handles all git and GitHub manually after the project is complete. (Decided 2026-09-29, Session 1.)

## On "start"
1. Read `memory.md` in full (if it does not exist yet, this is Session 1 — say so).
2. Summarize, in plain language, where the project left off.
3. Propose next step(s) based on current state and the phases above — use judgment, not a checklist.
4. Flag anything Saif must do himself (accounts, keys, dashboards, testing) before that work can continue.
5. Wait for Saif's go-ahead before writing or running any code.

## On "end"
1. Append an entry to `memory.md`:
   - Session start timestamp
   - Session end timestamp
   - Summary: what was done, what was decided, what's still open, and any pending action for Saif
2. Update `learning.md`:
   - Concepts learned this session (not just what was coded)
   - Commands used
   - Approach/method followed
   - Blockers hit
   - How each blocker was resolved
3. Update `interview-prep.md`:
   - New Q&A generated from the actual work done this session — grounded in what was really built/decided, not generic trivia. Include agent- and system-design questions (why the LLM extracts constraints but code does the math, how the confirmation gate works, how hallucinated prices are prevented, why totals are computed server-side, how the planner guarantees dietary rules, how tool calling works, how free-tier rate limits are handled, why synthetic menus, how the eval proves correctness).

## On project completion
Generate `final-interview-prep.md` — a comprehensive, rigorous Q&A covering the project end to end (the problem, data sourcing and licensing, cleaning and chain detection, synthetic menu design, database design, the tools layer, the meal planner and its guarantees, the agent loop and safety design, frontend architecture and cart sync, payments and signature verification, MCP, evaluation and failure cases, deployment trade-offs on free tiers, what would be done differently at real scale, and why a perfect eval score would have been a red flag).

---

## File map
| File / Folder | Purpose |
|---|---|
| `data/raw/` | Raw Overpass JSON (read-only). |
| `data/reference/` | Hand-built reference files (e.g. `localities.csv`, chain name mapping). |
| `data/processed/` | Cleaned restaurants, branches, generated `menus.json`. |
| `data_pipeline/` | `fetch_osm.py`, `clean.py`, `enrich.py`, `generate_menus.py`, `validate_menus.py`, `load_db.py`. |
| `backend/app/tools/` | The shared tools layer (JSON-returning functions). |
| `backend/app/planner/` | Meal planner logic. |
| `backend/app/agent/` | Agent loop, LiteLLM config, prompts, tool schemas. |
| `backend/app/api/` | FastAPI routes for the website. |
| `backend/app/payments/` | Razorpay test integration and signature verification. |
| `backend/app/mcp_server.py` | MCP server exposing the tools. |
| `backend/db/migrations/` | SQL migrations. |
| `backend/tests/` | Unit, property-based and integration tests. |
| `mobile/` | The Expo React Native app (screens, components, Dawat AI chat, theme tokens). Owned by Claude. |
| `frontend/`, `frontend_old/` | **Legacy web reference, read-only.** Not extended, not deployed. Logic is ported from `frontend_old/src/lib` into `mobile/`. |
| `docs/MOBILE_PLAN.md`, `docs/MOBILE_RULES.md`, `docs/design/mobile_flow_v2.png` | The mobile plan, the client rules, the design reference. |
| `evals/` | Eval conversations, runner, results, failure cases. |
| `results/` | `results/eda/` charts and other generated outputs. |
| `docs/` | `data_insights.md`, architecture diagram, design notes. |
| `memory.md` | Session log. Read at the start of every session to resume exactly where things left off. |
| `learning.md` | Session-by-session learning log — concepts, commands, approach, blockers, resolutions. |
| `interview-prep.md` | Rolling interview Q&A, updated every session. |
| `final-interview-prep.md` | Comprehensive final Q&A, created once the project is complete. |
| `DECISIONS.md` | One entry per meaningful decision and its reasoning (data cleaning rules, chain mapping, area assignment, menu schema, planner rules and scoring, LLM provider choice, agent rules, tool JSON schemas, deployment choices). Kept separate from memory.md so it stands alone as a clean artifact. |

## Engineering discipline
- **No fabricated results:** never report a metric, chart, insight, or claim without actually running the code that produces it. If something can't be verified yet, say so explicitly instead of estimating.
- **Code decides, LLM talks:** prices, totals, availability and rule checks always come from code and the database.
- **Reproducibility:** fixed seeds for menu generation and eval runs; log provider, model and prompt version for every eval run.
- **Raw data is sacred:** all transformations are code-driven and rerunnable from `data/raw/`.
- **Test locally, never on Supabase (Saif, 2026-10-06, D-052):** tests, evals, rule-breaker runs and migration rehearsals run only against the local PostgreSQL 17 (`TEST_DATABASE_URL`, built by `backend/db/local_setup.py`); they refuse to start if it isn't on this machine. Supabase gets only real migrations (`migrate.py --apply`, after they pass locally), the seed, and the live app.
- **Daily work avoids Supabase entirely (Saif, 2026-10-07, D-059, after an egress warning):** the app runs in local mode: backend `dev_server.py start` (the local `dawat_dev` database + the local dev login) and the Expo app in dev mode with the dev-login switch (see `docs/MOBILE_PLAN.md`; the backend is never bound to a network interface without Saif's approval). `dev_server.py start --supabase` is only for an occasional, deliberate light check. The dev login can never be on in a deployed app (five locks, D-059).
- **Secrets:** API keys only in `.env` / hosting env vars — never in code, notebooks, logs, commits or the app bundle (`EXPO_PUBLIC_*` values are embedded in the app and readable by anyone; only public values like the API URL and the Supabase publishable key may use that prefix). Auth tokens live in `expo-secure-store`.
- **Security basics:** server-side price computation, Razorpay signature verification, Supabase RLS, input validation on every route, no secrets in agent traces shown in the UI.
- **Free tier only:** respect Overpass, Nominatim, Gemini and Groq usage limits; cache aggressively; never loop API calls.
- **Licensing and ethics:** OpenStreetMap attribution; no scraping; no fake ratings on real restaurants; demo banner always visible; no real personal data in demo accounts.
- **Environment:** pinned dependencies, kept up to date as they change.
- **Repo structure:** keep it consistent across sessions.

## Working style
- **No whole-codebase dumps.** For any multi-file or multi-step piece of work, propose a short module-by-module plan first, then implement and verify one module at a time — don't write the entire thing in one pass.
- Each module should be independently reviewable and testable (run the script, hit the endpoint, open the page) before moving to the next.
- Notebooks and scripts are built step by step (load → profile → visualise → decide), not generated as one giant block.
- Explain the *why* behind each step in plain language as it is done — Saif is learning, not just collecting code.
- When something needs Saif (account, key, dashboard, test, decision), stop and say exactly what he needs to do, step by step.

---

## claude-code-setup
Read the full codebase and current project structure, then explicitly suggest:
- MCP servers that would meaningfully help this specific project (e.g. Supabase read-only, Context7 for Expo / React Native / FastAPI docs). Playwright and the `ui-checker` agent are web-only and do not fit a native app; they stay for the legacy `frontend/` only.
- Claude Code skills that align with the work being done (e.g. Expo's official skills if Saif approves them, testing).
- Hooks that would help enforce the session-control, read-only-raw-data, no-secrets-in-git and no-push-without-instruction rules above automatically, plus env-file protection for `mobile/.env` and a secret scan for `EXPO_PUBLIC_` names (proposed, not yet saved).
- Sub-agents that would help split or parallelize the work (e.g. one for the data pipeline, one for backend/agent, one for the mobile app, one for evals). A native accessibility/contrast checker (reading the app's theme tokens and running Jest) would replace `ui-checker`.
- Test tooling: Jest + React Native Testing Library now; Maestro for device flows later.

Do this proactively whenever the codebase changes significantly — not just once at the start.
