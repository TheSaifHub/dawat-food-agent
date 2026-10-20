import type { Metadata } from "next";

import { TrackView } from "@/components/orders/TrackView";

// The order is only known once the backend answers (in the browser, with the visitor's token), so the component
// renders the heading and sets the full title.
export const metadata: Metadata = { title: "Order" };

export default async function OrderPage({ params }: PageProps<"/orders/[orderNo]">) {
  const { orderNo } = await params;
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-10">
      <TrackView orderNumber={decodeURIComponent(orderNo)} />
    </div>
  );
}
