// The conversation with Dawat AI, kept in memory for this sign-in (D-058 on the web, ported for the app).
//
// Rules held here (consent and identity, so tested hard in __tests__/chat.test.tsx):
//  - One turn at a time. A message is only the words (and the conversation id): see chatBody() in chat.ts.
//  - Card buttons are ordinary messages, "Yes" or "No". Nothing here calls confirm, place-order or payment routes.
//  - A card or plan option can be answered only while it is under the LATEST reply and no turn is running (the
//    backend acts on a "yes" only for the card shown under the previous reply, so the app never offers an old one).
//  - Only a real 401 signs the user out (session.withToken); limits, a missing conversation and network errors do not.
//  - A different user, or nobody, gets an empty chat at once, and a turn still running for the old user is dropped.
//  - Leaving the screen stops the stream. The backend stops the turn at its next step boundary (D-075), but a step
//    already running can still finish, so the cart is read again now and twice more shortly after.

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { CART_TOOLS, MAX_MESSAGE_CHARS, sendChat, type Card, type ChatHandlers, type PlanOption, type Reply, type Step } from './chat';
import { useCart } from './cart';
import { useSession } from './session';

export type ChatMessage =
  | { id: string; role: 'user'; text: string }
  | {
      id: string;
      role: 'assistant';
      text: string;
      status: Reply['status'];
      card: Card | null;
      cardText: string | null;
      plans: PlanOption[] | null;
      payment: Reply['payment'] | null;
      steps: Step[];
    }
  | { id: string; role: 'notice'; text: string; tone: 'info' | 'error' };

type NewMessage = ChatMessage extends infer M ? (M extends { id: string } ? Omit<M, 'id'> : never) : never;

type ChatCtx = {
  messages: ChatMessage[];
  sending: boolean;
  /** No answer after 4 s: the free backend is waking up. */
  slow: boolean;
  /** Tool steps of the turn that is running, as they arrive. */
  liveSteps: Step[];
  send: (text: string) => Promise<void>;
  /** Stops the running turn (leaving the screen does this). */
  stop: () => void;
  /** The id of the reply whose card or plan options can be answered right now, else null. */
  actionableId: string | null;
};

const Ctx = createContext<ChatCtx | null>(null);

export function useChat(): ChatCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error('useChat must be used inside <ChatProvider>');
  return c;
}

const KEEP = 100;
const LATE_REFRESH_MS = [10_000, 25_000];

export function ChatProvider({ children }: { children: ReactNode }) {
  const { state, withToken } = useSession();
  const { refresh } = useCart();
  const userId = state.status === 'signedIn' ? state.me.user_id : null;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [slow, setSlow] = useState(false);
  const [liveSteps, setLiveSteps] = useState<Step[]>([]);

  const owner = useRef<string | null>(null);
  const conversation = useRef<string | null>(null);
  const turn = useRef(0); // bumped to drop a running turn's late events
  const running = useRef(false);
  const controller = useRef<AbortController | null>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const nextId = useRef(1);

  const push = useCallback((m: NewMessage) => {
    const msg = { ...m, id: `m${nextId.current++}` } as ChatMessage;
    setMessages((all) => [...all, msg].slice(-KEEP));
  }, []);

  const clearTimers = useCallback(() => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  }, []);

  const endTurn = useCallback(() => {
    running.current = false;
    controller.current = null;
    setSending(false);
    setSlow(false);
    setLiveSteps([]);
  }, []);

  // A different user (or nobody): an empty chat now, and any running turn is dropped.
  useEffect(() => {
    if (owner.current === userId) return;
    owner.current = userId;
    turn.current += 1;
    controller.current?.abort();
    clearTimers();
    conversation.current = null;
    setMessages([]);
    endTurn();
  }, [userId, endTurn, clearTimers]);

  useEffect(
    () => () => {
      turn.current += 1;
      controller.current?.abort();
      clearTimers();
    },
    [clearTimers],
  );

  const send = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text || text.length > MAX_MESSAGE_CHARS || running.current || !userId) return;
      running.current = true;
      const mine = ++turn.current;
      const me = userId;
      const alive = () => turn.current === mine && owner.current === me;
      const ctl = new AbortController();
      controller.current = ctl;
      setSending(true);
      setSlow(false);
      setLiveSteps([]);
      push({ role: 'user', text });

      const steps: Step[] = [];
      let replied = false;
      const handlers: ChatHandlers = {
        onStart: (id) => {
          if (alive()) conversation.current = id;
        },
        onStep: (s) => {
          if (!alive()) return;
          steps.push(s);
          setLiveSteps([...steps]);
          if (CART_TOOLS.has(s.tool) && s.ok) void refresh();
        },
        onReply: (r) => {
          if (!alive()) return;
          replied = true;
          push({
            role: 'assistant',
            text: r.text,
            status: r.status,
            card: r.card ?? null,
            cardText: r.card_text ?? null,
            plans: r.plans ?? null,
            payment: r.payment ?? null,
            steps: [...steps],
          });
        },
        onSlow: () => alive() && setSlow(true),
      };

      const failure = await withToken(
        (token) => sendChat(text, conversation.current, token, handlers, ctl.signal),
        (f) => f?.kind === 'sign_in',
      );
      if (!alive()) return; // stopped, or the user changed: whoever did that already tidied up
      endTurn();
      if (failure && !replied) {
        if (failure.kind === 'missing_conversation') conversation.current = null;
        if (failure.kind !== 'sign_in') push({ role: 'notice', text: failure.message, tone: failure.kind === 'limit' ? 'info' : 'error' });
      }
      void refresh(); // the contract: read the cart again after the turn
    },
    [userId, withToken, refresh, push, endTurn],
  );

  const stop = useCallback(() => {
    if (!running.current) return;
    turn.current += 1; // the running turn's late events are now ignored
    controller.current?.abort();
    endTurn();
    push({ role: 'notice', text: 'Stopped. Dawat AI stops at its next step; a step already running can still finish, so your cart is being checked.', tone: 'info' });
    void refresh();
    clearTimers();
    timers.current = LATE_REFRESH_MS.map((ms) => setTimeout(() => void refresh(), ms));
  }, [endTurn, push, refresh, clearTimers]);

  const last = messages[messages.length - 1];
  const actionableId = !sending && last?.role === 'assistant' ? last.id : null;

  const value = useMemo(() => ({ messages, sending, slow, liveSteps, send, stop, actionableId }), [messages, sending, slow, liveSteps, send, stop, actionableId]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
