// NEXT_PUBLIC_ values are inlined into the browser bundle at build time.
// Never put secrets here.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL?.trim() || "http://127.0.0.1:8000").replace(/\/+$/, "");

// Public by design: the URL and publishable key only let a browser sign in.
// All data access goes through the backend, which verifies the token itself.
export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim() || "";
export const SUPABASE_PUBLISHABLE_KEY = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY?.trim() || "";
