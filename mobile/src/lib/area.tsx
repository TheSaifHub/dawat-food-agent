// The delivery area the user picked. Not a secret, but it lives in the keystore anyway: the app has one storage
// module (tokenStore.ts) and no AsyncStorage (a test forbids it). A failed read or write only means "pick again".

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import * as SecureStore from 'expo-secure-store';

const KEY = 'dawat.area';

export type PickedArea = { area_id: string; name: string };

type AreaCtx = { area: PickedArea | null; ready: boolean; setArea: (a: PickedArea) => void };

const Ctx = createContext<AreaCtx | null>(null);

export function useArea(): AreaCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error('useArea must be used inside <AreaProvider>');
  return c;
}

export function parseArea(raw: string | null): PickedArea | null {
  if (!raw) return null;
  try {
    const v = JSON.parse(raw) as Partial<PickedArea>;
    return typeof v.area_id === 'string' && v.area_id && typeof v.name === 'string' && v.name
      ? { area_id: v.area_id, name: v.name }
      : null;
  } catch {
    return null;
  }
}

export function AreaProvider({ children }: { children: ReactNode }) {
  const [area, setAreaState] = useState<PickedArea | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let live = true;
    SecureStore.getItemAsync(KEY)
      .then((raw) => live && setAreaState(parseArea(raw)))
      .catch(() => {})
      .finally(() => live && setReady(true));
    return () => {
      live = false;
    };
  }, []);

  const setArea = useCallback((a: PickedArea) => {
    setAreaState(a);
    SecureStore.setItemAsync(KEY, JSON.stringify(a)).catch(() => {});
  }, []);

  const value = useMemo(() => ({ area, ready, setArea }), [area, ready, setArea]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
