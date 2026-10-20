"use client";

// The home page's working part (Phase 7c, D-049): pick an area, then cuisine shortcuts and the chains that deliver
// there, most branches in range first. No "top picks": there are no ratings, by rule.

import Link from "next/link";
import { useEffect, useState } from "react";

import { AreaPicker } from "@/components/browse/AreaPicker";
import { RestaurantCard } from "@/components/browse/RestaurantCard";
import { Announcer, ErrorNote, Loading } from "@/components/common/Loading";
import { api, type ToolBody } from "@/lib/api";
import { rememberArea, usePreferredArea } from "@/lib/area";
import { listingHref, type AreaHome } from "@/lib/catalog";

type State =
  | { kind: "idle" }
  | { kind: "loading"; slow: boolean }
  | { kind: "ok"; home: AreaHome }
  | { kind: "error"; message: string };

const chip = "inline-flex min-h-10 items-center rounded-full border border-input bg-card px-4 text-sm font-medium hover:bg-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

export function HomeBrowse() {
  const preferred = usePreferredArea(null);
  const [picked, setPicked] = useState<string | null>(null);
  const area = picked ?? preferred;
  const [state, setState] = useState<State>({ kind: "idle" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!area) return;
    const controller = new AbortController();
    queueMicrotask(() => setState({ kind: "loading", slow: false }));
    api<AreaHome>(`/areas/${encodeURIComponent(area)}/home`, {
      signal: controller.signal,
      onSlow: () => setState((s) => (s.kind === "loading" ? { kind: "loading", slow: true } : s)),
    }).then((res) => {
      if (res.ok && (res.data.status === "ok" || res.data.status === "empty")) setState({ kind: "ok", home: res.data });
      else if (res.ok) setState({ kind: "error", message: (res.data as unknown as ToolBody).message ?? "That area isn't covered." });
      else if (res.kind !== "aborted") setState({ kind: "error", message: res.message });
    });
    return () => controller.abort();
  }, [area, attempt]);

  function choose(areaId: string) {
    rememberArea(areaId);
    setPicked(areaId);
  }

  const announcement =
    state.kind === "loading" ? "Loading restaurants near you…"
    : state.kind === "ok" ? (state.home.status === "ok"
        ? `${state.home.restaurants_in_range} restaurants deliver to ${state.home.area.name}`
        : state.home.message ?? "")
    : state.kind === "error" ? state.message : "";

  return (
    <div className="flex w-full flex-col gap-10">
      <Announcer text={announcement} />
      <div className="flex flex-col items-center gap-3">
        <AreaPicker value={area ?? ""} onChange={choose} />
        {area === "" ? <p className="text-sm text-muted-foreground">Choose an area to see who delivers there.</p> : null}
      </div>

      {state.kind === "loading" ? <Loading what="restaurants near you" slow={state.slow} /> : null}
      {state.kind === "error" ? <ErrorNote message={state.message} onRetry={() => setAttempt((n) => n + 1)} /> : null}
      {state.kind === "ok" ? <AreaSections home={state.home} /> : null}
    </div>
  );
}

function AreaSections({ home }: { home: AreaHome }) {
  const id = home.area.area_id;
  if (home.status === "empty") return <p className="text-center">{home.message}</p>;
  return (
    <>
      <p className="text-center text-lg">
        <strong>{home.restaurants_in_range}</strong> restaurants deliver to <strong>{home.area.name}</strong>.{" "}
        <Link href={listingHref(id)} className="inline-block py-1 text-plum underline underline-offset-2">See them all</Link>
      </p>

      <section aria-labelledby="cuisines-heading" className="flex flex-col gap-4">
        <h2 id="cuisines-heading" className="font-display text-3xl font-semibold text-plum">What are you in the mood for?</h2>
        <ul className="flex flex-wrap gap-2">
          <li><Link href={listingHref(id, { veg_only: true })} className={chip}>Pure veg</Link></li>
          <li><Link href={listingHref(id, { mild: true })} className={chip}>Mild-friendly</Link></li>
          {home.cuisines.map((c) => (
            <li key={c.cuisine}>
              <Link href={listingHref(id, { cuisine: c.cuisine })} className={chip}>
                {c.cuisine}<span className="ml-1.5 text-muted-foreground"><span className="sr-only">, </span>{c.restaurants}<span className="sr-only"> restaurants</span></span>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      {home.chains.length ? (
        <section aria-labelledby="chains-heading" className="flex flex-col gap-4">
          <div>
            <h2 id="chains-heading" className="font-display text-3xl font-semibold text-plum">Chains near you</h2>
            <p className="text-sm text-muted-foreground">The chains with the most branches that deliver to {home.area.name}.</p>
          </div>
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {home.chains.map((c) => (
              <li key={c.restaurant_id}><RestaurantCard card={c} freeFrom={home.free_delivery_from} /></li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}
