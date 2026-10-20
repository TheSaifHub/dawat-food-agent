-- ════════════════════════════════════════════════════════════════════════════════════════════════════════════
-- 0015 · name_confirmed: has this person confirmed the name Dawat shows for them?   (D-064, Google-only sign-in)
--
-- After the first Google sign-in the website shows "Confirm your name". This flag records that they did.
--   · It is a WEBSITE-FLOW flag only. Orders, cart, chat, payments and every other safety rule never read it.
--   · Additive: one new column. New profiles start false; the fixed seed users (is_demo) are marked true, so a
--     seed user signing in through the dev login doesn't meet the screen.
-- ════════════════════════════════════════════════════════════════════════════════════════════════════════════

alter table public.users
  add column if not exists name_confirmed boolean not null default false;

update public.users set name_confirmed = true where is_demo and not name_confirmed;
