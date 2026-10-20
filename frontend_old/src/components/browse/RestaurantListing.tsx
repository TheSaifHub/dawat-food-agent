"use client";

// The restaurant listing (Phase 7c, D-049/D-056). The filters live in the URL, so a filtered view can be shared or
// bookmarked and the back button undoes a filter. Only restaurants that can deliver to the area are listed (8 km),
// nearest first by default. Filters: pure veg, mild-friendly, cuisine, distance, price for one. No delivery-time
// filter (Dawat never makes up ETAs) and no rating sort (there are no ratings).

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

import { AreaPicker } from "@/components/browse/AreaPicker";
import { RestaurantCard } from "@/components/browse/RestaurantCard";
import { Announcer, ErrorNote, Loading } from "@/components/common/Loading";
import { api, type ToolBody } from "@/lib/api";
import { rememberArea, usePreferredArea } from "@/lib/area";
import { AREA_ANSWERS, type Listing, type RestaurantCard as Card } from "@/lib/catalog";

const PAGE = 24;
const DISTANCES = [2, 3, 5];
const PRICES = [150, 250, 400];

type State =
  | { kind: "idle" }
  | { kind: "loading"; slow: boolean }
  | { kind: "ok"; listing: Listing; cards: Card[]; more: "idle" | "loading" | "error" }
  | { kind: "area"; message: string }
  | { kind: "error"; message: string };

const selectClass = "h-11 rounded-lg border border-input bg-card px-3 text-base outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background";
const toggleClass = "inline-flex h-11 items-center gap-2 rounded-full border border-input px-4 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring aria-pressed:border-plum aria-pressed:bg-plum aria-pressed:text-ivory";

export function RestaurantListing() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const area = usePreferredArea(params.get("area"));
  const [state, setState] = useState<State>({ kind: "idle" });
  const [attempt, setAttempt] = useState(0);
  const list = useRef<HTMLUListElement>(null);
  const ids = { cuisine: useId(), km: useId(), price: useId(), sort: useId() };

  const filters = {
    cuisine: params.get("cuisine") || null,
    veg_only: params.get("veg_only") === "1",
    mild: params.get("mild") === "1",
    max_km: Number(params.get("max_km")) || null,
    max_price_for_one: Number(params.get("max_price_for_one")) || null,
    sort: (["distance", "price", "name"].includes(params.get("sort") ?? "") ? params.get("sort") : "distance") as Listing["filters"]["sort"],
  };
  const key = `${area}|${params.toString()}|${attempt}`;

  function setParam(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params.toString());
    if (area && !next.get("area")) next.set("area", area);
    for (const [k, v] of Object.entries(changes)) {
      if (v === null || v === "") next.delete(k);
      else next.set(k, v);
    }
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  }

  async function load(offset: number, signal?: AbortSignal, onSlow?: () => void) {
    return api<Listing>(`/areas/${encodeURIComponent(area!)}/restaurants`, {
      query: { ...filters, veg_only: filters.veg_only || null, mild: filters.mild || null, offset, limit: PAGE },
      signal, onSlow,
    });
  }

  useEffect(() => {
    if (!area) return;
    const controller = new AbortController();
    queueMicrotask(() => setState({ kind: "loading", slow: false }));
    load(0, controller.signal, () => setState((s) => (s.kind === "loading" ? { kind: "loading", slow: true } : s)))
      .then((res) => {
        if (res.ok && (res.data.status === "ok" || res.data.status === "empty")) {
          setState({ kind: "ok", listing: res.data, cards: res.data.restaurants, more: "idle" });
        } else if (res.ok && AREA_ANSWERS.has((res.data as unknown as ToolBody).status)) {
          setState({ kind: "area", message: (res.data as unknown as ToolBody).message ?? "That area isn't covered." });
        } else if (!res.ok && res.kind !== "aborted") {
          setState({ kind: "error", message: res.message });
        }
      });
    return () => controller.abort();
    // `key` captures the area, every filter and retries.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  async function showMore() {
    if (state.kind !== "ok" || state.more === "loading") return;
    const first = state.cards.length;
    setState({ ...state, more: "loading" });
    const res = await load(first);
    if (res.ok) {
      setState({ ...state, cards: [...state.cards, ...res.data.restaurants], more: "idle" });
      // Keyboard users continue at the first new card (the button may have just disappeared on the last page).
      requestAnimationFrame(() => list.current?.children[first]?.querySelector<HTMLAnchorElement>("a")?.focus());
    } else setState({ ...state, more: "error" });
  }

  const announcement =
    state.kind === "loading" ? "Loading restaurants…"
    : state.kind === "ok" ? `${state.listing.total} ${state.listing.total === 1 ? "restaurant delivers" : "restaurants deliver"} to ${state.listing.area.name}`
      + (state.more === "loading" ? ". Loading more…" : `. Showing ${state.cards.length}.`)
    : state.kind === "area" || state.kind === "error" ? state.message : "";

  const listing = state.kind === "ok" ? state.listing : null;
  const facets = listing?.cuisine_facets ?? [];

  return (
    <div className="flex flex-col gap-6">
      <Announcer text={announcement} />
      <form className="flex flex-col gap-4 rounded-xl border border-border bg-card p-4" onSubmit={(e) => e.preventDefault()}
            aria-label="Filter restaurants">
        <div className="flex flex-wrap items-end gap-4">
          <AreaPicker value={area ?? ""} onChange={(id) => { rememberArea(id); setParam({ area: id }); }} />
          <div className="flex flex-col gap-1.5">
            <label htmlFor={ids.cuisine} className="text-sm font-medium">Cuisine</label>
            <select id={ids.cuisine} className={selectClass} value={filters.cuisine ?? ""}
                    onChange={(e) => setParam({ cuisine: e.target.value || null })}>
              <option value="">Any cuisine</option>
              {filters.cuisine && !facets.some((f) => f.cuisine === filters.cuisine) ? (
                <option value={filters.cuisine}>{filters.cuisine}</option>
              ) : null}
              {facets.map((f) => <option key={f.cuisine} value={f.cuisine}>{f.cuisine} ({f.restaurants})</option>)}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor={ids.km} className="text-sm font-medium">Distance</label>
            <select id={ids.km} className={selectClass} value={filters.max_km ?? ""}
                    onChange={(e) => setParam({ max_km: e.target.value || null })}>
              <option value="">Up to {listing?.max_delivery_km ?? 8} km</option>
              {DISTANCES.map((d) => <option key={d} value={d}>Within {d} km</option>)}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor={ids.price} className="text-sm font-medium">Price for one</label>
            <select id={ids.price} className={selectClass} value={filters.max_price_for_one ?? ""}
                    onChange={(e) => setParam({ max_price_for_one: e.target.value || null })}>
              <option value="">Any price</option>
              {PRICES.map((p) => <option key={p} value={p}>Up to ₹{p}</option>)}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor={ids.sort} className="text-sm font-medium">Sort by</label>
            <select id={ids.sort} className={selectClass} value={filters.sort}
                    onChange={(e) => setParam({ sort: e.target.value === "distance" ? null : e.target.value })}>
              <option value="distance">Nearest first</option>
              <option value="price">Price for one, low to high</option>
              <option value="name">Name, A to Z</option>
            </select>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className={toggleClass} aria-pressed={filters.veg_only}
                  onClick={() => setParam({ veg_only: filters.veg_only ? null : "1" })}>
            Pure veg
          </button>
          <button type="button" className={toggleClass} aria-pressed={filters.mild}
                  onClick={() => setParam({ mild: filters.mild ? null : "1" })}>
            Mild-friendly
          </button>
        </div>
      </form>

      {area === "" ? <p className="text-center">Choose an area to see the restaurants that deliver there.</p> : null}
      {state.kind === "loading" ? <Loading what="restaurants" slow={state.slow} /> : null}
      {state.kind === "area" ? <p role="alert" className="text-center">{state.message}</p> : null}
      {state.kind === "error" ? <ErrorNote message={state.message} onRetry={() => setAttempt((n) => n + 1)} /> : null}

      {state.kind === "ok" ? (
        <section aria-labelledby="results-heading" className="flex flex-col gap-4">
          <h2 id="results-heading" className="font-sans text-xl">
            <strong>{state.listing.total}</strong> {state.listing.total === 1 ? "restaurant delivers" : "restaurants deliver"} to{" "}
            <strong>{state.listing.area.name}</strong>
          </h2>
          <p className="text-sm text-muted-foreground">
            Delivery is free when your food from one restaurant comes to ₹{state.listing.free_delivery_from} or more.
            Prices for one are the typical main dish.
          </p>
          {state.listing.status === "empty" ? <p>{state.listing.message}</p> : (
            <ul ref={list} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {state.cards.map((c) => (
                <li key={c.restaurant_id}><RestaurantCard card={c} freeFrom={state.listing.free_delivery_from} /></li>
              ))}
            </ul>
          )}
          {state.cards.length < state.listing.total ? (
            <div className="flex flex-col items-center gap-2">
              {/* aria-disabled, not disabled: a disabled button drops keyboard focus (ui-checker, 7c). */}
              <button type="button" onClick={showMore} aria-disabled={state.more === "loading"}
                      className="inline-flex h-11 items-center rounded-lg border border-input bg-card px-5 font-medium hover:bg-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring aria-disabled:opacity-60">
                {state.more === "loading" ? "Loading…" : `Show more (${state.listing.total - state.cards.length} left)`}
              </button>
              {state.more === "error" ? <p role="alert" className="text-sm text-destructive">Couldn&apos;t load more. Please try again.</p> : null}
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
