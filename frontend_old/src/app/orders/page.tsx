import type { Metadata } from "next";

import { OrdersView } from "@/components/orders/OrdersView";

export const metadata: Metadata = { title: "Your orders" };

export default function OrdersPage() {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-10">
      <h1 className="font-display text-5xl font-semibold text-plum">Your orders</h1>
      <OrdersView />
    </div>
  );
}
