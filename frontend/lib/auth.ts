"use client";

// Sign-in for every page: Supabase normally, the LOCAL dev login only under NEXT_PUBLIC_DAWAT_DEV_LOGIN === "1".
//
// THE DEV LOGIN NEVER SHIPS. Every path into it is guarded with the full inline condition:
//   process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_DAWAT_DEV_LOGIN === "1"

import { SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL } from "@/lib/config";
import { accessToken as supabaseAccessToken, supabase } from "@/lib/supabase";

export const DEV_LOGIN = process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_DAWAT_DEV_LOGIN === "1";

export const authConfigured = DEV_LOGIN || Boolean(SUPABASE_URL && SUPABASE_PUBLISHABLE_KEY);

/** The current access token for a backend call, or null when signed out. */
export async function accessToken(): Promise<string | null> {
  if (process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_DAWAT_DEV_LOGIN === "1") {
    return (await import("@/lib/devauth")).accessToken();
  }
  return supabaseAccessToken();
}

/** Called on sign-in and sign-out events. Returns an unsubscribe function. */
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

/** "Continue with Google". Production: Supabase Auth's Google provider (the browser leaves for Google and comes back to
 *  /login). Local dev mode: the backend's fake Google user, with no network call outside localhost. */
export async function signInWithGoogle(options: { newLocalUser?: boolean } = {}): Promise<{ error: null | { status?: number } }> {
  if (process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_DAWAT_DEV_LOGIN === "1") {
    return (await import("@/lib/devauth")).signInGoogle(options.newLocalUser === true);
  }
  const sb = supabase();
  if (!sb) return { error: { status: 503 } };
  const { error } = await sb.auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo: `${window.location.origin}/login` },
  });
  return { error: error ? { status: error.status } : null };
}
