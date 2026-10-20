"use client";

// The browser's Supabase client: sign-in only. Pages use lib/auth.ts, which picks this or the local dev login. Dawat's data never comes from Supabase directly (the browser has no
// table grants, D-020); the page sends the access token to the backend, which verifies it (D-022).
//
// The session lives in the browser's storage and is refreshed automatically. Every page that needs data fetches it
// in the browser (the backend may be asleep, and a server-side fetch would hit Vercel's time limit), so there is no
// server-side session and no cookie sync.

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

import { SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL } from "@/lib/config";

let client: SupabaseClient | null = null;

export const authConfigured = Boolean(SUPABASE_URL && SUPABASE_PUBLISHABLE_KEY);

/** The shared client, or null when the two public values aren't set (sign-in then shows as unavailable). */
export function supabase(): SupabaseClient | null {
  if (!authConfigured) return null;
  // Local mode (D-059) never creates a Supabase client, so nothing in it reaches Supabase.
  if (process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_DAWAT_DEV_LOGIN === "1") return null;
  client ??= createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
  });
  return client;
}

/** The current access token for a backend call, or null when signed out. supabase-js refreshes it if it expired. */
export async function accessToken(): Promise<string | null> {
  const sb = supabase();
  if (!sb) return null;
  const { data } = await sb.auth.getSession();
  return data.session?.access_token ?? null;
}
