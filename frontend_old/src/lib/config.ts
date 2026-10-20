// NEXT_PUBLIC_ values are inlined into the browser bundle at build time,
// so on Vercel this must be set before the build runs. Never put secrets here.
// `||` (not `??`) so a blank value copied from .env.example still falls back to the default.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL?.trim() || "http://localhost:8000").replace(/\/+$/, "");

// Public by design: the URL and the publishable key only let a browser sign in. All data access goes through the
// backend, which verifies the token itself (D-020, D-022). Blank → sign-in is shown as unavailable, nothing crashes.
// Each name is written out in full (no dynamic lookup) so Next can inline it.
export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim() || "";
export const SUPABASE_PUBLISHABLE_KEY = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY?.trim() || "";
