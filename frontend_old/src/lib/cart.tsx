"use client";

// The one cart the whole site shares (Phase 7e, D-057). The backend owns it: every change goes through the cart
// routes, and the page shows the cart the backend sends back. No price, fee or total is ever computed here. In 7f the
// Dawat AI chat changes the same backend cart, and this provider refreshes it, so the page and the chat never differ.
//
// Messages: the tools' own `message` fields are written for Dawat AI ("Tell the user…"), so the website maps each
// status to its own words below and never shows a tool message to a person.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, type ApiResult } from "@/lib/api";
import { useSession } from "@/lib/session";
import { accessToken } from "@/lib/auth";

export type CartLine = { item_id: string; name: string; price: number; qty: number; line_total: number; is_veg: boolean;
                         spice_level: number; serves: number };
export type CartBranch = {
  branch_id: string; restaurant_id: string; restaurant: string; branch_label: string; branch_area: string;
  items: CartLine[]; items_total: number; distance_km?: number; delivery_fee?: number; free_delivery?: boolean;
  add_for_free_delivery?: number; gst_food?: number; gst_delivery?: number; taxes?: number; total?: number;
};
export type Unavailable = CartLine & { branch_id: string; restaurant: string; reason: "branch_closed" | "unavailable" | "too_far";
                                      distance_km?: number; max_km?: number };
export type Cart = {
  status: "ok" | "empty" | "needs_delivery_area";
  cart_id: string | null;
  cart_status?: "open" | "confirmed";
  delivery: { area_id: string; area: string; address_id: string | null; address_label: string | null } | null;
  branches: CartBranch[];
  unavailable?: Unavailable[];
  items_total?: number;
  delivery_total?: number;
  taxes_total?: number;
  grand_total: number | null;
  can_confirm?: boolean;
  quote_id?: string;
};
export type PlacedOrder = { order_id: string; order_number: string; restaurant: string; branch_label: string; total: number };
export type Placed = { checkout_id: string; orders: PlacedOrder[]; grand_total: number };

export type Outcome = { ok: true; message: string; qty?: number } | { ok: false; message: string; signIn?: boolean };
/** `qty` is how many of that dish are left in the cart afterwards, from the cart the backend sent back. */

type ToolAnswer = { status: string; cart?: Cart; [k: string]: unknown };

const FAILED = "That didn't work. Please try again.";

/** The website's words for each answer (never the tool's message, which is written for Dawat AI). */
export function sayWhy(result: ApiResult<ToolAnswer>, name?: string): string {
  if (!result.ok && result.kind !== "http") return result.message;           // offline, timeout
  const body = (result.data ?? {}) as ToolAnswer;
  switch (body.status) {
    case "too_far":
      return `This restaurant is ${body.distance_km} km from your delivery point, beyond Dawat's ${body.max_km} km range.`;
    case "item_unavailable": return `${name ?? "That dish"} isn't available right now.`;
    case "branch_unavailable": return "This branch isn't taking orders right now.";
    case "qty_limit": return `At most ${body.max_qty} of one dish per order.`;
    case "not_in_cart": return "That dish is no longer in your cart.";
    case "stale_quote":
    case "quote_changed": return "Something in your cart changed (a price, an item or a fee). Please check the new total and confirm again.";
    case "cannot_confirm": return "Your cart can't be ordered yet. Remove the items marked unavailable, or change where to deliver.";
    case "not_confirmed": return "Please confirm your cart first.";
    case "unknown_address": return "That address isn't one of yours.";
    case "unknown_area":
    case "confirm_area":
    case "needs_area": return "Please choose an area from the list.";
    case "outside_coverage": return "Dawat doesn't deliver there yet.";
    default: return result.status === 401 ? "Please sign in again." : FAILED;
  }
}

type CartContext = {
  cart: Cart | null;
  /** True until the first load finishes (signed in) or we know there's no user. */
  loading: boolean;
  refresh: () => Promise<void>;
  add: (itemId: string, branchId: string, name: string, browseArea?: string | null) => Promise<Outcome>;
  remove: (itemId: string, branchId: string, qty?: number) => Promise<Outcome>;
  setDelivery: (to: { area: string } | { address_id: string }) => Promise<Outcome>;
  placeOrder: () => Promise<{ ok: true; placed: Placed } | { ok: false; message: string }>;
  itemCount: number;
};

const Ctx = createContext<CartContext | null>(null);

export function CartProvider({ children }: { children: React.ReactNode }) {
  const { session } = useSession();
  const signedIn = session.state === "signed_in";
  const [cart, setCart] = useState<Cart | null>(null);
  const [loading, setLoading] = useState(true);

  const call = useCallback(async (path: string, init: Parameters<typeof api>[1] = {}) => {
    const res = await api<ToolAnswer>(path, { ...init, token: await accessToken() });
    const body = (res.ok || res.kind === "http") ? (res.data as ToolAnswer | null) : null;
    if (body?.cart) setCart(body.cart);                       // every write answer carries the fresh cart
    return res;
  }, []);

  const refresh = useCallback(async () => {
    if (!signedIn) {
      setCart(null);
      setLoading(session.state === "loading");
      return;
    }
    const res = await api<Cart>("/cart", { token: await accessToken() });
    if (res.ok) setCart(res.data);
    setLoading(false);
  }, [signedIn, session.state]);

  useEffect(() => {
    queueMicrotask(() => void refresh());
    // The chat (7f) or another tab may change the same cart: look again when the visitor comes back to this tab.
    const onFocus = () => void refresh();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refresh]);

  const add = useCallback(async (itemId: string, branchId: string, name: string, browseArea?: string | null): Promise<Outcome> => {
    if (!signedIn) return { ok: false, message: "Sign in to add dishes to your cart.", signIn: true };
    const res = await call("/cart/items", { method: "POST", body: { item_id: itemId, branch_id: branchId, qty: 1 } });
    if (!res.ok) {
      if (res.status === 409 || res.status === 404 || res.status === 422) void refresh();
      return { ok: false, message: sayWhy(res, name) };
    }
    // A new cart takes the backend's default (the saved address, else the saved area). With neither, it delivers
    // to the area being browsed, as the chat does with the area the user names (D-042). An existing point is kept.
    if (!(res.data as ToolAnswer).cart?.delivery && browseArea) {
      await call("/cart/delivery", { method: "PUT", body: { area: browseArea } });
    }
    const qty = qtyInCart((res.data as ToolAnswer).cart ?? null, itemId, branchId);
    // The count makes each message different, so a second "Added…" is read out too.
    return { ok: true, message: qty > 1 ? `Added ${name} (${qty} in cart).` : `Added ${name} to your cart.`, qty };
  }, [signedIn, call, refresh]);

  const remove = useCallback(async (itemId: string, branchId: string, qty?: number): Promise<Outcome> => {
    const res = await call(`/cart/items/${encodeURIComponent(itemId)}`, { method: "DELETE", query: { branch_id: branchId, qty } });
    if (res.ok) return { ok: true, message: qty ? "Removed one." : "Removed from your cart.",
                         qty: qtyInCart((res.data as ToolAnswer).cart ?? null, itemId, branchId) };
    return { ok: false, message: sayWhy(res) };
  }, [call]);

  const setDelivery = useCallback(async (to: { area: string } | { address_id: string }): Promise<Outcome> => {
    const res = await call("/cart/delivery", { method: "PUT", body: to });
    if (res.ok) return { ok: true, message: "Delivery point updated." };
    return { ok: false, message: sayWhy(res) };
  }, [call]);

  /** The website's Confirm button is the user's yes (D-026): confirm exactly the quote on screen, then place it. */
  const placeOrder = useCallback(async () => {
    if (!cart?.cart_id || !cart.quote_id) return { ok: false as const, message: "Your cart can't be ordered yet." };
    const confirmed = await call("/cart/confirm", { method: "POST", body: { cart_id: cart.cart_id, quote_id: cart.quote_id } });
    if (!confirmed.ok) return { ok: false as const, message: sayWhy(confirmed) };
    const placed = await call("/orders", { method: "POST", body: { cart_id: cart.cart_id } });
    if (!placed.ok) {
      void refresh();
      return { ok: false as const, message: sayWhy(placed) };
    }
    void refresh();
    return { ok: true as const, placed: placed.data as unknown as Placed };
  }, [cart, call, refresh]);

  const itemCount = useMemo(
    () => (cart?.branches ?? []).reduce((n, b) => n + b.items.reduce((m, i) => m + i.qty, 0), 0)
      + (cart?.unavailable ?? []).reduce((n, i) => n + i.qty, 0),
    [cart],
  );

  const value = useMemo(() => ({ cart, loading, refresh, add, remove, setDelivery, placeOrder, itemCount }),
    [cart, loading, refresh, add, remove, setDelivery, placeOrder, itemCount]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useCart(): CartContext {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useCart must be used inside <CartProvider>");
  return ctx;
}

/** How many of this dish from this branch are in the cart (0 if none). */
export function qtyInCart(cart: Cart | null, itemId: string, branchId: string): number {
  const b = cart?.branches.find((x) => x.branch_id === branchId);
  return b?.items.find((i) => i.item_id === itemId)?.qty ?? 0;
}
