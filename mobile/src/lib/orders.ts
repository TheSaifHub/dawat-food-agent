// Order tracking (simulated, D-061). Everything shown comes from GET /orders/{order}: the status, the timeline, the
// rider's position and the bill. There is no delivery estimate anywhere: the backend sends none and the app invents none.

export type OrderStatus = 'placed' | 'confirmed' | 'preparing' | 'picked_up' | 'on_the_way' | 'delivered' | 'cancelled';
export type LatLon = { lat: number; lon: number };

export type Track = {
  status: string;
  order_id: string;
  order_number: string;
  order_status: OrderStatus;
  payment_status: string;
  restaurant: string;
  branch_label: string;
  delivery_area: string | null;
  is_sample: boolean;
  items: { item_id: string; dish_name: string; unit_price: number; qty: number; is_veg: boolean }[];
  items_total: number;
  delivery_fee: number;
  taxes: number;
  total: number;
  placed_at: string;
  timeline: { status: OrderStatus; at: string }[];
  simulated_tracking: boolean;
  route: { from: LatLon; to: LatLon };
  rider: (LatLon & { stage: 'picked_up' | 'on_the_way' | 'delivered' }) | null;
  next_update_in_s: number | null;
};

export const STEPS: { status: OrderStatus; label: string }[] = [
  { status: 'placed', label: 'Placed' },
  { status: 'confirmed', label: 'Confirmed' },
  { status: 'preparing', label: 'Preparing' },
  { status: 'picked_up', label: 'Picked up' },
  { status: 'on_the_way', label: 'On the way' },
  { status: 'delivered', label: 'Delivered' },
];

export const MIN_POLL_MS = 5_000;

/**
 * When to ask again, or null to stop. While the rider is on the way: every 5 s (the position changes on every read).
 * Otherwise when the backend says the next change is due (never sooner than 5 s). Nothing moves after delivery, for
 * a cancelled order, or when the order is not simulated (an unpaid order or a demo account's sample order).
 */
export function nextPollDelayMs(o: Track): number | null {
  if (o.order_status === 'delivered' || o.order_status === 'cancelled' || !o.simulated_tracking) return null;
  if (o.rider?.stage === 'on_the_way') return MIN_POLL_MS;
  if (o.next_update_in_s === null || o.next_update_in_s === undefined) return null;
  return Math.max(MIN_POLL_MS, o.next_update_in_s * 1000);
}

/** The time a status was reached, from the server's timeline (local time, hours and minutes), or null if not yet. */
export function reachedAt(o: Track, status: OrderStatus): string | null {
  const hit = o.timeline.find((t) => t.status === status);
  if (!hit) return null;
  const d = new Date(hit.at);
  return Number.isNaN(d.getTime()) ? null : d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
}

/** Maps points into a w x h box (with padding) for the plain fallback map: x grows east, y grows south. */
export function projectPoints(points: LatLon[], w: number, h: number, pad = 28): { x: number; y: number }[] {
  const lats = points.map((p) => p.lat);
  const lons = points.map((p) => p.lon);
  const minLat = Math.min(...lats), maxLat = Math.max(...lats);
  const minLon = Math.min(...lons), maxLon = Math.max(...lons);
  const spanLat = Math.max(maxLat - minLat, 1e-6);
  const spanLon = Math.max(maxLon - minLon, 1e-6);
  const innerW = w - 2 * pad, innerH = h - 2 * pad;
  // one scale for both axes, so distances are not stretched, centred in the box
  const scale = Math.min(innerW / spanLon, innerH / spanLat);
  const offX = pad + (innerW - spanLon * scale) / 2;
  const offY = pad + (innerH - spanLat * scale) / 2;
  return points.map((p) => ({ x: offX + (p.lon - minLon) * scale, y: offY + (maxLat - p.lat) * scale }));
}

// ---- Map labels that do not overlap -----------------------------------------------------------------------------

export type LabelSide = 'top' | 'bottom' | 'left' | 'right';
const SIDES: LabelSide[] = ['top', 'bottom', 'right', 'left'];
const LABEL_H = 16;
const DOT_R = 14;
const GAP = 4;

/** Rough pixel width of a label (the maps draw them in a small bold font). */
export const labelWidth = (text: string): number => text.length * 7 + 8;

type Box = [number, number, number, number];
const labelBox = (side: LabelSide, p: { x: number; y: number }, w: number): Box => {
  const o = DOT_R + GAP;
  if (side === 'top') return [p.x - w / 2, p.y - o - LABEL_H, p.x + w / 2, p.y - o];
  if (side === 'bottom') return [p.x - w / 2, p.y + o, p.x + w / 2, p.y + o + LABEL_H];
  if (side === 'right') return [p.x + o, p.y - LABEL_H / 2, p.x + o + w, p.y + LABEL_H / 2];
  return [p.x - o - w, p.y - LABEL_H / 2, p.x - o, p.y + LABEL_H / 2];
};
const hit = (a: Box, b: Box) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];

/**
 * Which side of its dot each label goes on so that no two labels overlap each other or another dot. Points are in map
 * pixels. Labels are placed in order, each on the first side (top, bottom, right, left) that is free; if none is free
 * the first is used. Labels stay on top when the points are far apart. (A copy of this rule runs inside the Leaflet
 * map in lib/osm.ts; a test keeps the two the same.)
 */
export function placeLabels(points: { x: number; y: number }[], texts: string[]): LabelSide[] {
  const dots: Box[] = points.map((p) => [p.x - DOT_R, p.y - DOT_R, p.x + DOT_R, p.y + DOT_R]);
  const placed: Box[] = [];
  return points.map((p, i) => {
    const w = labelWidth(texts[i]);
    let pick: LabelSide = SIDES[0];
    let found = false;
    for (const s of SIDES) {
      const b = labelBox(s, p, w);
      if (!placed.some((q) => hit(b, q)) && !dots.some((d, j) => j !== i && hit(b, d))) {
        pick = s;
        found = true;
        break;
      }
    }
    placed.push(labelBox(found ? pick : SIDES[0], p, w));
    return found ? pick : SIDES[0];
  });
}

/** Where to draw a label (left, top, width in map pixels) for a dot at `p` on the chosen side. */
export function labelRect(side: LabelSide, p: { x: number; y: number }, text: string): { left: number; top: number; width: number; height: number } {
  const b = labelBox(side, p, labelWidth(text));
  return { left: b[0], top: b[1], width: b[2] - b[0], height: b[3] - b[1] };
}
