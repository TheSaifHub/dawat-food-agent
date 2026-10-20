"use client";

// Sign-in for every page: Supabase normally, the LOCAL dev login only under `npm run dev:local` (D-059).
//
// THE DEV LOGIN NEVER SHIPS. Every path into it is written as the full build-time condition
//     process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_DAWAT_DEV_LOGIN === "1"
// inline (not through a variable), because Next replaces both values with fixed strings at build time: in a
// production build the condition is `"production" === "development" && …`, the bundler drops the branch, and with it
// the dynamic import of lib/devauth.ts. Three more locks back this up: next.config.ts refuses the flag outside
// `next dev`, `npm run build` scans its output for the dev login and fails if it finds it, and the backend has no
// dev routes unless it was started for them on a local database.

import { SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL } from "@/lib/config";
import { accessToken as supabaseAccessToken, supabase } from "@/lib/supabase";

/** For what the page SHOWS only (never to guard an import): the dev sign-in panel and the "Local data" badge. */
export const DEV_LOGIN = process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_DAWAT_DEV_LOGIN === "1";

export const authConfigured = DEV_LOGIN || Boolean(SUPABASE_URL && SUPABASE_PUBLISHABLE_KEY);

/** The current access token for a backend call, or null when signed out. */
export async function accessToken(): Promise<string | null> {
  if (process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_DAWAT_DEV_LOGIN === "1") {
    return (await import("@/lib/devauth")).accessToken();
  }
  return supabaseAccessToken();
}

/** Called soon after subscribing (the stored session), then on every sign-in and sign-out; not on token refreshes,
 *  which don't change who the user is. Returns the unsubscribe function. */
export function onAuthChange(cb: () => void): () => void {
  if (process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_DAWAT_DEV_LOGIN === "1") {
    let unsubscribe: (() => void) | null = null;
    let closed = false;
    void import("@/lib/devauth").then((m) => {
      if (!closed) unsubscribe = m.onAuthChange(cb);
    });
    return () => {
      closed = true;
      unsubscribe?.();
    };
  }
  const sb = supabase();
  if (!sb) return () => {};
  // Supabase asks for no awaited calls inside this callback (they can deadlock its lock): the caller defers its work.
  const { data } = sb.auth.onAuthStateChange((event) => {
    if (event !== "TOKEN_REFRESHED") cb();
  });
  return () => data.subscription.unsubscribe();
}

export async function signOut(): Promise<void> {
  if (process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_DAWAT_DEV_LOGIN === "1") {
    return (await import("@/lib/devauth")).signOut();
  }
  await supabase()?.auth.signOut();
}

/** A fresh guest account (the start of "Try as Priya / Arjun"). `error.status` 429 = too many from this network. */
export async function signInAnonymously(): Promise<{ error: null | { status?: number } }> {
  if (process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_DAWAT_DEV_LOGIN === "1") {
    return (await import("@/lib/devauth")).signInAnonymously();
  }
  const sb = supabase();
  if (!sb) return { error: { status: 503 } };
  const { error } = await sb.auth.signInAnonymously();
  return { error: error ? { status: error.status } : null };
}

/** Dev login only: the seed users (null otherwise, or when the backend has no dev routes). */
export async function devSeedUsers(): Promise<{ user_id: string; display_name: string }[] | null> {
  if (process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_DAWAT_DEV_LOGIN === "1") {
    return (await import("@/lib/devauth")).seedUsers();
  }
  return null;
}

/** Dev login only: sign in as one of the seed users. */
export async function devSignInSeedUser(userId: string): Promise<boolean> {
  if (process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_DAWAT_DEV_LOGIN === "1") {
    return (await (await import("@/lib/devauth")).signInSeedUser(userId)).error === null;
  }
  return false;
}
