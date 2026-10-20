-- ════════════════════════════════════════════════════════════════════════════════════════════════════════════
-- 0012 · Per-visitor demo accounts: which persona an account plays, and which orders are samples   (D-048)
--
-- "Try as Priya / Arjun" signs a visitor in anonymously, then POST /demo/start seeds that account once.
--   users.demo_persona  set once, atomically, by /demo/start; null for every other account. It also lets the
--                       Phase 10 clean-up find visitor accounts. (users.is_demo still means the three fixed seed
--                       users from load_db.py, D-021.)
--   orders.is_sample    true for the past orders /demo/start creates through the real tools and then backdates,
--                       so the site can label them "sample orders". Every real order keeps the default false.
-- Additive only: two new columns with safe defaults. No existing row changes meaning.
-- ════════════════════════════════════════════════════════════════════════════════════════════════════════════

alter table public.users
  add column if not exists demo_persona text check (demo_persona in ('priya', 'arjun'));

alter table public.orders
  add column if not exists is_sample boolean not null default false;
