-- ════════════════════════════════════════════════════════════════════════
-- 0007 · What the user said "yes" to, and where each order goes   (D-026)
--
-- carts.confirmed_quote / confirmed_total: the fingerprint and total of the exact quote the user confirmed
--   (lines, prices, fees, GST, delivery point). place_order recomputes the quote and refuses if the
--   fingerprint differs: a price that changed after the "yes" is never charged silently.
-- orders.delivery_*: a snapshot of where the order goes (an address can be edited or deleted later; the
--   order, and Phase 8's tracking map, must keep the point it was placed for).
-- ════════════════════════════════════════════════════════════════════════

alter table public.carts
  add column if not exists confirmed_total integer check (confirmed_total >= 0),
  add column if not exists confirmed_quote text check (confirmed_quote ~ '^[0-9a-f]{20}$');

-- a confirmed or ordered cart always records what was confirmed; an open one never does
alter table public.carts add constraint carts_confirmation_recorded check (
  (status in ('confirmed', 'ordered')) = (confirmed_quote is not null and confirmed_total is not null)
  or status = 'abandoned');

alter table public.orders
  add column if not exists delivery_area_id text not null references public.areas (area_id),
  add column if not exists delivery_lat double precision not null check (delivery_lat between 17.25 and 17.60),
  add column if not exists delivery_lon double precision not null check (delivery_lon between 78.20 and 78.65);
