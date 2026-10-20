-- ════════════════════════════════════════════════════════════════════════════════════════════════════════════
-- 0011 · A daily count of chat messages across ALL users, for the global demo cap   (D-048)
--
-- Per-visitor demo accounts (anonymous sign-in) mean anyone can make many accounts, so the per-user hourly limit
-- alone can't protect the free Gemini quota. POST /chat takes one slot per message from today's row (the day in
-- IST) with a single atomic statement that only increments while the count is below the cap, so concurrent
-- messages can never push it past the cap.
-- Additive only: one new table. No existing row or column changes.
-- ════════════════════════════════════════════════════════════════════════════════════════════════════════════

create table if not exists public.chat_daily_usage (
  day        date primary key,                                  -- the IST calendar day
  count      integer not null default 0 check (count >= 0),
  updated_at timestamptz not null default now()
);

-- Backend only (it connects as the table owner); the browser roles get nothing.
alter table public.chat_daily_usage enable row level security;
revoke all on public.chat_daily_usage from anon, authenticated;
