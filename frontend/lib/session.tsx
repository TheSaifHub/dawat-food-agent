"use client";

// Who is signed in, for every page. Follows sign-in state in the browser and asks the backend
// for the profile (GET /me).

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import { accessToken, authConfigured, onAuthChange, signOut as authSignOut } from "@/lib/auth";

export type Me = {
  user_id: string;
  display_name: string;
  is_demo: boolean;
  /** The website's "Confirm your name" step is done. */
  name_confirmed: boolean;
  /** The name Google gave us, from the verified token: shown in "Keep it, or change it?". */
  account_name: string | null;
};

export type Session =
  | { state: "loading" }
  | { state: "signed_out" }
  | { state: "signed_in"; me: Me }
  /** Signed in with Supabase, but backend couldn't confirm it (offline, waking up). */
  | { state: "unconfirmed"; message: string };

type SessionContext = {
  session: Session;
  /** Reload the profile from the backend. */
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
    await authSignOut();
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
      queueMicrotask(() => setSession({ state: "signed_out" }));
      return;
    }
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
