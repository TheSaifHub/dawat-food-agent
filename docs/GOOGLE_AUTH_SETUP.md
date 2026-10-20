# Google sign-in: setup checklist (for Saif)

Dawat signs people in with **Google only** (D-064). In local mode (`npm run dev:local`) a fake Google user is used, so
none of this is needed for daily work. Do this **after 30 Oct**, in this order. Claude does not do any of it: it
involves your Google account and the Supabase dashboard.

Never paste the Google client secret into chat, a file in this repo, or any `NEXT_PUBLIC_` variable. It goes only
into the Supabase dashboard (step 3).

Replace `<ref>` with your Supabase project ref (the part before `.supabase.co` in your project URL) and
`<site>` with the deployed frontend address (for example `https://dawat.vercel.app`; you get it in Phase 10).

## 0. Before anything: the database

1. Tell Claude "apply 0015 to Supabase". Claude shows the plan (`migrate.py`, no `--apply`), you approve, then
   it applies **0014** (payments) and **0015** (`users.name_confirmed`). Both were only applied to the local databases so far.
   The backend works without 0015 only until someone signs in: `/me` reads the new column.

## 1. Google Cloud: the OAuth client

1. Go to <https://console.cloud.google.com/> and create a project (name: `Dawat`).
2. **APIs & Services → OAuth consent screen** (may be called *Google Auth Platform → Branding*):
   - User type **External**, app name `Dawat`, your email as support and developer contact.
   - Scopes: only the defaults (`openid`, `email`, `profile`). Nothing else is needed.
   - Leave publishing status on **Testing** and add your own Google account(s) under **Test users**
     (only listed accounts can sign in while it is in testing). Press *Publish app* later if strangers should sign in;
     with these basic scopes Google does not require verification.
3. **APIs & Services → Credentials → Create credentials → OAuth client ID**:
   - Application type **Web application**, name `Dawat web`.
   - **Authorized JavaScript origins** (add each):
     - `http://localhost:3000`
     - `<site>` (add it when you have it)
   - **Authorized redirect URIs** (exactly one, Supabase's callback, not the website's):
     - `https://<ref>.supabase.co/auth/v1/callback`
4. Create. Copy the **Client ID** and **Client secret** (keep the secret in your password manager).

## 2. Supabase: turn on the Google provider

1. Dashboard → your project → **Authentication → Sign In / Providers → Google**.
2. Enable it, paste the **Client ID** and **Client secret** from step 1, Save.
   (The "Callback URL" shown there must equal the redirect URI you entered in step 1.3.)

## 3. Supabase: allowed redirect URLs

1. **Authentication → URL Configuration**.
2. **Site URL**: `<site>` (use `http://localhost:3000` until the site is deployed).
3. **Redirect URLs** (add all):
   - `http://localhost:3000/**`
   - `<site>/**`
   The website sends people back to `<origin>/login`, so these must be allowed or Supabase falls back to the Site URL.

## 4. Supabase: switch off everything else

1. **Authentication → Sign In / Providers**:
   - turn **off** *Allow anonymous sign-ins* (the backend already refuses anonymous tokens; this removes the door too);
   - turn **off** the **Email** provider (Google is the only way in).
2. Existing visitor demo accounts (anonymous) stop working. Claude can list them read-only; deleting them is a
   Phase 10 clean-up that needs your approval.

## 5. Frontend settings (public values only)

`frontend/.env.local` (or Vercel's environment variables) needs only these two, both public:

- `NEXT_PUBLIC_SUPABASE_URL` = `https://<ref>.supabase.co`
- `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` = the publishable (anon) key

Do **not** add `NEXT_PUBLIC_DAWAT_DEV_LOGIN` anywhere (the build refuses it outside `npm run dev:local`).
The backend keeps `SUPABASE_URL` in `backend/.env` / Render (it verifies tokens against Supabase's public keys; no secret).

## 6. Test it (once, lightly: Supabase egress is limited)

1. Backend: `.venv\Scripts\python backend\dev_server.py start --supabase`. Frontend: `npm run dev` (not `dev:local`).
2. Open `http://localhost:3000/login` → **Continue with Google** → choose your account.
3. Expected: you land back on the site, see **Confirm your name** (your Google name prefilled), press Continue, and arrive on the home page.
4. Sign out, sign in again: no name screen this time.
5. Phase 10 checklist item: repeat steps 2–4 on the deployed site.

## If something goes wrong

- *redirect_uri_mismatch* (Google error page): step 1.3 must be exactly `https://<ref>.supabase.co/auth/v1/callback`.
- *Access blocked / not a test user*: add the account under step 1.2 Test users.
- Back on the site but still signed out, or sent to the wrong address: step 3 (Redirect URLs / Site URL).
- "Couldn't start Google sign-in": the two public values in step 5 are missing or wrong.

---

# Part B: native iOS and Android sign-in (added 2026-10-15; for after 30 Oct; yours to do)

The app is now a native mobile app (D-068). Part A above (the Google Cloud project, the consent screen, the Supabase Google provider, the disabled Email and anonymous options) still applies; its web redirect steps (3 and 5) are legacy. What changes is how the app gets a Google token. Claude does not do any of this: it involves your Google account and the Supabase dashboard. Never paste a client secret into chat or the repo.

1. **Google Cloud: create three OAuth client IDs** in the same project as Part A:
   - **Web application** (needed by Supabase; its client ID and secret go only into the Supabase Google provider, as in Part A).
   - **Android:** package name = the app's Android package (Claude will tell you the exact value from `app.json`), plus the **SHA-1 fingerprint** of the signing key. A development build, an EAS build and a Play-signed build each have a different SHA-1, so you may need to add more than one. Claude will tell you which command prints it.
   - **iOS:** the app's bundle identifier (also from `app.json`). Creating this client ID needs no paid Apple account.
2. **Supabase → Authentication → Sign In / Providers → Google:** under authorized client IDs, add the **Android** and **iOS** client IDs next to the Web one, so ID tokens from the apps are accepted. Leave "Skip nonce check" off unless Claude says the chosen library needs it.
3. **Deep-link scheme:** `dawat://` is set in `app.json` by Claude. The native ID-token flow needs no extra redirect URL in Supabase.
4. **The app's public settings (`mobile/.env`, public values only):** `EXPO_PUBLIC_API_URL`, `EXPO_PUBLIC_SUPABASE_URL`, `EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, `EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID`, and the iOS client ID. These are embedded in the app bundle, so they must all be public values. Never put the Google client secret here.
5. **Expo Go cannot do native Google sign-in.** Real sign-in needs a development build (a local Android Studio build or an EAS build). Daily work uses the local dev login and needs none of this.
6. **Test once, lightly:** sign in with Google on an Android emulator or phone, see "Confirm your name", then Home. Report what you see.
7. **iOS note:** running on a real iPhone beyond a short test, or TestFlight, needs a paid Apple Developer account. That is your decision (see `docs/MOBILE_PLAN.md`, distribution).
