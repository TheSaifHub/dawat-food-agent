"use client";

// The browser's Supabase client: sign-in only.
// Dawat's data never comes from Supabase directly; the page sends the access token to the backend.

import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL } from "@/lib/config";

let client: SupabaseClient | null = null;

export const authConfigured = Boolean(SUPABASE_URL && SUPABASE_PUBLISHABLE_KEY);

/** The shared client, or null when the two public values aren't set (sign-in then shows as unavailable). */
export function supabase(): SupabaseClient | null {
  if (!authConfigured) return null;
  // Local mode never creates a Supabase client, so nothing in it reaches Supabase.
  if (process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_DAWAT_DEV_LOGIN === "1") return null;
  client ??= createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
  });
  return client;
}

/** The current access token for a backend call, or null when signed out. */
export async function accessToken(): Promise<string | null> {
  const sb = supabase();
  if (!sb) return null;
  const { data } = await sb.auth.getSession();
  return data.session?.access_token ?? null;
}
