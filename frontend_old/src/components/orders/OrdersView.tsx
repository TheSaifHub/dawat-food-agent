"use client";

// Your orders (Phase 7g): past checkouts, newest first, at the prices paid then (GET /orders). Each restaurant's order
// has its own #DW number and links to its tracking page. Sample orders from a demo account are marked as such.

import Link from "next/link";
import { useEffect, useState } from "react";

import { ErrorNote, Loading } from "@/components/common/Loading";
import { api } from "@/lib/api";
import { accessToken } from "@/lib/auth";
import { HISTORY_LIMIT, orderHref, statusLabel, when, type Checkout, type History } from "@/lib/orders";
import { useSession } from "@/lib/session";

type State =
  | { kind: "loading"; slow: boolean }
  | { kind: "ok"; history: History }
  | { kind: "error"; message: string };

export const signInLink = "inline-flex h-11 items-center rounded-lg bg-plum px-5 font-semibold text-ivory focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";
export const textLink = "inline-block py-1 text-plum underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

export function OrdersView() {
  const { session } = useSession();
  const [state, setState] = useState<State>({ kind: "loading", slow: false });
  const [attempt, setAttempt] = useState(0);
  const signedIn = session.state === "signed_in";

  useEffect(() => {
    if (!signedIn) return;
    const controller = new AbortController();
    queueMicrotask(() => setState({ kind: "loading", slow: false }));
    const onSlow = () => setState((s) => (s.kind === "loading" ? { kind: "loading", slow: true } : s));
    void (async () => {
      const res = await api<History>("/orders", {
        query: { limit: HISTORY_LIMIT }, token: await accessToken(), signal: controller.signal, onSlow,
      });
      if (controller.signal.aborted) return;
      setState(res.ok ? { kind: "ok", history: res.data } : { kind: "error", message: res.message });
    })();
    return () => controller.abort();
  }, [signedIn, attempt]);

  if (session.state === "loading") return <Loading what="your orders" slow={false} />;
  if (!signedIn) {
    return (
      <div className="flex flex-col items-start gap-4">
        <p>Sign in to see your orders.</p>
        <Link href="/login" className={signInLink}>Sign in</Link>
      </div>
    );
  }
  if (state.kind === "loading") return <Loading what="your orders" slow={state.slow} />;
  if (state.kind === "error") return <ErrorNote message={state.message} onRetry={() => setAttempt((a) => a + 1)} />;

  const { checkouts, has_more } = state.history;
  if (!checkouts.length) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p>No orders yet.</p>
        <Link href="/restaurants" className={textLink}>Find something to eat</Link>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-6">
      <ol className="flex flex-col gap-6">
        {checkouts.map((c) => <CheckoutCard key={c.checkout_id} checkout={c} />)}
      </ol>
      {has_more ? <p className="text-sm text-muted-foreground">Showing your {HISTORY_LIMIT} most recent orders.</p> : null}
    </div>
  );
}

function CheckoutCard({ checkout }: { checkout: Checkout }) {
  const several = checkout.orders.length > 1;
  return (
    <li className="flex flex-col gap-3 rounded-xl border border-border bg-card p-5 shadow-sm">
      <h2 className="flex flex-wrap items-baseline justify-between gap-2 font-sans text-base font-semibold">
        <span>{when(checkout.placed_at)}</span>
        {several ? <span className="font-normal text-muted-foreground">{checkout.orders.length} restaurants · total ₹{checkout.grand_total}</span> : null}
      </h2>
      <ul className="flex flex-col divide-y divide-border">
        {checkout.orders.map((o) => (
          <li key={o.order_id} className="flex flex-col gap-1.5 py-3 first:pt-0 last:pb-0">
            <p className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
              <Link href={orderHref(o.order_number)} className="font-sans text-lg font-semibold tabular-nums text-plum underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
                #{o.order_number}<span className="sr-only">, track this order</span>
              </Link>
              <span className="font-semibold">₹{o.total}</span>
            </p>
            <p>{o.restaurant} <span className="text-muted-foreground">· {o.branch_label}</span></p>
            <p className="text-sm text-muted-foreground">{o.items.map((i) => `${i.qty} × ${i.name}`).join(", ")}</p>
            <p className="flex flex-wrap gap-2 text-sm">
              <span className="rounded-full bg-secondary px-3 py-0.5 text-secondary-foreground">{statusLabel(o.order_status)}</span>
              {o.is_sample ? <span className="rounded-full border border-border px-3 py-0.5 text-muted-foreground">Sample order</span> : null}
            </p>
          </li>
        ))}
      </ul>
    </li>
  );
}
