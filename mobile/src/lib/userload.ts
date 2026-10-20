// Loads one signed-in route for the CURRENT user and never shows another user's answer.
//
// The held answer is stored with the user id it was fetched for and is only handed out while that is still the signed-in
// user; a late answer for a user who has since signed out or been replaced is dropped. Orders and preferences are
// private, so this is identity code (tested hard in __tests__/account.test.tsx). The token is never seen here: the
// session's `request` adds it.

import { useCallback, useEffect, useRef, useState } from 'react';
import { useFocusEffect } from 'expo-router';
import { useSession } from './session';

export type UserLoad<T> =
  | { status: 'loading'; slow: boolean }
  | { status: 'error'; message: string }
  | { status: 'ok'; data: T };

type Held<T> = { userId: string; path: string; load: UserLoad<T> };

const LOADING: UserLoad<never> = { status: 'loading', slow: false };

/** Fetches `path` each time the screen comes into view. `okStatuses` are the bodies' `status` values that mean "show it". */
export function useUserLoad<T extends { status?: string }>(path: string | null, okStatuses: string[] = ['ok', 'empty']): UserLoad<T> & { reload: () => void } {
  const { state, request } = useSession();
  const userId = state.status === 'signedIn' ? state.me.user_id : null;
  const userRef = useRef(userId);
  useEffect(() => {
    userRef.current = userId; // read by a late answer to see who is signed in now
  }, [userId]);
  const [held, setHeld] = useState<Held<T> | null>(null);
  const [tick, setTick] = useState(0);

  useFocusEffect(
    useCallback(() => {
      if (userId === null || path === null) return;
      let live = true;
      // Keep what is already shown for this same user and route while it refreshes; anything else starts from "loading".
      setHeld((h) => (h && h.userId === userId && h.path === path && h.load.status === 'ok' ? h : { userId, path, load: LOADING }));
      void request<T>(path, {
        onSlow: () => live && setHeld((h) => (h && h.load.status === 'loading' ? { ...h, load: { status: 'loading', slow: true } } : h)),
      }).then((r) => {
        if (!live || userRef.current !== userId) return; // left the screen, or a different person is signed in now
        if (!r.ok) return setHeld({ userId, path, load: { status: 'error', message: r.message } });
        const st = r.data?.status;
        if (st && !okStatuses.includes(st)) {
          const m = (r.data as { message?: unknown }).message;
          return setHeld({ userId, path, load: { status: 'error', message: typeof m === 'string' ? m : "That didn't work. Please try again." } });
        }
        setHeld({ userId, path, load: { status: 'ok', data: r.data } });
      });
      return () => {
        live = false;
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps -- okStatuses is a constant list per call site
    }, [userId, path, request, tick]),
  );

  const load: UserLoad<T> = held && held.userId === userId && held.path === path ? held.load : LOADING;
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...load, reload };
}
