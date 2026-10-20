"use client";

// The cart and checkout (Phase 7e, D-057). Everything on this page is the backend's cart: the lines, each
// restaurant's delivery fee and GST, the totals, and what can't be ordered right now. Pressing "Place order" is the
// user's yes for exactly the total on screen (D-026): the page confirms that quote and places it; if anything changed
// since (a price, a fee), the backend refuses and the page shows the new cart to confirm again.

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";

import { AreaPicker } from "@/components/browse/AreaPicker";
import { Announcer, Loading } from "@/components/common/Loading";
import { DietMark } from "@/components/restaurant/RestaurantView";
import { api } from "@/lib/api";
import { useCart, type Cart, type CartBranch, type Placed, type Unavailable } from "@/lib/cart";
import { restaurantHref } from "@/lib/catalog";
import { orderHref } from "@/lib/orders";
import { useSession } from "@/lib/session";
import { accessToken } from "@/lib/auth";

type Address = { address_id: string; label: string; line1: string; area_id: string; area: string; is_default: boolean };

const REASONS: Record<Unavailable["reason"], string> = {
  branch_closed: "This branch isn't taking orders now.",
  unavailable: "Not available right now.",
  too_far: "Too far from your delivery point.",
};

export function CartView() {
  const { session } = useSession();
  const { cart, loading, remove, add, setDelivery, placeOrder } = useCart();
  const [note, setNote] = useState<{ text: string; ok: boolean; seq: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [placed, setPlaced] = useState<Placed | null>(null);
  // When a line leaves the cart (Remove, or − on the last one), its buttons go with it and focus would fall to the
  // page body. This names the heading to move focus to once the new cart renders.
  const refocus = useRef<string | null>(null);

  function report(text: string, ok: boolean) {
    setNote((n) => ({ text, ok, seq: (n?.seq ?? 0) + 1 }));
  }

  useEffect(() => {
    const id = refocus.current;
    if (!id) return;
    refocus.current = null;
    if (document.activeElement && document.activeElement !== document.body) return;   // focus wasn't lost
    (document.getElementById(id) ?? document.getElementById("total-heading") ?? document.getElementById("cart-empty"))?.focus();
  }, [cart]);

  const waiting = session.state === "loading" || (session.state === "signed_in" && loading);
  const signedIn = session.state === "signed_in";
  const empty = !cart || (cart.branches.length === 0 && !(cart.unavailable?.length));
  const announcement = waiting ? "Loading your cart…" : !signedIn ? ""
    : placed ? `Order placed. Total ₹${placed.grand_total}.` : note?.text ?? (empty ? "Your cart is empty" : "");

  async function onPlace() {
    setBusy(true);
    const r = await placeOrder();
    setBusy(false);
    if (r.ok) setPlaced(r.placed);
    else report(r.message, false);
  }

  // One Announcer stays mounted whatever the page shows, so every outcome is a change to the same live region
  // (a region that arrives already filled is often not read out).
  return (
    <>
      <Announcer text={announcement} seq={note?.seq} />
      {waiting ? <Loading what="your cart" slow={false} />
        : !signedIn ? (
          <div className="flex flex-col items-start gap-3">
            <p>Sign in to see your cart and order.</p>
            <Link href="/login" className="inline-flex h-11 items-center rounded-lg bg-plum px-5 font-semibold text-ivory focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">Sign in</Link>
          </div>
        )
        : placed ? <PlacedPanel placed={placed} />
        : (
          <div className="flex flex-col gap-8">
            {note ? (
              <p className={`rounded-lg px-4 py-2 ${note.ok ? "bg-secondary text-secondary-foreground" : "border border-destructive text-destructive"}`}>{note.text}</p>
            ) : null}

            {empty ? (
              <div className="flex flex-col items-start gap-3">
                <p id="cart-empty" tabIndex={-1} className="focus:outline-none">Your cart is empty.</p>
                <Link href="/restaurants" className="inline-block py-1 text-plum underline underline-offset-2">Browse restaurants</Link>
              </div>
            ) : (
              <>
                <DeliveryChooser cart={cart!} onChange={async (to) => { const r = await setDelivery(to); report(r.message, r.ok); }} />

                {cart!.unavailable?.length ? (
                  <section aria-labelledby="unavailable-heading" className="flex flex-col gap-3 rounded-xl border border-destructive p-4">
                    <h2 id="unavailable-heading" tabIndex={-1} className="font-sans text-lg font-semibold text-destructive focus:outline-none">Can&apos;t be ordered right now</h2>
                    <ul className="flex flex-col gap-2">
                      {cart!.unavailable.map((u) => (
                        <li key={`${u.branch_id}-${u.item_id}`} className="flex flex-wrap items-center justify-between gap-2">
                          <span>{u.qty} × {u.name}, {u.restaurant}: {u.reason === "too_far" && u.distance_km
                            ? `${u.distance_km} km away, beyond Dawat's ${u.max_km} km range.` : REASONS[u.reason]}</span>
                          <button type="button" className="inline-block py-1 text-plum underline underline-offset-2"
                                  onClick={async () => {
                                    refocus.current = "unavailable-heading";
                                    const r = await remove(u.item_id, u.branch_id);
                                    report(r.ok ? `Removed ${u.name}.` : r.message, r.ok);
                                  }}>
                            Remove<span className="sr-only"> {u.name}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </section>
                ) : null}

                {cart!.branches.map((b) => (
                  <BranchBill key={b.branch_id} branch={b}
                              onMinus={async (id, name) => {
                                refocus.current = `bill-${b.branch_id}`;
                                const r = await remove(id, b.branch_id, 1);
                                report(r.ok ? (r.qty ? `Removed one ${name} (${r.qty} left).` : `Removed ${name} from your cart.`) : r.message, r.ok);
                              }}
                              onPlus={async (id, name) => { const r = await add(id, b.branch_id, name); report(r.message, r.ok); }}
                              onRemove={async (id, name) => {
                                refocus.current = `bill-${b.branch_id}`;
                                const r = await remove(id, b.branch_id);
                                report(r.ok ? `Removed ${name}.` : r.message, r.ok);
                              }} />
                ))}

                <section aria-labelledby="total-heading" className="flex flex-col gap-3 rounded-xl border border-border bg-card p-5">
                  <h2 id="total-heading" tabIndex={-1} className="font-display text-2xl font-semibold focus:outline-none">Total</h2>
                  {cart!.grand_total === null ? (
                    <p>Choose where to deliver to see the delivery fees and your total.</p>
                  ) : (
                    <>
                      <dl className="grid grid-cols-[1fr_auto] gap-y-1">
                        <dt>Food</dt><dd className="text-right">₹{cart!.items_total}</dd>
                        <dt>Delivery</dt><dd className="text-right">₹{cart!.delivery_total}</dd>
                        <dt>GST</dt><dd className="text-right">₹{cart!.taxes_total}</dd>
                        <dt className="pt-2 text-lg font-semibold">To pay</dt><dd className="pt-2 text-right text-lg font-semibold">₹{cart!.grand_total}</dd>
                      </dl>
                      {cart!.branches.length > 1 ? (
                        <p className="text-sm text-muted-foreground">Each restaurant is its own order, with its own delivery fee and GST.</p>
                      ) : null}
                      <button type="button" onClick={onPlace} aria-disabled={busy || !cart!.can_confirm}
                              onClickCapture={(e) => { if (busy || !cart!.can_confirm) e.stopPropagation(); }}
                              className="inline-flex h-12 items-center justify-center rounded-lg bg-plum px-6 text-lg font-semibold text-ivory focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring aria-disabled:opacity-60">
                        {busy ? "Placing your order…" : `Place order · ₹${cart!.grand_total}`}
                      </button>
                      {!cart!.can_confirm ? (
                        <p className="text-sm text-destructive">Remove the items that can&apos;t be ordered first.</p>
                      ) : null}
                      <p className="text-sm text-muted-foreground">
                        This is a demo: the order is simulated, and payment stays pending until test payments are added.
                      </p>
                    </>
                  )}
                </section>
              </>
            )}
          </div>
        )}
    </>
  );
}

function DeliveryChooser({ cart, onChange }: { cart: Cart; onChange: (to: { area: string } | { address_id: string }) => void }) {
  const [addresses, setAddresses] = useState<Address[] | null>(null);
  const groupId = useId();

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const res = await api<{ addresses: Address[] }>("/me/addresses", { token: await accessToken() });
      if (!cancelled) setAddresses(res.ok ? res.data.addresses : []);
    })();
    return () => { cancelled = true; };
  }, []);

  const d = cart.delivery;
  return (
    <section aria-labelledby="deliver-heading" className="flex flex-col gap-3 rounded-xl border border-border bg-card p-5">
      <h2 id="deliver-heading" className="font-display text-2xl font-semibold">Deliver to</h2>
      <p>
        {d ? <>Now: <strong>{d.address_label ?? d.area}</strong>{d.address_label ? `, ${d.area}` : " (area centre)"}</>
           : "Choose where to deliver: fees depend on the distance."}
      </p>
      {addresses?.length ? (
        <fieldset className="flex flex-col gap-2" aria-describedby={groupId}>
          <legend className="text-sm font-medium">Your saved addresses</legend>
          <p id={groupId} className="sr-only">Choosing one updates the delivery fees.</p>
          {addresses.map((a) => (
            <label key={a.address_id} className="flex items-start gap-2">
              <input type="radio" name="address" className="mt-1.5 size-4 shrink-0 accent-plum" checked={d?.address_id === a.address_id}
                     onChange={() => onChange({ address_id: a.address_id })} />
              <span><strong>{a.label}</strong>: {a.line1}, {a.area}</span>
            </label>
          ))}
        </fieldset>
      ) : null}
      <AreaPicker value={d && !d.address_id ? d.area_id : ""} label={addresses?.length ? "Or an area" : "Area"}
                  onChange={(areaId) => onChange({ area: areaId })} />
    </section>
  );
}

function BranchBill({ branch: b, onMinus, onPlus, onRemove }: {
  branch: CartBranch;
  onMinus: (itemId: string, name: string) => void;
  onPlus: (itemId: string, name: string) => void;
  onRemove: (itemId: string, name: string) => void;
}) {
  const step = "inline-flex size-9 items-center justify-center rounded-md border border-input bg-card font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";
  return (
    <section aria-labelledby={`bill-${b.branch_id}`} className="flex flex-col gap-3 rounded-xl border border-border bg-card p-5">
      <h2 id={`bill-${b.branch_id}`} tabIndex={-1} className="font-display text-2xl font-semibold focus:outline-none">
        <Link href={restaurantHref(b.branch_id)} className="underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">{b.restaurant}</Link>
        <span className="ml-2 font-sans text-base font-normal text-muted-foreground">{b.branch_label}</span>
      </h2>
      <ul className="divide-y divide-border">
        {b.items.map((i) => (
          <li key={i.item_id} className="flex flex-wrap items-center justify-between gap-3 py-2">
            <span className="flex items-center gap-2"><DietMark isVeg={i.is_veg} />{i.name} <span className="text-muted-foreground">₹{i.price}</span></span>
            <span className="flex items-center gap-2">
              <span role="group" aria-label={`${i.name}, ${i.qty} in cart`} className="inline-flex items-center gap-1">
                <button type="button" className={step} onClick={() => onMinus(i.item_id, i.name)}>
                  <span aria-hidden="true">−</span><span className="sr-only">Remove one {i.name}</span>
                </button>
                <span className="min-w-6 text-center" aria-hidden="true">{i.qty}</span>
                <button type="button" className={step} onClick={() => onPlus(i.item_id, i.name)}>
                  <span aria-hidden="true">+</span><span className="sr-only">Add one more {i.name}</span>
                </button>
              </span>
              <span className="w-16 text-right font-medium">₹{i.line_total}</span>
              <button type="button" className="inline-block py-1 text-sm text-plum underline underline-offset-2" onClick={() => onRemove(i.item_id, i.name)}>
                Remove<span className="sr-only"> {i.name}</span>
              </button>
            </span>
          </li>
        ))}
      </ul>
      {b.total !== undefined ? (
        <dl className="grid grid-cols-[1fr_auto] gap-y-1 border-t border-border pt-3 text-sm">
          <dt>Food</dt><dd className="text-right">₹{b.items_total}</dd>
          <dt>Delivery ({b.distance_km} km)</dt><dd className="text-right">{b.free_delivery ? "Free" : `₹${b.delivery_fee}`}</dd>
          <dt>GST on food (5%)</dt><dd className="text-right">₹{b.gst_food}</dd>
          {b.gst_delivery ? <><dt>GST on delivery (18%)</dt><dd className="text-right">₹{b.gst_delivery}</dd></> : null}
          <dt className="font-semibold">This order</dt><dd className="text-right font-semibold">₹{b.total}</dd>
        </dl>
      ) : null}
      {b.add_for_free_delivery ? (
        <p className="text-sm text-muted-foreground">Add ₹{b.add_for_free_delivery} more from here for free delivery.</p>
      ) : null}
    </section>
  );
}

function PlacedPanel({ placed }: { placed: Placed }) {
  // The Place order button is gone once this shows: move focus to the result instead of leaving it on the page body.
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus(); }, []);
  return (
    <section aria-labelledby="placed-heading" className="flex flex-col gap-4 rounded-xl border-2 border-plum bg-card p-6">
      <h2 id="placed-heading" ref={heading} tabIndex={-1} className="font-display text-3xl font-semibold text-plum focus:outline-none">Order placed</h2>
      <ul className="flex flex-col gap-2">
        {placed.orders.map((o) => (
          <li key={o.order_id}>
            <Link href={orderHref(o.order_number)} className="font-semibold text-plum underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
              #{o.order_number}<span className="sr-only">, track this order</span>
            </Link> · {o.restaurant}, {o.branch_label} · ₹{o.total}
          </li>
        ))}
      </ul>
      <p className="text-lg">Total ₹{placed.grand_total}. Payment is pending in this demo.</p>
      <p className="flex flex-wrap gap-x-6">
        <Link href="/orders" className="inline-block py-1 text-plum underline underline-offset-2">Your orders</Link>
        <Link href="/restaurants" className="inline-block py-1 text-plum underline underline-offset-2">Keep browsing</Link>
      </p>
    </section>
  );
}
