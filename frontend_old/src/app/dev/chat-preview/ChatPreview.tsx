"use client";

// The dev preview's client half: the real ChatPanelView, fed fixture.json instead of the live chat. Buttons only
// change what's shown here; nothing is sent to the backend.

import Link from "next/link";
import { useState } from "react";

import { ChatPanelView } from "@/components/chat/ChatWidget";
import type { Card, Step } from "@/lib/chat";
import type { ChatMessage } from "@/lib/chat-context";

import fixture from "./fixture.json";
import type { PreviewView } from "./page";

const messages = fixture.messages as unknown as ChatMessage[];
const planCard = fixture.plan_card as unknown as Card;
// The thinking view also shows a step that failed, as the panel would.
const liveSteps = [...(fixture.live_steps as unknown as Step[]),
  { step: 2, tool: "add_to_cart", arguments: {}, status: "item_unavailable", ok: true, latency_ms: 120, counts: {} }] as Step[];

function shown(view: PreviewView): ChatMessage[] {
  if (view === "empty" || view === "signed-out") return [];
  if (view === "plan-card") {
    return [...messages.slice(0, 2), messages[2],
      { id: 4, role: "assistant", status: "ok", steps: [], plans: null, card: planCard,
        text: "That plan replaces nothing in your cart. Shall I add it?" }];
  }
  if (view === "plans") return messages.slice(0, 2);
  if (view === "thinking") return [...messages, { id: 5, role: "user", text: "Also add one paneer tikka" }];
  return messages;
}

export function ChatPreview({ view }: { view: PreviewView }) {
  const [draft, setDraft] = useState("");
  const [log, setLog] = useState<string[]>([]);
  const record = async (text: string) => { setLog((l) => [...l, text]); };
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 py-8">
      <h1 className="font-display text-4xl font-semibold text-plum">Chat preview (dev only)</h1>
      <p>Fixed sample conversation: plans and cards are real planner output from the local test database. Nothing is sent.</p>
      <ul className="flex flex-wrap gap-3">
        {(["conversation", "plans", "thinking", "plan-card", "signed-out", "empty"] as const).map((v) => (
          <li key={v}><Link href={`/dev/chat-preview?view=${v}`} aria-current={v === view ? "page" : undefined}
                            className="inline-block py-1 text-plum underline underline-offset-2">{v}</Link></li>
        ))}
      </ul>
      {log.length ? <p>Would send: {log.map((t) => `“${t}”`).join(", ")}</p> : null}
      <ChatPanelView id="chat-preview" onClose={() => setLog((l) => [...l, "(closed)"])} signedIn={view !== "signed-out"}
                     messages={shown(view)} liveSteps={view === "thinking" ? liveSteps : []} busy={view === "thinking"}
                     send={record} draft={draft} setDraft={setDraft} startOver={() => setLog((l) => [...l, "(new chat)"])} />
    </div>
  );
}
