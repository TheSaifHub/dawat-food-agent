// Past orders and tracking (Phase 7g). Everything shown comes from the backend: GET /orders (get_user_history, the
// prices paid then) and GET /orders/{DW number} (track_order, scoped to the signed-in user). The website adds only
// words and dates; it computes no amount.

export type OrderItem = { item_id: string; name: string; price_paid: number; qty: number; line_total: number; is_veg: boolean };

export type HistoryOrder = {
  order_id: string;
  order_number: string;            // "DW1042"
  is_sample: boolean;
  restaurant: string;
  branch_id: string;
  branch_label: string;
  order_status: OrderStatus;
  payment_status: string;
  items: OrderItem[];
  items_total: number;
  delivery_fee: number;
  taxes: number;
  total: number;
  delivery_area: string;
};

export type Checkout = { checkout_id: string; placed_at: string; orders: HistoryOrder[]; grand_total: number };
export type History = { status: "ok" | "empty"; checkouts: Checkout[]; has_more: boolean };

export type OrderStatus = "placed" | "confirmed" | "preparing" | "picked_up" | "on_the_way" | "delivered" | "cancelled";

export type Tracked = {
  status: "ok";
  order_id: string;
  order_number: string;
  order_status: OrderStatus;
  payment_status: string;
  restaurant: string;
  branch_id: string;
  branch_label: string;
  delivery_area: string;
  is_sample: boolean;
  items: { item_id: string; dish_name: string; unit_price: number; qty: number; is_veg: boolean }[];
  items_total: number;
  delivery_fee: number;
  taxes: number;
  total: number;
  placed_at: string;
  timeline: { status: OrderStatus; at: string }[];
};

/** The history page shows the 20 most recent checkouts (the backend's maximum). */
export const HISTORY_LIMIT = 20;

export const STATUS_LABELS: Record<OrderStatus, string> = {
  placed: "Placed",
  confirmed: "Confirmed by the restaurant",
  preparing: "Being prepared",
  picked_up: "Picked up",
  on_the_way: "On the way",
  delivered: "Delivered",
  cancelled: "Cancelled",
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[status as OrderStatus] ?? status;
}

export function paymentLabel(status: string): string {
  return status === "paid" ? "Paid" : status === "pending" ? "Payment pending (demo)" : status === "refunded" ? "Refunded"
    : status === "failed" ? "Payment failed" : status;
}

/** Still moving: no delivery time is shown, and the page says why (7g choice 2). */
export function isOpen(status: string): boolean {
  return status !== "delivered" && status !== "cancelled";
}

/** "DW1042" → "/orders/DW1042". */
export function orderHref(orderNumber: string): string {
  return `/orders/${encodeURIComponent(orderNumber.replace(/^#/, ""))}`;
}

const DATE = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit",
});

/** A backend timestamp as Hyderabad time, e.g. "7 Oct 2026, 12:05 am". */
export function when(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : DATE.format(d);
}
