# Mobile rules for Dawat (the `mobile/` app)

Adapted from `docs/FRONTEND_RULES.md` (the web version, now legacy). The API details are in `docs/API_CONTRACT.md` (see its "Mobile client" section). The design is `docs/design/mobile_flow_v2.png`. Claude owns `mobile/`.

## Correctness and safety (non-negotiable)
1. **Never compute or invent money.** Show `price`, `line_total`, `delivery_fee`, `taxes`, `total`, `grand_total` exactly as the API returns them (`₹` + integer). No client-side totals, tax, fees or "savings". The design's Food / Delivery / GST / Total tiles come straight from the cart response.
2. **Never invent facts:** no ETAs (the API says there is none), no star ratings, reviews, offers or discounts, no "Online" presence, no favourite hearts, no notification bell, no Cancelled status, no Wallet. Anything in the design the backend does not support is left out or disabled and listed in `NEEDS_BACKEND.md`.
3. **Ordering gate:** cart → the user confirms *that* summary → `POST /cart/confirm {cart_id, quote_id}` → `POST /payments/start {cart_id}` → the test payment sheet → `POST /payments/simulate` → `POST /payments/verify`. An order exists only after `/payments/verify` answers `ok`; never show "order placed" earlier. Never send an amount, a CVV, an expiry or a real card number. A 402 creates no order: keep the cart and let the user retry. On `stale_quote` / `quote_changed` re-fetch the cart, show the new total and ask again. On `needs_refund` show its message and send the user back to the cart.
3a. **Card buttons send exactly `Yes` or `No` through the chat** (whatever the label says, e.g. "Yes, place this order" or "No, change it"). They never call confirm or place-order directly. Cards and plan cards are rendered from the API payload, never built or edited on the device.
3b. **Tracking is simulated:** say so, show no ETA, and move the rider marker only to the `rider` position the API returns.
3c. **Payment is labelled** "Test payment (simulated). No real money." wherever it appears.
4. **No secrets in the app bundle.** `EXPO_PUBLIC_*` variables are **embedded in the app bundle** and readable by anyone who unpacks the app, so they follow the same no-secrets rule as `NEXT_PUBLIC_*` did on the web. Allowed: API base URL, Supabase URL, Supabase publishable (anon) key, Google client IDs. Never: service keys, LLM keys, the Google client secret, `PAYMENT_SIM_SECRET`.
5. **The user id comes only from the token.** Never send a user id, price, status or `source` in any body (the API refuses extra fields).
6. **The dev login must never ship.** Gate every use behind one inline build-time condition (`__DEV__ && process.env.EXPO_PUBLIC_DAWAT_DEV_LOGIN === "1"`) and make the release build fail if its output contains the dev-login code (the same idea as D-059's five locks; details in M1).
7. **Tokens live in `expo-secure-store`,** never in AsyncStorage or logs. Don't show raw backend errors or stack traces; show the body's `message` or a friendly line.

## Required on every screen
- **Demo banner**, always visible: "Demo project. Menus, prices and orders are simulated. Not affiliated with any restaurant."
- **"© OpenStreetMap contributors"** on every map screen (restaurant map, order tracking) and in Profile → About.
- Local dev mode shows a visible "Local data" badge.
- A **"Waking up Dawat AI…"** state when the backend is slow on first call (poll `GET /health`; 70 s timeout for the first calls).
- Loading, empty and error states for every list and action.

## Design and brand
- Follow `docs/design/mobile_flow_v2.png`: soft flatter cards, bento tiles, big radii, bottom tab bar (Home, Dawat AI, Cart with badge, Orders, Profile; active tab raised). The lowercase "dawat" wordmark with "Food, your way" under it. An initial avatar instead of a photo.
- **Use only the palette in `docs/MOBILE_PLAN.md` section 1** (legend: coral `#FF5844`, sky `#A6D3F2`, butter `#F7D78C`, sage `#AFC3A8`, surface `#DBDBE5`; sampled: page, navy, ink, muted, coral tint). **Primary CTAs are navy with white text. White on coral fails (3.12:1) and is never used.** Coral = icons, badges with dark text, active states and large text only, never small text on a light surface. Dark `ink` on sky, butter and sage; `muted` never on sage. Small pills ("Best match", "Variety") are navy with white text. Every pair is checked by a test.
- Fonts: the design's rounded geometric sans; **Noto Sans Telugu** for Telugu script. Replies may be English, Hinglish or Telugu: render any Unicode.
- Never copy another company's name, logo, colours, layouts or assets. No copyrighted photos: placeholders or illustrations unless Saif approves free licensed photos with credit.

## Accessibility
- 44pt minimum touch targets; `accessibilityLabel` (and role) on every icon button; veg/non-veg shown by the standard dot **plus** text; spice as words (Mild / Medium / Spicy).
- Readable contrast (AA 4.5:1 body, 3:1 large text and UI); dynamic text sizes (no fixed heights that clip); safe areas; the Android back button always does the expected thing.
- Chat: new replies announced to screen readers; the thinking panel is optional detail, not required to use the app.

## UX behaviour to keep
- **Area first:** browsing, dish search and the planner need a delivery area (`GET /areas`). Remember it on the device (a convenience only; the app works without it) and ask once.
- Treat 200 answers like `needs_area`, `confirm_area`, `needs_info`, `over_budget`, `no_valid_plan` as normal screens with a helpful message, not errors.
- Order numbers: show `#DW1234`, never a UUID. Deep link `dawat://orders/DW1234`.
- The chat's thinking panel lists `step` events live, then folds into "How Dawat AI got this · N steps".
- After any cart-changing step and after `done`, re-fetch `GET /cart` so the cart tab and badge match.
- Preferences saved on the Profile screen use `PUT /me/preferences/{key}`; never infer or auto-save one.

## Tests
Full rigour (tests proven to fail when the code is broken on purpose) for identity, consent and money logic: token handling, the "Yes"/"No" card buttons, the order gate, showing server totals unchanged, the dev-login lock. Proportionate tests elsewhere. Tools: Jest + React Native Testing Library; Maestro for device flows later.

## Out of scope
Real-money payments, scraping, any paid service, fake reviews, a web or PWA version, store publishing unless Saif pays and decides.

## Working agreement
Claude owns `mobile/`, the backend, databases, migrations, tests and deployment configs. `frontend/` and `frontend_old/` are read-only legacy references. If the app needs a new field or route, tell Saif and add it to `NEEDS_BACKEND.md`; don't work around the API by computing things on the device.
