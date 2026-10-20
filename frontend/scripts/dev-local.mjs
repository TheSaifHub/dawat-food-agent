// `npm run dev:local`: the dev site in LOCAL mode (D-059). Starts `next dev` with the dev login on, for this one
// process. It's the only thing that sets the flag (next.config.ts refuses it otherwise). Pair it with the backend's
// `dev_server.py start` (local mode, the dawat_dev database), and nothing reaches Supabase.

import { spawn } from "node:child_process";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const nextBin = require.resolve("next/dist/bin/next");

const child = spawn(process.execPath, [nextBin, "dev", ...process.argv.slice(2)], {
  stdio: "inherit",
  env: { ...process.env, NEXT_PUBLIC_DAWAT_DEV_LOGIN: "1", DAWAT_DEV_LAUNCHER: "1" },
});
child.on("exit", (code, signal) => process.exit(code ?? (signal ? 1 : 0)));
