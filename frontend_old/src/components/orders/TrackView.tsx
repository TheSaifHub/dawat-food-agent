"use client";

// One order's tracking page (Phase 7g): /orders/DW1042. GET /orders/{number} answers only for the signed-in user's own
// orders (another user's number looks exactly like a missing one, D-057). The timeline is shown exactly as the
// backend gives it, and there is no delivery time: nothing on this page is invented (CLAUDE.md: never an ETA that no
// tool returned). The moving rider map arrives with the simulated status updates in Phase 8.

import Link from "next/link";
import { useEffect, useState } from "react";

import { ErrorNote, Loading } from "@/components/common/Loading";
import { signInLink, textLink } from "@/components/orders/OrdersView";
import { DietMark } from "@/components/restaurant/RestaurantView";
import { api } from "@/lib/api";
import { accessToken } from "@/lib/auth";
import { restaurantHref } from "@/lib/catalog";
import { isOpen, paymentLabel, statusLabel, when, type Tracked } from "@/lib/orders";
import { useSession } from "@/lib/session";

type State =
  | { kind: "loading"; slow: boolean }
  | { kind: "ok"; order: Tracked }
  | { kind: "missing" }
  | { kind: "error"; message: string };

export function TrackView({ orderNumber }: { orderNumber: string }) {
  const { session } = useSession();
  const [state, setState] = useState<State>({ kind: "loading", slow: false });
  const [attempt, setAttempt] = useState(0);
  const signedIn = session.state === "signed_in";
  const shown = orderNumber.toUpperCase().replace(/^#/, "");

  useEffect(() => {
    if (!signedIn) return;
    const controller = new AbortController();
    queueMicrotask(() => setState({ kind: "loading", slow: false }));
    const onSlow = () => setState((s) => (s.kind === "loading" ? { kind: "loading", slow: true } : s));
    void (async () => {
      const res = await api<Tracked>(`/orders/${encodeURIComponent(orderNumber)}`, {
        token: await accessToken(), signal: controller.signal, onSlow,
      });
      if (controller.signal.aborted) return;
      if (res.ok) setState({ kind: "ok", order: res.data });
      else if (res.status === 404 || res.status === 422) setState({ kind: "missing" });
      else setState({ kind: "error", message: res.message });
    })();
    return () => controller.abort();
  }, [signedIn, orderNumber, attempt]);

  useEffect(() => {
    document.title = state.kind === "missing" ? "Order not found · Dawat"
      : state.kind === "ok" ? `Order #${state.order.order_number} · Dawat` : `Order #${shown} · Dawat`;
  }, [state, shown]);

  // Order numbers in DM Sans with even-width digits: Cormorant's old-style figures make "1012" read like "1o12".
  const heading = state.kind === "missing"
    ? <h1 className="font-display text-5xl font-semibold text-plum">Order not found</h1>
    : (
      <h1 className="font-display text-5xl font-semibold text-plum">
        Order <span className="font-sans tabular-nums">#{state.kind === "ok" ? state.order.order_number : shown}</span>
      </h1>
    );

  if (session.state === "loading") return <>{heading}<Loading what="your order" slow={false} /></>;
  if (!signedIn) {
    return (
      <>
        {heading}
        <div className="flex flex-col items-start gap-4">
          <p>Sign in to see this order.</p>
          <Link href="/login" className={signInLink}>Sign in</Link>
        </div>
      </>
    );
  }
  if (state.kind === "loading") return <>{heading}<Loading what="your order" slow={state.slow} /></>;
  if (state.kind === "error") return <>{heading}<ErrorNote message={state.message} onRetry={() => setAttempt((a) => a + 1)} /></>;
  if (state.kind === "missing") {
    return (
      <>
        {heading}
        <div className="flex flex-col items-start gap-3">
          <p>We couldn&apos;t find order #{shown} in your account.</p>
          <Link href="/orders" className={textLink}>See all your orders</Link>
        </div>
      </>
    );
  }

  const o = state.order;
  return (
    <>
      {heading}
      <div className="flex flex-col gap-1">
        <p className="text-lg">
          <Link href={restaurantHref(o.branch_id)} className="font-semibold text-plum underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">{o.restaurant}</Link>
          <span className="text-muted-foreground"> · {o.branch_label}</span>
        </p>
        <p className="text-muted-foreground">Placed {when(o.placed_at)} · Deliver to {o.delivery_area}</p>
        {o.is_sample ? <p><span className="rounded-full border border-border px-3 py-0.5 text-sm text-muted-foreground">Sample order</span></p> : null}
      </div>

      <section aria-labelledby="status-heading" className="flex flex-col gap-3 rounded-xl border border-border bg-card p-5">
        <h2 id="status-heading" className="font-display text-2xl font-semibold">Status: {statusLabel(o.order_status)}</h2>
        <ol className="flex flex-col gap-2 border-l-2 border-plum pl-4">
          {o.timeline.map((e, i) => (
            <li key={`${e.status}-${i}`} className="flex flex-wrap justify-between gap-x-4">
              <span className="font-medium">{statusLabel(e.status)}</span>
              <span className="text-sm text-muted-foreground">{when(e.at)}</span>
            </li>
          ))}
        </ol>
        {isOpen(o.order_status) ? (
          <p className="text-sm text-muted-foreground">No delivery time yet. Status updates aren&apos;t switched on in this demo.</p>
        ) : null}
      </section>

      <section aria-labelledby="items-heading" className="flex flex-col gap-3">
        <h2 id="items-heading" className="font-display text-2xl font-semibold">What you ordered</h2>
        <ul className="flex flex-col divide-y divide-border rounded-xl border border-border bg-card">
          {o.items.map((i) => (
            <li key={i.item_id} className="flex items-start justify-between gap-4 px-4 py-3">
              <span className="flex gap-3"><span className="mt-1"><DietMark isVeg={i.is_veg} /></span>{i.qty} × {i.dish_name}</span>
              <span className="shrink-0">₹{i.unit_price}{i.qty > 1 ? " each" : ""}</span>
            </li>
          ))}
        </ul>
        <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1">
          <dt>Food</dt><dd className="text-right">₹{o.items_total}</dd>
          <dt>Delivery</dt><dd className="text-right">{o.delivery_fee ? `₹${o.delivery_fee}` : "Free"}</dd>
          <dt>GST</dt><dd className="text-right">₹{o.taxes}</dd>
          <dt className="font-semibold">Total</dt><dd className="text-right font-semibold">₹{o.total}</dd>
        </dl>
        <p className="text-sm text-muted-foreground">{paymentLabel(o.payment_status)}</p>
      </section>

      <p><Link href="/orders" className={textLink}>All your orders</Link></p>
    </>
  );
}
