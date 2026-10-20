# Running the Dawat app on your Android phone over USB (local mode)

For Saif. Written 2026-10-15, updated for the Oppo the same day. Goal: the app on your phone (in Expo Go) talks to the backend on this PC **over the USB cable only**. **Nothing listens on Wi-Fi/LAN and nothing is bound to `0.0.0.0`.** Local data only; no Supabase.

Items marked **(verify)** come from my reading of the Expo docs or from memory of the tools and are checked by me the first time we run them; tell me what you see.

## Test devices
| Phone | Role | adb serial | Android | Expo Go | Status |
|---|---|---|---|---|---|
| **Oppo K10 5G** (ColorOS) | **Main test phone** | `N7QW9XWGAIWCQKIZ` | 14 | 57.0.9 (SDK 57) | Listed as `device` |
| **Samsung A56** (SM-A566E) | **Test phone from 2026-10-17** (plugged in alone) | `RZGL90DPYHZ` | 16 | 57.0.9 (SDK 57) | Listed as `device`; reverse for tcp:8000 and tcp:8081 set |

Android 14 and Expo Go 57.0.9 were read from the phone by `adb` on 2026-10-15 (`getprop ro.build.version.release`, `dumpsys package host.exp.exponent`). Expo Go's major version is the SDK it runs, so **the app stays on SDK 57; no change.**

**Always name the phone with `-s`.** With two phones ever connected, plain `adb` commands fail ("more than one device"), and `adb reverse` could target the wrong one:
```
C:\platform-tools\adb.exe -s N7QW9XWGAIWCQKIZ devices
C:\platform-tools\adb.exe -s N7QW9XWGAIWCQKIZ reverse tcp:8000 tcp:8000
C:\platform-tools\adb.exe -s N7QW9XWGAIWCQKIZ reverse tcp:8081 tcp:8081
C:\platform-tools\adb.exe -s N7QW9XWGAIWCQKIZ reverse --list
C:\platform-tools\adb.exe -s N7QW9XWGAIWCQKIZ logcat -s ReactNativeJS
```
(`adb devices` itself takes no `-s`; it lists every phone.)

## Oppo / ColorOS notes
ColorOS closes background apps aggressively. Without these settings Expo Go can be killed mid-session and the app reloads or loses its connection:
1. **Battery optimisation:** Settings → Battery → (App battery management) → **Expo Go → Unrestricted** (wording varies by ColorOS version; also try Settings → Apps → App management → Expo Go → Battery usage → Allow background activity). **(verify on your screen)**
2. **Auto-launch / background freeze:** in the same Expo Go page, allow "Auto launch" and turn off any "Freeze when in background" or "Deep optimisation" option if present.
3. **Recent apps lock:** open the recent-apps screen and lock Expo Go (pull the card down or tap the lock icon) so "clear all" doesn't kill it.
4. **Developer options:** keep **USB debugging** on. Turn on **"Disable permission monitoring"** only if shown (it is not needed for us). If "Install via USB" or "USB debugging (Security settings)" appears, that's for installing APKs later (M8), not for Expo Go.
5. **Stay awake while charging** (Developer options) so the screen doesn't sleep during a test.
6. After each cable reconnect, `adb reverse` must be run again (forwarding is lost). The USB mode "File transfer" is the most reliable.
7. If the phone shows "Allow USB debugging?" again after a reboot, accept it.

## How it works (so the risk is clear)
- The backend runs on `127.0.0.1:8000` (loopback). `backend/dev_server.py` starts uvicorn with no `--host`, so uvicorn's default (loopback only) applies. I checked: no `--host`, no `0.0.0.0`.
- `adb reverse tcp:8000 tcp:8000` makes **the phone's** `localhost:8000` travel through the USB cable to **the PC's** `localhost:8000`. The PC's ports are not opened to the network; only the cable carries the traffic. Same for Metro (the Expo dev server) on port 8081.
- The app's API address is therefore `http://localhost:8000` on the phone.
- The dev login (`/dev/auth/*`) exists only in local mode and is reachable only through that loopback/USB path. Nobody on your Wi-Fi can reach it.
- Unplugging the cable (or `adb kill-server`) ends the forwarding. Run `adb reverse` again after each reconnect.

## One-time setup
1. **adb is not at `C:\platform-tools` yet** (I checked on 2026-10-15: the folder does not exist and `adb` is not on the PATH). Install it (system software, so you do it):
   - Download "SDK Platform-Tools for Windows" from `developer.android.com/tools/releases/platform-tools`.
   - Unzip it so that `C:\platform-tools\adb.exe` exists.
   - Check in PowerShell: `C:\platform-tools\adb.exe version`. Tell me the output.
2. **Phone:** Settings → About phone → tap "Build number" 7 times → Developer options → **USB debugging ON**.
3. Plug in the USB cable (a data cable, not charge-only). Choose "File transfer" if the phone asks. Accept the "Allow USB debugging?" prompt on the phone (tick "Always allow from this computer").
4. `C:\platform-tools\adb.exe devices` should list your phone as `device` (not `unauthorized` or `offline`). **Done for the Oppo.**
5. **Expo Go** from the Play Store. The app's SDK must match the Expo Go version. **Done: Expo Go 57.0.9 on the Oppo = SDK 57, which is what `mobile/` uses.** If the Play Store later updates Expo Go to a newer SDK, the app will show "incompatible"; tell me and we decide whether to upgrade the project.

## Each time you run the app
In three separate terminals, from `D:\DAWAT`:

1. **Backend (local mode):**
   `.venv\Scripts\python backend\dev_server.py start`
   (stop it later with `... stop`). It must say `http://127.0.0.1:8000` and local data.
2. **Forward the ports over USB:**
   ```
   C:\platform-tools\adb.exe -s N7QW9XWGAIWCQKIZ reverse tcp:8000 tcp:8000
   C:\platform-tools\adb.exe -s N7QW9XWGAIWCQKIZ reverse tcp:8081 tcp:8081
   ```
3. **Expo dev server, loopback only:**
   `cd mobile` then `npx expo start --localhost`
   `--localhost` keeps Metro off the network. **(verify)** I will run `npx expo start --help` to confirm the flag in the installed version.
4. **Open the app in Expo Go on the phone:** in Expo Go choose "Enter URL manually" and type `exp://localhost:8081`. (The QR code may point at a LAN address and not work; typing the URL is the reliable way over USB. **(verify)**)
5. The app's `.env` (copied from `.env.example`; public values only) has `EXPO_PUBLIC_API_URL=http://localhost:8000`. The local dev-login switch is set only for that one dev process by an npm script I add in M1, never in a `.env` file (same idea as D-059).

## What you should see / what to tell me
- The app opens with the "Local data" badge and the demo banner. A green "backend ok" state means `GET /health` worked through the cable.
- If the app says it cannot reach the backend: check `adb devices` (Oppo listed?), that you ran both `adb -s ... reverse` lines after plugging in, and that `dev_server.py status` says running. Send me the exact message.
- "Project is incompatible with this version of Expo Go": the SDK and Expo Go versions differ (see step 5 of one-time setup).

## Things I will NOT do without your explicit approval
- Bind the backend or Metro to `0.0.0.0` or a LAN address, or open a Windows Firewall rule.
- Use a tunnel (ngrok, `expo start --tunnel`) or run the dev login on any reachable network.
- Point the app at Supabase before 30 Oct.

## Limits to know
- This is **Expo Go**, so no native modules: native Google sign-in and on-device speech need a development build later (M8/Phase 9). Local dev login is used until then.
- Android only. I cannot test iOS from this PC.
- Android blocks plain `http://` in release builds; Expo Go and debug builds allow it for local development. The production API will be HTTPS.

## Known issues and fixes found on the Oppo (2026-10-15)
- **"Uncaught Error: java.io.IOException: Failed to download remote update" in Expo Go.** Cause: `adb reverse` reaches the PC's **IPv4** loopback (`127.0.0.1`), but Node resolved `localhost` to IPv6 (`[::1]`), so Metro listened only on `[::1]:8081` and the connection was refused. Fix: start Metro with Node preferring IPv4, still loopback only:
  `cd mobile` then `$env:NODE_OPTIONS="--dns-result-order=ipv4first"; npx expo start --localhost --port 8081` (PowerShell). Check with `netstat -ano | findstr :8081`: it must show `127.0.0.1:8081`, never `0.0.0.0`.
- **Black strip above the demo banner, no status icons.** Expo Go on this phone lets the system draw the status-bar strip, so the app's dark icons sat on black. The app now sets the Android status bar to butter (the banner colour) with dark icons. Verified by screenshot.
- **The gear icon over the "Local data" badge** is Expo Go's own floating dev-menu button, not part of the app (the app has no gear). Release builds do not have it, and the badge itself is shown only in dev builds, so it is not moved.
- **Rounded views drawn as hard squares (only in one place).** A `View` with `borderRadius` plus a fill or border, used as the icon wrapper inside the tab bar's `Pressable`, rendered as a hard square on the Oppo (Expo Go, Android 14). I tried four variants (fill, ring, nested circle, translate instead of margin) and did not find the cause. Checked on the Oppo on 2026-10-15: **round buttons (pill radius), the round initial avatar on Profile (plain `View`, `borderRadius: size / 2`) and the tiles all render correctly.** So the problem is specific to that tab-bar spot, not to rounded views in general. The active tab's circle is therefore drawn with an Ionicons `ellipse` glyph, which is always round. If a rounded view ever looks square elsewhere, check it on the phone before trusting it.
- **Start Metro with `npm run dev:local`** (from `mobile/`). It turns the local dev login on for that one process, keeps Metro on loopback, and sets Node to prefer IPv4 (the fix above), so you no longer type the `NODE_OPTIONS` line. `npm start` is the normal start with no dev login.
- **Saved sign-in after a relaunch:** after force-stopping Expo Go and reopening, the app stayed signed in on two later tries (once on the name screen, once on Home). One earlier relaunch showed the Welcome screen instead; I could not reproduce it and did not find a cause. If you see it, tell me what you did just before.

## Samsung A56 (added 2026-10-17)
- **Read from the phone by adb:** model SM-A566E, Android 16, Expo Go 57.0.9 = SDK 57, so `mobile/` (Expo SDK 57) is supported.
- **Commands:** always `adb -s RZGL90DPYHZ ...`, and only `reverse tcp:8000 tcp:8000` and `reverse tcp:8081 tcp:8081`. Open the app with `adb -s RZGL90DPYHZ shell am start -a android.intent.action.VIEW -d "exp://localhost:8081" host.exp.exponent`. Metro and the backend stay on loopback.
- **No-chat smoke test (2026-10-17, local data):** Welcome, "Seed user with address" sign-in, Home, the area picker (searchable list, picked Abids), "Restaurants near Abids" (472), Grand's menu, Add (Veg Dum Biryani, cart badge 1), the Cart (Delivering to Abids; items Rs280, delivery Rs25, GST Rs19, total Rs324 from the server) all worked.
- **Is the "hard square" problem Oppo-only?** On the A56 the Home tab's active circle drew **round**, and so did the Cart, Orders and Profile active circles (all four seen on screenshots). The Oppo problem (a `View` with `borderRadius` as the tab-bar icon wrapper drawn square) did not appear here, so it looks **specific to the Oppo/ColorOS**. **Status (Saif, 2026-10-17): not proven, Oppo-only likely; no extra comparison needed.** Detail: the circle is now an Ionicons `ellipse` glyph (always round), so this A56 check says the glyph renders round, not that the old `View` version would have. If you want proof, I can temporarily swap the old `View` version back and look at it on both phones.
- **Android 16 note:** the gesture bar sits under the tab bar and the layout cleared it (safe-area bottom padding), nothing overlapped in the screenshots.
- **Other things seen:** Expo Go's dev gear button overlaps the top-right of the screen under the banner (Expo Go's own overlay, as on the Oppo); the "Local data" badge is ours and dev-only.
- **Narrow width and large text (A56, 2026-10-17):** `wm density 540` (320 dp wide) with `font_scale 1.3`, then reset with `wm density reset` and `font_scale 1.0`. Home, Cart, Orders, Profile and Chat fit; the tab label and wrapped button text were fixed. Oppo not yet checked.
- **Oppo cannot be resized over adb (2026-10-17):** `wm density`, `wm size` and `settings put system font_scale` are refused (WRITE_SECURE_SETTINGS / WRITE_SETTINGS) unless "USB debugging (Security settings)" is on. Set Display size and Font size by hand in Settings, then restore them by hand. Original: 720x1612, density 320, font 1.0.
