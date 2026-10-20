# Frontend Requirements Pending Backend Support

This file documents features, routes, or fields present in the frontend UI design that are not currently provided by the backend API (`docs/API_CONTRACT.md`). Per frontend rules, these features must not be faked or computed client-side.

---

### 1. Payment Integration (Phase 8 Razorpay Checkout)
- **Status:** Placeholders on cart & chat.
- **Need:** Real/simulated Razorpay flow (`POST /payments/start`, browser checkout script, `POST /payments/verify`).
- **Notes:** Cart ordering flow gate now halts at `POST /cart/confirm` and requires payment. Kept as a clear placeholder until checkout contract is signaled ready.

### 2. Live Order Tracking Map & Rider Coordinates (Phase 8)
- **Status:** Placeholder vector map in `order-tracking` and restaurant views.
- **Need:** Real-time rider coordinates / websocket / polling feed for moving courier position (`simulated_tracking.rider`).
- **Notes:** Order timeline statuses are displayed from `GET /orders/{order}` without fake ETAs.

### 3. Delivery Notes / Special Instructions
- **Status:** Removed from checkout form.
- **Need:** Field on `PUT /cart/delivery` or `POST /cart/confirm` to persist rider/kitchen delivery instructions (e.g. `instructions: string`).
- **Notes:** The API contract currently accepts only `{ area?: string, address_id?: uuid }` on `PUT /cart/delivery`.

### 4. Payment Method Choice (UPI vs Cards vs Netbanking vs COD)
- **Status:** Removed from cart checkout.
- **Need:** Payment method selection is handled upstream by Razorpay standard checkout once wired. Cash on Delivery (COD) is not in the contract.

### 5. Instant Re-Order Endpoint
- **Status:** Removed from profile past orders.
- **Need:** An endpoint such as `POST /cart/reorder { order_id }` or a tool action to clone all items from a past order into the cart.

### 6. Arbitrary Persona Switcher Without Sign-Out
- **Status:** Header persona quick-switcher removed; switching personas requires signing out or selecting a persona on the `/login` page via `tryAs()`.
- **Need:** The backend locks demo personas (`POST /demo/start` returns 409 `persona_locked` if another persona was started on the same session). Full persona switching requires clearing the session.

### 7. User Address Management (Creation & Selection)
- **Status:** Address picker in cart limited to existing saved addresses from `GET /me/addresses` with fallback to area selection via `PUT /cart/delivery`.
- **Need:** `POST /me/addresses` and `PUT /me/addresses/{id}` routes for creating/editing addresses from the UI.


---

# Mobile app (added 2026-10-15): design elements the backend does not support

The sections above were written for the legacy web frontend. For the mobile app (`docs/design/mobile_flow_v2.png`), these design elements are **left out or disabled**, not faked:

| Design element | Screen | Why not | What it would need |
|---|---|---|---|
| "Wallet (simulated)" payment option | Payment | Only fixed test card and UPI test values are accepted by `/payments/simulate`. | A wallet method in the simulated gateway, with its own test rules. |
| "Payment methods" row | Profile | There are no saved payment methods and none should be stored. | Nothing recommended; the row is hidden. |
| Notification bell | Home | No notifications feature or endpoint. | A notification model and a push service. |
| Favourite hearts | Restaurant header | No favourites table or route. | `POST/DELETE /me/favourites` plus a list route. |
| "Cancelled" order status | Orders | The simulated progression has no cancelled state and there is no cancel route. | A cancel route, a status event and a refund record. |
| "Online" under Dawat AI | Chat header | No presence concept; claiming it would be invented. | Nothing; the label is dropped. |
| Delivery time or ETA, star ratings | Menu, tracking | Never provided and not to be invented (CLAUDE.md). | Nothing. |
| Real food photos | Cards, menu | No copyrighted images; placeholders or illustrations until Saif decides on free licensed photos with credit. | A licensing decision and an image field per dish. |
| User photo avatar | Home, Profile | There is no profile-photo field or upload. | An avatar URL on the user (and storage). The app shows an initial avatar instead. |
| Add, edit or delete an address | Profile | The backend has `GET /me/addresses` only; there is no write route. Addresses are shown read-only (M6). | `POST/PUT/DELETE /me/addresses` with the same "area must be one we deliver to" checks as the cart. |
| "Load more" in Orders | Orders | `GET /orders` returns at most 20 checkouts (newest first) and a `has_more` flag, but takes no cursor or offset. The app shows "Showing your latest 20 orders." (M6). | A `before=<placed_at>` cursor on `GET /orders`. |
