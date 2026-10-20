-- ════════════════════════════════════════════════════════════════════════
-- 0003 · Dawat AI: conversations, messages, agent_traces   (D-020)
-- Every tool call is logged to agent_traces (it powers the "Dawat AI is thinking" panel and the evals).
-- Traces hold tool names, arguments and short result summaries, never secrets or API keys.
-- ════════════════════════════════════════════════════════════════════════

create table if not exists public.conversations (
  conversation_id uuid primary key default gen_random_uuid(),
  user_id         uuid not null references public.users (user_id) on delete cascade,
  channel         text not null default 'web' check (channel in ('web', 'mcp', 'voice')),
  language        text check (language in ('en', 'hinglish', 'te', 'mixed')),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
create index if not exists conversations_user_idx on public.conversations (user_id, updated_at desc);
create or replace trigger conversations_touch
  before update on public.conversations for each row execute function public.touch_updated_at();

create table if not exists public.messages (
  message_id      bigint generated always as identity primary key,
  conversation_id uuid not null references public.conversations (conversation_id) on delete cascade,
  role            text not null check (role in ('user', 'assistant', 'tool')),
  content         text not null check (char_length(content) <= 20000),
  created_at      timestamptz not null default now()
);
create index if not exists messages_conversation_idx on public.messages (conversation_id, message_id);

create table if not exists public.agent_traces (
  trace_id        bigint generated always as identity primary key,
  conversation_id uuid not null references public.conversations (conversation_id) on delete cascade,
  message_id      bigint references public.messages (message_id) on delete set null,
  step            smallint not null check (step between 1 and 20),   -- tool-call number within one turn
  tool_name       text not null,
  arguments       jsonb not null default '{}'::jsonb,
  result_summary  jsonb,
  ok              boolean not null,
  error           text,
  latency_ms      integer check (latency_ms >= 0),
  provider        text,                                               -- e.g. gemini / groq (logged for evals)
  model           text,
  prompt_version  text,
  created_at      timestamptz not null default now()
);
create index if not exists agent_traces_conversation_idx on public.agent_traces (conversation_id, trace_id);
