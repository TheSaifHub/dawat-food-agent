> **LEGACY (2026-10-15, D-068):** these are the rules for the retired web frontend. The current client is the native mobile app: see `docs/MOBILE_RULES.md`.

# Frontend rules for Dawat

Short list. The rules come from CLAUDE.md and the decisions so far. The API details are in `docs/API_CONTRACT.md`.

## Correctness and safety (non-negotiable)
1. **Never compute or invent money.** Show `price`, `line_total`, `delivery_fee`, `taxes`, `total`, `grand_total` exactly as the API returns them (`₹` + integer). No client-side totals, tax, fees or "savings".
2. **Never invent facts**: no ETAs (the API says there is none), no ratings, reviews, delivery times, offers or discounts. Real restaurant names and locations only; everything else is simulated.
3. **Ordering gate**: show the cart → user confirms *that* summary → `POST /cart/confirm {cart_id, quote_id}` → `POST /payments/start {cart_id}` → your test checkout sheet → `POST /payments/simulate` (simulated gateway, fixed test card/UPI values only, see API_CONTRACT §Payments) → `POST /payments/verify` with the three values checkout returns. An order exists only after a verified payment: never show "order placed" before `/payments/verify` answers `ok`. Never send an amount, and never send a CVV, expiry or real card number. A failed payment (402) creates no order: keep the cart as it is and let the user retry. Never skip a step, never reuse an old `quote_id`. On `stale_quote` / `quote_changed` re-fetch the cart, show the new total and ask again. On `needs_refund` show its message (no order was placed) and send the user back to the cart.
3a. **Tracking is simulated**: say so in the UI, show no ETA, and move the rider marker only to the `rider` position the API returns.
4. **No secrets in the browser.** Only `NEXT_PUBLIC_*` values: API URL, Supabase URL, Supabase publishable (anon) key, Razorpay test key id later. No service keys, no LLM keys.
5. **The user id comes only from the token.** Never send a user id, price, status or `source` in any body (the API refuses extra fields).
6. **The dev login must never ship** (API_CONTRACT §3). Gate it with the full inline condition `process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_DAWAT_DEV_LOGIN === "1"`, and make the production build fail if its output contains the dev-login code.
7. Don't log tokens, and don't show raw backend errors or stack traces. Show the body's `message` or a friendly line.

## Required on every page
- **Demo banner**, always visible: "Demo project. Menus, prices and orders are simulated. Not affiliated with any restaurant."
- **Footer credit**: "© OpenStreetMap contributors" (a link to openstreetmap.org/copyright). Map tiles carry their own attribution too.
- **Dawat AI chat launcher** on every page, sharing one cart with the page (re-fetch `GET /cart` after cart-changing steps and after `done`).
- **"Waking up Dawat AI…" loader** if the backend is slow on first call (free-tier cold start). Poll `GET /health`; use a 70 s timeout for the first calls.
- Local dev mode shows a visible "Local data" badge.

## Brand
- Name **Dawat**; agent **Dawat AI**; tagline "Every order, a feast."
- Colours: Plum `#5B1E4E` (primary), Gold `#D8AE4A` (accent), Ivory `#FAF6EF` (background), Night `#22161F` (text).
- **Gold is for lines, icons and highlights on plum or night only. Never gold text on ivory.**
- Fonts: Cormorant Garamond (headings), DM Sans (body/UI), via Google Fonts.
- Logo: a Mughal-style arch with a covered dish, gold line art on plum, as an inline SVG component. Original design.
- Never copy another company's name, logo, colours, layouts or assets. Photos only from free sources with credit (Unsplash/Pexels), or neutral illustrations.

## Accessibility
- WCAG AA: 4.5:1 for body text, 3:1 for large text, UI borders and focus rings.
- Real `<button>`, `<a>`, `<label>`; everything keyboard-reachable with a visible focus ring; skip link; one `main` landmark.
- Works down to **360 px** wide with no horizontal page scroll.
- Veg/non-veg shown with the standard dot **plus** text (not colour alone); spice shown as words (Mild / Medium / Spicy) with the level.
- Chat: one polite live region for new replies; Escape closes it; focus returns to the launcher; modal below ~640 px.

## UX behaviour to keep
- **Area first**: browsing, dish search and the planner all need a delivery area (`GET /areas`). Remember it (localStorage, wrapped in try/catch) and ask once.
- Treat 200 answers like `needs_area`, `confirm_area` ("Did you mean Madhapur?"), `needs_info`, `over_budget`, `no_valid_plan` as normal screens with a helpful message, not errors.
- Order numbers: show `DW1042`, link to `/orders/DW1042`. Never a UUID.
- The chat's thinking panel lists `step` events live, then folds into "How Dawat AI got this · N steps".
- Confirmation cards and plan cards are rendered from the API payload. Never build or edit a card on the client.
- Save to `localStorage`/`sessionStorage` only for per-viewer conveniences, always in try/catch, and the page must work without it.
- Preferences saved on the settings screen use `PUT /me/preferences/{key}`; never infer or auto-save a preference.

## Pages expected (Phase 7)
Home (area selector, cuisine shortcuts, chains near you) · Restaurant listing (filters: veg, mild, price, cuisine, distance; no delivery-time filter) · Restaurant page (menu by category, branch info, Leaflet + OSM map) · Cart · Checkout · Orders and order tracking · Profile (preferences, addresses, sign out) · Login (Try as Priya / Arjun first, email second).

## Out of scope
Real-money payments (Razorpay TEST mode only; test keys start with `rzp_test_`), native apps, scraping, any paid service, fake reviews.

## Working agreement
Gemini owns `frontend/`. Claude owns the backend, databases, migrations, tests and deployment. If the frontend needs a new field or route, ask Saif; don't work around the API by computing things on the client.
