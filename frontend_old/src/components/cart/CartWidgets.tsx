"use client";

// Small cart pieces used across pages (Phase 7e): the header link with its count, the bar at the bottom of browsing
// pages, and the Add / − qty + control on menu rows. They only show what the backend's cart says.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

import { qtyInCart, useCart } from "@/lib/cart";

export function CartLink() {
  const { itemCount } = useCart();
  return (
    <Link href="/cart" className="inline-flex h-10 items-center gap-1.5 rounded-md px-2 sm:px-3 text-ivory underline-offset-4 hover:underline focus-visible:outline-gold">
      Cart
      {itemCount > 0 ? (
        <span className="rounded-full bg-gold px-2 text-sm font-semibold text-night">
          {itemCount}<span className="sr-only"> {itemCount === 1 ? "item" : "items"}</span>
        </span>
      ) : null}
    </Link>
  );
}

/** "3 items · ₹540 · View cart", pinned to the bottom of browsing pages once something is in the cart. */
export function CartBar() {
  const { cart, itemCount } = useCart();
  const pathname = usePathname();
  const shown = !!cart && itemCount > 0 && pathname !== "/cart" && pathname !== "/login";
  const bar = useRef<HTMLDivElement>(null);
  // The bar's height goes into --cartbar-h: the page's scroll padding keeps keyboard focus above it (WCAG 2.4.11,
  // globals.css), and the Dawat AI launcher and panel sit just above it instead of covering "View cart".
  useEffect(() => {
    const el = bar.current;
    if (!shown || !el) return;
    const root = document.documentElement;
    const update = () => root.style.setProperty("--cartbar-h", `${el.offsetHeight}px`);
    update();
    const watch = new ResizeObserver(update);
    watch.observe(el);
    return () => { watch.disconnect(); root.style.removeProperty("--cartbar-h"); };
  }, [shown]);
  if (!shown) return null;
  const total = cart.grand_total;
  return (
    <div ref={bar} className="sticky bottom-0 z-20 border-t border-gold/60 bg-plum text-ivory">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
        <p>
          <strong>{itemCount}</strong> {itemCount === 1 ? "item" : "items"}
          {total !== null ? <> · total <strong>₹{total}</strong></> : null}
          {cart.branches.length > 1 ? <> from {cart.branches.length} restaurants</> : null}
        </p>
        <Link href="/cart" className="inline-flex h-11 items-center rounded-lg bg-ivory px-5 font-semibold text-plum focus-visible:outline-gold">
          View cart
        </Link>
      </div>
    </div>
  );
}

/** Add, or − qty + once the dish is in the cart. `onResult` shows the outcome in the page's status line. */
export function AddControl({ itemId, branchId, name, browseArea, disabled, onResult }: {
  itemId: string;
  branchId: string;
  name: string;
  browseArea: string | null;
  disabled?: boolean;
  onResult: (message: string, ok: boolean, signIn?: boolean) => void;
}) {
  const { cart, add, remove } = useCart();
  const qty = qtyInCart(cart, itemId, branchId);
  const base = "inline-flex h-10 items-center justify-center rounded-lg border font-semibold focus-visible:outline-2";
  // Add and the −/qty/+ group replace each other, which would drop keyboard focus on the page body. Remember which
  // control should take focus once the cart answers, and move it there when the swap renders.
  const addRef = useRef<HTMLButtonElement>(null);
  const plusRef = useRef<HTMLButtonElement>(null);
  const focusNext = useRef<"add" | "plus" | null>(null);
  useEffect(() => {
    if (focusNext.current === "plus" && qty > 0) plusRef.current?.focus();
    else if (focusNext.current === "add" && qty === 0) addRef.current?.focus();
    else return;
    focusNext.current = null;
  }, [qty]);

  async function plus() {
    if (qty === 0) focusNext.current = "plus";
    const r = await add(itemId, branchId, name, browseArea);
    if (!r.ok) focusNext.current = null;
    onResult(r.message, r.ok, r.ok ? false : r.signIn);
  }
  async function minus() {
    if (qty === 1) focusNext.current = "add";
    const r = await remove(itemId, branchId, 1);
    if (!r.ok) focusNext.current = null;
    onResult(r.ok ? (r.qty ? `Removed one ${name} (${r.qty} left).` : `Removed ${name} from your cart.`) : r.message, r.ok);
  }

  if (qty === 0) {
    return (
      <button ref={addRef} type="button" onClick={plus} aria-disabled={disabled}
              className={`${base} w-20 border-plum bg-card text-plum hover:bg-secondary focus-visible:outline-offset-2 focus-visible:outline-ring aria-disabled:opacity-50`}
              onClickCapture={(e) => { if (disabled) e.stopPropagation(); }}>
        Add<span className="sr-only"> {name}</span>
      </button>
    );
  }
  return (
    <div className="inline-flex items-center rounded-lg border border-plum bg-plum text-ivory" role="group" aria-label={`${name}, ${qty} in cart`}>
      <button type="button" onClick={minus} className={`${base} w-9 border-transparent focus-visible:-outline-offset-4 focus-visible:outline-gold`}>
        <span aria-hidden="true">−</span><span className="sr-only">Remove one {name}</span>
      </button>
      <span className="min-w-6 text-center font-semibold" aria-hidden="true">{qty}</span>
      <button ref={plusRef} type="button" onClick={plus} className={`${base} w-9 border-transparent focus-visible:-outline-offset-4 focus-visible:outline-gold`}>
        <span aria-hidden="true">+</span><span className="sr-only">Add one more {name}</span>
      </button>
    </div>
  );
}
