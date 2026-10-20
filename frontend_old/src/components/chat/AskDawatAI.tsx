"use client";

// The Dawat AI line on the home page (Phase 7f): what it does, and examples that open the chat with the text ready
// to send. Nothing is sent until the visitor presses Send (each message uses the free model quota).

import { CHAT_EXAMPLES } from "@/components/chat/ChatWidget";
import { useChat } from "@/lib/chat-context";

export function AskDawatAI() {
  const { openWith, setOpen } = useChat();
  return (
    <section aria-labelledby="ask-heading" className="w-full rounded-2xl bg-plum px-5 py-6 text-ivory sm:px-8">
      <div className="flex flex-col gap-4">
        <h2 id="ask-heading" className="font-display text-3xl font-semibold">Just ask Dawat AI</h2>
        <p className="max-w-2xl">
          Say what you feel like eating, with a budget or for a group, in English, Hinglish or Telugu. Dawat AI finds
          dishes near you, adds them to your cart and places the order only after you say yes.
        </p>
        <ul className="flex flex-wrap gap-2" aria-label="Examples">
          {CHAT_EXAMPLES.map((t) => (
            <li key={t}>
              <button type="button" onClick={() => openWith(t)}
                      className="min-h-11 rounded-full border border-gold/70 px-4 py-2 text-left text-ivory hover:bg-plum-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gold">
                “{t}”
              </button>
            </li>
          ))}
        </ul>
        <div>
          <button type="button" onClick={() => setOpen(true)}
                  className="inline-flex h-11 items-center rounded-lg bg-ivory px-5 font-semibold text-plum focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gold">
            Open Dawat AI
          </button>
        </div>
      </div>
    </section>
  );
}
