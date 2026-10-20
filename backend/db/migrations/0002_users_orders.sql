-- ════════════════════════════════════════════════════════════════════════
-- 0002 · Users, preferences, addresses, carts, orders, tracking   (D-020)
-- Money is whole rupees (menu prices are whole rupees; taxes are rounded server-side in Phase 4).
-- All totals are computed by the backend; the database re-checks that they add up.
-- CONFIRMATION GATE: an order can only be created from a cart whose status is 'confirmed'.
-- ════════════════════════════════════════════════════════════════════════

create or replace function public.touch_updated_at() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  return new;
end $$;

-- ─── users: 1:1 with Supabase Auth; no real personal data (demo accounts are fictional) ─
create table if not exists public.users (
  user_id      uuid primary key references auth.users (id) on delete cascade,
  display_name text not null check (char_length(display_name) between 1 and 60),
  is_demo      boolean not null default false,
  created_at   timestamptz not null default now()
);

create table if not exists public.user_preferences (
  user_id    uuid not null references public.users (user_id) on delete cascade,
  key        text not null check (key in ('diet', 'max_spice', 'default_area', 'language')),
  value      jsonb not null,
  updated_at timestamptz not null default now(),
  primary key (user_id, key),
  check (
    (key = 'diet' and value in ('"vegetarian"'::jsonb, '"eggetarian"'::jsonb, '"non_vegetarian"'::jsonb))
    or (key = 'max_spice' and jsonb_typeof(value) = 'number' and value::integer between 0 and 3)
    or (key in ('default_area', 'language') and jsonb_typeof(value) = 'string')
  )
);
create or replace trigger user_preferences_touch
  before update on public.user_preferences for each row execute function public.touch_updated_at();

create table if not exists public.addresses (
  address_id uuid primary key default gen_random_uuid(),
  user_id    uuid not null references public.users (user_id) on delete cascade,
  label      text not null check (char_length(label) between 1 and 30),       -- "Home", "Office"
  line1      text not null check (char_length(line1) between 1 and 200),
  area_id    text not null references public.areas (area_id),
  lat        double precision check (lat between 17.25 and 17.60),
  lon        double precision check (lon between 78.20 and 78.65),
  is_default boolean not null default false,
  created_at timestamptz not null default now()
);
create index if not exists addresses_user_idx on public.addresses (user_id);
create unique index if not exists addresses_one_default_idx on public.addresses (user_id) where is_default;

-- ─── carts: open → confirmed (explicit "yes") → ordered ─────────────────
create table if not exists public.carts (
  cart_id      uuid primary key default gen_random_uuid(),
  user_id      uuid not null references public.users (user_id) on delete cascade,
  status       text not null default 'open' check (status in ('open', 'confirmed', 'ordered', 'abandoned')),
  confirmed_at timestamptz,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  check (status not in ('confirmed', 'ordered') or confirmed_at is not null)
);
create index if not exists carts_user_idx on public.carts (user_id);
create unique index if not exists carts_one_open_per_user_idx on public.carts (user_id) where status = 'open';
create or replace trigger carts_touch
  before update on public.carts for each row execute function public.touch_updated_at();

-- No price column: prices are always read from menu_items at the moment totals are computed.
create table if not exists public.cart_items (
  cart_id   uuid not null references public.carts (cart_id) on delete cascade,
  item_id   text not null references public.menu_items (item_id) on delete restrict,
  branch_id text not null references public.branches (branch_id) on delete restrict,
  qty       integer not null check (qty between 1 and 20),
  added_at  timestamptz not null default now(),
  primary key (cart_id, item_id, branch_id)
);
create index if not exists cart_items_branch_idx on public.cart_items (branch_id);

-- Items can only change while the cart is open (a confirmed cart must be re-opened, which drops the
-- confirmation, so nothing can be slipped in after the user said "yes"). The item must be on the
-- branch's restaurant menu, available, and the branch open for the demo.
create or replace function public.cart_items_guard() returns trigger
language plpgsql set search_path = '' as $$
declare
  c_status text; item_restaurant text; item_available boolean; branch_restaurant text; branch_open boolean;
begin
  select status into c_status from public.carts where cart_id = coalesce(new.cart_id, old.cart_id);
  if c_status is null then
    return coalesce(new, old);            -- the cart itself is being deleted (cascade)
  end if;
  if c_status <> 'open' then
    raise exception 'cart % is %; items can only change while it is open', coalesce(new.cart_id, old.cart_id), c_status
      using errcode = 'check_violation';
  end if;
  if tg_op = 'DELETE' then
    return old;
  end if;
  select restaurant_id, is_available into item_restaurant, item_available from public.menu_items where item_id = new.item_id;
  select restaurant_id, open_for_demo into branch_restaurant, branch_open from public.branches where branch_id = new.branch_id;
  if item_restaurant is distinct from branch_restaurant then
    raise exception 'item % is not on the menu of branch %', new.item_id, new.branch_id using errcode = 'check_violation';
  end if;
  if not item_available or not branch_open then
    raise exception 'item % or branch % is not available', new.item_id, new.branch_id using errcode = 'check_violation';
  end if;
  return new;
end $$;
create or replace trigger cart_items_guard
  before insert or update or delete on public.cart_items for each row execute function public.cart_items_guard();

-- ─── orders: one per branch; a multi-restaurant checkout shares a checkout_id ─
create table if not exists public.orders (
  order_id            uuid primary key default gen_random_uuid(),
  checkout_id         uuid not null,
  user_id             uuid not null references public.users (user_id) on delete restrict,
  cart_id             uuid not null references public.carts (cart_id) on delete restrict,
  branch_id           text not null references public.branches (branch_id),
  address_id          uuid references public.addresses (address_id),
  status              text not null default 'placed' check (status in (
                        'placed', 'confirmed', 'preparing', 'picked_up', 'on_the_way', 'delivered', 'cancelled')),
  items_total         integer not null check (items_total > 0),
  delivery_fee        integer not null check (delivery_fee >= 0),
  taxes               integer not null check (taxes >= 0),
  grand_total         integer not null,
  payment_status      text not null default 'pending' check (payment_status in ('pending', 'paid', 'failed', 'refunded')),
  razorpay_order_id   text,
  razorpay_payment_id text,
  created_at          timestamptz not null default now(),
  check (grand_total = items_total + delivery_fee + taxes),
  unique (checkout_id, branch_id)
);
create index if not exists orders_user_idx on public.orders (user_id, created_at desc);
create index if not exists orders_cart_idx on public.orders (cart_id);

-- THE CONFIRMATION GATE (second layer; place_order checks in code first).
-- The tools layer inserts every order of a checkout while the cart is 'confirmed', then marks it 'ordered'.
create or replace function public.orders_require_confirmed_cart() returns trigger
language plpgsql set search_path = '' as $$
declare
  c_status text; c_user uuid;
begin
  select status, user_id into c_status, c_user from public.carts where cart_id = new.cart_id for update;
  if c_status is null then
    raise exception 'order refused: cart % does not exist', new.cart_id using errcode = 'check_violation';
  end if;
  if c_user <> new.user_id then
    raise exception 'order refused: cart % belongs to another user', new.cart_id using errcode = 'check_violation';
  end if;
  if c_status <> 'confirmed' then
    raise exception 'order refused: cart % is %, not confirmed', new.cart_id, c_status using errcode = 'check_violation';
  end if;
  if not exists (select 1 from public.cart_items where cart_id = new.cart_id and branch_id = new.branch_id) then
    raise exception 'order refused: cart % has no items from branch %', new.cart_id, new.branch_id using errcode = 'check_violation';
  end if;
  return new;
end $$;
create or replace trigger orders_require_confirmed_cart
  before insert on public.orders for each row execute function public.orders_require_confirmed_cart();

-- Snapshot of what was ordered, at the price charged.
create table if not exists public.order_items (
  order_id   uuid not null references public.orders (order_id) on delete cascade,
  item_id    text not null references public.menu_items (item_id) on delete restrict,
  dish_name  text not null,
  unit_price integer not null check (unit_price > 0),
  qty        integer not null check (qty between 1 and 20),
  is_veg     boolean not null,
  primary key (order_id, item_id)
);

-- At commit time, an order's items_total must equal the sum of its items (deferred, so the backend
-- can insert the order and its items in one transaction).
create or replace function public.check_order_items_total() returns trigger
language plpgsql set search_path = '' as $$
declare
  o_id uuid := coalesce(new.order_id, old.order_id);
  expected integer; actual integer;
begin
  select items_total into expected from public.orders where order_id = o_id;
  if expected is null then
    return null;                          -- order deleted
  end if;
  select coalesce(sum(unit_price * qty), 0) into actual from public.order_items where order_id = o_id;
  if actual <> expected then
    raise exception 'order %: items add up to %, but items_total is %', o_id, actual, expected using errcode = 'check_violation';
  end if;
  return null;
end $$;
-- Constraint triggers can't use OR REPLACE; migrate.py applies each file exactly once.
-- Their names become constraint names too, so they must not clash with Postgres's auto-named CHECK
-- constraints (e.g. orders_items_total_check for "items_total > 0"); --test caught exactly that.
create constraint trigger order_items_sum_matches_order
  after insert or update or delete on public.order_items
  deferrable initially deferred for each row execute function public.check_order_items_total();
create constraint trigger orders_total_matches_items
  after insert or update of items_total on public.orders
  deferrable initially deferred for each row execute function public.check_order_items_total();

-- ─── simulated tracking: status timeline + rider position ──────────────
create table if not exists public.order_status_events (
  event_id   bigint generated always as identity primary key,
  order_id   uuid not null references public.orders (order_id) on delete cascade,
  status     text not null check (status in (
               'placed', 'confirmed', 'preparing', 'picked_up', 'on_the_way', 'delivered', 'cancelled')),
  rider_lat  double precision,
  rider_lon  double precision,
  created_at timestamptz not null default now()
);
create index if not exists order_status_events_order_idx on public.order_status_events (order_id, created_at);
