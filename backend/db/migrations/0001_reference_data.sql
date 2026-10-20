-- ════════════════════════════════════════════════════════════════════════
-- 0001 · Reference data: areas, restaurants, branches, dishes, dish_aliases, menu_items   (D-020)
-- Loaded by data_pipeline/load_db.py (3e) from data/processed/ and data/reference/.
-- Read-only for app users. No browser access: the website reads through the FastAPI backend.
-- Each dish and each alias is stored ONCE; a menu item is just (restaurant, dish, price).
-- ════════════════════════════════════════════════════════════════════════

create extension if not exists pg_trgm with schema extensions;   -- fuzzy matching ("biriyani", "kodi biryni")

-- ─── areas (170, data/reference/localities.csv) ─────────────────────────
create table if not exists public.areas (
  area_id   text primary key check (area_id ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  name      text not null unique,
  name_te   text,                                            -- Telugu name from OSM, if any
  lat       double precision not null check (lat between 17.25 and 17.60),   -- OSM relation 7868535 bbox, padded
  lon       double precision not null check (lon between 78.20 and 78.65),
  source    text not null check (source in ('osm', 'hand-added'))
);

create table if not exists public.area_aliases (
  area_id    text not null references public.areas (area_id) on delete cascade,
  alias      text not null,
  alias_norm text not null,                                  -- lower-cased, punctuation removed (same rule as dishes)
  primary key (area_id, alias_norm),
  unique (alias_norm)                                        -- an alias names exactly one area
);

-- ─── restaurants (brand level, 1,112) and branches (place level, 1,340) ─
create table if not exists public.restaurants (
  restaurant_id   text primary key,
  name            text not null,
  is_chain        boolean not null,
  branch_count    integer not null check (branch_count >= 1),
  cuisines        text[] not null check (cardinality(cuisines) between 1 and 3),
  primary_cuisine text not null,
  veg_only        boolean not null,
  meal_capable    boolean not null,                          -- a main + side/bread/rice can be built (planner rule)
  price_band      text not null,
  price_level     numeric(4, 3) not null check (price_level between 0 and 1),
  check (primary_cuisine = cuisines[1]),
  check (is_chain = (branch_count >= 2))
);
create index if not exists restaurants_name_trgm_idx on public.restaurants using gin (lower(name) extensions.gin_trgm_ops);

create table if not exists public.branches (
  branch_id       text primary key,
  restaurant_id   text not null references public.restaurants (restaurant_id) on delete restrict,
  label           text not null,                             -- "Madhapur", "Madhapur 2"
  osm_ref         text not null unique check (osm_ref ~ '^(node|way|relation)/[0-9]+$'),
  osm_name        text not null,                             -- name as mapped in OSM (attribution, traceability)
  amenity         text not null check (amenity in ('restaurant', 'fast_food', 'cafe')),
  lat             double precision not null check (lat between 17.25 and 17.60),
  lon             double precision not null check (lon between 78.20 and 78.65),
  area_id         text not null references public.areas (area_id),
  area_method     text not null check (area_method in ('address tag', 'nearest area')),
  area_distance_m integer not null check (area_distance_m >= 0),
  street          text,
  postcode        text,
  open_for_demo   boolean not null default true,             -- planner/tools only use open branches
  unique (restaurant_id, label)
);
create index if not exists branches_restaurant_idx on public.branches (restaurant_id);
create index if not exists branches_area_idx on public.branches (area_id);

-- ─── dishes (319) and their aliases (≈1,815), each stored once ──────────
create table if not exists public.dishes (
  dish_id     text primary key check (dish_id ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  name        text not null unique,
  category    text not null check (category in (
                'biryani', 'mandi', 'kebab', 'starter', 'curry', 'bread', 'rice', 'noodles', 'soup', 'salad', 'pizza',
                'pasta', 'burger', 'sandwich', 'roll', 'shawarma', 'fried_chicken', 'mexican', 'continental',
                'breakfast', 'tiffin', 'meals', 'snack', 'bakery', 'dessert', 'drink')),
  course      text not null check (course in ('main', 'side', 'dessert', 'drink')),
  is_veg      boolean not null,                              -- egg counts as non-veg (D-017)
  spice_level smallint not null check (spice_level between 0 and 3),
  serves      smallint not null check (serves in (1, 2)),
  price_low   integer not null check (price_low > 0),
  price_high  integer not null check (price_high >= price_low and price_high <= 1500),
  notes       text
);

create table if not exists public.dish_aliases (
  dish_id    text not null references public.dishes (dish_id) on delete cascade,
  alias      text not null,                                  -- as written: "kodi biryani", "కోడి బిర్యానీ"
  alias_norm text not null,                                  -- normalised form used for matching
  script     text not null check (script in ('latin', 'telugu')),
  primary key (dish_id, alias_norm),
  unique (alias_norm)                                        -- an alias identifies exactly one dish (D-017)
);
create index if not exists dish_aliases_trgm_idx on public.dish_aliases using gin (alias_norm extensions.gin_trgm_ops);

-- ─── menu items (23,780): only the restaurant's price for a dish ───────
create table if not exists public.menu_items (
  item_id       text primary key,
  restaurant_id text not null references public.restaurants (restaurant_id) on delete restrict,
  dish_id       text not null references public.dishes (dish_id) on delete restrict,
  price         integer not null check (price > 0),          -- whole rupees
  is_available  boolean not null default true,
  unique (restaurant_id, dish_id),
  check (item_id = restaurant_id || '__' || dish_id)
);
create index if not exists menu_items_dish_idx on public.menu_items (dish_id);

-- ─── guards: the veg promise and price ranges, enforced by the database ─
-- A menu item's price must sit inside its dish's range, and a veg-only restaurant can never list a non-veg dish.
create or replace function public.menu_items_guard() returns trigger
language plpgsql set search_path = '' as $$
declare
  d_low integer; d_high integer; d_veg boolean; r_veg_only boolean;
begin
  select price_low, price_high, is_veg into d_low, d_high, d_veg from public.dishes where dish_id = new.dish_id;
  if new.price < d_low or new.price > d_high then
    raise exception 'menu item %: price % outside dish range %..%', new.item_id, new.price, d_low, d_high
      using errcode = 'check_violation';
  end if;
  select veg_only into r_veg_only from public.restaurants where restaurant_id = new.restaurant_id;
  if r_veg_only and not d_veg then
    raise exception 'veg-only restaurant % cannot list non-veg dish %', new.restaurant_id, new.dish_id
      using errcode = 'check_violation';
  end if;
  return new;
end $$;
create or replace trigger menu_items_guard
  before insert or update on public.menu_items for each row execute function public.menu_items_guard();

-- The same promise from the other two sides: a dish on a veg-only menu cannot become non-veg,
-- and a restaurant with non-veg items cannot be switched to veg-only.
create or replace function public.dishes_veg_guard() returns trigger
language plpgsql set search_path = '' as $$
begin
  if old.is_veg and not new.is_veg and exists (
      select 1 from public.menu_items m join public.restaurants r using (restaurant_id)
      where m.dish_id = new.dish_id and r.veg_only) then
    raise exception 'dish % is on a veg-only menu and cannot become non-veg', new.dish_id using errcode = 'check_violation';
  end if;
  return new;
end $$;
create or replace trigger dishes_veg_guard
  before update of is_veg on public.dishes for each row execute function public.dishes_veg_guard();

create or replace function public.restaurants_veg_guard() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.veg_only and not old.veg_only and exists (
      select 1 from public.menu_items m join public.dishes d using (dish_id)
      where m.restaurant_id = new.restaurant_id and not d.is_veg) then
    raise exception 'restaurant % has non-veg items and cannot become veg-only', new.restaurant_id using errcode = 'check_violation';
  end if;
  return new;
end $$;
create or replace trigger restaurants_veg_guard
  before update of veg_only on public.restaurants for each row execute function public.restaurants_veg_guard();

-- ─── convenience view: a menu item with its dish's fields ──────────────
-- security_invoker: the view runs with the caller's permissions, never the owner's.
create or replace view public.menu_items_full with (security_invoker = true) as
select m.item_id, m.restaurant_id, m.dish_id, d.name, m.price, d.is_veg, d.spice_level, d.serves,
       d.category, d.course, m.is_available,
       coalesce((select array_agg(a.alias order by a.alias) from public.dish_aliases a where a.dish_id = d.dish_id),
                '{}'::text[]) as aliases
from public.menu_items m
join public.dishes d using (dish_id);
