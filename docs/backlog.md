# Backlog: later phases

Ideas and requirements decided along the way, kept for the phase where they belong. Phase 2 items live in `docs/phase2_backlog.md`.

## Areas and regions
- **"Old City" region (Saif, 2026-09-30):** a named region grouping Charminar, Purani Haveli, Afzalgunj, Falaknuma and nearby areas. It lets users say "old city" and see or be asked about those areas.
  - It is a grouping *above* `data/reference/localities.csv`, not a single point.
  - "Old City" was deliberately **not** made an alias of Charminar, because the old city is larger than the area around the monument (D-009).
  - Decide the member list with Saif when this is built (likely Phase 4 tools or Phase 7 UI).

## Phase 3 — Menus & Database (from Phase 2, 2026-09-30)
- ~~Veg-only restaurants must get veg-only menus.~~ **Done (D-019):** `validate_menus.py` fails on any non-veg item on a veg-only menu (37 restaurants).
- ~~Multi-cuisine template~~ **Done (D-017):** the generic Hyderabad family-restaurant template (biryanis, Chinese basics, North Indian curries, breads).
- ~~Minerva Coffee Shop is veg-only from general knowledge~~ **Done (D-014 addendum 2):** Saif verified it as pure vegetarian; its cuisine is now South Indian + Cafe and its menu was regenerated.
- **Chains share one menu across all their branches** (`restaurants` is the brand level, `branches` the place level). Done in `menus.json`; the DB schema (3d) must model menu_items per restaurant, not per branch.
- **menus.json is about 8.5 MB** because aliases are repeated per item. If the seed or repo size becomes a problem, move aliases to a `dishes` table and join.

## Phase 4 — Tools layer
- **Done in 4b (D-023):** repeated standalone names come back as separate `choices` labelled by area.
- ~~**Repeated standalone names:**~~ 43 exact names (46 ignoring case) are shared by 95 (105) separate restaurants (e.g. "Hot Chips"; D-015). Compare names case-insensitively. `search_restaurants` must return them as distinct results labelled by area. The agent should ask "which one: Madhapur or KPHB?" just as it does for chain branches.
- **Done in 4b:** branch results include `street`.
- ~~**Numbered branch labels**~~ ("Madhapur 1", "Madhapur 2") exist for 47 branches. Show the street (`branches.csv` → `street`) where available to help the user choose.

- **Done in 4c (D-024):** `search_dishes` answers `search_restaurants`' `dish_query` status ("biryani in Madhapur").
- **Done in 4f/4g (D-027):** order history, saved preferences (saved only when the user asks) and the website routes (`app/api/`). Phase 4 is complete.

## Phase 6 — Dawat AI Agent
- **From 4f (D-027), preferences:**
  - The runtime, not the LLM, fills `user_message` (the user's latest message) for `save_preference` / `delete_preference`.
  - The agent's tool schema offers only `chat_request` / `chat_confirmed` as the source, never `settings`.
  - The agent may *offer* to save ("Want me to remember you're vegetarian?") but saves only on the user's yes.
  - Phase 10 eval cases:
    - "I'm vegetarian, show me biryani" saves nothing;
    - "remember I'm vegetarian" saves diet;
    - a yes to the offer saves it as `chat_confirmed`;
    - "forget my spice level" deletes only `max_spice`.
- **From 4c (D-024):** the agent must act on `search_dishes`' fields:
  - `typo_corrections` → mention them;
  - `unmatched_words` → say we don't have that;
  - `quantity` → use it in add_to_cart;
  - `people` → use plan_meal;
  - `confirm_dish` / `confirm_area` → ask before searching again.
  - Requests naming two dishes are split into two calls.
- **From 4e (D-026):** ordering is always view_cart → show the summary → a clear "yes" → `confirm_cart(cart_id, quote_id)` → `place_order(cart_id)`.
  - On `stale_quote` or `quote_changed`, show the new summary and ask again; never retry silently.
  - `confirmation_cleared` means the same.
  - The agent must never call `confirm_cart` without a yes in the user's own latest message: an eval case for Phase 10.
- **Out-of-coverage areas (Saif, 2026-09-30):** when a user asks for an area outside our coverage, Dawat AI must **say so clearly**. It must not silently snap the request to the nearest covered area, and must not invent restaurants there.
  - Coverage means OSM relation 7868535 (D-005). Known examples just outside it are **Bowenpally**, which is left out of the area list (D-009), and **Manikonda**.
  - **Done in 4b (D-023):** `resolve_area` returns `outside_coverage`, `unknown_area`, `confirm_area` or `needs_area`, and `search_restaurants` stops on any of them. Still to do: a Phase 10 eval case.
  - The check belongs in code, in the tools layer: an unknown or out-of-coverage area returns an explicit "not covered" result, and the agent explains it. It should also be one of the Phase 10 eval cases.
- **From Phase 5 (D-028/D-029), the planner:**
  - The `MealRequest` field descriptions in `app/planner/request.py` become the `plan_meal` tool schema. The LLM sends whole numbers, never "₹1,000" as text.
  - Set `non_spicy_veg_count` **only** when the user said who ("the vegetarian one can't eat spicy"); otherwise leave it null.
  - `needs_info`: ask for `missing[0]` only, one question at a time.
  - `over_budget`: quote `cheapest_total` and `largest_group_within_budget` exactly. Offer to raise the budget or plan for fewer people. Never present `cheapest_plan` as the user's plan.
  - `no_valid_plan`: explain `reasons`. `planner_error`: apologise, offer a dish search instead.
  - Show plans as options with their totals as given, plus each plan's `diet_note` line.
  - On a pick: `add_plan_to_cart(request, plan_id)` with the **same** request. Then:
    - `cart_not_empty` → ask whether to replace, then pass `replace=true` only on a yes;
    - `plan_changed` → show the fresh plans;
    - then the usual summary → yes → `confirm_cart` gate.
  - Phase 10 eval cases:
    - the ₹500 spicy + one vegetarian demo request;
    - ₹150 for 4 (honest over-budget answer with the real price);
    - an unclear overlap (the note says "whoever");
    - "for 12 people" (refused: max 10);
    - "₹1000" written as text;
    - a group where everyone is veg (no non-veg anywhere);
    - the agent picking a plan and then the user changing the budget (plan_changed).
- **From Session 12 (D-028 addendum, D-030, D-031):**
  - **`confirm_cart` from chat.** The runtime, not the LLM, passes `source="chat"` and `user_message`, which is the user's own latest message. Neither appears in the tool schema the LLM sees. Never pass `source="website"` from the agent: it skips the yes check.
  - On `no_clear_yes`:
    - `consent = no`: ask what to change.
    - `consent = unclear`: show the summary again and ask for a clear yes.
    - Never retry `confirm_cart` in the same turn.
  - **`add_plan_to_cart(replace=true)`** gets the same treatment (Session 13, D-030 addendum, enforced in code): the runtime passes `source="chat"` and `user_message`. `no_clear_yes` → ask "replace your cart?" again. Phase 10 eval case: "ok thanks" to the replace question must not replace.
  - **`over_budget`:** say "the cheapest plan I found costs ₹X". Never say that no plan can exist; the planner is a heuristic (D-029 Session 12 addendum).
  - **Models:** `gemini/gemini-3.5-flash-lite` primary, `groq/openai/gpt-oss-120b` fallback. A Gemini 503 "high demand" was seen live on 3.8 Flash, so the fallback path must be tested with a simulated 503 and 429.
  - Phase 10 eval cases:
    - "yes" to a summary two messages back (must not count);
    - "yes but change the address" (unclear);
    - a Hinglish "haan kar do" and a Telugu "sare, order pettu" (yes);
    - "ok wait" (no);
    - an emoji-only "👍" (unclear: Dawat AI asks again).
- **From 6a (D-032), the LLM client:**
  - The agent loop calls only `app.agent.llm.chat()`; on `LLMUnavailable` it shows `user_message` and logs `attempts` to `agent_traces` (already scrubbed).
  - Send back the assistant's `raw_message` unchanged (Gemini 3 thought signatures).
  - Test a conversation that switches provider mid-way (Gemini → Groq and back) in 6c.
  - Tool `arguments` arrive as a raw JSON string: parse and validate them in 6c; malformed JSON goes back to the model as a correction, never a crash.
- **From 6b (D-033), the tools layer for the agent:**
  - 6c calls `run_tool(name, arguments, ToolContext(conn, user_id, user_message))`. `user_message` is the user's latest message, taken from the conversation.
  - `run_tool` doesn't commit: the loop commits after each successful write tool, and rolls back plus returns a generic error on an exception.
  - Keep tool results compact before sending them back (same token budget as the tool list).
  - `set_delivery` is area-only; a saved-address picker is a later decision (Phase 7/9).
- **From 6c (D-034), seen live, for 6d and 6f:**
  - **Language:** Gemini answered English questions in Telugu or Hinglish (twice), and Groq slipped into Devanagari partway through a Hinglish reply. The 6d prompt must say: reply in the user's language **and script**; English stays English.
  - **Grounding check (6f):** match every number shown next to a dish, not only "₹N". Groq put prices in a "Price (₹)" table column.
  - 6e: run `run_turn` on an **autocommit** connection (each tool commits on its own), and persist `Turn.messages` and `Turn.traces`.
- **From 6d/6e (D-035 to D-037), for 6f:**
  - Grounding checks must cover **names** as well as numbers: the 6e live run spelled "Annapura" for "Annapurna".
  - Check that each plan's `diet_note` is copied word for word.
  - Show order ids in a friendlier form: Phase 7's tracking page can link to them instead of showing the raw UUID in chat.
- **Phase 9 (memory), partly done early:** the saved **diet** is now used in plans and chat adds (D-039, Session 16). Saved **max_spice** is still not applied. a saved `diet = vegetarian` (or `max_spice`) must flow into `plan_meal` automatically: the user counts as vegetarian / non-spicy in `veg_count` / `non_spicy_count`. Not done in Phase 5 because applying preferences is Phase 9's job.

## Phase 7 — Web App
- **From 6e (D-037), the chat widget:**
  - Sign-in is required to chat, so add a one-click "Try the demo account" login (Saif's choice). Signed-out visitors see a sign-in prompt in the widget.
  - Read `POST /chat` as a server-sent event stream: `start` → `step`* (the thinking panel) → `reply` → `done`, or `error`.
  - HTTP 429 means the hourly demo limit: show its message.
  - Keep `conversation_id` from `start` and send it with the next message.
- **Order numbers (Saif, Session 15):** show a short order number like **#DW1042**, never the full UUID. This needs a short, human-friendly number per order, generated in code. Dawat AI's replies should use it too.
- **From 4g (D-027):** the website calls the routes in D-027's table.
  - Ordering is `GET /cart` → the user confirms that summary → `POST /cart/confirm {cart_id, quote_id}` → `POST /orders`.
  - A 409 response carries the fresh cart to show (stale quote, quote changed, item unavailable).
  - Preferences live at `/me/preferences`, and each one comes with `how_saved` text for the profile page.
  - Browsing routes are public; how sign-in looks is still to be decided.

## Phase 8 — Payments, Orders & Tracking
- **From D-045 (Session 16): resolved in D-061.** A chat message no longer re-opens a confirmed cart while its payment attempt is open (live, < 30 min, same quote).
- Open from D-061: no Razorpay webhook; refunds are recorded not called; re-run the 6f live evals on prompt v6; apply migration 0014 to Supabase after 30 Oct.

## Phase 10 — Deploy checklist
- **Re-check Supabase sign-in once before deploying (Saif, Session 20):** daily work uses the local dev login (D-059), so Supabase's own sign-in isn't exercised day to day. Before deploy, in the browser against Supabase: "Try as Priya" and "Try as Arjun" (anonymous sign-in + `/demo/start`), email sign-up and sign-in, sign-out, and a token refresh (stay signed in past an hour, then use the cart).
- **Dev login is absent from the deployed app (D-059, lock 5):** the Render service has no `DAWAT_DEV_LOGIN`; `/dev/auth/*` answers 404 on the live backend; the Vercel build passed `npm run check:no-dev-auth`.
