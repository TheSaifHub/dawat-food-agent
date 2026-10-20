# Dawat API contract (for clients)

> **Clients:** the native mobile app (`mobile/`, see section 6) is the current client. Mentions of the website, CORS, `localStorage` and `NEXT_PUBLIC_*` describe the legacy web frontend and do not apply to the app.

Written from the backend code on 2026-10-11. If the code and this file disagree, the code wins: tell Saif.
Base URL: `NEXT_PUBLIC_API_URL` (local: `http://localhost:8000`). JSON everywhere except `/chat` (SSE).
Interactive docs for exact schemas: `GET /docs` (OpenAPI at `/openapi.json`).

## 1. Ground rules

- **The server computes every price and total.** No request ever carries a price, total, user id or order status. Bodies are strict: an unknown field is a **422**.
- **Show money exactly as returned** (whole rupees, integers). Never add up lines yourself; use `grand_total`, `delivery_fee`, `taxes`, `total`.
- **Auth** is `Authorization: Bearer <access_token>`. No cookies, no `credentials: "include"`. CORS allows only origins in the backend's `ALLOWED_ORIGINS`, methods GET/POST/PUT/PATCH/DELETE, headers `Authorization` and `Content-Type` only.
- **Status in the body, code in HTTP.** A tool-backed route returns the tool's JSON unchanged. Its `status` field says what happened and decides the HTTP code. Always read `status`, not just the HTTP code.
- `GET /health` → `{status:"ok", service, version}`. No database, no auth. Use it for the "Waking up Dawat AI…" loader (free-tier cold start can take a while).

## 2. Error codes

| Code | Meaning | Body |
|---|---|---|
| 401 | No/invalid/expired token, or the account no longer exists. Sign in again. | `{"detail": "..."}` + `WWW-Authenticate: Bearer` |
| 402 | `payment_failed` from `/payments/simulate`: the simulated test payment failed. No order; the cart is still confirmed; the same payment can be tried again. Body `{status, message}`. | `{status, message}` |
| 403 | `not_requested` | tool JSON |
| 404 | `not_found`, `unknown_item/branch/address`, `not_in_cart`. Another user's cart/order looks the same as a missing one. | tool JSON |
| 409 | The action is not possible in the current state. Body has `status`, a `message` and usually the fresh `cart` to show. Statuses: `item_unavailable`, `branch_unavailable`, `too_far`, `qty_limit`, `cannot_confirm`, `stale_quote`, `not_confirmed`, `no_clear_yes`, `quote_changed`, `plan_changed`, `cart_not_empty`, `confirm_preference`, `persona_locked`, and the payment ones: `payment_required` (POST /orders: pay first), `needs_refund` (paid, but the cart changed: no order), `payment_conflict`. A 409 may have changed data (`quote_changed` re-opens the cart): re-fetch `GET /cart`. | tool JSON |
| 422 | The request is wrong: bad shape, unknown field, bad value (`invalid_input`, `not_on_this_menu`, `needs_branch`, and `bad_signature` from /payments/verify). Also an area question on a write (`needs_area`, `confirm_area`, `unknown_area`, `outside_coverage`, `needs_info`). FastAPI validation errors are `{"detail":[{loc,msg,type}]}`. | mixed |
| 429 | Chat limits only: `{"status":"rate_limited"}` (30 messages/hour/user) or `{"status":"daily_limit"}` (global per-day cap). Both have a plain `message` to show. | `{status, message}` |
| 500 | A bug. Generic `{"detail":"Something went wrong on our side. Please try again."}`. | |
| 503 | Sign-in not configured / key check unavailable (`{"detail"}`), `planner_error` (try again), or `payments_not_configured` / `payment_unavailable` (nothing was charged or ordered). Treat as "temporarily unavailable". | |

**200 answers that are not a success** (show them, don't treat as errors): `needs_area`, `confirm_area` ("Did you mean…?" with a suggestion), `unknown_area`, `outside_coverage`, `needs_info` (planner needs people/budget/area), `needs_delivery_area` (cart has no delivery point), `over_budget`, `no_valid_plan`, `no_match`, `dish_query`, `confirm_dish`, `empty`, `already_placed`, `already_paid`, `already_started`, `not_saved`. Read `message`/`suggestions`/`choices` in the body.

## 3. Sign-in flow

Accounts live in Supabase Auth (the browser talks to Supabase directly for sign-in; the backend only verifies the token). The backend creates the profile on the first authenticated request.

1. **Google is the only sign-in (D-064).** `supabase.auth.signInWithOAuth({provider:"google", options:{redirectTo: <site>/login}})`. Email/password, anonymous sign-ins and "Try as Priya / Arjun" are gone: `POST /demo/start` no longer exists and an anonymous token (`is_anonymous: true`) is a 401.
2. Send `session.access_token` as the Bearer token. Refresh is supabase-js's job.
3. `GET /me` → `{user_id, display_name, is_demo, name_confirmed, account_name}`. `account_name` is the name Google gave us (from the verified token, null if none). While `name_confirmed` is false the website shows "Confirm your name" and sends every other page there; the backend itself never needs the flag (orders, cart, chat work regardless).
4. `POST /me/name` `{name?: string|null}` (token). Omitted/null = keep the Google account name (taken from the token, not the body); a string = the changed name, trimmed (1–60 characters, no control characters, no `<` `>` or HTML entities) else 422 `invalid_input` with a message. Sets `name_confirmed` and returns `{status:"ok", display_name, name_confirmed}`. Only the caller's own profile can change; extra fields are 422.
5. Sign-out is client-side (`supabase.auth.signOut()`); there is no backend route.

Public (no token): `/health`, `/areas`, `/areas/{id}/home`, `/areas/{id}/restaurants`, `/restaurants`, `/dishes`, `/branches/{id}`, `/branches/{id}/menu`, `POST /plans`. Everything else needs a token.

### Local dev login (no Supabase)

Daily development must not touch Supabase. The backend and frontend are started in **local mode**; the Supabase calls above are replaced by the backend's `/dev/auth` routes:

- Backend: `.venv\Scripts\python backend\dev_server.py start` (local `dawat_dev` database; `--supabase` is for deliberate checks only). Only this launcher sets `DAWAT_DEV_LOGIN=1`; never put it in `.env`.
- Frontend: start the dev server with `NEXT_PUBLIC_DAWAT_DEV_LOGIN=1` **and** `NODE_ENV=development` (the old frontend did this through `npm run dev:local`, which sets that variable for one `next dev` process).
- Routes (exist only in local mode; elsewhere they are 404):
  - `POST /dev/auth/google` (no body, or `{new_user: true}`) → `{access_token, expires_at, user_id}` — the replacement for "Continue with Google": a fake Google user with a local-only name and email (the same user each time; `new_user` makes a fresh one to see "Confirm your name" again).
  - `GET /dev/auth/users` → `{users:[{user_id, display_name}]}` (the seed users).
  - `POST /dev/auth/seed-user {user_id}` → `{access_token, expires_at, user_id}`.
- The token is an ordinary Bearer token, valid 12 h (`expires_at` is Unix seconds). Keep it in `localStorage` and send it the same way. When it expires, treat the user as signed out.
- **The dev login must never ship.** Gate every use behind the full inline condition `process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_DAWAT_DEV_LOGIN === "1"` so the bundler removes it from production builds, and fail the production build if a scan of the output finds it. A backend started for production refuses the flag, and a dev token is a 401 there.

## 4. Routes

Ids: `branch_id` is an opaque string such as `b-n10280159820`; `item_id` is an opaque string; `cart_id` / `order_id` / `checkout_id` / `address_id` are UUID strings; `area_id` is a slug such as `madhapur` or `banjara-hills`. Treat all as opaque and pass them back unchanged.

### Browsing (public)
| Route | Notes |
|---|---|
| `GET /areas` | `{status, areas:[{area_id, name, name_te}]}` for the area picker. |
| `GET /areas/{area_id}/home` | Cuisine shortcuts and chains near the area. |
| `GET /areas/{area_id}/restaurants` | Query: `cuisine, veg_only, mild, max_km (≤8), max_price_for_one, sort=distance\|price\|name, offset, limit`. One card per restaurant with distance, delivery fee, price for one. Only restaurants with an open branch within 8 km. |
| `GET /restaurants?q=&area=&limit=` | Name search. May answer `needs_choice` with `choices` (chain branches / shared names): ask the user which, then use the chosen `branch_id`. |
| `GET /dishes?q=&area=&is_veg=&max_spice=0-3&max_price=&category=&limit=` | Dish search (typos, Hinglish, Telugu). `area` is required for prices: without it `needs_area`. |
| `GET /branches/{branch_id}?area=` | Restaurant page header and map; with `area`, whether it delivers there and the fee. |
| `GET /branches/{branch_id}/menu?category=&is_veg=&max_spice=&max_price=` | Menu items from the database. |

### Meal planner
- `POST /plans` (public; a token gives plans priced from the user's address). Body is a **MealRequest**, strict, all fields optional:
  `{budget: int 1–20000 (whole bill incl. delivery+GST), people: int 1–10, veg_count: int, non_spicy_count: int, non_spicy_veg_count: int|null, spice_preference: "mild"|"medium"|"spicy"|null, meal_type: "breakfast"|"lunch"|"dinner"|"meal"|"snack", area: string|null}`.
  Numbers must be JSON numbers, not strings. Missing budget/people/area → 200 `needs_info` with what to ask. Success: `{status:"ok", plans:[{plan_id, label, grand_total, items_total, delivery_total, taxes_total, diet_note, budget_left, restaurants:[…]}]}` — up to 3 genuinely different plans (Best match / Best value / Variety). `over_budget` / `no_valid_plan` come with the real cheapest price or the largest group the budget covers. Show `diet_note` as given.
- `POST /cart/plan` (token) `{request: <the same MealRequest>, plan_id, replace: bool=false}`. Never send items. The plan is re-computed server-side by `plan_id`; if it no longer matches → 409 `plan_changed`. If the cart has items and `replace` is false → 409 `cart_not_empty`; send `replace:true` only after the user clicked "Replace cart" in your dialog.

### Cart and ordering (token)
The gate: `GET /cart` → user clicks Confirm on **that** summary → `POST /cart/confirm` with its `quote_id` → pay (`POST /payments/start`, the checkout sheet + `POST /payments/simulate`, `POST /payments/verify`). The order is created by the verified payment.
| Route | Body / notes |
|---|---|
| `GET /cart` | See §5. |
| `POST /cart/items` | `{item_id, branch_id, qty: int 1..MAX (default 1)}` → the whole cart. |
| `DELETE /cart/items/{item_id}?branch_id=&qty=` | No `qty` removes the line. `branch_id` only needed if the item is in the cart from two branches (else 409/422 `needs_branch`). |
| `PUT /cart/delivery` | `{area?: "Madhapur", address_id?: uuid}`. Area typos give the area answers above as 422. |
| `POST /cart/confirm` | `{cart_id, quote_id}`. `stale_quote` (409) if the cart changed since that summary: re-fetch and ask again. |
| `POST /orders` | `{cart_id}`. **Does not create an order any more (Phase 8): every order is paid for first.** After the checks (404 unknown cart, 409 `not_confirmed`, 409 `quote_changed` = cart re-opened, show the new total and ask again) it answers **409 `payment_required`** `{cart_id, quote_id, grand_total, message}`. Go on to §Payments. A cart that was already paid and ordered answers 200 `already_placed` with the orders. |
| `GET /orders?limit=` | History, newest first, at the prices paid. Also moves any due simulated progress forward (see §Tracking). |
| `GET /orders/{order}` | `{order}` is `DW1042`, `#DW1042`, `1042` or the order UUID. See §Tracking for the response. Other users' orders are 404. |

### Payments (TEST payments only; no real money)
An order exists only after a verified payment. The server runs a **local simulated gateway** by default (`gateway:"simulated"`, no Razorpay account). The same routes work with real Razorpay test mode later (`gateway:"razorpay"`); build the sheet for the simulated one and read `gateway` from the start response.

**Flow (simulated):** `GET /cart` → user confirms → `POST /cart/confirm` → `POST /payments/start` → the user fills **your** checkout sheet → `POST /payments/simulate` (the "pay" button) → on success `POST /payments/verify` with the three values it returned → orders exist. A failed payment returns 402 and nothing else changes.

| Route | Body / notes |
|---|---|
| `POST /payments/start` | `{cart_id}` (the confirmed cart). Never send an amount: the server uses the confirmed total. 200 `{status:"ok", gateway:"simulated"\|"razorpay", key_id, razorpay_order_id, amount (paise), amount_rupees, currency:"INR", cart_id, quote_id, attempt_id, reused, name, description}`. Show `amount_rupees` on the sheet. Calling it again for the same quote returns the same `razorpay_order_id` (`reused:true`). Errors: 404 unknown cart, 409 `not_confirmed` / `quote_changed`, 503 `payments_not_configured` / `payment_unavailable` (nothing was charged or ordered). |
| `POST /payments/simulate` | **Simulated gateway only.** Body (exactly these, nothing else; extra fields such as `cvv`, `expiry`, `amount` are refused with 422): `{razorpay_order_id, outcome:"success"\|"failure", method:"card"\|"upi", card_number?, upi_id?}`. Card: send `card_number` only. UPI: send `upi_id` only. **Success** 200 `{status:"ok", razorpay_order_id, razorpay_payment_id:"pay_TEST_xxxxxxxxxxxx", razorpay_signature (64 hex), message}`: pass these three straight to `/payments/verify`. **Failure** 402 `{status:"payment_failed", message}`: no order, the cart stays confirmed, the same `razorpay_order_id` can be paid again (do **not** call `/payments/start` again unless the cart changed). Other answers: 422 `invalid_input` (not a test value; the number is never echoed), 404 `not_found` (not this user's order), 409 `payment_conflict` (already paid or refunded), 503 `payments_not_configured` (the server is in Razorpay mode, so use Razorpay's own checkout). |
| `POST /payments/verify` | The three values from the payment step, with exactly these names: `{razorpay_order_id, razorpay_payment_id, razorpay_signature}`. Success: 200 `{status:"ok", payment_status:"paid", checkout_id, orders:[{order_id, order_number:"DW1042", restaurant, branch_label, status, payment_status:"paid", items_total, delivery_fee, taxes, total}], grand_total}`: one order per restaurant. Repeating it is harmless: 200 `already_paid` with the same orders. |

`/payments/verify` answers to handle: **422 `bad_signature`** (nothing ordered; the user can pay again) · **409 `needs_refund`** `{amount, message}` (the payment went through but the cart or a price changed before it finished, so **no order was placed**; show the message, the refund is simulated, send the user back to the cart) · 409 `payment_conflict` (a different payment is already recorded for this order) · 404 `not_found` (not this user's) · 422 `invalid_input` (odd-shaped values) · 503 as above.

**The only values the simulated gateway accepts** (anything else, including a real card number, is refused with 422 and never stored). Show these as a hint on the sheet:

| Method | Value | Result |
|---|---|---|
| Card | `4111 1111 1111 1111` (Visa test) | pays |
| Card | `5555 5555 5555 4444` (Mastercard test) | pays |
| Card | `4000 0000 0000 0002` | always fails (402), even if `outcome` is `"success"` |
| UPI | `success@razorpay` | pays |
| UPI | `failure@razorpay` | always fails (402), even if `outcome` is `"success"` |

Spaces and dashes in the card number are fine. **Do not send expiry or CVV** (show the fields if you want the sheet to feel real, but accept any value and leave them out of the request). Never store or log what the user types. Suggested sheet: method tabs (Card / UPI), the test-value hint above, a **Pay ₹{amount_rupees}** button that sends `outcome:"success"`, and a clearly labelled **Simulate failed payment** button that sends `outcome:"failure"` with the same instrument. Label the whole sheet "Test payment: no real money".

**Real Razorpay later** (only if `start.gateway === "razorpay"`): open `https://checkout.razorpay.com/v1/checkout.js` with `new Razorpay({key: start.key_id, amount: start.amount, currency: start.currency, order_id: start.razorpay_order_id, name: start.name, description: start.description, handler: (r) => POST /payments/verify with r.razorpay_order_id, r.razorpay_payment_id, r.razorpay_signature})`. If the user closes the window nothing is created. While a payment is open, a chat message does **not** re-open the confirmed cart (as long as the payment was started within the last 30 minutes).

Payment from chat: after the user's "yes", the `reply` event carries `payment` (§5). Show a **Pay ₹X** button that calls `POST /payments/start` with that `cart_id` and goes on from there. The chat never creates an order by itself.

### Tracking (simulated)
`GET /orders/{order}` returns `{status:"ok", order_id, order_number, checkout_id, order_status, payment_status, restaurant, branch_id, branch_label, delivery_area, is_sample, items, items_total, delivery_fee, taxes, total, placed_at, timeline:[{status, at}], simulated_tracking, route:{from:{lat,lon}, to:{lat,lon}}, rider, next_update_in_s}`.
- Statuses in order: `placed → confirmed → preparing → picked_up → on_the_way → delivered` (and `cancelled`). Suggested words: Placed, Confirmed, Preparing, Picked up, On the way, Delivered.
- It is a **simulation**: a paid order moves along by itself, about **6 minutes** in total (confirmed at 1:00, preparing 2:15, picked up 3:45, on the way 4:30, delivered 6:00 after the order was placed). Say "simulated" in the UI. There is **no ETA**; never show one. Unpaid orders and the demo accounts' sample orders do not move (`simulated_tracking:false`).
- `route.from` is the restaurant, `route.to` the delivery point (always present): draw them on the Leaflet map.
- `rider` is `null` until picked up, then `{lat, lon, stage}` with `stage` = `picked_up` (at the restaurant), `on_the_way` (moving in a straight line toward the delivery point; the position changes on every read) or `delivered` (at the delivery point). Move the marker to it. `null` for unpaid and sample orders.
- `next_update_in_s`: whole seconds until the next status change, `null` when delivered or not simulated. Poll `GET /orders/{order}` about every 5 s while `rider.stage` is `on_the_way`, otherwise after `next_update_in_s` (at least 5 s). Stop when `order_status` is `delivered`.
- Each read writes any due status events, so the timeline is the same however often or late it is read.

### Me (token)
- `GET /me`, `GET /me/addresses` (`{status:"ok"|"empty", addresses:[{address_id, label, line1, area_id, area, is_default}]}`).
- `GET /me/preferences`; `PUT /me/preferences/{key}` `{value: string|int}`; `DELETE /me/preferences/{key}` (key `diet`, `max_spice`, `default_area`, `language`, or `all` for delete). Saved with source "settings" (explicit by nature).
- `POST /me/name`: §3.

### Cart shape (`GET /cart`, and inside most cart responses)
`{status: "ok"|"empty"|"needs_delivery_area", cart_id, cart_status:"open"|"confirmed", delivery:{area_id, area, address_id, address_label, lat, lon}|null, branches:[{branch_id, restaurant, branch_label, branch_area, distance_km, items:[{item_id, name, price, qty, line_total, is_veg, spice_level, serves}], items_total, delivery_fee, free_delivery, gst_food, gst_delivery, taxes, total}], items_total, delivery_total, taxes_total, grand_total, can_confirm, quote_id, unavailable:[{…item, branch_id, restaurant, reason:"branch_closed"|"unavailable"|"too_far"}], issues?, confirmed_total?}`.
- `needs_delivery_area`: `grand_total` is null; ask for an area or address, then `PUT /cart/delivery`. Don't show a total.
- `can_confirm` false (e.g. unavailable items) → disable Confirm. `quote_id` exists only when it can be confirmed.
- Any change to a confirmed cart re-opens it (`confirmation_cleared`).
- Fees: ₹25 up to 2 km + ₹10 per extra km started; free when a restaurant's items ≥ ₹499; delivery range 8 km; GST 5% food, 18% delivery. All computed server-side, shown here for copy only.

## 5. Chat: `POST /chat` (token, Server-Sent Events)

Body: `{message: string (1–2000), conversation_id?: uuid}`. Omit `conversation_id` to start one; reuse the one from the `start` event to continue. Errors before streaming are normal JSON: 401, 404 `not_found` (conversation isn't this user's), 422, 429 (`rate_limited`, `daily_limit`).

Use `fetch` + a stream reader (not `EventSource`: it can't send the Authorization header or a POST body). Response is `text/event-stream`; each event is `event: <name>\ndata: <json>\n\n`.

| Event | Data |
|---|---|
| `start` | `{conversation_id}` |
| `step` | One per tool call, live: `{step, tool, arguments, status, ok, latency_ms, counts}`. For the "Dawat AI is thinking" panel. No secrets inside. |
| `reply` | `{text, status:"ok"\|"busy"\|"step_cap", message_id, card, card_text, plans, payment}`. `payment` is `{cart_id, quote_id, grand_total}` when the user just said yes to an order (so it now needs paying), else `null`. It is built by code from the tool result, so it is present even when `status` is `busy`. Show a Pay button; **the order does not exist until the payment is verified**. |
| `error` | `{message}` (something crashed server-side; show it) |
| `done` | `{}` always last |

After any `step` whose `tool` changes the cart (`add_to_cart`, `remove_from_cart`, `set_delivery`, `add_plan_to_cart`, `confirm_cart`, `place_order`) and again after `done`, re-fetch `GET /cart` so the page cart matches.

**Reply text** may contain order numbers like `DW1042` (or `#DW1042`): link them to `/orders/DW1042`. Never show a full UUID to the user. Replies can be in English, Hinglish (Latin script) or Telugu script: render any Unicode.

### Confirmation card (`reply.card`, or null)
Code builds the card, not the model. The user's next "yes" can act **only** on the card shown under the previous reply. Show it with buttons; a button sends an ordinary chat message ("yes" / "no") in the same conversation (it is not a separate API call). Every card has `kind` and `card_id`. `card_text` is the same card as one line of plain text (use as the accessible label or fallback).
- `order`: `{cart_id, quote_id, grand_total, deliver_to, lines:[{name, qty, line_total, is_veg, restaurant}]}`.
- `plan`: `{plan_id, request, label, grand_total, lines, deliver_to, replace, nonveg:[names], saved_diet}`. `replace` true means it will replace the whole cart: say so.
- `diet`: `{items:[{item_id, branch_id, qty, name}], saved_diet}`. Non-veg for a saved vegetarian: "is it for someone else?".
- `preference`: `{offer:{action, …}, label}`.
- `remove`: `{items:[{item_id, branch_id, qty|null (null = all), name}]}`.
- `delivery`: `{area_id, area}`.
The user may also type their own answer; a vague one gets asked again, never acted on.

### Plan cards (`reply.plans`, or null)
Up to 3 options from this turn's `plan_meal`: `{plan_id, label, grand_total, items_total, delivery_total, taxes_total, diet_note, budget_left, restaurants:[{restaurant, branch_id, branch_label, distance_km, delivery_fee, free_delivery, taxes, total, items:[{name, qty, line_total, is_veg, spice_level, role}]}]}`. Render as selectable cards; picking one **sends a chat message naming its label** (e.g. "Go with Best value"). The model then adds that plan; a plan card then appears for the user's yes. (The website's non-chat route is `POST /cart/plan`.)

Rules the UI must respect: one chat turn at a time per user (disable the input while streaming); keep the conversation in memory/sessionStorage keyed by user id; if `status` is `busy` or `step_cap`, show the `text` as is (it says what was or wasn't done).

## 6. Mobile client (iOS and Android app, added 2026-10-15)

The backend and every route above are unchanged. The mobile app (`mobile/`) is just another client.

- **Base URL:** `EXPO_PUBLIC_API_URL`. It is embedded in the app bundle, so it must be a public value. Local development: an Android emulator reaches the host machine at `http://10.0.2.2:8000`; an iOS simulator uses `http://localhost:8000`. A real phone needs a network address, which needs Saif's approval (see `docs/MOBILE_PLAN.md`, networking). Production: the Render HTTPS URL.
- **No CORS.** Native apps do not send an Origin header, so `ALLOWED_ORIGINS` plays no part and nothing changes in the backend. (Do not add `*`.)
- **Token storage:** keep the access token (and, in production, the Supabase refresh token) in `expo-secure-store`. Never in AsyncStorage, logs or URLs. Send `Authorization: Bearer <access_token>`. On 401, clear it and show the sign-in screen.
- **Streaming `/chat`:** use `fetch` from `expo/fetch` (its response body is a stream you read with `getReader()`), a `TextDecoder`, and the same SSE parsing as `frontend_old/src/lib/chat.ts`. `EventSource` cannot POST or send headers. The Expo docs show this pattern; M4 starts with a real emulator streaming check before anything is built on it.
- **Deep links:** URL scheme `dawat://` (set in `app.json`). Used for `dawat://orders/<order_no>` (for example from a chat reply). Never put a token, cart id or quote id in a link.
- **Cleartext HTTP:** Android blocks plain `http://` in release builds; the debug build used for local development allows it. Production uses HTTPS only.
- **Sign-in:** the app signs in with Google on the device and passes the Google ID token to Supabase (`signInWithIdToken`); the backend still only verifies the Supabase token. Local mode uses `POST /dev/auth/google` (section 3), gated as in `docs/MOBILE_RULES.md` rule 6. Native setup steps are in `docs/GOOGLE_AUTH_SETUP.md` (Part B).
- **Money, ids, `source`:** same rules as section 1. The app never sends a price, a user id or a `source`.
