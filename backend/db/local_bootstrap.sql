-- Local stand-ins for the pieces of Supabase that Dawat's migrations and code rely on (D-052).
-- Runs ONLY on the local test database (backend/db/local_setup.py checks the host first). Idempotent.
--
-- What Supabase provides and a plain PostgreSQL 17 doesn't:
--   roles anon / authenticated / service_role   migrations revoke table access from them (0004, 0005, 0006)
--   schema extensions                           pg_trgm is created there (0001) and its operator class used
--   schema auth, auth.users                     public.users.user_id references auth.users(id) (0002);
--                                               app/tools/users.py reads auth.users to create a profile
--   auth.uid()                                  the RLS policies (0004)
-- These are minimal: only the columns and behaviour our code touches. Real sign-in is never tested locally;
-- tests sign their own throwaway tokens (tests/conftest.py).

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon nologin noinherit; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated nologin noinherit; end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then create role service_role nologin noinherit bypassrls; end if;
end $$;

create schema if not exists extensions;
create schema if not exists auth;

create table if not exists auth.users (
  id                 uuid primary key,
  email              text unique,
  raw_user_meta_data jsonb not null default '{}'::jsonb,
  is_anonymous       boolean not null default false,
  created_at         timestamptz not null default now()
);

-- Same definition as Supabase's: the signed-in user's id from the request's JWT claims, or null.
create or replace function auth.uid() returns uuid
  language sql stable
as $$
  select coalesce(
    nullif(current_setting('request.jwt.claim.sub', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')
  )::uuid
$$;

grant usage on schema auth to anon, authenticated, service_role;
grant usage on schema extensions to anon, authenticated, service_role;
