-- ════════════════════════════════════════════════════════════════════════════════════════════════════════════
-- 0013 · Short order numbers: "#DW1042" instead of a UUID   (Saif, Session 15; Phase 7e, D-057)
--
-- People read order numbers out loud and type them into the chat ("track DW1042"), so every order gets a short
-- number from a database sequence: unique, never reused, never typed by the client. The order_id UUID stays the
-- real key; the number is only a label. Lookups by number are still scoped to the signed-in user (track_order).
-- Additive only: one new column, filled for existing orders by Postgres when it is added, plus a unique index.
-- ════════════════════════════════════════════════════════════════════════════════════════════════════════════

alter table public.orders
  add column if not exists order_no bigint generated always as identity (start with 1001);

create unique index if not exists orders_order_no_idx on public.orders (order_no);
