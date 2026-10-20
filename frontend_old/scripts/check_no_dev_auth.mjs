// D-059 lock 4: after `next build`, prove the local dev login is NOT in the build. Runs as part of `npm run build`
// (so a Vercel deploy fails if it ever is), and on its own as `npm run check:no-dev-auth`.
//
// It scans every file of the production build (.next, minus the dev server's own folder and the cache) for strings
// that exist only in the dev login's code. Exit 1 lists each file and marker found.

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

// Source maps hold the original SOURCE text (so the condition's own wording), not code that runs; Next doesn't serve
// browser source maps by default (productionBrowserSourceMaps is off).
const SKIP_EXT = /\.map$/;
const ROOT = new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const BUILD = join(ROOT, ".next");
const SKIP = new Set(["dev", "cache"]);                    // `next dev` output and the build cache are not shipped
const MARKERS = [
  "dawat-dev-login",                                       // lib/devauth.ts's storage key
  "/dev/auth/",                                            // the backend's dev routes
  "NEXT_PUBLIC_DAWAT_DEV_LOGIN",                           // the flag's name: a production build has no reason to keep it
  "Local development sign-in",                             // LoginPanel's dev section
  "Local development: local data",                         // the banner's local-mode line
];

function* files(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      if (!(dir === BUILD && SKIP.has(name))) yield* files(path);
    } else {
      if (!SKIP_EXT.test(name)) yield path;
    }
  }
}

let buildId;
try {
  buildId = readFileSync(join(BUILD, "BUILD_ID"), "utf8").trim();
} catch {
  console.error("No production build found (.next/BUILD_ID). Run `next build` first.");
  process.exit(1);
}

const found = [];
let scanned = 0;
for (const path of files(BUILD)) {
  const text = readFileSync(path).toString("latin1");
  scanned += 1;
  for (const marker of MARKERS) if (text.includes(marker)) found.push(`${relative(ROOT, path)}: ${marker}`);
}

if (found.length) {
  console.error(`DEV LOGIN FOUND IN THE PRODUCTION BUILD (${buildId}). This build must not be deployed (D-059):`);
  for (const f of found) console.error("  " + f);
  process.exit(1);
}
console.log(`check:no-dev-auth OK: ${scanned} files of build ${buildId} contain no dev login code.`);
