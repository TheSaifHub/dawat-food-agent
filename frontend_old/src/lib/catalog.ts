// Browsing API shapes (Phase 7c, backend app/tools/browse.py, D-056). Only the fields the pages read.

export type CardBranch = { branch_id: string; label: string; area: string; street: string | null; distance_km: number };

export type RestaurantCard = {
  restaurant_id: string;
  name: string;
  cuisines: string[];
  veg_only: boolean;
  is_chain: boolean;
  branch: CardBranch;
  more_branches_in_range: number;
  delivery_fee: number;
  price_for_one: number | null;
  mild_mains: number;
  mild_friendly: boolean;
};

export type CuisineCount = { cuisine: string; restaurants: number };
export type AreaRef = { area_id: string; name: string };

export type AreaHome = {
  status: "ok" | "empty";
  area: AreaRef;
  restaurants_in_range: number;
  cuisines: CuisineCount[];
  chains: RestaurantCard[];
  max_delivery_km: number;
  free_delivery_from: number;
  message?: string;
};

export type Listing = {
  status: "ok" | "empty";
  area: AreaRef;
  filters: { cuisine: string | null; veg_only: boolean; mild: boolean; max_km: number; max_price_for_one: number | null; sort: Sort };
  total: number;
  offset: number;
  restaurants: RestaurantCard[];
  cuisine_facets: CuisineCount[];
  free_delivery_from: number;
  max_delivery_km: number;
  message?: string;
};

export type Sort = "distance" | "price" | "name";

/** Answers about the area itself (typo, outside coverage): shown as a message, never as an empty list. */
export const AREA_ANSWERS = new Set(["needs_area", "confirm_area", "unknown_area", "outside_coverage"]);

export function restaurantHref(branchId: string): string {
  return `/restaurant/${encodeURIComponent(branchId)}`;
}

export function listingHref(areaId: string, params: Record<string, string | number | boolean | null | undefined> = {}): string {
  const q = new URLSearchParams({ area: areaId });
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== "" && v !== false) q.set(k, v === true ? "1" : String(v));
  }
  return `/restaurants?${q.toString()}`;
}
