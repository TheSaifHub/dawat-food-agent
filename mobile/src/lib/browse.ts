// Browsing data from the public routes (no sign-in): GET /areas, /areas/{id}/home, /areas/{id}/restaurants.
// Every number shown (distance, delivery fee, typical price) comes from the backend as is. The app computes no price.

import { useCallback, useEffect, useState } from 'react';
import { api } from './api';

export type Area = { area_id: string; name: string; name_te: string | null };

export type Branch = { branch_id: string; label: string; area: string; street: string | null; distance_km: number };

export type RestaurantCardData = {
  restaurant_id: string;
  name: string;
  cuisines: string[];
  veg_only: boolean;
  is_chain: boolean;
  branch: Branch;
  more_branches_in_range: number;
  delivery_fee: number;
  /** Median price of the restaurant's single-serving mains. Null when there is none. */
  price_for_one: number | null;
  mild_mains: number;
  mild_friendly: boolean;
};

export type CuisineCount = { cuisine: string; restaurants: number };

export type HomeData = {
  area: { area_id: string; name: string };
  restaurants_in_range: number;
  cuisines: CuisineCount[];
  chains: RestaurantCardData[];
};

export type Sort = 'distance' | 'price' | 'name';

export type ListData = {
  total: number;
  offset: number;
  restaurants: RestaurantCardData[];
  cuisine_facets: CuisineCount[];
  free_delivery_from: number;
  max_delivery_km: number;
};

export type Filters = { cuisine: string | null; vegOnly: boolean; mild: boolean; sort: Sort };

export const PAGE_SIZE = 20;

export function listPath(areaId: string, f: Filters, offset: number): string {
  const q = [`limit=${PAGE_SIZE}`, `offset=${offset}`, `sort=${f.sort}`];
  if (f.cuisine) q.push(`cuisine=${encodeURIComponent(f.cuisine)}`);
  if (f.vegOnly) q.push('veg_only=true');
  if (f.mild) q.push('mild=true');
  return `/areas/${encodeURIComponent(areaId)}/restaurants?${q.join('&')}`;
}

export function homePath(areaId: string): string {
  return `/areas/${encodeURIComponent(areaId)}/home`;
}

/** "Waking up Dawat AI…" is shown while a request is still running after 4 s (the free backend sleeps). */
export type Load<T> =
  | { status: 'loading'; slow: boolean }
  | { status: 'error'; message: string }
  | { status: 'ok'; data: T };

/** One public GET. `path` null means "nothing to load yet". `reload()` tries again. */
export function useLoad<T extends { status?: string }>(path: string | null): Load<T> & { reload: () => void } {
  const [state, setState] = useState<Load<T>>({ status: 'loading', slow: false });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (path === null) return;
    const ctl = new AbortController();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- starts the loading state for a fetch that this effect runs
    setState({ status: 'loading', slow: false });
    api<T>(path, {
      signal: ctl.signal,
      onSlow: () => setState((s) => (s.status === 'loading' ? { status: 'loading', slow: true } : s)),
    }).then((r) => {
      if (ctl.signal.aborted) return;
      if (!r.ok) return setState({ status: 'error', message: r.message });
      // The browse routes answer 200 with {status: 'ok'} or a status such as unknown_area / invalid.
      if (r.data && r.data.status && r.data.status !== 'ok') {
        const m = (r.data as { message?: unknown }).message;
        return setState({ status: 'error', message: typeof m === 'string' ? m : "That didn't work. Please try again." });
      }
      setState({ status: 'ok', data: r.data });
    });
    return () => ctl.abort();
  }, [path, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload };
}
