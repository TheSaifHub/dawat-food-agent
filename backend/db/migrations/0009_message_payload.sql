-- ════════════════════════════════════════════════════════════════════════
-- 0009 · Keep each chat message exactly as the model saw it   (D-037)
--
-- messages.content is the readable text (what the chat shows). payload is the full message in the LLM's own
-- format: the assistant's tool calls (with Gemini's thought signatures) and each tool's compact result. The next
-- turn replays the conversation from payload, so a provider switch or a follow-up question sees exactly what came
-- before. Additive only: no existing row or column changes. Old rows (none yet) simply have no payload.
-- ════════════════════════════════════════════════════════════════════════

alter table public.messages add column if not exists payload jsonb;

-- The per-user hourly limit (30 messages, Saif, Session 15) counts a user's recent messages.
create index if not exists messages_created_idx on public.messages (conversation_id, created_at);
