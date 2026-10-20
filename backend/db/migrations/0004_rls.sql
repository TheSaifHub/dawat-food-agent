-- ════════════════════════════════════════════════════════════════════════
-- 0004 · Row Level Security and privileges   (D-020, approved by Saif: backend-only data access)
--
-- How data is reached:
--   · The FastAPI backend connects directly to Postgres (DATABASE_URL). It is the table owner, which
--     Postgres exempts from RLS, so the backend scopes every query to the verified user in code.
--   · The browser uses Supabase only for login. It gets NO table privileges here, so the Data API
--     can read or write nothing (auto-expose of new tables is off in the dashboard as well).
--   · RLS is still ON everywhere, with "own rows only" policies on user-owned tables: a second layer
--     in case a table is ever exposed later. Reference tables get no policies (deny by default).
-- ════════════════════════════════════════════════════════════════════════

-- ─── RLS on, everywhere ─────────────────────────────────────────────────
alter table public.areas               enable row level security;
alter table public.area_aliases        enable row level security;
alter table public.restaurants         enable row level security;
alter table public.branches            enable row level security;
alter table public.dishes              enable row level security;
alter table public.dish_aliases        enable row level security;
alter table public.menu_items          enable row level security;
alter table public.users               enable row level security;
alter table public.user_preferences    enable row level security;
alter table public.addresses           enable row level security;
alter table public.carts               enable row level security;
alter table public.cart_items          enable row level security;
alter table public.orders              enable row level security;
alter table public.order_items         enable row level security;
alter table public.order_status_events enable row level security;
alter table public.conversations       enable row level security;
alter table public.messages            enable row level security;
alter table public.agent_traces        enable row level security;

-- ─── no browser privileges (explicit, in case any default grant exists) ─
revoke all on all tables    in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
revoke execute on function
  public.menu_items_guard(), public.dishes_veg_guard(), public.restaurants_veg_guard(), public.touch_updated_at(),
  public.cart_items_guard(), public.orders_require_confirmed_cart(), public.check_order_items_total()
  from public, anon, authenticated;

-- ─── "own rows only" policies (second layer; inactive while no privileges are granted) ─
-- (select auth.uid()) is evaluated once per query, not once per row.
create policy users_own_select on public.users
  for select to authenticated using (user_id = (select auth.uid()));

create policy user_preferences_own_all on public.user_preferences
  for all to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy addresses_own_all on public.addresses
  for all to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy carts_own_select on public.carts
  for select to authenticated using (user_id = (select auth.uid()));

create policy cart_items_own_select on public.cart_items
  for select to authenticated using (exists (
    select 1 from public.carts c where c.cart_id = cart_items.cart_id and c.user_id = (select auth.uid())));

-- Orders are created and changed only by the backend; users may only read their own.
create policy orders_own_select on public.orders
  for select to authenticated using (user_id = (select auth.uid()));

create policy order_items_own_select on public.order_items
  for select to authenticated using (exists (
    select 1 from public.orders o where o.order_id = order_items.order_id and o.user_id = (select auth.uid())));

create policy order_status_events_own_select on public.order_status_events
  for select to authenticated using (exists (
    select 1 from public.orders o where o.order_id = order_status_events.order_id and o.user_id = (select auth.uid())));

create policy conversations_own_select on public.conversations
  for select to authenticated using (user_id = (select auth.uid()));

create policy messages_own_select on public.messages
  for select to authenticated using (exists (
    select 1 from public.conversations c where c.conversation_id = messages.conversation_id and c.user_id = (select auth.uid())));

create policy agent_traces_own_select on public.agent_traces
  for select to authenticated using (exists (
    select 1 from public.conversations c where c.conversation_id = agent_traces.conversation_id and c.user_id = (select auth.uid())));
