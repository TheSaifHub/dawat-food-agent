# Dawat mobile app: plan (2026-10-15)

Status: **APPROVED by Saif on 2026-10-15 (answers recorded in section 7). M0 is built (D-069); M1 onward need Saif's go.** Written from the design (`docs/design/mobile_flow_v2.png`), the current backend contract, and the Expo docs read through Context7. Things I could not verify from the docs are marked **(to verify)** and get a small spike before anything depends on them.

## 1. Palette (design v2, `docs/design/mobile_flow_v2.png`; replaces the earlier cream/saffron/teal/vermilion palette)

The v2 legend gives five colours exactly. The rest I sampled from the PNG with a script (median of 8x8 patches, several places each). M0 freezes these as theme tokens.

| Token | Value | Source | Used for |
|---|---|---|---|
| `accent` (coral) | `#FF5844` | legend | icons, badges (with dark text), active states, large text, on-white/navy/green only (see rules) |
| `sky` | `#A6D3F2` | legend | Ask Dawat AI tile, hero tile, Delivery chip, selected states |
| `butter` | `#F7D78C` | legend | Biryani tile, menu header, "Best match" card, selected states |
| `sage` | `#AFC3A8` | legend | Tiffin tile, success badges (Delivered), dividers |
| `surface` | `#DBDBE5` | legend | cards, surfaces, inactive chips, disabled fills |
| `page` | `#E8F6FD` | sampled (3 patches: `#E9F7FE`, `#E7F5FE`, `#E8F6FD`) | the page behind the screens |
| `card` | `#FFFFFF` | sampled (about `#F7FBFD`; rounded to white for the contrast maths) | white cards and sheets |
| `navy` | `#21364B` | sampled (6 patches, `#1E374B` to `#21364C`) | primary buttons, Total tile, active segment, the "Choose" buttons |
| `ink` | `#050D1A` | sampled (darkest heading strokes `#00000F` to `#030B1B`; the exact ink is hidden by anti-aliasing) | body text and headings |
| `muted` | `#325574` | sampled (the "Food, your way" subtitle strokes) | secondary text |
| `coralTint` | `#FBE8EA` | sampled (GST tile `#FBE8EA` / `#FEE7E8`) | the GST tile, "Variety" card |

The tiles in the PNG are rendered a little lighter than the legend (for example the sky tile samples as `#BCE4FD`). **The legend values are used exactly**; sampled tints are only for the tokens the legend does not list.

**Contrast (WCAG 2.x, computed 2026-10-15; the M0 Jest test recomputes every row and fails if one drops):**

| Text / icon on fill | Ratio | Verdict |
|---|---|---|
| white on `navy` | 12.40 | pass (all primary CTAs, Total tile, segments) |
| white on `accent` | **3.12** | **fail for text (needs 4.5). Never used.** |
| `ink` on `accent` | 6.24 | pass (coral badges use dark text) |
| `navy` on `accent` | 3.97 | large text/UI only |
| `ink` on page / card / surface | 17.64 / 19.46 / 14.16 | pass |
| `ink` on sky / butter / sage / coralTint | 12.25 / 13.95 / 10.38 / 16.53 | pass |
| `navy` on page / card / surface | 11.24 / 12.40 / 9.02 | pass |
| `navy` on sky / butter / sage | 7.81 / 8.89 / 6.61 | pass |
| `muted` on page / card / surface / coralTint | 7.08 / 7.81 / 5.68 / 6.64 | pass |
| `muted` on butter / sky | 5.60 / 4.92 | pass |
| `muted` on sage | **4.17** | **fail for small text: use `ink` on sage** |
| `accent` on card | 3.12 | passes 3:1 (icons, large text, UI) |
| `accent` on navy | 3.97 | passes 3:1 |
| `accent` on page | **2.83** | **fails even 3:1** |
| `accent` on surface | **2.27** | **fails 3:1** |

**Rules that follow from the numbers:**
1. Primary CTAs (Continue with Google, Yes place this order, Place order, Pay, View cart, Choose, active segment) are **navy with white text**, as in the image. Nothing is white-on-coral.
2. Coral is for icons, badges with dark (`ink`) text, active states and large text. **Never small text on a light surface.** Because coral is under 3:1 on `page` and `surface`, a lone coral icon or dot on those backgrounds also needs a companion cue (the veg/non-veg dot has a text label; a selected state also changes shape or weight). Coral sits on white cards (3.12), navy or green when it must stand alone.
3. Dark text on sky, butter and sage tiles: `ink`, or `navy` for emphasis. Secondary `muted` text is allowed on page, card, surface, butter, sky and coralTint, **not on sage**.
4. **The small white pills** ("Best match", "Best value", "Variety"; in the image white text on light orange, blue and red fills, all failing) become **navy pills with white text** (12.40:1). The three are told apart by a small colored dot (coral, sky, butter) inside the pill and by their words.
5. The cart badge is a coral circle with `ink` text (6.24:1).

**Tracking card (decided by Saif, 2026-10-15):** the order-tracking "On the way" card is navy `#21364B` with white text (12.40:1), not green. On it, `sage` text is 6.61:1, `sky` 7.81:1, `butter` 8.89:1, and coral icons 3.97:1: all pass. The palette is the legend plus navy, page, ink, muted and the coral tint.

## 2. Technology choices (compared briefly)

| Topic | Choice | Rejected / alternatives | Why |
|---|---|---|---|
| Workflow | **Expo managed (continuous native generation).** Start in the Android emulator and Expo Go; move to a **development build** at M8, or earlier if a native module needs it (Google sign-in, speech). | Bare React Native; Expo Go only | Expo Go cannot do native Google sign-in or custom native modules. A dev build is "your own Expo Go" (Expo docs). Nothing in M0–M7 needs a native module, so Expo Go is enough until then. |
| Navigation | **Expo Router** (file-based, on React Navigation), JS `Tabs` with a custom tab bar component | `NativeTabs` (marked unstable in the docs) | The design's raised-circle active tab is a custom bar; NativeTabs gives the platform's native look. |
| State | React Context + small hooks, ported from `frontend_old` (`session`, `cart`, `chat-context`) | Redux, Zustand, TanStack Query | The app is small, the server is the source of truth, and the ported logic is already tested in spirit. Fewer dependencies. |
| Icons | `@expo/vector-icons` (ships with Expo) | lucide-react-native + react-native-svg | No extra dependency. |
| Fonts | `expo-font` with `@expo-google-fonts/*` packages; Noto Sans Telugu for Telugu. The design's font is a rounded geometric sans; I will identify the closest free Google font in M0 by rendering candidates next to the PNG, and ask you to pick. | System font | Matches the design; Telugu must render correctly. **(to verify)** the Noto Sans Telugu package name and weights in M0. |
| Images | `expo-image`; round cutouts from placeholders drawn as SVG/illustration (`react-native-svg`). No copyrighted photos. | Stock photos | Rule from you. Free licensed photos (Unsplash/Pexels, with credit) only if you decide. |
| Soft, flat cards | v2 is flatter than v1: big radii, tinted tiles, a very soft single shadow. iOS `shadow*` props, Android `elevation` (one shadow is enough for this look). | Two-layer neumorphic shadows | **(to verify)** whether the chosen SDK's React Native supports `boxShadow` on both platforms. |
| Chat streaming (SSE) | **`fetch` from `expo/fetch`**: the Expo docs show `resp.body.getReader()` streaming, with `Accept: text/event-stream`; also the global `fetch` on Android and iOS unless `EXPO_PUBLIC_USE_RN_FETCH=1`. We read chunks, decode with `TextDecoder`, and reuse the SSE parser from `frontend_old/src/lib/chat.ts`. | `react-native-sse` (an `EventSource` clone: cannot send a POST body or headers by design, so it does not fit `/chat`); polling | The docs describe it, but **I have not run it**. M4 begins with a 1-hour spike against the real `/chat` on the emulator (events arrive one by one, not all at the end). If it fails, the fallback is a non-streaming `/chat` call (needs a small backend change: you decide). |
| Maps | **A Leaflet map in a `react-native-webview`** with OpenStreetMap tiles and the built-in attribution, plus the "© OpenStreetMap contributors" text under the map. | `react-native-maps` (uses Google Maps on Android, needs a Google key and billing: rejected); `@maplibre/maplibre-react-native` (native, no key, but needs a development build) | Free, works in Expo Go, tiles and attribution as the design needs, and I already have Leaflet working in `frontend_old`. **(to verify)** the OSM tile usage policy is fine for demo traffic (it forbids heavy use and requires a valid identification); if not, MapLibre with a free tile source is the upgrade at M8. |
| Testing | Jest (`jest-expo`) + React Native Testing Library; full rigour (break-it-on-purpose) on identity, consent and money logic; later Maestro for device flows | Detox | Maestro is the simplest cross-platform device runner. **(to verify)** it runs against the Windows Android emulator in M7. |
| Tokens | `expo-secure-store` for the token; AsyncStorage only for harmless conveniences (the last area) | | Secure storage is the platform keystore. |

## 3. Dev networking for a real phone (your call: nothing here is done)

The backend now listens on `127.0.0.1` only. Options, safest first:

1. **Android emulator (recommended for M0–M7).** The emulator reaches the PC's loopback at `http://10.0.2.2:8000`. **The backend stays bound to localhost.** Needs Android Studio, which only you can install (I will guide you).
2. **A real Android phone over USB with `adb reverse tcp:8000 tcp:8000`.** The phone's `localhost:8000` is forwarded to the PC's loopback over the cable. **Still no network exposure.** Needs USB debugging turned on, and Android's platform-tools.
3. **A phone over Wi-Fi (LAN).** Needs the backend to listen on a LAN address (`0.0.0.0` or the PC's IP), plus Metro for Expo Go. **The risk:** local mode also serves the dev login (`POST /dev/auth/google`), which hands a valid token to *anyone who can reach the port*. On a shared or public Wi-Fi, a stranger could sign in as the local test user, place fake orders into the dev database, and spend your Gemini/Groq free quota through `/chat`; the Windows firewall may also be opened up by the prompt. Home Wi-Fi is a smaller risk, but still more than zero. **I will not do this without your explicit approval**, and if you approve, I would bind to the specific LAN IP, keep the firewall rule to the private profile, and turn it off afterwards.
4. **A tunnel (ngrok etc.): rejected.** It puts the backend on the public internet.

**iOS caveat:** the iOS Simulator needs a Mac. On Windows, iOS can be tried only in Expo Go on a physical iPhone (LAN, so option 3's risk) or through an EAS cloud build that needs a paid Apple account for a real device. I cannot test iOS myself, and nothing in the app will be iOS-specific beyond what Expo handles.

## 4. Distribution (costs are what I know; please confirm current prices; you decide)

| Route | Cost | Notes |
|---|---|---|
| Expo Go (a QR code, dev only) | free | Both platforms. Your phone must reach Metro (LAN, section 3). Not for sharing with recruiters long-term. |
| Android APK, sideloaded | free | Built by `eas build` (free tier has monthly build limits and queues **(to verify)**) or locally with Android Studio. Share the APK link. iPhone users cannot use it. |
| Google Play | one-time fee, about US$25 | Needs a Google Play developer account and a store listing. Not needed for a portfolio. |
| TestFlight / App Store | about US$99 per year | Needs an Apple Developer account. The only way to put a real iOS build on iPhones other than yours. |

My recommendation for the portfolio: **Android APK plus a screen-recorded demo video**, no store fees; the iOS app is the same code and is described honestly as "builds for iOS, not store-published".

## 5. Port from `frontend_old/src/lib` (adapt, not copy)

`api.ts` (result object, never throws, "slow" callback, timeout) → same, with `expo/fetch` and the base URL from `EXPO_PUBLIC_API_URL`. `session.tsx` and `auth.ts` → token in `expo-secure-store`, Google ID token via the native library (after 30 Oct), the dev login in local mode. `devauth.ts` → gated by one inline build-time condition plus a release-build scan (M1). `cart.tsx` → the single cart provider, badge. `chat.ts` / `chat-context.tsx` → the `expo/fetch` SSE reader and the conversation (kept in memory per user; secure-store not needed). `orders.ts`, `catalog.ts`, `area.ts` → port; `supabase.ts` and Leaflet-in-browser code are not ported.

## 6. Modules (each reviewable on its own; I stop for your OK after each)

| Module | What | Tests (rigour) | Needs from you |
|---|---|---|---|
| **M0** Scaffold + theme | `mobile/` via the current Expo template, exact pins, TypeScript strict, Expo Router, theme tokens from the PNG, font choice, DawatLogo wordmark, the shared Screen shell (banner, safe areas, "Local data" badge), the soft Card/Tile/Button primitives, `.env.example` | Contrast test over every token pair in the section 1 table (fails when a pair drops below its threshold); lint, typecheck | Install Android Studio + an emulator (or tell me you have an Android phone); pick the font from candidates; approve the palette values |
| **M1** Sign-in + name | Welcome screen, "Continue with Google" (local mode: dev login), secure-store token, `/me`, Confirm-your-name screen, auth gate, sign out | **Full rigour:** token storage, 401 handling, dev-login lock (release build scan), no user id/source in bodies | Nothing (real Google after 30 Oct) |
| **M2** Home + browse | Area picker, Home bento tiles (Ask Dawat AI, Biryani, Tiffin, Veg only, Under ₹200, ₹500 plan, chains near you; an initial avatar, no photo), restaurant list | Proportionate | Ruling on the free food images (placeholders vs licensed photos) |
| **M3** Restaurant + cart | Menu by category, veg dot, spice words, Add/qty, cart tab with badge, server totals, delivery point | **Full rigour:** totals are shown unchanged from the API; the app never sends a price | |
| **M4** Chat | SSE spike first; chat tab, thinking panel, plan cards, confirmation card with Yes/No buttons that send exactly "Yes"/"No" | **Full rigour:** card buttons send only "Yes"/"No" and never call confirm/place; the cart refresh after steps | |
| **M5** Payment + tracking | Test payment sheet (fixed test card/UPI values only; Wallet absent), verify, order placed screen, tracking screen with the simulated timeline and rider on the map | **Full rigour:** no "placed" before verify; 402 keeps the cart; `needs_refund` handling; no CVV/expiry sent | |
| **M6** Orders + Profile | Active/Past orders, order detail (`#DW1234`), Profile (name, addresses read-only, language/diet preferences, About with OSM credit, Sign out) | Proportionate (order-number display tested) | |
| **M7** Polish + accessibility | 44pt targets, labels, dynamic text, back button, error/empty/slow states, Telugu rendering, Maestro smoke flows | Accessibility checks in Jest + a manual device pass | A manual pass on the emulator or phone, and your screenshots |
| **M8** Builds | Development build, release APK, the `EXPO_PUBLIC_` audit, README install steps, Google native sign-in after 30 Oct | Release scan | The Part B steps in `docs/GOOGLE_AUTH_SETUP.md`; your decision on EAS vs local build and on store fees |

Not touched: the backend, the database, the tools, the planner, the agent and their tests, `frontend/`, `frontend_old/`. Two small backend items may come up, and I would ask first: a deep-link-friendly order lookup already exists (order numbers), and a non-streaming chat fallback if the SSE spike fails.

## 7. Saif's answers (2026-10-15)

1. **Test device:** a physical Android phone over USB, USB debugging on, Expo Go installed, adb expected at `C:\platform-tools`. **No Wi-Fi/LAN exposure and no `0.0.0.0` binding.** Steps: `docs/MOBILE_DEVICE_SETUP.md`. (On 2026-10-15 adb was **not found** at `C:\platform-tools`; the setup doc says how to put it there.)
2. **Logo:** the lowercase "dawat" wordmark with "Food, your way". The old arch may return later as the app icon.
3. **Food images:** placeholders and illustrations for now.
4. **Map:** Leaflet in a WebView is OK **if** OpenStreetMap's tile policy allows it; otherwise a static placeholder map. Policy checked on 2026-10-15 (`operations.osmfoundation.org/policies/tiles/`): interactive use of `tile.openstreetmap.org` by a small app is allowed if the app shows attribution on the map, sends a distinct stable User-Agent (generic library defaults are blocked), a web page sends a valid Referer, honours cache headers (or keeps tiles at least 7 days), and does no bulk download, prefetch or offline saving. Access is best-effort and may be blocked without notice. **Verdict:** allowed for demo use, with one real risk: a WebView rendering inline HTML has no valid Referer and a browser-like User-Agent, so tiles might be refused. M5 starts with a tiny spike on the phone (load a tile through the WebView with a proper `baseUrl`); if tiles are refused or the policy is unsafe to rely on, the tracking screen uses a static placeholder map (the route line and rider marker drawn by the app over a plain background) with the OSM credit kept.
5. **Distribution:** Android APK plus a demo video only. No paid store accounts.
6. **`.claude/`:** apply the section 8 proposals, but show the exact diff first and wait for OK.

## 8. Proposed `.claude/` changes (NOT SAVED; for your review)

Nothing under `.claude/` has been changed. Proposed:

**`settings.json` allow rules (narrow, read-only or local-only):**
- `Bash(npm test*)`, `Bash(npm run test*)`, `Bash(npm run lint*)`, `Bash(npm run typecheck*)`, `Bash(npx tsc --noEmit*)`, `Bash(npx jest*)`, `Bash(npx expo-doctor*)`, and the same `PowerShell(...)` forms, so tests and checks in `mobile/` run without a prompt.
- **Ask (not allow):** `npm install*`, `npx expo install*` (each package is reviewed and pinned exactly, like the pip rule), `npx expo start*` / `npx expo run:*` (long-running, opens ports), and every `eas *` command (cloud account, may cost).
- **Deny (unchanged):** the `**/.env` deny rules already cover `mobile/.env` and `mobile/.env.local`; I would add `Edit/Read(**/.env.preview)` and `.env.production` is already there.

**`guard.py` hook:**
- `.env` protection: the existing name check already matches `mobile/.env` by file name (tests cover it). Proposed: one more test that proves it for a `mobile/` path.
- New secret rule: block writing any variable whose **name** starts with `EXPO_PUBLIC_` (or `NEXT_PUBLIC_`) and contains `SECRET`, `SERVICE_ROLE`, `PRIVATE`, `PASSWORD`, `DATABASE`, `GEMINI`, `GROQ`, `LLM` or `PAYMENT_SIM`, with any value. These names are embedded in the app bundle, so they are always a mistake. (The existing pattern already catches long literal values on names containing SECRET/TOKEN/API_KEY; this closes the short-value and name cases.) Planted-bug tests as before.

**Agents:** `ui-checker` is web-only (Playwright, CSS); I would leave it untouched and mark it legacy in its description, and later propose a `mobile-checker` (reads the theme tokens, runs the contrast test, checks touch-target sizes and labels in the source).

## 8. Native Google sign-in: plan for Phase 10 (added 2026-10-15, M1)

**What the current Expo docs say** (read through Context7, `docs.expo.dev/guides/google-authentication`): Google sign-in is done with a native library, either `@react-native-google-signin/google-signin` (widely used) or `react-native-nitro-google-signin` (newer). Both need custom native code, so they need **a config plugin in the app config and a development build**. **They do not work in Expo Go.** The docs' general note on authentication says the same for any provider that needs custom native code.

**What that means for Dawat**
- **Now (Expo Go on the Oppo):** the local dev login only (`npm run dev:local`). The "Continue with Google" button in a normal start says plainly that Google sign-in is not set up yet. Nothing pretends to be Google.
- **Phase 10 (after 30 Oct, with Saif's accounts):**
  1. Install `@react-native-google-signin/google-signin` and add its config plugin (Saif approves each install; the usual 14-day version check applies).
  2. Build a **development build** (free paths: local `npx expo run:android` with Android Studio, or `eas build --profile development` within the free EAS limits **(to verify)**). Expo Go can no longer open the app once this library is in it, so dev work after this point uses the development build; `npm run dev:local` still works with it.
  3. Google Cloud (Saif): an OAuth **Web** client (its ID is the public `EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID`) and an **Android** client for package `com.dawat.app` with the SHA-1 of the signing key (the debug key for development builds, the EAS or release key for the APK). Exact steps go into `docs/GOOGLE_AUTH_SETUP.md` Part B **(to verify against the current Google console)**.
  4. The app gets a Google **ID token** on the device and passes it to Supabase `signInWithIdToken`; Supabase returns the session token that the backend already verifies. The backend does not change. Supabase's Google provider must list the web client ID **(to verify)**.
  5. The token still goes only into `expo-secure-store`. The dev login stays impossible in release builds (the `npm run check:release` scan).
- **Not chosen:** the browser-based `expo-auth-session` flow. It works in Expo Go, but needs redirect-URI setup per environment and is the weaker experience; it is kept as a fallback only if the native route fails.
- **iOS:** the same library supports it (an iOS client ID and URL scheme), but it cannot be built or tested from this Windows PC; it stays "builds for iOS, not tested" (section 4).
