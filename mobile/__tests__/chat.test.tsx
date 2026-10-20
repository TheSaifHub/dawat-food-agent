import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { Text } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { SessionProvider, useSession, type Session } from '@/lib/session';
import { CartProvider, useCart } from '@/lib/cart';
import { ChatProvider, useChat } from '@/lib/chat-context';
import { SseParser, chatBody, stepLine, stepOutcome, type Card, type PlanOption, type Reply } from '@/lib/chat';

// eslint-disable-next-line @typescript-eslint/no-require-imports
const fs = require('fs');
// eslint-disable-next-line @typescript-eslint/no-require-imports
const path = require('path');
declare const __dirname: string;

const mockStore = new Map<string, string>();
jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(async (k: string) => mockStore.get(k) ?? null),
  setItemAsync: jest.fn(async (k: string, v: string) => {
    mockStore.set(k, v);
  }),
  deleteItemAsync: jest.fn(async (k: string) => {
    mockStore.delete(k);
  }),
}));
const mockRouter = { push: jest.fn(), replace: jest.fn(), navigate: jest.fn(), back: jest.fn(), canGoBack: () => true };
jest.mock('expo-router', () => ({
  useRouter: () => mockRouter,
  useLocalSearchParams: () => ({}),
  // runs the callback when the screen mounts and its cleanup when it unmounts, like a screen gaining and losing focus
  useFocusEffect: (cb: () => void | (() => void)) => require('react').useEffect(cb, [cb]), // eslint-disable-line @typescript-eslint/no-require-imports
}));
const mockChat = jest.fn();
jest.mock('expo/fetch', () => ({ fetch: (...a: unknown[]) => mockChat(...a) }));

const KEY = 'dawat.access_token';
const TOKEN = 'tok-SECRET-AAA';
const ME = (id: string) => ({ user_id: id, display_name: 'Tester', is_demo: false, name_confirmed: true, account_name: 'Tester' });

type Call = { method: string; path: string; body: unknown; auth: string | null };
let calls: Call[];
let chatCalls: { body: Record<string, unknown>; auth: string | null; signal: AbortSignal; url: string; method: string }[];
let handlers: Record<string, (c: Call) => { status: number; body?: unknown }>;
let consoleCalls = 0;

beforeEach(() => {
  mockStore.clear();
  mockStore.set(KEY, TOKEN);
  calls = [];
  chatCalls = [];
  handlers = {
    'GET /me': (c) => ({ status: 200, body: ME(c.auth === 'Bearer tok-B' ? 'user-B' : 'user-A') }),
    'GET /cart': () => ({ status: 200, body: { status: 'empty', cart_id: null, delivery: null, branches: [], grand_total: 0 } }),
  };
  (globalThis as unknown as { fetch: unknown }).fetch = jest.fn(async (url: string, init: RequestInit) => {
    const p = url.replace('http://localhost:8000', '');
    const c: Call = { method: init.method ?? 'GET', path: p, body: init.body ? JSON.parse(init.body as string) : undefined, auth: ((init.headers ?? {}) as Record<string, string>).Authorization ?? null };
    calls.push(c);
    const h = handlers[`${c.method} ${p.split('?')[0]}`];
    if (!h) throw new TypeError('Network request failed');
    const r = h(c);
    return { ok: r.status < 300, status: r.status, text: async () => (r.body === undefined ? '' : JSON.stringify(r.body)) };
  });
  mockChat.mockReset();
  consoleCalls = 0;
  for (const m of ['log', 'info', 'warn', 'error', 'debug'] as const) jest.spyOn(console, m).mockImplementation(() => void consoleCalls++);
});
afterEach(() => jest.restoreAllMocks());

// ---- a controllable event stream, like expo/fetch's -------------------------------------------------------------
function makeStream(signal: AbortSignal) {
  const enc = new TextEncoder();
  const queue: { value?: Uint8Array; done?: boolean }[] = [];
  let waiter: { resolve: (v: unknown) => void; reject: (e: Error) => void } | null = null;
  let aborted = false;
  const deliver = (item: { value?: Uint8Array; done?: boolean }) => {
    if (waiter) {
      const w = waiter;
      waiter = null;
      w.resolve(item);
    } else queue.push(item);
  };
  signal.addEventListener('abort', () => {
    aborted = true;
    if (waiter) {
      waiter.reject(new Error('aborted'));
      waiter = null;
    }
  });
  const reader = {
    read: () =>
      aborted
        ? Promise.reject(new Error('aborted'))
        : queue.length
          ? Promise.resolve(queue.shift())
          : new Promise((resolve, reject) => {
              waiter = { resolve, reject };
            }),
  };
  return {
    res: { ok: true, status: 200, headers: { get: () => 'text/event-stream' }, body: { getReader: () => reader }, text: async () => '' },
    emit: (event: string, data: unknown) => deliver({ value: enc.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`) }),
    raw: (text: string) => deliver({ value: enc.encode(text) }),
    end: () => deliver({ done: true }),
  };
}

type Stream = ReturnType<typeof makeStream>;
/** The next /chat request streams; `script` runs when it arrives and can emit events at the test's pace. */
function nextTurn(script: (s: Stream, n: number) => void | Promise<void>) {
  mockChat.mockImplementationOnce(async (url: string, init: { method: string; headers: Record<string, string>; body: string; signal: AbortSignal }) => {
    chatCalls.push({ url, method: init.method, auth: init.headers.Authorization ?? null, body: JSON.parse(init.body), signal: init.signal });
    const s = makeStream(init.signal);
    void Promise.resolve(script(s, chatCalls.length));
    return s.res;
  });
}
const failing = (status: number, body?: unknown) =>
  mockChat.mockImplementationOnce(async (url: string, init: { method: string; headers: Record<string, string>; body: string; signal: AbortSignal }) => {
    chatCalls.push({ url, method: init.method, auth: init.headers.Authorization ?? null, body: JSON.parse(init.body), signal: init.signal });
    return { ok: false, status, headers: { get: () => 'application/json' }, body: null, text: async () => JSON.stringify(body ?? {}) };
  });

const REPLY = (over: Partial<Reply> = {}): Reply => ({ text: 'Here you go.', status: 'ok', message_id: 1, card: null, plans: null, payment: null, ...over });
const ORDER_CARD: Card = { kind: 'order', card_id: 'cd1', grand_total: 314, deliver_to: 'Madhapur', lines: [{ name: 'Idli (2 pcs)', qty: 2, line_total: 140, is_veg: true, restaurant: 'Udupi Vihar' }] };
const PLAN = (label: string): PlanOption => ({
  plan_id: `p-${label}`,
  label,
  grand_total: 471,
  items_total: 400,
  delivery_total: 25,
  taxes_total: 46,
  diet_note: null,
  budget_left: 29,
  restaurants: [{ restaurant: 'Udupi Vihar', branch_id: 'b1', branch_label: 'Madhapur', distance_km: 0.1, delivery_fee: 25, free_delivery: false, taxes: 46, total: 471, items: [{ name: 'Idli', qty: 2, line_total: 140, is_veg: true, spice_level: 0, role: 'main' }] }],
});
const happyTurn = (reply: Reply = REPLY(), steps: object[] = []) =>
  nextTurn((s) => {
    s.emit('start', { conversation_id: 'conv-1' });
    steps.forEach((st) => s.emit('step', st));
    s.emit('reply', reply);
    s.emit('done', {});
    s.end();
  });
const STEP = (tool: string, n = 1, ok = true) => ({ step: n, tool, arguments: {}, status: 'ok', ok, latency_ms: 5, counts: {} });

let chatApi: ReturnType<typeof useChat>;
let sessionApi: Session;
let cartApi: ReturnType<typeof useCart>;
function Probe() {
  chatApi = useChat();
  sessionApi = useSession();
  cartApi = useCart();
  return <Text testID="n">{String(chatApi.messages.length)}</Text>;
}
const Providers = ({ children }: { children: React.ReactNode }) => (
  <SessionProvider>
    <CartProvider>
      <ChatProvider>{children}</ChatProvider>
    </CartProvider>
  </SessionProvider>
);
async function mount() {
  await render(
    <Providers>
      <Probe />
    </Providers>,
  );
  await waitFor(() => expect(sessionApi.state.status).toBe('signedIn'));
  await waitFor(() => expect(cartApi.loading).toBe(false));
}
const cartGets = () => calls.filter((c) => c.method === 'GET' && c.path === '/cart').length;
const sendAndWait = async (text: string) => {
  await act(async () => {
    await chatApi.send(text);
  });
};

describe('reading the event stream', () => {
  test('events survive being cut anywhere, CRLF, and several in one chunk', () => {
    const p = new SseParser();
    const whole = 'event: start\ndata: {"a":1}\n\nevent: step\ndata: {"b":2}\n\n';
    const got = [];
    for (const ch of whole) got.push(...p.push(ch)); // one character at a time
    expect(got).toEqual([
      { event: 'start', data: '{"a":1}' },
      { event: 'step', data: '{"b":2}' },
    ]);
    expect(new SseParser().push('event: reply\r\ndata: {"c":3}\r\n\r\nevent: done\ndata: {}\n\n')).toEqual([
      { event: 'reply', data: '{"c":3}' },
      { event: 'done', data: '{}' },
    ]);
  });
  test('the request body is the words and the conversation id, nothing else', () => {
    expect(chatBody('hi', null)).toEqual({ message: 'hi' });
    expect(chatBody('hi', 'c1')).toEqual({ message: 'hi', conversation_id: 'c1' });
  });
  test('step words use the tool name, search words and counts, never a price', () => {
    expect(stepLine({ ...STEP('search_dishes'), arguments: { query: 'biryani', area: 'Madhapur', max_price: 500 }, counts: { results_count: 12 } })).toBe('Searched dishes: “biryani”, Madhapur · 12 results');
    expect(stepOutcome({ ...STEP('x'), ok: false }).good).toBe(false);
    expect(stepOutcome({ ...STEP('x'), status: 'confirm_plan' }).text).toBe('asking you first');
  });
});

describe('sending and streaming', () => {
  test('the first message sends only its words with the bearer token; the next adds the conversation id', async () => {
    await mount();
    happyTurn();
    await sendAndWait('biryani for 2');
    happyTurn();
    await sendAndWait('and a dessert');
    expect(chatCalls.map((c) => [c.method, c.url, c.auth])).toEqual([
      ['POST', 'http://localhost:8000/chat', `Bearer ${TOKEN}`],
      ['POST', 'http://localhost:8000/chat', `Bearer ${TOKEN}`],
    ]);
    expect(chatCalls[0].body).toEqual({ message: 'biryani for 2' });
    expect(chatCalls[1].body).toEqual({ message: 'and a dessert', conversation_id: 'conv-1' });
    for (const c of chatCalls) expect(Object.keys(c.body).sort()).not.toContain('price');
    expect(JSON.stringify(chatCalls.map((c) => c.body))).not.toMatch(/price|total|user|source|amount|card_id|quote|cart_id|token/i);
  });
  test('steps show up as they arrive, before the reply', async () => {
    await mount();
    let s!: Stream;
    nextTurn((st) => {
      s = st;
      st.emit('start', { conversation_id: 'conv-1' });
    });
    let p!: Promise<void>;
    await act(async () => {
      p = chatApi.send('hello');
      await new Promise((r) => setTimeout(r, 10));
    });
    expect(chatApi.sending).toBe(true);
    expect(chatApi.liveSteps).toHaveLength(0);
    await act(async () => {
      s.emit('step', STEP('search_dishes', 1));
      await new Promise((r) => setTimeout(r, 10));
    });
    expect(chatApi.liveSteps.map((x) => x.tool)).toEqual(['search_dishes']);
    expect(chatApi.messages.filter((m) => m.role === 'assistant')).toHaveLength(0);
    await act(async () => {
      s.emit('reply', REPLY({ text: 'Found some.' }));
      s.emit('done', {});
      s.end();
      await p;
    });
    expect(chatApi.sending).toBe(false);
    const a = chatApi.messages.find((m) => m.role === 'assistant');
    expect(a && a.role === 'assistant' && a.steps.map((x) => x.tool)).toEqual(['search_dishes']);
  });
  test('only one turn at a time, and empty or over-long messages are not sent', async () => {
    await mount();
    let s!: Stream;
    nextTurn((st) => {
      s = st;
    });
    let p!: Promise<void>;
    nextTurn(() => undefined); // if the app wrongly sends a second request, this records it
    await act(async () => {
      p = chatApi.send('one');
      await new Promise((r) => setTimeout(r, 10));
      void chatApi.send('two');
      void chatApi.send('   ');
      await new Promise((r) => setTimeout(r, 10));
    });
    expect(chatCalls).toHaveLength(1);
    await act(async () => {
      s.emit('reply', REPLY());
      s.end();
      await p;
    });
    await sendAndWait('x'.repeat(2001));
    expect(chatCalls).toHaveLength(1);
  });
  test('the token is never in a message, a notice or the console', async () => {
    await mount();
    failing(500);
    await sendAndWait('hi');
    expect(JSON.stringify(chatApi.messages)).not.toContain(TOKEN);
    expect(consoleCalls).toBe(0);
  });
});

describe('the cart follows the chat', () => {
  test('a cart-changing step refreshes the cart at once; a search step does not; and the cart is read after the turn', async () => {
    await mount();
    const base = cartGets();
    let s!: Stream;
    nextTurn((st) => {
      s = st;
      st.emit('start', { conversation_id: 'c' });
    });
    let p!: Promise<void>;
    await act(async () => {
      p = chatApi.send('add idli');
      await new Promise((r) => setTimeout(r, 10));
      s.emit('step', STEP('search_dishes', 1));
      await new Promise((r) => setTimeout(r, 20));
    });
    expect(cartGets()).toBe(base);
    await act(async () => {
      s.emit('step', STEP('add_to_cart', 2));
      await new Promise((r) => setTimeout(r, 20));
    });
    expect(cartGets()).toBe(base + 1);
    await act(async () => {
      s.emit('reply', REPLY());
      s.emit('done', {});
      s.end();
      await p;
    });
    expect(cartGets()).toBe(base + 2);
  });
  test('a failed cart step does not trigger a refresh', async () => {
    await mount();
    const base = cartGets();
    nextTurn((st) => {
      st.emit('step', STEP('add_to_cart', 1, false));
      st.emit('reply', REPLY());
      st.end();
    });
    await sendAndWait('add');
    expect(cartGets()).toBe(base + 1); // only the one after the turn
  });
});

describe('how a turn can fail: only a real 401 signs the user out', () => {
  test('401 signs out, deletes the saved sign-in and shows the notice on Welcome', async () => {
    await mount();
    failing(401, { detail: 'expired' });
    await sendAndWait('hi');
    expect(sessionApi.state).toMatchObject({ status: 'signedOut', notice: 'Please sign in again.' });
    expect(mockStore.has(KEY)).toBe(false);
  });
  test.each([
    ['429 daily limit', 429, { status: 'daily_limit', message: 'Dawat AI has reached its daily limit.' }, /daily limit/],
    ['429 hourly limit', 429, { status: 'rate_limited', message: 'Too many messages this hour.' }, /Too many messages/],
    ['422', 422, {}, /can't be sent/],
    ['500', 500, {}, /went wrong/],
  ])('%s: a notice, still signed in, sign-in kept', async (_n, status, body, words) => {
    await mount();
    failing(status as number, body);
    await sendAndWait('hi');
    expect(sessionApi.state.status).toBe('signedIn');
    expect(mockStore.get(KEY)).toBe(TOKEN);
    const n = chatApi.messages.find((m) => m.role === 'notice');
    expect(n && n.text).toMatch(words);
    expect(chatApi.sending).toBe(false);
  });
  test('a network error keeps the user signed in and says so', async () => {
    await mount();
    mockChat.mockImplementationOnce(async () => {
      throw new TypeError('Network request failed');
    });
    await sendAndWait('hi');
    expect(sessionApi.state.status).toBe('signedIn');
    expect(mockStore.get(KEY)).toBe(TOKEN);
    expect(chatApi.messages.find((m) => m.role === 'notice')?.text).toMatch(/Can't reach Dawat/);
  });
  test('a stream that ends with an error event shows its message; still signed in', async () => {
    await mount();
    nextTurn((s) => {
      s.emit('error', { message: 'Something broke on our side.' });
      s.emit('done', {});
      s.end();
    });
    await sendAndWait('hi');
    expect(chatApi.messages.find((m) => m.role === 'notice')?.text).toBe('Something broke on our side.');
    expect(sessionApi.state.status).toBe('signedIn');
  });
  test('an unknown conversation (404) starts a new one on the next message', async () => {
    await mount();
    happyTurn();
    await sendAndWait('one');
    failing(404, { status: 'not_found' });
    await sendAndWait('two');
    happyTurn();
    await sendAndWait('three');
    expect(chatCalls[1].body).toEqual({ message: 'two', conversation_id: 'conv-1' });
    expect(chatCalls[2].body).toEqual({ message: 'three' });
  });
});

describe('stopping, and leaving the screen', () => {
  test('stop aborts the request, ignores whatever arrives later, and reads the cart now and again soon after', async () => {
    jest.useFakeTimers({ doNotFake: ['setImmediate', 'nextTick'] });
    try {
      await mount();
      let s!: Stream;
      nextTurn((st) => {
        s = st;
        st.emit('start', { conversation_id: 'c' });
      });
      await act(async () => {
        void chatApi.send('slow one');
        await jest.advanceTimersByTimeAsync(50);
      });
      const base = cartGets();
      await act(async () => {
        chatApi.stop();
        await jest.advanceTimersByTimeAsync(5);
      });
      expect(chatCalls[0].signal.aborted).toBe(true);
      expect(chatApi.sending).toBe(false);
      expect(cartGets()).toBe(base + 1);
      await act(async () => {
        s.emit('reply', REPLY({ text: 'LATE' })); // the backend finished anyway: the app must not show it
        await jest.advanceTimersByTimeAsync(30_000);
      });
      expect(chatApi.messages.some((m) => m.role === 'assistant')).toBe(false);
      expect(cartGets()).toBe(base + 3); // now, +10 s, +25 s
      expect(chatApi.messages.find((m) => m.role === 'notice')?.text).toMatch(/Stopped/);
    } finally {
      jest.useRealTimers();
    }
  });
  test('stop with no turn running does nothing', async () => {
    await mount();
    await act(async () => chatApi.stop());
    expect(chatApi.messages).toHaveLength(0);
  });
});

describe('whose chat it is', () => {
  const wrapScreen = (ui: React.ReactElement) => (
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 360, height: 800 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
      <Providers>{ui}</Providers>
    </SafeAreaProvider>
  );
  test('signing out empties the chat and drops a running turn; the next user starts a new conversation', async () => {
    await mount();
    happyTurn(REPLY({ text: 'A-private' }));
    await sendAndWait('mine');
    expect(chatApi.messages.length).toBe(2);
    let s!: Stream;
    nextTurn((st) => {
      s = st;
    });
    await act(async () => {
      void chatApi.send('another');
      await new Promise((r) => setTimeout(r, 10));
      await sessionApi.signOut();
    });
    expect(chatApi.messages).toHaveLength(0);
    expect(chatCalls[1].signal.aborted).toBe(true);
    await act(async () => {
      s.emit('reply', REPLY({ text: 'LATE-FOR-A' }));
      await new Promise((r) => setTimeout(r, 10));
    });
    expect(chatApi.messages).toHaveLength(0);
    await act(async () => {
      await sessionApi.signInWithToken('tok-B');
    });
    await waitFor(() => expect(sessionApi.state.status).toBe('signedIn'));
    happyTurn();
    await sendAndWait('hello from B');
    expect(chatCalls[2].body).toEqual({ message: 'hello from B' }); // not A's conversation id
    expect(chatCalls[2].auth).toBe('Bearer tok-B');
    expect(JSON.stringify(chatApi.messages)).not.toContain('A-private');
  });
  test('a late 401 for the old user cannot sign the new user out', async () => {
    await mount();
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    mockChat.mockImplementationOnce(async (url: string, init: { method: string; headers: Record<string, string>; body: string; signal: AbortSignal }) => {
      chatCalls.push({ url, method: init.method, auth: init.headers.Authorization ?? null, body: JSON.parse(init.body), signal: init.signal });
      await gate; // the old user's request is still out when the user changes
      return { ok: false, status: 401, headers: { get: () => 'application/json' }, body: null, text: async () => '{}' };
    });
    await act(async () => {
      void chatApi.send('mine');
      await new Promise((r) => setTimeout(r, 10));
      await sessionApi.signOut();
      await sessionApi.signInWithToken('tok-B');
    });
    await waitFor(() => expect(sessionApi.state.status).toBe('signedIn'));
    await act(async () => {
      release();
      await new Promise((r) => setTimeout(r, 30));
    });
    expect(sessionApi.state.status).toBe('signedIn');
    expect(mockStore.get(KEY)).toBe('tok-B');
  });
  test('leaving the chat screen stops the stream (the providers stay mounted)', async () => {
    const ChatScreen = require('@/app/(tabs)/chat').default as React.ComponentType;
    let setShow!: (v: boolean) => void;
    function Host() {
      const [show, set] = require('react').useState(true) as [boolean, (v: boolean) => void];
      setShow = set;
      return show ? <ChatScreen /> : <Probe />;
    }
    await render(wrapScreen(<Host />));
    await screen.findByLabelText('Message Dawat AI');
    await waitFor(() => expect(calls.some((c) => c.path === '/me')).toBe(true));
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30));
    });
    nextTurn(() => undefined);
    await fireEvent.press(await screen.findByRole('button', { name: 'Biryani for 2, less spicy' }));
    await waitFor(() => expect(chatCalls).toHaveLength(1));
    expect(chatCalls[0].signal.aborted).toBe(false);
    await act(async () => {
      setShow(false); // the user goes to another tab: only the screen goes away
    });
    expect(chatCalls[0].signal.aborted).toBe(true);
    expect(chatApi.sending).toBe(false);
  });
});

describe('cards: the answer is a plain "Yes" or "No" in the chat, nothing else', () => {
  jest.setTimeout(30_000);
  const wrapScreen = (ui: React.ReactElement) => (
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 360, height: 800 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
      <Providers>{ui}</Providers>
    </SafeAreaProvider>
  );
  const open = async () => {
    const ChatScreen = require('@/app/(tabs)/chat').default as React.ComponentType;
    await render(wrapScreen(<ChatScreen />));
    await screen.findByLabelText('Message Dawat AI');
    // signed in: the screen shows before the session has answered /me, and sending needs a user
    await waitFor(() => expect(calls.some((c) => c.path === '/me')).toBe(true));
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30));
    });
  };
  const typeAndSend = async (text: string) => {
    await fireEvent.changeText(screen.getByLabelText('Message Dawat AI'), text);
    await fireEvent.press(screen.getByRole('button', { name: 'Send' }));
  };

  test('Yes sends exactly "Yes" and No sends exactly "No"; no confirm, order or payment route is ever called', async () => {
    await open();
    happyTurn(REPLY({ text: 'Ready to order?', card: ORDER_CARD, cardText: 'Order 2 Idli for Rs 314' } as Partial<Reply>));
    await typeAndSend('order my idli');
    const yesButton = await screen.findByRole('button', { name: /^Yes/ });
    happyTurn(REPLY({ text: 'Okay.' }));
    await fireEvent.press(yesButton);
    await waitFor(() => expect(chatCalls).toHaveLength(2));
    expect(chatCalls[1].body.message).toBe('Yes');
    expect(Object.keys(chatCalls[1].body).sort()).toEqual(['conversation_id', 'message']);
    expect(calls.filter((c) => /\/cart\/confirm|\/orders|\/payments|\/cart\/plan/.test(c.path))).toHaveLength(0);
  });

  test('"No" is sent as exactly "No"', async () => {
    await open();
    happyTurn(REPLY({ text: 'Ready to order?', card: ORDER_CARD }));
    await typeAndSend('order');
    const noButton = await screen.findByRole('button', { name: /^No/ });
    happyTurn(REPLY({ text: 'Okay, not ordering.' }));
    await fireEvent.press(noButton);
    await waitFor(() => expect(chatCalls).toHaveLength(2));
    expect(chatCalls[1].body.message).toBe('No');
    expect(calls.filter((c) => /\/cart\/confirm|\/orders|\/payments|\/cart\/plan/.test(c.path))).toHaveLength(0);
  });

  test('a card can be answered only under the latest reply: not while a turn runs, not after a newer message', async () => {
    await open();
    happyTurn(REPLY({ text: 'Ready to order?', card: ORDER_CARD }));
    await typeAndSend('order');
    const yes = await screen.findByRole('button', { name: /^Yes/ });
    expect(yes).toBeTruthy();
    // a newer message goes out: the old card loses its buttons at once, while the turn runs
    nextTurn(() => undefined); // never answers
    await typeAndSend('actually, show me the cart');
    await waitFor(() => expect(chatCalls).toHaveLength(2));
    expect(screen.queryByRole('button', { name: /^Yes/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /^No/ })).toBeNull();
    expect(screen.getByText(/This question has passed/)).toBeTruthy();
  });

  test('if the answer fails to send, the old card is not offered again', async () => {
    await open();
    happyTurn(REPLY({ text: 'Ready to order?', card: ORDER_CARD }));
    await typeAndSend('order');
    const yesButton = await screen.findByRole('button', { name: /^Yes/ });
    failing(500);
    await fireEvent.press(yesButton);
    await waitFor(() => expect(chatCalls).toHaveLength(2));
    await screen.findByText(/went wrong/);
    expect(screen.queryByRole('button', { name: /^Yes/ })).toBeNull();
  });

  test('plan options send a message naming the label, and are offered only under the latest reply', async () => {
    await open();
    happyTurn(REPLY({ text: 'Here are three.', plans: [PLAN('Best match'), PLAN('Best value')] }));
    await typeAndSend('budget 500');
    const choose = await screen.findByRole('button', { name: 'Choose Best value' });
    happyTurn(REPLY({ text: 'Added.' }));
    await fireEvent.press(choose);
    await waitFor(() => expect(chatCalls).toHaveLength(2));
    expect(chatCalls[1].body.message).toBe('Go with Best value');
    expect(screen.queryByRole('button', { name: 'Choose Best match' })).toBeNull();
  });

  test('the plan card says when it replaces the cart; money shown is the server figure', async () => {
    await open();
    const plan: Card = { kind: 'plan', card_id: 'p1', label: 'Best value', grand_total: 4242, deliver_to: 'Madhapur', lines: ORDER_CARD.kind === 'order' ? ORDER_CARD.lines : [], replace: true, nonveg: ['Chicken Biryani'], saved_diet: 'vegetarian' };
    happyTurn(REPLY({ text: 'Add this?', card: plan }));
    await typeAndSend('plan');
    expect(await screen.findByText('This replaces everything now in your cart.')).toBeTruthy();
    expect(screen.getByText('Total ₹4242')).toBeTruthy();
    expect(screen.getByText(/Includes non-veg: Chicken Biryani \(you saved vegetarian\)/)).toBeTruthy();
  });

  test('a reply that needs payment shows a Pay button that only opens the payment screen: the chat pays nothing', async () => {
    await open();
    happyTurn(REPLY({ text: 'Confirmed.', payment: { cart_id: 'c1', quote_id: 'q1', grand_total: 314 } }));
    await typeAndSend('yes');
    expect(await screen.findByText(/Confirmed: ₹314/)).toBeTruthy();
    const before = calls.length;
    await fireEvent.press(screen.getByRole('button', { name: 'Pay ₹314' }));
    expect(mockRouter.push).toHaveBeenCalledWith('/payment');
    expect(calls.slice(before).filter((c) => /\/payments|\/orders|\/cart\/confirm/.test(c.path))).toHaveLength(0);
    expect(chatCalls).toHaveLength(1); // and it sent no chat message either
  });

  test('the thinking panel shows while a turn runs, says Waking up on a cold start, and folds into a summary after', async () => {
    await open();
    let s!: Stream;
    nextTurn((st) => {
      s = st;
      st.emit('start', { conversation_id: 'c' });
      st.emit('step', { ...STEP('search_dishes'), counts: { results_count: 3 } });
    });
    await typeAndSend('biryani');
    expect(await screen.findByText('Dawat AI is thinking…')).toBeTruthy();
    expect(await screen.findByText(/Searched dishes · 3 results · done/)).toBeTruthy();
    await act(async () => {
      s.emit('reply', REPLY({ text: 'Done.' }));
      s.emit('done', {});
      s.end();
    });
    expect(await screen.findByRole('button', { name: /How Dawat AI got this, 1 step/ })).toBeTruthy();
    expect(screen.queryByText('Dawat AI is thinking…')).toBeNull();
  });
});

describe('source rules for the chat code', () => {
  const dir = path.join(__dirname, '..', 'src');
  const files = ['lib/chat.ts', 'lib/chat-context.tsx', 'components/ChatParts.tsx', 'app/(tabs)/chat.tsx'];
  const src = (f: string) => fs.readFileSync(path.join(dir, f), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
  test('the chat never calls confirm, order, payment or plan routes itself', () => {
    for (const f of files) expect(src(f)).not.toMatch(/['"`]\/(orders|payments|cart\/confirm|cart\/plan|cart\/items)/);
  });
  test('only the chat library talks to /chat, and the token is used only in the Authorization header', () => {
    const s = src('lib/chat.ts');
    expect(s.match(/\$\{token\}/g)).toHaveLength(1);
    expect(s).toContain('Authorization: `Bearer ${token}`');
    const handedOver = 'sendChat(text, conversation.current, token, handlers, ctl.signal)';
    expect(src('lib/chat-context.tsx')).toContain(handedOver);
    for (const f of files.filter((x) => x !== 'lib/chat.ts')) expect(src(f).replace(handedOver, '').replace('(token) =>', '')).not.toMatch(/Bearer|\btoken\b/);
  });
  test('the only words a card button sends are Yes and No', () => {
    const s = src('components/ChatParts.tsx');
    expect(s).toContain("export const YES = 'Yes';");
    expect(s).toContain("export const NO = 'No';");
    expect(s.match(/onAnswer\(([^)]*)\)/g)?.sort()).toEqual(['onAnswer(NO)', 'onAnswer(YES)']);
  });
  test('no price arithmetic in chat screens', () => {
    const money = '(price|line_total|items_total|grand_total|delivery_fee|delivery_total|taxes|total)';
    for (const f of files) {
      expect(src(f)).not.toMatch(new RegExp(`\\b${money}\\b\\s*[*+\\-/]\\s*[\\w(]`));
      expect(src(f)).not.toMatch(new RegExp(`reduce\\([^)]*${money}`));
    }
  });
});
