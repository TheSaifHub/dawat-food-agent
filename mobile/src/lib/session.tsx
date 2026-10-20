// Who is signed in. Ported in spirit from frontend_old/src/lib/session.tsx.
//
// The rules (identity, so they are tested hard in __tests__/session.test.tsx):
//  - The token is kept in the keystore (tokenStore.ts) and in memory. It is never logged and never put in a URL.
//  - ONLY a real HTTP 401 from the backend signs the user out. A network error, a timeout, a 5xx (including the
//    backend's 503 "sign-in keys unreachable") or an unreadable answer keeps the token and shows "can't reach Dawat"
//    with a retry button, because the sign-in itself was not shown to be bad.
//  - The user id is never sent by the app: the backend takes it from the token.
//  - A sign-out (or a new sign-in) while a request is in flight must not be undone by that request's late answer.

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api, isRejectedToken, DEFAULT_TIMEOUT_MS, type ApiOptions, type ApiResult } from './api';
import { clearToken, readToken, saveToken } from './tokenStore';

export type Me = {
  user_id: string;
  display_name: string;
  is_demo: boolean;
  name_confirmed: boolean;
  account_name: string | null;
};

export type SessionState =
  | { status: 'loading'; slow: boolean }
  | { status: 'signedOut'; notice?: string }
  | { status: 'unreachable'; message: string }
  | { status: 'signedIn'; me: Me };

export type Outcome = { ok: true } | { ok: false; message: string };

export type Session = {
  state: SessionState;
  /** Retry "who am I?" after "can't reach Dawat". Keeps the token. */
  retry: () => void;
  /** Take a token from a sign-in route, keep it, and load the profile. */
  signInWithToken: (token: string) => Promise<Outcome>;
  signOut: () => Promise<void>;
  /** null/undefined keeps the account name (the backend reads it from the token); a string is the changed name. */
  confirmName: (name?: string | null) => Promise<Outcome>;
  /** Any signed-in call. A real 401 signs the user out; nothing else does. */
  request: <T>(path: string, options?: Omit<ApiOptions, 'token'>) => Promise<ApiResult<T>>;
  /**
   * For calls `request` cannot make (the chat stream). The token is handed to `run` for the one call and not kept.
   * `rejected` says whether the result means "the backend rejected this sign-in" (a real 401); only then is the user
   * signed out. Returns null, and runs nothing, when nobody is signed in.
   */
  withToken: <T>(run: (token: string) => Promise<T>, rejected: (result: T) => boolean) => Promise<T | null>;
};

const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
  const s = useContext(SessionContext);
  if (!s) throw new Error('useSession must be used inside <SessionProvider>');
  return s;
}

export function SessionProvider({ children, timeoutMs = DEFAULT_TIMEOUT_MS }: { children: ReactNode; timeoutMs?: number }) {
  const [state, setState] = useState<SessionState>({ status: 'loading', slow: false });
  const tokenRef = useRef<string | null>(null);
  const gen = useRef(0); // bumped by every sign-in and sign-out; an older answer is ignored

  const dropSession = useCallback(async (notice?: string) => {
    gen.current += 1;
    tokenRef.current = null;
    setState({ status: 'signedOut', notice });
    await clearToken();
  }, []);

  const loadMe = useCallback(
    async (token: string) => {
      const mine = gen.current;
      setState({ status: 'loading', slow: false });
      const r = await api<Me>('/me', {
        token,
        timeoutMs,
        onSlow: () => mine === gen.current && setState((s) => (s.status === 'loading' ? { status: 'loading', slow: true } : s)),
      });
      if (mine !== gen.current) return;
      if (r.ok) setState({ status: 'signedIn', me: r.data });
      else if (isRejectedToken(r)) await dropSession('Please sign in again.');
      else setState({ status: 'unreachable', message: r.message });
    },
    [dropSession, timeoutMs],
  );

  useEffect(() => {
    let live = true;
    (async () => {
      const token = await readToken();
      if (!live) return;
      if (!token) return setState({ status: 'signedOut' });
      tokenRef.current = token;
      await loadMe(token);
    })();
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once, at launch
  }, []);

  const retry = useCallback(() => {
    if (tokenRef.current) void loadMe(tokenRef.current);
    else setState({ status: 'signedOut' });
  }, [loadMe]);

  const signInWithToken = useCallback(
    async (token: string): Promise<Outcome> => {
      if (!(await saveToken(token))) return { ok: false, message: "Couldn't save your sign-in on this device." };
      gen.current += 1;
      tokenRef.current = token;
      await loadMe(token);
      return { ok: true };
    },
    [loadMe],
  );

  const signOut = useCallback(() => dropSession(), [dropSession]);

  const request = useCallback(
    async <T,>(path: string, options: Omit<ApiOptions, 'token'> = {}): Promise<ApiResult<T>> => {
      const mine = gen.current;
      const r = await api<T>(path, { ...options, token: tokenRef.current });
      if (isRejectedToken(r) && mine === gen.current) await dropSession('Please sign in again.');
      return r;
    },
    [dropSession],
  );

  const withToken = useCallback(
    async <T,>(run: (token: string) => Promise<T>, rejected: (result: T) => boolean): Promise<T | null> => {
      const token = tokenRef.current;
      if (!token) return null;
      const mine = gen.current;
      const result = await run(token);
      if (rejected(result) && mine === gen.current) await dropSession('Please sign in again.');
      return result;
    },
    [dropSession],
  );

  const confirmName = useCallback(
    async (name?: string | null): Promise<Outcome> => {
      const r = await request<{ display_name: string; name_confirmed: boolean }>('/me/name', {
        method: 'POST',
        body: name ? { name } : {},
      });
      if (!r.ok) return { ok: false, message: r.message };
      setState((s) =>
        s.status === 'signedIn'
          ? { status: 'signedIn', me: { ...s.me, display_name: r.data.display_name, name_confirmed: r.data.name_confirmed } }
          : s,
      );
      return { ok: true };
    },
    [request],
  );

  const value = useMemo(
    () => ({ state, retry, signInWithToken, signOut, confirmName, request, withToken }),
    [state, retry, signInWithToken, signOut, confirmName, request, withToken],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
