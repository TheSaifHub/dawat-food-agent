// The one cart the whole app shares. Ported from frontend_old/src/lib/cart.tsx for native.
//
// The backend owns the cart and every number in it. This file never computes a price, a fee, a tax or a total: it
// shows the cart the backend sends back after every change. The only arithmetic is counting items (the tab badge).
// Request bodies carry ids and a quantity only: never a price, a user id or a "source" (the backend takes the user
// from the token). Writes are sent one at a time, in tap order, so a late answer can never replace a newer cart.
// Signing out (or another user signing in) empties this cart at once: one user's cart is never shown to another.
//
// The tools' own `message` fields are written for Dawat AI, so each status is mapped to the app's own words (sayWhy).

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { type ApiResult } from './api';
import { useSession } from './session';

export type CartLine = {
  item_id: string;
  name: string;
  price: number;
  qty: number;
  line_total: number;
  is_veg: boolean;
  spice_level: number;
  serves: number;
};
export type CartBranch = {
  branch_id: string;
  restaurant: string;
  branch_label: string;
  branch_area: string;
  items: CartLine[];
  items_total: number;
  distance_km?: number;
  delivery_fee?: number;
  free_delivery?: boolean;
  add_for_free_delivery?: number;
  gst_food?: number;
  gst_delivery?: number;
  taxes?: number;
  total?: number;
};
export type Unavailable = CartLine & {
  branch_id: string;
  restaurant: string;
  reason: 'branch_closed' | 'unavailable' | 'too_far';
  distance_km?: number;
  max_km?: number;
};
export type Cart = {
  status: 'ok' | 'empty' | 'needs_delivery_area';
  cart_id: string | null;
  cart_status?: 'open' | 'confirmed';
  delivery: { area_id: string; area: string; address_id: string | null; address_label: string | null } | null;
  branches: CartBranch[];
  unavailable?: Unavailable[];
  items_total?: number;
  delivery_total?: number;
  taxes_total?: number;
  grand_total: number | null;
  can_confirm?: boolean;
  quote_id?: string;
  confirmed_total?: number;
};

export type Outcome = { ok: true; message: string; qty?: number } | { ok: false; message: string };

type ToolAnswer = { status: string; cart?: Cart; [k: string]: unknown };

const FAILED = "That didn't work. Please try again.";

/** The app's words for each answer (never the tool's message, which is written for Dawat AI). */
export function sayWhy(result: ApiResult<ToolAnswer>, name?: string): string {
  if (!result.ok && result.kind !== 'http') return result.message; // offline, timeout
  const body = (result.data ?? {}) as ToolAnswer;
  switch (body.status) {
    case 'too_far':
      return `This restaurant is ${body.distance_km} km from your delivery point, beyond Dawat's ${body.max_km} km range.`;
    case 'item_unavailable':
      return `${name ?? 'That dish'} isn't available right now.`;
    case 'branch_unavailable':
      return "This branch isn't taking orders right now.";
    case 'qty_limit':
      return `At most ${body.max_qty} of one dish per order.`;
    case 'not_in_cart':
      return 'That dish is no longer in your cart.';
    case 'stale_quote':
    case 'quote_changed':
      return 'Something in your cart changed (a price, an item or a fee). Please check the new total and confirm again.';
    case 'cannot_confirm':
      return "Your cart can't be ordered yet. Remove the items marked unavailable, or change where to deliver.";
    case 'unknown_address':
      return "That address isn't one of yours.";
    case 'unknown_area':
    case 'confirm_area':
    case 'needs_area':
      return 'Please choose an area from the list.';
    case 'outside_coverage':
      return "Dawat doesn't deliver there yet.";
    default:
      return result.ok ? FAILED : result.status === 401 ? 'Please sign in again.' : FAILED;
  }
}

/** How many of this dish from this branch are in the cart (0 if none). Branch-aware: one dish id can be in two branches. */
export function qtyInCart(cart: Cart | null, itemId: string, branchId: string): number {
  const b = cart?.branches.find((x) => x.branch_id === branchId);
  return b?.items.find((i) => i.item_id === itemId)?.qty ?? 0;
}

/** Items in the cart, counted (not priced). */
export function countItems(cart: Cart | null): number {
  return (
    (cart?.branches ?? []).reduce((n, b) => n + b.items.reduce((m, i) => m + i.qty, 0), 0) +
    (cart?.unavailable ?? []).reduce((n, i) => n + i.qty, 0)
  );
}

export type BrowseArea = { area_id: string; name: string };

export type ConfirmOutcome = { ok: true; confirmedTotal: number | null } | { ok: false; message: string };

type CartContext = {
  cart: Cart | null;
  /** True until the first load finishes. */
  loading: boolean;
  /** Set when the last load failed, so the cart screen can say so instead of showing an empty cart. */
  loadError: string | null;
  refresh: () => Promise<void>;
  /** `browseArea` is the area the user is browsing: a cart that is empty (or has no delivery point) delivers there. */
  add: (itemId: string, branchId: string, name: string, browseArea?: BrowseArea | null) => Promise<Outcome>;
  remove: (itemId: string, branchId: string, qty?: number) => Promise<Outcome>;
  setDelivery: (to: { area: string } | { address_id: string }) => Promise<Outcome>;
  /** The user's "yes" on the review screen: confirms exactly the quote on screen. Creates no order and takes no payment. */
  confirm: () => Promise<ConfirmOutcome>;
  itemCount: number;
};

const Ctx = createContext<CartContext | null>(null);

export function CartProvider({ children }: { children: ReactNode }) {
  const { state, request } = useSession();
  const userId = state.status === 'signedIn' ? state.me.user_id : null;
  const [cart, setCart] = useState<Cart | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const cartRef = useRef<Cart | null>(null);
  const owner = useRef<string | null>(null); // whose cart is in state
  const queue = useRef<Promise<unknown>>(Promise.resolve());

  const put = useCallback((c: Cart | null) => {
    cartRef.current = c;
    setCart(c);
  }, []);

  // A different user, or nobody: drop the cart immediately.
  useEffect(() => {
    if (owner.current !== userId) {
      owner.current = userId;
      put(null);
      setLoadError(null);
      setLoading(userId !== null);
    }
  }, [userId, put]);

  /** One write at a time, in the order the user tapped. */
  const serial = useCallback(<T,>(fn: () => Promise<T>): Promise<T> => {
    const run = queue.current.then(fn, fn);
    queue.current = run.catch(() => undefined);
    return run;
  }, []);

  const call = useCallback(
    async (path: string, init: { method?: 'GET' | 'POST' | 'PUT' | 'DELETE'; body?: unknown } = {}) => {
      const mine = owner.current;
      const res = await request<ToolAnswer>(path, init);
      const body = res.ok || res.kind === 'http' ? (res.data as ToolAnswer | null) : null;
      // Every write answer carries the fresh cart; ignore it if the user changed while it was in flight.
      if (body?.cart && owner.current === mine && mine !== null) put(body.cart);
      return res;
    },
    [request, put],
  );

  const refresh = useCallback(async () => {
    if (!userId) return;
    const mine = owner.current;
    const res = await serial(() => request<Cart>('/cart'));
    if (owner.current !== mine) return;
    if (res.ok) {
      put(res.data);
      setLoadError(null);
    } else if (res.kind !== 'http' || res.status !== 401) {
      setLoadError(res.message);
    }
    setLoading(false);
  }, [userId, request, put, serial]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- load once per signed-in user (refresh sets the loading state)
    if (userId) void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load once per signed-in user
  }, [userId]);

  const add = useCallback(
    (itemId: string, branchId: string, name: string, browseArea?: BrowseArea | null): Promise<Outcome> =>
      serial(async () => {
        const wasEmpty = countItems(cartRef.current) === 0;
        let areaFailed = false;
        // The first dish in a cart delivers to the area being browsed, not to whatever the backend would default to
        // (a saved address or area). This has to happen BEFORE the dish is added: the backend refuses a dish whose
        // restaurant is beyond its range from the cart's delivery point. A cart that already has dishes keeps its
        // delivery point: the screens say so when it differs from the browsed area.
        if (browseArea && wasEmpty && cartRef.current?.delivery?.area_id !== browseArea.area_id) {
          const set = await call('/cart/delivery', { method: 'PUT', body: { area: browseArea.name } });
          areaFailed = !set.ok;
        }
        const res = await call('/cart/items', { method: 'POST', body: { item_id: itemId, branch_id: branchId, qty: 1 } });
        if (!res.ok) {
          if (res.kind === 'http' && [404, 409, 422].includes(res.status)) void refresh();
          return { ok: false, message: sayWhy(res, name) } as Outcome;
        }
        // A cart with dishes but no delivery point at all (it could not be set above) gets the browsed area now.
        const there = (res.data as ToolAnswer).cart?.delivery;
        if (browseArea && !there) {
          const set = await call('/cart/delivery', { method: 'PUT', body: { area: browseArea.name } });
          areaFailed = areaFailed || !set.ok;
        }
        if (areaFailed) return { ok: true, message: `Added ${name}, but we could not set delivery to ${browseArea?.name}. Check the cart.` } as Outcome;
        const qty = qtyInCart(cartRef.current, itemId, branchId);
        return { ok: true, message: qty > 1 ? `Added ${name} (${qty} in cart).` : `Added ${name} to your cart.`, qty } as Outcome;
      }),
    [call, refresh, serial],
  );

  const remove = useCallback(
    (itemId: string, branchId: string, qty?: number): Promise<Outcome> =>
      serial(async () => {
        const q = [`branch_id=${encodeURIComponent(branchId)}`];
        if (qty !== undefined) q.push(`qty=${qty}`);
        const res = await call(`/cart/items/${encodeURIComponent(itemId)}?${q.join('&')}`, { method: 'DELETE' });
        if (res.ok) {
          return { ok: true, message: qty ? 'Removed one.' : 'Removed from your cart.', qty: qtyInCart(cartRef.current, itemId, branchId) } as Outcome;
        }
        if (res.kind === 'http' && [404, 409, 422].includes(res.status)) void refresh();
        return { ok: false, message: sayWhy(res) } as Outcome;
      }),
    [call, refresh, serial],
  );

  const setDelivery = useCallback(
    (to: { area: string } | { address_id: string }): Promise<Outcome> =>
      serial(async () => {
        const res = await call('/cart/delivery', { method: 'PUT', body: to });
        return res.ok ? ({ ok: true, message: 'Delivery point updated.' } as Outcome) : ({ ok: false, message: sayWhy(res) } as Outcome);
      }),
    [call, serial],
  );

  const confirm = useCallback(
    (): Promise<ConfirmOutcome> =>
      serial(async () => {
        const c = cartRef.current; // the cart on screen right now
        if (!c || !c.cart_id || !c.quote_id || c.can_confirm === false || c.grand_total === null) {
          return { ok: false, message: "Your cart can't be ordered yet." } as ConfirmOutcome;
        }
        const res = await call('/cart/confirm', { method: 'POST', body: { cart_id: c.cart_id, quote_id: c.quote_id } });
        if (!res.ok) {
          void refresh(); // show the new bill, so the user can read it and decide again
          return { ok: false, message: sayWhy(res) } as ConfirmOutcome;
        }
        return { ok: true, confirmedTotal: cartRef.current?.confirmed_total ?? cartRef.current?.grand_total ?? null } as ConfirmOutcome;
      }),
    [call, refresh, serial],
  );

  const itemCount = useMemo(() => countItems(cart), [cart]);
  const value = useMemo(
    () => ({ cart, loading, loadError, refresh, add, remove, setDelivery, confirm, itemCount }),
    [cart, loading, loadError, refresh, add, remove, setDelivery, confirm, itemCount],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useCart(): CartContext {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useCart must be used inside <CartProvider>');
  return ctx;
}
