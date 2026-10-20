"use client";

// A restaurant branch's page (Phase 7d): header, whether it delivers to your area, the map, then the menu by
// category. Every price, fee and distance comes from the backend; the page only groups and filters what it was given.
// Add-to-cart arrives with the cart in 7e.

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { VegMark } from "@/components/browse/RestaurantCard";
import { Announcer, ErrorNote, Loading } from "@/components/common/Loading";
import { AddControl } from "@/components/cart/CartWidgets";
import { BranchMap } from "@/components/restaurant/BranchMap";
import { api } from "@/lib/api";
import { usePreferredArea } from "@/lib/area";
import { restaurantHref } from "@/lib/catalog";

type BranchInfo = {
  status: "ok";
  restaurant: { restaurant_id: string; name: string; cuisines: string[]; veg_only: boolean; is_chain: boolean;
                price_for_one: number | null; mild_friendly: boolean };
  branch: { branch_id: string; label: string; area_id: string; area: string; street: string | null; lat: number; lon: number };
  other_branches: { branch_id: string; label: string; area: string }[];
  free_delivery_from: number;
  max_delivery_km: number;
  delivery?: { status: string; area?: { area_id: string; name: string }; distance_km?: number; delivery_fee?: number | null;
               message?: string };
};

export type MenuItem = { item_id: string; name: string; price: number; is_veg: boolean; spice_level: number;
                         serves: number; category: string; course: string };
type Menu = { status: "ok"; items: MenuItem[] };

type State =
  | { kind: "loading"; slow: boolean }
  | { kind: "ok"; info: BranchInfo; menu: MenuItem[] }
  | { kind: "missing" }
  | { kind: "error"; message: string };

const CATEGORY_NAMES: Record<string, string> = {        // backend app/tools/categories.py CATEGORIES, in its order
  biryani: "Biryani", mandi: "Mandi", kebab: "Kebabs", starter: "Starters", curry: "Curries", bread: "Breads",
  rice: "Rice", noodles: "Noodles", soup: "Soups", salad: "Salads", pizza: "Pizza", pasta: "Pasta", burger: "Burgers",
  sandwich: "Sandwiches", roll: "Rolls", shawarma: "Shawarma", fried_chicken: "Fried chicken", mexican: "Mexican",
  continental: "Continental", breakfast: "Breakfast", tiffin: "Tiffins", meals: "Meals", snack: "Snacks",
  bakery: "Bakery", dessert: "Desserts", drink: "Drinks",
};
export const SPICE_NAMES = ["Not spicy", "Mild", "Medium", "Hot"];

function categoryName(c: string): string {
  return CATEGORY_NAMES[c] ?? c.replace(/_/g, " ").replace(/^./, (x) => x.toUpperCase());
}

export function RestaurantView({ branchId }: { branchId: string }) {
  const area = usePreferredArea(null);
  const [state, setState] = useState<State>({ kind: "loading", slow: false });
  const [attempt, setAttempt] = useState(0);
  const [vegOnly, setVegOnly] = useState(false);
  const [note, setNote] = useState<{ text: string; ok: boolean; signIn?: boolean; seq: number } | null>(null);

  useEffect(() => {
    if (state.kind === "missing") document.title = "Restaurant not found · Dawat";
  }, [state.kind]);

  useEffect(() => {
    if (area === null) return;                          // still deciding which area to judge delivery for
    const controller = new AbortController();
    const onSlow = () => setState((s) => (s.kind === "loading" ? { kind: "loading", slow: true } : s));
    queueMicrotask(() => setState({ kind: "loading", slow: false }));
    const id = encodeURIComponent(branchId);
    Promise.all([
      api<BranchInfo>(`/branches/${id}`, { query: { area: area || null }, signal: controller.signal, onSlow }),
      api<Menu>(`/branches/${id}/menu`, { signal: controller.signal }),
    ]).then(([info, menu]) => {
      if (info.ok && menu.ok) {
        setState({ kind: "ok", info: info.data, menu: menu.data.items });
        document.title = `${info.data.restaurant.name}, ${info.data.branch.label} · Dawat`;
        return;
      }
      if (info.status === 404 || menu.status === 404) {
        setState({ kind: "missing" });
        return;
      }
      const failed = !info.ok ? info : !menu.ok ? menu : null;
      if (failed && failed.kind !== "aborted") setState({ kind: "error", message: failed.message });
    });
    return () => controller.abort();
  }, [branchId, area, attempt]);

  const grouped = useMemo(() => {
    if (state.kind !== "ok") return [];
    const groups: { category: string; items: MenuItem[] }[] = [];
    for (const item of state.menu) {
      if (vegOnly && !item.is_veg) continue;
      const g = groups.find((x) => x.category === item.category);
      if (g) g.items.push(item);
      else groups.push({ category: item.category, items: [item] });
    }
    return groups;
  }, [state, vegOnly]);

  const shown = grouped.reduce((n, g) => n + g.items.length, 0);
  const announcement = note ? note.text : state.kind === "loading" ? "Loading the restaurant…"
    : state.kind === "ok" ? (vegOnly ? `Showing ${shown} veg dishes`
      : `${state.info.restaurant.name}, ${state.info.branch.label}: menu loaded, ${shown} dishes`)
    : state.kind === "missing" ? "Restaurant not found" : state.message;
  return (
    <>
      <Announcer text={announcement} seq={note?.seq} />
      <Body state={state} grouped={grouped} vegOnly={vegOnly} setVegOnly={setVegOnly} retry={() => setAttempt((n) => n + 1)}
            browseArea={area || null} note={note}
            onResult={(text, ok, signIn) => setNote((n) => ({ text, ok, signIn, seq: (n?.seq ?? 0) + 1 }))} />
    </>
  );
}

function Body({ state, grouped, vegOnly, setVegOnly, retry, browseArea, note, onResult }: {
  browseArea: string | null;
  note: { text: string; ok: boolean; signIn?: boolean } | null;
  onResult: (text: string, ok: boolean, signIn?: boolean) => void;
  state: State;
  grouped: { category: string; items: MenuItem[] }[];
  vegOnly: boolean;
  setVegOnly: (f: (v: boolean) => boolean) => void;
  retry: () => void;
}) {
  if (state.kind === "loading") return <Loading what="the menu" slow={state.slow} />;
  if (state.kind === "missing") {
    return (
      <div className="flex flex-col items-center gap-3 py-10 text-center">
        <h1 className="font-display text-4xl font-semibold text-plum">Restaurant not found</h1>
        <p>This branch isn&apos;t on Dawat, or it isn&apos;t open for the demo.</p>
        <Link href="/restaurants" className="inline-block py-1 text-plum underline underline-offset-2">Browse restaurants</Link>
      </div>
    );
  }
  if (state.kind === "error") return <ErrorNote message={state.message} onRetry={retry} />;

  const { info } = state;
  const r = info.restaurant, b = info.branch;
  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1 className="font-display text-5xl font-semibold text-plum">{r.name}</h1>
        <p className="text-lg">{b.label}{b.street ? ` · ${b.street}` : ""}</p>
        {r.cuisines.length ? <p className="text-muted-foreground">{r.cuisines.join(" · ")}</p> : null}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          {r.veg_only ? <VegMark /> : null}
          {r.price_for_one !== null ? <span>About ₹{r.price_for_one} for one</span> : null}
          {r.mild_friendly ? <span className="rounded-full bg-secondary px-2.5 py-0.5 text-sm text-secondary-foreground">Mild-friendly</span> : null}
        </div>
      </header>

      <div className="grid gap-6 md:grid-cols-[1fr_1fr]">
        <section aria-labelledby="delivery-heading" className="flex flex-col gap-3 rounded-xl border border-border bg-card p-5">
          <h2 id="delivery-heading" className="font-display text-2xl font-semibold">Delivery</h2>
          <DeliveryNote info={info} />
          <p className="text-sm text-muted-foreground">
            In {b.area}, Hyderabad. Location from OpenStreetMap; menu and prices are simulated for this demo.
          </p>
          {info.other_branches.length ? (
            <details className="text-sm">
              <summary className="cursor-pointer py-1 font-medium text-plum">
                {info.other_branches.length} other {info.other_branches.length === 1 ? "branch" : "branches"}
              </summary>
              <ul className="mt-2 flex max-h-48 flex-col gap-1 overflow-y-auto p-1">
                {info.other_branches.map((o) => (
                  <li key={o.branch_id}>
                    <Link href={restaurantHref(o.branch_id)} className="inline-block py-1 underline underline-offset-2">{o.label}</Link>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </section>
        <BranchMap lat={b.lat} lon={b.lon} label={`${r.name}, ${b.label}`} />
      </div>

      <section aria-labelledby="menu-heading" className="flex flex-col gap-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="menu-heading" className="font-display text-3xl font-semibold text-plum">Menu</h2>
          {!r.veg_only ? (
            <button type="button" aria-pressed={vegOnly} onClick={() => setVegOnly((v) => !v)}
                    className="inline-flex h-11 items-center rounded-full border border-input px-4 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring aria-pressed:border-plum aria-pressed:bg-plum aria-pressed:text-ivory">
              Veg only
            </button>
          ) : null}
        </div>
        {/* The visible half of the cart outcome; the Announcer above reads the same text aloud. */}
        {note ? (
          <p className={`rounded-lg px-4 py-2 ${note.ok ? "bg-secondary text-secondary-foreground" : "border border-destructive text-destructive"}`}>
            {note.text}
            {note.signIn ? <> <Link href="/login" className="inline-block py-1 font-medium underline underline-offset-2">Sign in</Link></> : null}
          </p>
        ) : null}
        {info.delivery?.status === "too_far" ? (
          <p className="text-muted-foreground">This branch is too far to deliver to you, so its dishes can&apos;t be added.</p>
        ) : null}
        <nav aria-label="Menu categories" className="-mx-4 overflow-x-auto px-4">
          {/* py-1: room for the chips' focus rings inside this sideways-scrolling row (ui-checker, 7d). */}
          <ul className="flex gap-2 py-1">
            {grouped.map((g) => (
              <li key={g.category} className="shrink-0">
                <a href={`#cat-${g.category}`}
                   onClick={() => requestAnimationFrame(() => document.getElementById(`cat-${g.category}`)?.focus({ preventScroll: true }))}
                   className="inline-flex min-h-10 items-center rounded-full bg-muted px-4 text-sm font-medium hover:bg-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
                  {categoryName(g.category)} <span className="ml-1.5 text-muted-foreground">{g.items.length}</span>
                </a>
              </li>
            ))}
          </ul>
        </nav>
        {grouped.map((g) => (
          <section key={g.category} id={`cat-${g.category}`} aria-labelledby={`cat-${g.category}-h`} tabIndex={-1}
                   className="scroll-mt-4 focus:outline-none">
            <h3 id={`cat-${g.category}-h`} className="mb-2 font-display text-2xl font-semibold">{categoryName(g.category)}</h3>
            <ul className="divide-y divide-border rounded-xl border border-border bg-card">
              {g.items.map((i) => (
                <MenuRow key={i.item_id} item={i} branchId={b.branch_id} browseArea={browseArea}
                         tooFar={info.delivery?.status === "too_far"} onResult={onResult} />
              ))}
            </ul>
          </section>
        ))}
      </section>
    </div>
  );
}

function DeliveryNote({ info }: { info: BranchInfo }) {
  const d = info.delivery;
  if (!d) {
    return (
      <p>
        <Link href="/" className="inline-block py-1 text-plum underline underline-offset-2">Choose your area</Link> to see if
        this branch delivers to you.
      </p>
    );
  }
  if (d.status === "ok" && d.area) {
    return (
      <p>
        Delivers to <strong>{d.area.name}</strong>: {d.distance_km?.toFixed(1)} km away, ₹{d.delivery_fee} delivery
        (free when your food comes to ₹{info.free_delivery_from} or more).
      </p>
    );
  }
  if (d.status === "too_far" && d.area) {
    return (
      <p>
        Too far to deliver to <strong>{d.area.name}</strong> ({d.distance_km?.toFixed(1)} km; Dawat delivers up to{" "}
        {info.max_delivery_km} km).
      </p>
    );
  }
  return <p>{d.message ?? "Choose your area to see if this branch delivers to you."}</p>;
}

/** Veg or non-veg, as the familiar square marks, with the meaning in text. */
export function DietMark({ isVeg }: { isVeg: boolean }) {
  return (
    <span className={`inline-flex size-4 shrink-0 items-center justify-center rounded-[3px] border-2 ${isVeg ? "border-veg" : "border-nonveg"}`}>
      {isVeg ? <span aria-hidden="true" className="size-1.5 rounded-full bg-veg" />
             : <span aria-hidden="true" className="size-0 border-x-[4px] border-b-[7px] border-x-transparent border-b-nonveg" />}
      <span className="sr-only">{isVeg ? "Veg" : "Non-veg"}</span>
    </span>
  );
}

function MenuRow({ item, branchId, browseArea, tooFar, onResult }: {
  item: MenuItem;
  branchId: string;
  browseArea: string | null;
  tooFar: boolean;
  onResult: (text: string, ok: boolean, signIn?: boolean) => void;
}) {
  return (
    <li className="flex items-start justify-between gap-4 px-4 py-3">
      <div className="flex min-w-0 gap-3">
        <span className="mt-1"><DietMark isVeg={item.is_veg} /></span>
        <div className="min-w-0">
          <p className="font-medium">{item.name}</p>
          <p className="text-sm text-muted-foreground">
            {SPICE_NAMES[item.spice_level] ?? ""}{item.serves > 1 ? ` · serves ${item.serves}` : ""}
          </p>
        </div>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-2">
        <p className="font-medium">₹{item.price}</p>
        {tooFar ? null : (
          <AddControl itemId={item.item_id} branchId={branchId} name={item.name} browseArea={browseArea} onResult={onResult} />
        )}
      </div>
    </li>
  );
}
