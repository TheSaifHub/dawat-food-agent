"use client";

// The Dawat AI chat on every page (Phase 7f, D-058): a launcher at the bottom right, and a panel that opens beside the
// page. On wide screens it's a non-modal dialog and the page stays usable; on phones it fills the screen, so it's
// modal there and the page behind is made inert. Escape or Close shuts it and focus goes back to the launcher. One
// live region, always mounted, reads out each reply.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useSyncExternalStore } from "react";

import { DawatLogo } from "@/components/brand/DawatLogo";
import { ConfirmCard, DoneSteps, LiveSteps, PlanCards, RichText } from "@/components/chat/ChatParts";
import { Announcer } from "@/components/common/Loading";
import { useChat } from "@/lib/chat-context";
import { useSession } from "@/lib/session";

export const CHAT_EXAMPLES = [
  "Chicken biryani in Madhapur",
  "₹500 for 2 people, one is vegetarian, something spicy",
  "Bhai, Gachibowli mein kuch spicy milega?",
];

export function ChatWidget() {
  const { open, setOpen, announcement } = useChat();
  const pathname = usePathname();
  const launcher = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(false);
  const panelId = useId();

  // Closing hands focus back to the launcher, so keyboard users land where they started.
  useEffect(() => {
    if (wasOpen.current && !open) launcher.current?.focus();
    wasOpen.current = open;
  }, [open]);

  // The dev preview shows its own panel; a second, hidden launcher there would only be a stray Tab stop.
  if (pathname.startsWith("/dev/")) return <Announcer text={announcement.text} seq={announcement.seq} />;
  return (
    <>
      <Announcer text={announcement.text} seq={announcement.seq} />
      {open ? <ChatPanel id={panelId} onClose={() => setOpen(false)} /> : (
        // The launcher floats over anything, plum sections included: a plum ring with an ivory gap shows on both.
        <button ref={launcher} type="button" aria-haspopup="dialog" onClick={() => setOpen(true)}
                className="fixed bottom-[calc(var(--cartbar-h,0px)+1rem)] right-4 z-40 inline-flex h-14 items-center gap-2 rounded-full border border-gold/70 bg-plum pl-2 pr-5 font-semibold text-ivory shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-plum focus-visible:ring-offset-2 focus-visible:ring-offset-ivory">
          <DawatLogo size={40} title="" className="rounded-full" />
          Ask Dawat AI
        </button>
      )}
    </>
  );
}

function ChatPanel({ id, onClose }: { id: string; onClose: () => void }) {
  const { session } = useSession();
  const chat = useChat();
  return <ChatPanelView id={id} onClose={onClose} signedIn={session.state === "signed_in"} {...chat} />;
}

export type ChatPanelProps = Pick<ReturnType<typeof useChat>, "messages" | "liveSteps" | "busy" | "send" | "draft" | "setDraft" | "startOver"> & {
  id: string;
  onClose: () => void;
  signedIn: boolean;
};

const NARROW = "(max-width: 639.98px)";             // below Tailwind's sm: the panel fills the screen

function useNarrow(): boolean {
  return useSyncExternalStore(
    (onChange) => { const mq = window.matchMedia(NARROW); mq.addEventListener("change", onChange); return () => mq.removeEventListener("change", onChange); },
    () => window.matchMedia(NARROW).matches,
    () => false,
  );
}

/** The panel itself, from props: the widget feeds it the live chat; the dev preview feeds it a fixed conversation. */
export function ChatPanelView({ id, onClose, signedIn, messages, liveSteps, busy, send, draft, setDraft, startOver }: ChatPanelProps) {
  const titleId = useId();
  const inputId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const narrow = useNarrow();

  // Focus goes into the panel: the message box, or the title when signed out (there's no box then).
  useEffect(() => { (input.current ?? heading.current)?.focus(); }, []);

  // Escape closes it wherever focus is (an example button on the page can open it without moving focus).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Full screen on a phone: the page behind can't take focus (it would be hidden under the panel, WCAG 2.4.11).
  // Live regions stay reachable so replies are still read out.
  useEffect(() => {
    const el = panel.current;
    if (!narrow || !el) return;
    const made: Element[] = [];
    for (const child of Array.from(document.body.children)) {
      if (child.contains(el) || child.getAttribute("role") === "status" || child.hasAttribute("inert")) continue;
      child.setAttribute("inert", "");
      made.push(child);
    }
    return () => made.forEach((c) => c.removeAttribute("inert"));
  }, [narrow]);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [messages, liveSteps, busy]);

  const isLast = (mid: number) => messages[messages.length - 1]?.id === mid;

  function submit() {
    if (!draft.trim() || busy) return;
    void send(draft);
  }

  return (
    <div id={id} ref={panel} role="dialog" aria-modal={narrow} aria-labelledby={titleId}
         className="fixed inset-0 z-50 flex flex-col bg-background sm:inset-auto sm:bottom-[calc(var(--cartbar-h,0px)+1rem)] sm:right-4 sm:h-[min(42rem,calc(100dvh-var(--cartbar-h,0px)-2rem))] sm:w-[26rem] sm:overflow-hidden sm:rounded-2xl sm:border sm:border-border sm:shadow-2xl">
      <div className="flex items-center gap-3 bg-plum px-4 py-3 text-ivory">
        <DawatLogo size={36} title="" className="rounded-[12px]" />
        <h2 id={titleId} ref={heading} tabIndex={-1} className="flex-1 font-display text-2xl font-semibold leading-none focus:outline-none">Dawat AI</h2>
        {signedIn && messages.length ? (
          <button type="button" onClick={startOver} aria-disabled={busy}
                  className="inline-flex h-10 items-center rounded-md px-2 text-sm text-ivory underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-gold aria-disabled:opacity-60">
            New chat
          </button>
        ) : null}
        <button type="button" onClick={onClose}
                className="inline-flex h-10 items-center rounded-md px-2 text-sm text-ivory underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-gold">
          Close<span className="sr-only"> Dawat AI</span>
        </button>
      </div>
      <div aria-hidden="true" className="h-px bg-gold/70" />

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {!signedIn ? <SignedOut /> : messages.length === 0 && !busy ? <Welcome onExample={(t) => { setDraft(t); input.current?.focus(); }} /> : (
          <ol className="flex flex-col gap-4" aria-label="Conversation">
            {messages.map((m) => (
              <li key={m.id} className={m.role === "user" ? "flex justify-end" : "flex flex-col gap-2"}>
                {m.role === "user" ? (
                  <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-plum px-3 py-2 text-ivory">
                    <span className="sr-only">You: </span>{m.text}
                  </p>
                ) : m.role === "notice" ? (
                  <p className="rounded-lg border border-destructive px-3 py-2 text-destructive">{m.text}</p>
                ) : (
                  <>
                    <div className="max-w-[95%] rounded-2xl rounded-bl-sm border border-border bg-card px-3 py-2">
                      <span className="sr-only">Dawat AI: </span><RichText text={m.text} />
                    </div>
                    <DoneSteps steps={m.steps} />
                    {m.plans?.length ? <PlanCards plans={m.plans} active={!busy && isLast(m.id)} onPick={(t) => void send(t)} /> : null}
                    {m.card ? <ConfirmCard card={m.card} active={!busy && isLast(m.id)} onAnswer={(t) => void send(t)} /> : null}
                  </>
                )}
              </li>
            ))}
            {busy ? <li><LiveSteps steps={liveSteps} /></li> : null}
          </ol>
        )}
        <div ref={end} />
      </div>

      {/* The site's demo banner and map credit can be covered by the panel (all of it on a phone), so it carries both. */}
      <p className={`border-t border-border bg-card px-4 pt-2 text-xs text-muted-foreground ${signedIn ? "" : "pb-3"}`}>
        Demo: menus, prices and orders are simulated. Restaurant data ©{" "}
        <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer"
           className="text-plum underline underline-offset-2">OpenStreetMap contributors<span className="sr-only"> (opens in a new tab)</span></a>
      </p>

      {signedIn ? (
        <form className="flex items-end gap-2 bg-card px-3 py-3" onSubmit={(e) => { e.preventDefault(); submit(); }}>
          <label htmlFor={inputId} className="sr-only">Message Dawat AI</label>
          <textarea id={inputId} ref={input} rows={2} maxLength={2000} value={draft} onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); } }}
                    placeholder="What would you like to eat?"
                    className="min-h-11 flex-1 resize-none rounded-lg border border-input bg-background px-3 py-2 placeholder:text-muted-foreground focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring" />
          <button type="submit" aria-disabled={busy || !draft.trim()}
                  className="inline-flex h-11 items-center rounded-lg bg-plum px-4 font-semibold text-ivory focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring aria-disabled:opacity-60">
            {busy ? "Wait…" : "Send"}
          </button>
        </form>
      ) : null}
    </div>
  );
}

function Welcome({ onExample }: { onExample: (text: string) => void }) {
  return (
    <div className="flex flex-col gap-4">
      <p>Tell Dawat AI what you&apos;d like, in English, Hinglish or Telugu. It finds real restaurants near you, works out
        the bill with the menu&apos;s prices, and orders only after you say yes.</p>
      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium">Try one:</p>
        {CHAT_EXAMPLES.map((t) => (
          <button key={t} type="button" onClick={() => onExample(t)}
                  className="min-h-11 rounded-lg border border-input bg-card px-3 py-2 text-left hover:bg-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
            {t}
          </button>
        ))}
      </div>
    </div>
  );
}

function SignedOut() {
  return (
    <div className="flex flex-col items-start gap-3">
      <p>Dawat AI needs you signed in, so it can fill your cart and place orders for you.</p>
      <p>No account? Try the demo as Priya or Arjun: one click, nothing to fill in.</p>
      <Link href="/login" className="inline-flex h-11 items-center rounded-lg bg-plum px-5 font-semibold text-ivory focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
        Sign in or try the demo
      </Link>
    </div>
  );
}
