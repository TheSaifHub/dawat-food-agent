-- ════════════════════════════════════════════════════════════════════════════════════════════════════════════
-- 0010 · A version stamp for the reference data, so the backend can cache it in memory   (D-053)
--
-- The backend keeps areas, restaurants, branches, dishes, aliases, food terms and every menu item in memory, so
-- browsing, dish search and the planner don't re-read them from the database on every request (egress on the free
-- tier). To know when its copy is out of date it reads ONE row: public.reference_version. Any insert, update,
-- delete or truncate on a reference table stamps a new random version (statement-level triggers, so a 23,784-row
-- seed stamps once per statement, not per row). A random uuid, not a counter: two different changes that are both
-- rolled back (tests) can never leave the same version behind.
-- Additive only: one new table, one function, eight triggers. No existing row or column changes.
-- ════════════════════════════════════════════════════════════════════════════════════════════════════════════

create table if not exists public.reference_version (
  id         smallint primary key default 1 check (id = 1),
  version    uuid not null default gen_random_uuid(),
  changed_at timestamptz not null default now()
);
insert into public.reference_version (id) values (1) on conflict (id) do nothing;

alter table public.reference_version enable row level security;
revoke all on public.reference_version from anon, authenticated;

create or replace function public.bump_reference_version() returns trigger
  language plpgsql
  set search_path = ''
as $$
begin
  update public.reference_version set version = gen_random_uuid(), changed_at = now() where id = 1;
  return null;
end $$;
revoke execute on function public.bump_reference_version() from public, anon, authenticated;

do $$
declare t text;
begin
  foreach t in array array['areas', 'area_aliases', 'restaurants', 'branches', 'dishes', 'dish_aliases', 'food_terms',
                           'menu_items']
  loop
    execute format('create or replace trigger %I after insert or update or delete or truncate on public.%I '
                   'for each statement execute function public.bump_reference_version()',
                   t || '_bump_reference_version', t);
  end loop;
end $$;
