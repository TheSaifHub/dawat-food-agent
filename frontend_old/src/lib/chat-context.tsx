"use client";

// The Dawat AI chat's state for the whole site (Phase 7f, D-058). It lives in the layout, so the conversation stays
// open while the visitor moves between pages, and the chat and the page share the one backend cart: after any step
// that changes the cart, and after every turn, the page's cart is fetched again.
//
// The conversation (its id and what was shown) is kept in this tab's sessionStorage, per user, so a reload doesn't
// lose it. That is only a convenience: the backend holds the real history, and a lost copy just starts a new chat.

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { useCart } from "@/lib/cart";
import { CART_TOOLS, sendChat, type Card, type PlanOption, type Step } from "@/lib/chat";
import { useSession } from "@/lib/session";
import { accessToken } from "@/lib/auth";

export type ChatMessage =
  | { id: number; role: "user"; text: string }
  | { id: number; role: "assistant"; text: string; status: "ok" | "busy" | "step_cap"; steps: Step[]; card: Card | null;
      plans: PlanOption[] | null }
  /** The website's own words when a turn didn't get a reply (a limit, offline, signed out). */
  | { id: number; role: "notice"; text: string };

/** A message before it gets its id (Omit on each kind, so each keeps its own fields). */
type Unsent = { [R in ChatMessage["role"]]: Omit<Extract<ChatMessage, { role: R }>, "id"> }[ChatMessage["role"]];

type Saved = { conversationId: string | null; messages: ChatMessage[] };

type ChatContext = {
  open: boolean;
  setOpen: (open: boolean) => void;
  /** Open the chat with this text in the box (not sent: the visitor presses Send). */
  openWith: (text: string) => void;
  draft: string;
  setDraft: (text: string) => void;
  messages: ChatMessage[];
  /** The steps of the turn in progress, live. */
  liveSteps: Step[];
  busy: boolean;
  send: (text: string) => Promise<void>;
  startOver: () => void;
  /** What the chat's live region says, and a count so a repeat is still read out. */
  announcement: { text: string; seq: number };
};

const Ctx = createContext<ChatContext | null>(null);
const MAX_KEPT = 60;                              // messages kept in sessionStorage

function storageKey(userId: string) {
  return `dawat.chat.${userId}`;
}

function load(userId: string): Saved {
  try {
    const raw = sessionStorage.getItem(storageKey(userId));
    const saved = raw ? (JSON.parse(raw) as Saved) : null;
    if (saved && Array.isArray(saved.messages)) return saved;
  } catch { /* private mode or bad data: start fresh */ }
  return { conversationId: null, messages: [] };
}

function save(userId: string, saved: Saved) {
  try {
    sessionStorage.setItem(storageKey(userId), JSON.stringify({ ...saved, messages: saved.messages.slice(-MAX_KEPT) }));
  } catch { /* storage full or blocked: the chat still works, it just won't survive a reload */ }
}

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const { session } = useSession();
  const { refresh: refreshCart } = useCart();
  const userId = session.state === "signed_in" ? session.me.user_id : null;

  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [liveSteps, setLiveSteps] = useState<Step[]>([]);
  const [busy, setBusy] = useState(false);
  const [announcement, setAnnouncement] = useState({ text: "", seq: 0 });
  const nextId = useRef(1);
  const loadedFor = useRef<string | null>(null);

  const announce = useCallback((text: string) => setAnnouncement((a) => ({ text, seq: a.seq + 1 })), []);

  // A different user (or none) gets their own conversation: never show one person's chat to another.
  useEffect(() => {
    if (loadedFor.current === userId) return;
    loadedFor.current = userId;
    const saved = userId ? load(userId) : { conversationId: null, messages: [] };
    nextId.current = saved.messages.reduce((n, m) => Math.max(n, m.id), 0) + 1;
    queueMicrotask(() => {
      setMessages(saved.messages);
      setConversationId(saved.conversationId);
      setLiveSteps([]);
    });
  }, [userId]);

  useEffect(() => {
    if (userId && loadedFor.current === userId) save(userId, { conversationId, messages });
  }, [userId, conversationId, messages]);

  const push = useCallback((m: Unsent) => {
    const withId = { ...m, id: nextId.current++ } as ChatMessage;
    setMessages((list) => [...list, withId]);
  }, []);

  const send = useCallback(async (raw: string) => {
    const text = raw.trim();
    if (!text || busy) return;
    if (!userId) {
      push({ role: "notice", text: "Sign in to chat with Dawat AI." });
      return;
    }
    setBusy(true);
    setLiveSteps([]);
    setDraft("");
    push({ role: "user", text });
    announce("Dawat AI is thinking…");
    const steps: Step[] = [];
    let cartChanged = false;

    const attempt = async (cid: string | null) => sendChat(text, cid, await accessToken(), {
      onStart: (id) => setConversationId(id),
      onStep: (s) => {
        steps.push(s);
        setLiveSteps([...steps]);
        if (s.ok && s.status === "ok" && CART_TOOLS.has(s.tool)) {
          cartChanged = true;
          void refreshCart();                  // the page's cart follows the chat live
        }
      },
      onReply: (r) => {
        push({ role: "assistant", text: r.text, status: r.status, steps: [...steps], card: r.card, plans: r.plans });
        announce(`Dawat AI: ${r.text}`);
      },
    });

    let failure = await attempt(conversationId);
    if (failure?.kind === "missing_conversation") {         // the saved conversation is gone: start a new one, once
      setConversationId(null);
      failure = await attempt(null);
    }
    if (failure) {
      push({ role: "notice", text: failure.message });
      announce(failure.message);
    }
    setLiveSteps([]);
    setBusy(false);
    if (cartChanged || failure) void refreshCart();
  }, [busy, userId, conversationId, push, announce, refreshCart]);

  const startOver = useCallback(() => {
    if (busy) return;
    setMessages([]);
    setConversationId(null);
    announce("Started a new chat.");
  }, [busy, announce]);

  const openWith = useCallback((text: string) => {
    setDraft(text);
    setOpen(true);
  }, []);

  const value = useMemo(() => ({ open, setOpen, openWith, draft, setDraft, messages, liveSteps, busy, send, startOver,
                                 announcement }),
    [open, openWith, draft, messages, liveSteps, busy, send, startOver, announcement]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useChat(): ChatContext {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useChat must be used inside <ChatProvider>");
  return ctx;
}
