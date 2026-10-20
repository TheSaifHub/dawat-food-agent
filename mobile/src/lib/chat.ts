// Talking to Dawat AI. Ported from frontend_old/src/lib/chat.ts for native, using the spike's finding (D-073) that
// expo/fetch streams POST /chat event by event in Expo Go.
//
//   start {conversation_id} -> step {...} per tool call, live -> reply {text, status, card, plans, payment} -> done
//   error {message} only if the backend crashed. Before the stream: 401, 404 (conversation), 422, 429 (limits).
//
// The body is the message and the conversation id, nothing else: never a price, a user id, a "source" or a card/quote
// id. The token is passed in for the one call, goes only into the Authorization header, and is never logged or kept.

import { fetch as streamFetch } from 'expo/fetch';
import { API_URL } from './config';
import { MESSAGES } from './api';

export type Step = {
  step: number;
  tool: string;
  arguments: Record<string, unknown>;
  status: string | null;
  ok: boolean;
  latency_ms: number;
  counts: Record<string, number>;
};

export type CardLine = { name: string; qty: number; line_total: number | null; is_veg: boolean | null; restaurant: string | null };
export type Card =
  | { kind: 'order'; card_id: string; grand_total: number; deliver_to: string | null; lines: CardLine[] }
  | { kind: 'plan'; card_id: string; label: string | null; grand_total: number; deliver_to: string | null; lines: CardLine[]; replace: boolean; nonveg: string[]; saved_diet: string | null }
  | { kind: 'diet'; card_id: string; items: { name: string; qty: number }[]; saved_diet: string | null }
  | { kind: 'preference'; card_id: string; offer: { action?: string }; label: string }
  | { kind: 'remove'; card_id: string; items: { name: string; qty: number | null }[] }
  | { kind: 'delivery'; card_id: string; area_id: string; area: string };

export type PlanItem = { name: string; qty: number; line_total: number; is_veg: boolean; spice_level: number; role: string };
export type PlanOption = {
  plan_id: string;
  label: string;
  grand_total: number;
  items_total: number;
  delivery_total: number;
  taxes_total: number;
  diet_note: string | null;
  budget_left: number | null;
  restaurants: {
    restaurant: string;
    branch_id: string;
    branch_label: string;
    distance_km: number;
    delivery_fee: number;
    free_delivery: boolean;
    taxes: number;
    total: number;
    items: PlanItem[];
  }[];
};

export type Reply = {
  text: string;
  status: 'ok' | 'busy' | 'step_cap';
  message_id: number | null;
  card: Card | null;
  card_text?: string | null;
  plans: PlanOption[] | null;
  payment?: { cart_id: string; quote_id: string; grand_total: number } | null;
};

export type ChatHandlers = {
  onStart: (conversationId: string) => void;
  onStep: (step: Step) => void;
  onReply: (reply: Reply) => void;
  /** Called once if nothing has come back after 4 s: "Waking up Dawat AI...". */
  onSlow?: () => void;
};

/** How a turn ended when it did not end with a reply. Only "sign_in" means the backend rejected the sign-in (a real 401). */
export type ChatFailure = { kind: 'limit' | 'missing_conversation' | 'sign_in' | 'aborted' | 'failed'; message: string };

export const MAX_MESSAGE_CHARS = 2000;
const TURN_TIMEOUT_MS = 120_000; // a cold start (~50 s) plus a slow model; the backend gives up sooner itself
const SLOW_MS = 4_000;

export type SseEvent = { event: string; data: string };

/** Splits a text stream into server-sent events. Chunks can cut an event anywhere; nothing is lost or repeated. */
export class SseParser {
  private buffer = '';
  push(chunk: string): SseEvent[] {
    this.buffer += chunk.replace(/\r\n/g, '\n');
    const out: SseEvent[] = [];
    let cut = this.buffer.indexOf('\n\n');
    while (cut !== -1) {
      const block = this.buffer.slice(0, cut);
      this.buffer = this.buffer.slice(cut + 2);
      cut = this.buffer.indexOf('\n\n');
      let event = 'message';
      const data: string[] = [];
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''));
      }
      out.push({ event, data: data.join('\n') });
    }
    return out;
  }
}

/** The request body: the words and the conversation, nothing else. */
export function chatBody(message: string, conversationId: string | null): { message: string; conversation_id?: string } {
  return conversationId ? { message, conversation_id: conversationId } : { message };
}

export async function sendChat(
  message: string,
  conversationId: string | null,
  token: string,
  handlers: ChatHandlers,
  signal?: AbortSignal,
): Promise<ChatFailure | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TURN_TIMEOUT_MS);
  const slow = setTimeout(() => handlers.onSlow?.(), SLOW_MS);
  const onAbort = () => controller.abort();
  signal?.addEventListener('abort', onAbort, { once: true });
  try {
    const res = await streamFetch(`${API_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', Authorization: `Bearer ${token}` },
      body: JSON.stringify(chatBody(message, conversationId)),
      signal: controller.signal,
    });
    clearTimeout(slow);
    if (!res.ok || !res.body) {
      let body: { message?: unknown } | null = null;
      try {
        body = JSON.parse(await res.text()) as { message?: unknown };
      } catch {
        body = null;
      }
      if (res.status === 401) return { kind: 'sign_in', message: MESSAGES.signIn };
      if (res.status === 404) return { kind: 'missing_conversation', message: 'That conversation has ended. Please send your message again.' };
      if (res.status === 429) {
        return { kind: 'limit', message: typeof body?.message === 'string' && body.message ? body.message : "You've reached the demo limit for now. Please try again later." };
      }
      return { kind: 'failed', message: res.status === 422 ? "That message can't be sent. Please shorten it and try again." : MESSAGES.server };
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    const parser = new SseParser();
    let replied = false;
    let failure: ChatFailure | null = null;
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      for (const ev of parser.push(decoder.decode(value, { stream: true }))) {
        let parsed: unknown = null;
        try {
          parsed = ev.data ? JSON.parse(ev.data) : null;
        } catch {
          continue;
        }
        if (ev.event === 'start') handlers.onStart((parsed as { conversation_id: string }).conversation_id);
        else if (ev.event === 'step') handlers.onStep(parsed as Step);
        else if (ev.event === 'reply') {
          replied = true;
          handlers.onReply(parsed as Reply);
        } else if (ev.event === 'error') {
          const m = (parsed as { message?: unknown } | null)?.message;
          failure = { kind: 'failed', message: typeof m === 'string' && m ? m : MESSAGES.server };
        }
      }
    }
    return replied ? null : (failure ?? { kind: 'failed', message: MESSAGES.server });
  } catch {
    if (signal?.aborted) return { kind: 'aborted', message: MESSAGES.aborted };
    return { kind: 'failed', message: controller.signal.aborted ? MESSAGES.timeout : MESSAGES.network };
  } finally {
    clearTimeout(timer);
    clearTimeout(slow);
    signal?.removeEventListener('abort', onAbort);
  }
}

// --- the thinking panel's words for each step -------------------------------------------------------------------

const TOOL_WORDS: Record<string, string> = {
  search_restaurants: 'Searched restaurants',
  get_menu: 'Opened a menu',
  search_dishes: 'Searched dishes',
  plan_meal: 'Planned meals',
  add_plan_to_cart: 'Added a plan to the cart',
  add_to_cart: 'Added to the cart',
  remove_from_cart: 'Removed from the cart',
  set_delivery: 'Changed where to deliver',
  view_cart: 'Checked the cart',
  confirm_cart: 'Confirmed the cart',
  place_order: 'Placed the order',
  track_order: 'Looked up an order',
  get_user_history: 'Read your past orders',
  get_preferences: 'Read your saved preferences',
  save_preference: 'Saved a preference',
  delete_preference: 'Forgot a preference',
  name_correction: 'Checked restaurant names',
};

const COUNT_WORDS: Record<string, [string, string]> = {
  results_count: ['result', 'results'],
  restaurants_count: ['restaurant', 'restaurants'],
  items_count: ['dish', 'dishes'],
  plans_count: ['plan', 'plans'],
  branches_count: ['branch', 'branches'],
  orders_count: ['order', 'orders'],
};

/** "Searched dishes: "biryani", Madhapur · 12 results". Only the tool's name, its search words and counts: no prices. */
export function stepLine(s: Step): string {
  const what = TOOL_WORDS[s.tool] ?? s.tool.replace(/_/g, ' ');
  const a = s.arguments ?? {};
  const words = [typeof a.query === 'string' ? `“${a.query}”` : null, typeof a.area === 'string' ? a.area : null].filter(Boolean).join(', ');
  const counts = Object.entries(s.counts ?? {})
    .filter(([k]) => k in COUNT_WORDS)
    .map(([k, n]) => `${n} ${COUNT_WORDS[k][n === 1 ? 0 : 1]}`)
    .join(', ');
  return [what + (words ? `: ${words}` : ''), counts].filter(Boolean).join(' · ');
}

/** A short word for the step's outcome, from its status (never the tool's message). */
export function stepOutcome(s: Step): { text: string; good: boolean } {
  if (!s.ok) return { text: "didn't work", good: false };
  switch (s.status) {
    case 'ok':
      return { text: 'done', good: true };
    case 'empty':
      return { text: 'empty', good: true };
    case 'needs_info':
    case 'needs_choice':
    case 'needs_area':
    case 'needs_branch':
    case 'needs_delivery_area':
    case 'confirm_area':
    case 'confirm_dish':
      return { text: 'needs your answer', good: true };
    case 'confirm_diet':
    case 'confirm_plan':
    case 'confirm_preference':
    case 'remove_not_asked':
    case 'delivery_not_asked':
    case 'cart_not_empty':
    case 'not_shown':
    case 'confirm_intent':
    case 'no_clear_yes':
      return { text: 'asking you first', good: true };
    case 'no_match':
    case 'no_dish_match':
    case 'no_match_with_filters':
    case 'none_near_area':
    case 'no_valid_plan':
      return { text: 'nothing found', good: true };
    case 'over_budget':
      return { text: 'over budget', good: true };
    case 'outside_coverage':
    case 'too_far':
      return { text: 'out of range', good: true };
    default:
      return { text: "couldn't do it", good: false };
  }
}

/** Tools whose success changes the cart: the app's cart is refreshed after them (the chat and the app share one). */
export const CART_TOOLS = new Set(['add_to_cart', 'add_plan_to_cart', 'remove_from_cart', 'set_delivery', 'confirm_cart', 'place_order']);
