-- ════════════════════════════════════════════════════════════════════════
-- 0005 · food_terms: the food lexicon, for understanding dish requests   (D-024)
-- Loaded by data_pipeline/load_db.py from data/reference/food_lexicon.csv.
-- search_dishes reads it once per server process (with dishes and dish_aliases) to understand
-- "rendu kodi biryani karam kam": numbers, ingredients (kodi = chicken), diet and spice words.
-- Reference data like 0001: no browser access, RLS on with no policies (deny by default).
-- ════════════════════════════════════════════════════════════════════════

create table if not exists public.food_terms (
  term_norm text primary key,                                -- normalised as dish_aliases.alias_norm
  term      text not null,                                   -- as written: "karam lekunda", "కోడి"
  means     text not null check (length(trim(means)) > 0),   -- "not spicy", "chicken", "2"
  kind      text not null check (kind in ('ingredient', 'dish word', 'diet', 'spice', 'number', 'portion')),
  language  text not null,
  check (kind <> 'number' or means ~ '^[0-9]+$')
);

alter table public.food_terms enable row level security;
revoke all on public.food_terms from anon, authenticated;
