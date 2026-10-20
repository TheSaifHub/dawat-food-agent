// Talking to Dawat AI (Phase 7f, D-058): POST /chat answers with a stream of server-sent events (backend
// app/api/chat.py). EventSource can't send a POST with a token, so this reads the stream from fetch itself.
//
//   start {conversation_id} → step {…} per tool call, live → reply {text, status, card, plans} → done
//   error {message} only if the backend crashed. Before the stream: 401, 404 (conversation), 422, 429 (limits).

import { apiUrl, MESSAGES } from "@/lib/api";

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
  | { kind: "order"; card_id: string; grand_total: number; deliver_to: string | null; lines: CardLine[] }
  | { kind: "plan"; card_id: string; label: string | null; grand_total: number; deliver_to: string | null; lines: CardLine[];
      replace: boolean; nonveg: string[]; saved_diet: string | null }
  | { kind: "diet"; card_id: string; items: { name: string; qty: number }[]; saved_diet: string | null }
  | { kind: "preference"; card_id: string; offer: { action?: string }; label: string }
  | { kind: "remove"; card_id: string; items: { name: string; qty: number | null }[] }
  | { kind: "delivery"; card_id: string; area_id: string; area: string };

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
  restaurants: { restaurant: string; branch_id: string; branch_label: string; distance_km: number; delivery_fee: number;
                 free_delivery: boolean; taxes: number; total: number; items: PlanItem[] }[];
};

export type Reply = { text: string; status: "ok" | "busy" | "step_cap"; message_id: number | null; card: Card | null;
                      plans: PlanOption[] | null };

export type ChatHandlers = {
  onStart: (conversationId: string) => void;
  onStep: (step: Step) => void;
  onReply: (reply: Reply) => void;
};

/** How a turn ended, when it didn't end with a reply. */
export type ChatFailure = { kind: "limit" | "missing_conversation" | "sign_in" | "failed"; message: string };

const TURN_TIMEOUT_MS = 120_000;      // a cold start (~50 s) plus a slow model; the backend gives up sooner itself

export async function sendChat(message: string, conversationId: string | null, token: string | null,
                               handlers: ChatHandlers, signal?: AbortSignal): Promise<ChatFailure | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TURN_TIMEOUT_MS);
  const onAbort = () => controller.abort();
  signal?.addEventListener("abort", onAbort, { once: true });
  try {
    const res = await fetch(apiUrl("/chat"), {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream",
                 ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify(conversationId ? { message, conversation_id: conversationId } : { message }),
      signal: controller.signal,
      cache: "no-store",
    });
    if (!res.ok || !res.body) {
      const body = await res.json().catch(() => null) as { message?: string } | null;
      if (res.status === 401) return { kind: "sign_in", message: "Please sign in again to chat." };
      if (res.status === 404) return { kind: "missing_conversation", message: "That conversation has ended. Please send your message again." };
      if (res.status === 429) return { kind: "limit", message: body?.message ?? "You've reached the demo limit for now." };
      return { kind: "failed", message: res.status === 422 ? "That message can't be sent. Please shorten it and try again." : MESSAGES.server };
    }

    const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = "";
    let replied = false;
    let failure: ChatFailure | null = null;
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value;
      let cut: number;
      while ((cut = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, cut);
        buffer = buffer.slice(cut + 2);
        let event = "message";
        let data = "";
        for (const line of block.split("\n")) {
          if (line.startsWith("event: ")) event = line.slice(7);
          else if (line.startsWith("data: ")) data += line.slice(6);
        }
        let parsed: unknown = null;
        try { parsed = data ? JSON.parse(data) : null; } catch { continue; }
        if (event === "start") handlers.onStart((parsed as { conversation_id: string }).conversation_id);
        else if (event === "step") handlers.onStep(parsed as Step);
        else if (event === "reply") { replied = true; handlers.onReply(parsed as Reply); }
        else if (event === "error") failure = { kind: "failed", message: (parsed as { message?: string })?.message ?? MESSAGES.server };
      }
    }
    return replied ? null : failure ?? { kind: "failed", message: MESSAGES.server };
  } catch {
    if (signal?.aborted) return { kind: "failed", message: MESSAGES.aborted };
    return { kind: "failed", message: controller.signal.aborted ? MESSAGES.timeout : MESSAGES.network };
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onAbort);
  }
}

// ─── the thinking panel's words for each step ──────────────────────────────────────────────────────────

const TOOL_WORDS: Record<string, string> = {
  search_restaurants: "Searched restaurants",
  get_menu: "Opened a menu",
  search_dishes: "Searched dishes",
  plan_meal: "Planned meals",
  add_plan_to_cart: "Added a plan to the cart",
  add_to_cart: "Added to the cart",
  remove_from_cart: "Removed from the cart",
  set_delivery: "Changed where to deliver",
  view_cart: "Checked the cart",
  confirm_cart: "Confirmed the cart",
  place_order: "Placed the order",
  track_order: "Looked up an order",
  get_user_history: "Read your past orders",
  get_preferences: "Read your saved preferences",
  save_preference: "Saved a preference",
  delete_preference: "Forgot a preference",
  name_correction: "Checked restaurant names",
};

const COUNT_WORDS: Record<string, [string, string]> = {
  results_count: ["result", "results"],
  restaurants_count: ["restaurant", "restaurants"],
  items_count: ["dish", "dishes"],
  plans_count: ["plan", "plans"],
  branches_count: ["branch", "branches"],
  orders_count: ["order", "orders"],
};

/** "Searched dishes: “biryani”, Madhapur · 12 results". Only the tool's name, its search words and counts: no prices. */
export function stepLine(s: Step): string {
  const what = TOOL_WORDS[s.tool] ?? s.tool.replace(/_/g, " ");
  const a = s.arguments ?? {};
  const words = [typeof a.query === "string" ? `“${a.query}”` : null, typeof a.area === "string" ? a.area : null]
    .filter(Boolean).join(", ");
  const counts = Object.entries(s.counts ?? {}).filter(([k]) => k in COUNT_WORDS)
    .map(([k, n]) => `${n} ${COUNT_WORDS[k][n === 1 ? 0 : 1]}`).join(", ");
  return [what + (words ? `: ${words}` : ""), counts].filter(Boolean).join(" · ");
}

/** A short word for the step's outcome, from its status (never the tool's message). */
export function stepOutcome(s: Step): { text: string; good: boolean } {
  if (!s.ok) return { text: "didn't work", good: false };
  switch (s.status) {
    case "ok": return { text: "done", good: true };
    case "empty": return { text: "empty", good: true };
    case "needs_info": case "needs_choice": case "needs_area": case "needs_branch": case "needs_delivery_area":
    case "confirm_area": case "confirm_dish": return { text: "needs your answer", good: true };
    case "confirm_diet": case "confirm_plan": case "confirm_preference": case "remove_not_asked": case "delivery_not_asked":
    case "cart_not_empty": case "not_shown": case "confirm_intent": case "no_clear_yes":
      return { text: "asking you first", good: true };
    case "no_match": case "no_dish_match": case "no_match_with_filters": case "none_near_area": case "no_valid_plan":
      return { text: "nothing found", good: true };
    case "over_budget": return { text: "over budget", good: true };
    case "outside_coverage": case "too_far": return { text: "out of range", good: true };
    default: return { text: "couldn't do it", good: false };
  }
}

/** Tools whose success changes the cart: the page's cart is refreshed after them (the chat and the page share one). */
export const CART_TOOLS = new Set(["add_to_cart", "add_plan_to_cart", "remove_from_cart", "set_delivery", "confirm_cart",
                                   "place_order"]);
