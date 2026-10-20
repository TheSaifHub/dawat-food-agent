"use client";

// Who is signed in, for every page (Phase 7b). Follows the sign-in state (lib/auth.ts) in the browser and asks the backend
// for the profile (GET /me), because the backend is the only judge of a token (D-022). The page never decides who
// the user is from Supabase's data alone.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import { accessToken, authConfigured, onAuthChange, signOut as authSignOut } from "@/lib/auth";

export type Persona = "priya" | "arjun";

export type Me = {
  user_id: string;
  display_name: string;
  is_demo: boolean;
  is_anonymous: boolean;
  demo_persona: Persona | null;
};

export type Session =
  | { state: "loading" }
  | { state: "signed_out" }
  | { state: "signed_in"; me: Me }
  /** Signed in with Supabase, but the backend couldn't confirm it (asleep, offline): show a retry, not a sign-in. */
  | { state: "unconfirmed"; message: string };

type SessionContext = {
  session: Session;
  /** Reload the profile from the backend (after a demo start, a sign-in, a name change). */
  refresh: () => Promise<Session>;
  signOut: () => Promise<void>;
};

const Ctx = createContext<SessionContext | null>(null);

async function loadSession(): Promise<Session> {
  const token = await accessToken();
  if (!token) return { state: "signed_out" };
  const res = await api<Me>("/me", { token });
  if (res.ok) return { state: "signed_in", me: res.data };
  if (res.status === 401) {
    await authSignOut();                            // a token the backend refuses is no session at all
    return { state: "signed_out" };
  }
  return { state: "unconfirmed", message: res.message };
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session>({ state: "loading" });

  const refresh = useCallback(async () => {
    const next = await loadSession();
    setSession(next);
    return next;
  }, []);

  useEffect(() => {
    if (!authConfigured) {
      // Sign-in isn't configured (no public Supabase values): everything else still works signed out.
      queueMicrotask(() => setSession({ state: "signed_out" }));
      return;
    }
    // Fires once with the stored session, then on every sign-in and sign-out (lib/auth.ts skips token refreshes,
    // which don't change who the user is). Supabase asks for no awaited calls inside its callback, so load afterwards.
    return onAuthChange(() => setTimeout(() => void refresh(), 0));
  }, [refresh]);

  const signOut = useCallback(async () => {
    await authSignOut();
    setSession({ state: "signed_out" });
  }, []);

  const value = useMemo(() => ({ session, refresh, signOut }), [session, refresh, signOut]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): SessionContext {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useSession must be used inside <SessionProvider>");
  return ctx;
}
