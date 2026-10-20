// One restaurant in a list (Phase 7c). Every number comes from the backend (D-056): distance to the area centre,
// the delivery fee for a small order, and the median single-serving main price. No ratings, no ETAs (D-049).

import Link from "next/link";

import { restaurantHref, type RestaurantCard as Card } from "@/lib/catalog";

/** The familiar green square-and-dot pure-veg mark, with its meaning in text for screen readers. */
export function VegMark({ label = "Pure veg" }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm font-medium text-veg">
      <span aria-hidden="true" className="inline-flex size-4 items-center justify-center rounded-[3px] border-2 border-veg">
        <span className="size-1.5 rounded-full bg-veg" />
      </span>
      {label}
    </span>
  );
}

export function RestaurantCard({ card, freeFrom }: { card: Card; freeFrom: number }) {
  const b = card.branch;
  return (
    <article className="relative flex h-full flex-col gap-2 rounded-xl border border-border bg-card p-4 shadow-sm transition-shadow focus-within:shadow-md hover:shadow-md">
      <h3 className="font-display text-2xl font-semibold leading-tight">
        {/* The whole card is clickable through this link's ::after; the link text is the restaurant's name. */}
        <Link href={restaurantHref(b.branch_id)} className="rounded-sm after:absolute after:inset-0 after:rounded-xl focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-ring focus-visible:after:ring-offset-2 focus-visible:after:ring-offset-background">
          {card.name}
        </Link>
      </h3>
      <p className="text-sm text-muted-foreground">
        {b.label}
        {b.street ? ` · ${b.street}` : ""}
      </p>
      {card.cuisines.length ? <p className="text-sm">{card.cuisines.join(" · ")}</p> : null}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {card.veg_only ? <VegMark /> : null}
        {card.mild_friendly ? (
          <span className="rounded-full bg-secondary px-2.5 py-0.5 text-sm text-secondary-foreground">Mild-friendly</span>
        ) : null}
      </div>
      <dl className="mt-auto grid grid-cols-3 gap-2 border-t border-border pt-3 text-sm">
        <div>
          <dt className="text-muted-foreground">Distance</dt>
          <dd className="font-medium">{b.distance_km.toFixed(1)} km</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Delivery</dt>
          <dd className="font-medium">₹{card.delivery_fee}<span className="sr-only">, free from ₹{freeFrom} of food</span></dd>
        </div>
        <div>
          <dt className="text-muted-foreground">For one</dt>
          <dd className="font-medium">{card.price_for_one === null ? "—" : `₹${card.price_for_one}`}</dd>
        </div>
      </dl>
      {card.more_branches_in_range > 0 ? (
        <p className="text-sm text-muted-foreground">
          +{card.more_branches_in_range} more {card.more_branches_in_range === 1 ? "branch that delivers" : "branches that deliver"} here
        </p>
      ) : null}
    </article>
  );
}
