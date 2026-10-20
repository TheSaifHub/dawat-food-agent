import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

const DEV_LOGIN_FLAG = "NEXT_PUBLIC_DAWAT_DEV_LOGIN";

// D-059 lock 4: the local dev login exists only under `npm run dev:local`. Its flag anywhere else (a build, `next
// start`, a Vercel deploy, an env file read by a plain `next dev`) stops Next here, before anything is built or served.
export default function config(phase: string): NextConfig {
  const flag = process.env[DEV_LOGIN_FLAG];
  if (flag !== undefined && flag.trim() !== "") {
    if (phase !== PHASE_DEVELOPMENT_SERVER || process.env.VERCEL) {
      throw new Error(`${DEV_LOGIN_FLAG} is set outside the local dev server. The dev login never goes into a build ` +
                      "or a deployment (D-059). Remove it.");
    }
    if (process.env.DAWAT_DEV_LAUNCHER !== "1") {
      throw new Error(`${DEV_LOGIN_FLAG} is set, but only \`npm run dev:local\` may set it (D-059). Remove it from ` +
                      "your environment or env files.");
    }
  }
  return {};
}
