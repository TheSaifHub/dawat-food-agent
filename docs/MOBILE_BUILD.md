# Building the Dawat Android APK (M8)

Prepared 2026-10-17. **Nothing here has been run yet.** You run the steps marked **(you)**. Cost: zero (EAS Free plan, a limited number of low-priority builds a month; no card). If any page asks for a card or a paid plan, stop and tell Claude.

## What is already set up (no install or build was done)
| Thing | Where | Value |
|---|---|---|
| Package / bundle id | `mobile/app.json` | `com.dawat.app` (permanent once published anywhere) |
| Name, slug, scheme | `mobile/app.json` | Dawat, `dawat`, `dawat://` |
| Version | `mobile/app.json` | `version` 0.1.0 (you change it by hand for a release), `android.versionCode` 1 |
| Version handling | `mobile/eas.json` | `appVersionSource: local`; the `apk` profile adds 1 to `versionCode` on every build (written into `app.json`) |
| Icon, adaptive icon, themed icon, splash | `mobile/assets/*.png`, drawn by `mobile/scripts/make-assets.py` | lowercase "dawat" wordmark (Outfit Bold, the in-app font, OFL licence) on navy `#21364B`; splash shows the tagline; no other artwork |
| Splash plugin | `mobile/app.json` | `expo-splash-screen` (already installed), navy, width 240 |
| Release profile | `mobile/eas.json` `apk` | installable APK, no dev login, no development client |
| Development profile | `mobile/eas.json` `development` | separate: development client, the **only** profile with the dev-login switch |
| Guard test | `mobile/__tests__/buildconfig.test.ts` | fails if the release profile ever carries the dev-login switch, or an asset is missing/not 1024x1024 |

## Which eas-cli to run (flagged)
Always `npx eas-cli@24.9.0 ...` (published 2026-10-02, 15 days old, so over your 14-day rule). The newest is 25.1.1 (2026-10-16, one day old); it was published by the official GitHub Actions pipeline of `github.com/expo/eas-cli`, but is too new for the rule. Nothing is installed globally; `npx` downloads it for each run.

## Steps you run, in order (PowerShell, from `D:\DAWAT\mobile`)
1. **(you) Expo account:** create a free account at expo.dev (email and password; no card). Never paste the password in chat.
2. **(you) Log in:** `npx eas-cli@24.9.0 login` (in Claude Code type `! npx eas-cli@24.9.0 login` so it can ask you interactively).
3. **(you) Link the project:** `npx eas-cli@24.9.0 init` — creates the project on expo.dev and writes its id into `app.json` (`extra.eas.projectId`). Tell Claude afterwards so the change is reviewed.
4. **Decide the backend address first (important):** the release APK talks to `EXPO_PUBLIC_API_URL`. Release builds block plain `http://` (cleartext) on Android, so an APK **cannot use the local backend** over `adb reverse`. A usable APK needs the deployed `https://` backend (Phase 10, Render). Until then, test with the **development build** (step 9), which can use the local backend. When the deployed address exists, Claude adds it to the `apk` profile `env` in `eas.json` (public value only).
5. **Before every build (Claude or you):** `npm test` and `npm run check:release` must both pass (the second fails if any dev-login code is in a release bundle).
6. **(you) Build:** `npx eas-cli@24.9.0 build --platform android --profile apk`
   - First build asks "Generate a new Android Keystore?" → **yes**. EAS stores the key; you never handle or paste it.
   - The free plan may queue you for a while. The command prints a link; the build page ends with a download link for the `.apk`.
7. **(you) Download** the `.apk` from that link into `D:\DAWAT\builds\` (create the folder; it is not part of the repo).
8. **(you) Install on the Oppo over USB** (phone plugged in, USB debugging on):
   ```
   C:\platform-tools\adb.exe devices
   C:\platform-tools\adb.exe -s N7QW9XWGAIWCQKIZ install -r D:\DAWAT\builds\<file>.apk
   ```
   `-r` replaces an older install. Then open "Dawat" from the app drawer.
9. **Development build (needs one install first, which Claude does only when you say):** `npx expo install expo-dev-client`, then `npx eas-cli@24.9.0 build --platform android --profile development`, install the same way, start Metro with `npm run dev:local`, and keep `adb reverse` for 8000 and 8081. This build is for testing with the local backend and (after 30 Oct) native Google sign-in. It has the dev-login switch and must never be shared.
10. **Signing fingerprint for Google sign-in (after 30 Oct):** `npx eas-cli@24.9.0 credentials` → Android → the keystore → copy the SHA-1 into the Google Cloud Android client (`docs/GOOGLE_AUTH_SETUP.md` Part B). A development build and a release build have different keys if their profiles differ; add each SHA-1 you use.

## What to look at on the phone after installing
Launcher icon (wordmark on navy, also check the round-mask shape), the splash (navy, wordmark and tagline), the app opening to Welcome with **only** "Continue with Google" (no "Local sign-in (dev only)"), the demo banner, and no gear/"Local data" badge. Report what you see; Claude acts on it.

## Still open (yours to fill in)
- **Map contact address** in the tile User-Agent (`mobile/src/lib/osm.ts`): `[fill in]`. Left as is; the tile policy asks for a real contact before a deployed build.
- **`MAP_BASE_URL`** (`osm.ts`): kept as the placeholder `https://dawat-demo.example/` until the backend/site is deployed.
- **Backend address** for the release profile (step 4).
- Cannot be tested before 30 Oct: real Google sign-in, the Supabase-backed backend, and the SHA-1 registration.
