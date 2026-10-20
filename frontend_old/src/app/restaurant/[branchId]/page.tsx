import type { Metadata } from "next";

import { RestaurantView } from "@/components/restaurant/RestaurantView";

// The name is only known once the backend answers (in the browser; the free backend may be asleep), so the
// component sets the full title then.
export const metadata: Metadata = { title: "Restaurant" };

export default async function RestaurantPage({ params }: PageProps<"/restaurant/[branchId]">) {
  const { branchId } = await params;
  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-10">
      <RestaurantView branchId={decodeURIComponent(branchId)} />
    </div>
  );
}
