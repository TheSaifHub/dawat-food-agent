-- ════════════════════════════════════════════════════════════════════════
-- 0008 · How every saved preference got there   (D-027)
--
-- Saif's rule: a preference is saved only when the user explicitly asks ("remember I'm vegetarian"), says yes
-- to Dawat AI's offer to save it, or sets it on the website's settings screen. Never inferred, never silent.
-- user_preferences.source records which of those it was (or 'seed' for the fictional demo users), so the
-- profile page and the agent can say "you asked me to remember this", and evals can audit every row.
-- No default after the backfill: a write that doesn't say where it came from is refused by the database.
-- language: only the three languages Dawat AI speaks (CLAUDE.md, Phase 6).
-- ════════════════════════════════════════════════════════════════════════

alter table public.user_preferences add column if not exists source text not null default 'seed'
  check (source in ('chat_request', 'chat_confirmed', 'settings', 'seed'));
alter table public.user_preferences alter column source drop default;

alter table public.user_preferences add constraint user_preferences_language_check
  check (key <> 'language' or value in ('"en"'::jsonb, '"hinglish"'::jsonb, '"te"'::jsonb));
