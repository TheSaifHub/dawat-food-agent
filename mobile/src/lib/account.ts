// What the Orders list and the Profile show, from the server's own answers (GET /orders, GET /me/preferences,
// GET /me/addresses). Nothing here adds up a price, ranks an order by anything but the time the server gave, or invents
// a status. The app never sends a user id, a price or a "source": the backend reads the user from the sign-in token.

export const ORDERS_LIMIT = 20; // the backend's maximum for GET /orders?limit=

export type HistoryItem = { item_id: string; name: string; price_paid: number; qty: number; line_total: number; is_veg: boolean };
export type HistoryOrder = {
  order_id: string;
  order_number: string;
  is_sample: boolean;
  restaurant: string;
  branch_label: string;
  order_status: string;
  items: HistoryItem[];
  total: number;
  delivery_area: string | null;
};
export type Checkout = { checkout_id: string; placed_at: string; orders: HistoryOrder[]; grand_total: number };
export type History = { status: 'ok' | 'empty'; checkouts: Checkout[]; has_more: boolean };

export type OrderRow = HistoryOrder & { placed_at: string };

const time = (iso: string): number => {
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? NaN : t;
};

/**
 * One row per order, newest first. The server already sends newest first; sorting again only guards the order of the
 * list (a stable sort by the server's own placed_at). Orders of one checkout keep the server's order.
 */
export function orderRows(h: History | null | undefined): OrderRow[] {
  if (!h || !Array.isArray(h.checkouts)) return [];
  const indexed = h.checkouts.map((c, i) => ({ c, i, t: time(c.placed_at) }));
  indexed.sort((a, b) => {
    if (Number.isNaN(a.t) || Number.isNaN(b.t) || a.t === b.t) return a.i - b.i;
    return b.t - a.t;
  });
  return indexed.flatMap(({ c }) => c.orders.map((o) => ({ ...o, placed_at: c.placed_at })));
}

/** The words for the six statuses the app shows. Anything else is not guessed at. */
const STATUS_WORDS: Record<string, string> = {
  placed: 'Placed',
  confirmed: 'Confirmed',
  preparing: 'Preparing',
  picked_up: 'Picked up',
  on_the_way: 'On the way',
  delivered: 'Delivered',
};
export const statusLabel = (s: string): string => STATUS_WORDS[s] ?? 'Status unavailable';

/** "17 Oct, 07:42 pm" in the phone's own time zone, from the server's timestamp; '' when it can't be read. */
export function placedLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

export const orderHref = (orderNumber: string) => `/orders/${encodeURIComponent(orderNumber)}` as const;

// ---- Profile ---------------------------------------------------------------------------------------------------

/** The four preferences the settings route supports, in the order the backend lists them. */
export const PREF_KEYS = ['diet', 'max_spice', 'default_area', 'language'] as const;
export type PrefKey = (typeof PREF_KEYS)[number];

export const PREF_TITLES: Record<PrefKey, string> = {
  diet: 'Diet',
  max_spice: 'Spice',
  default_area: 'Default delivery area',
  language: 'Language',
};

/** Choices for the three preferences with a fixed list. The value is exactly what the backend's route accepts. */
export const PREF_OPTIONS: Record<'diet' | 'max_spice' | 'language', { value: string | number; label: string }[]> = {
  diet: [
    { value: 'vegetarian', label: 'Vegetarian' },
    { value: 'eggetarian', label: 'Eggetarian' },
    { value: 'non_vegetarian', label: 'Non-vegetarian' },
  ],
  max_spice: [
    { value: 0, label: 'No spice' },
    { value: 1, label: 'Mild' },
    { value: 2, label: 'Medium' },
    { value: 3, label: 'Very spicy' },
  ],
  language: [
    { value: 'en', label: 'English' },
    { value: 'hinglish', label: 'Hinglish' },
    { value: 'te', label: 'Telugu' },
  ],
};

export type Pref = { value: string | number; label: string; source: string; how_saved: string; saved_at: string };
export type Prefs = { status: 'ok'; preferences: Partial<Record<PrefKey, Pref>> };

export type Address = { address_id: string; label: string; line1: string; area_id: string; area: string; is_default: boolean };
export type Addresses = { status: 'ok' | 'empty'; addresses: Address[] };

/** The body of a settings save: the value and nothing else (no source, no user id). */
export const prefBody = (value: string | number): { value: string | number } => ({ value });

export const prefPath = (key: PrefKey): string => `/me/preferences/${key}`;
