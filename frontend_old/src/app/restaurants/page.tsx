import type { Metadata } from "next";
import { Suspense } from "react";

import { RestaurantListing } from "@/components/browse/RestaurantListing";
import { Loading } from "@/components/common/Loading";

export const metadata: Metadata = { title: "Restaurants" };

// The listing reads its filters from the URL (useSearchParams), so it renders in the browser inside Suspense
// (Next 16: a prerendered page must wrap search-param readers in a Suspense boundary).
export default function RestaurantsPage() {
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-10">
      <h1 className="font-display text-5xl font-semibold text-plum">Restaurants</h1>
      <Suspense fallback={<Loading what="restaurants" slow={false} />}>
        <RestaurantListing />
      </Suspense>
    </div>
  );
}
