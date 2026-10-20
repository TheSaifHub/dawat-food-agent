import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { Text } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { SessionProvider, useSession, type Session } from '@/lib/session';
import { CartProvider } from '@/lib/cart';
import { INSTRUMENTS, TEST_NOTICE, simulateBody } from '@/lib/payments';

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
  useFocusEffect: (cb: () => void | (() => void)) => require('react').useEffect(cb, [cb]), // eslint-disable-line @typescript-eslint/no-require-imports
}));

jest.setTimeout(30_000);
const KEY = 'dawat.access_token';
const ME = { user_id: 'u1', display_name: 'Tester', is_demo: false, name_confirmed: true, account_name: 'Tester' };
const CONFIRMED = {
  status: 'ok',
  cart_id: 'c1',
  cart_status: 'confirmed',
  delivery: { area_id: 'madhapur', area: 'Madhapur', address_id: null, address_label: null },
  branches: [{ branch_id: 'b1', restaurant: 'Udupi Vihar', branch_label: 'Madhapur', branch_area: 'Madhapur', items: [], items_total: 360, total: 408 }],
  grand_total: 408,
  confirmed_total: 408,
  can_confirm: true,
  quote_id: 'q1',
};
const START = { status: 'ok', gateway: 'simulated', razorpay_order_id: 'order_TEST1', amount_rupees: 417, cart_id: 'c1', quote_id: 'q1' }; // 417 on purpose: not the cart's 408
const SIM_OK = { status: 'ok', razorpay_order_id: 'order_TEST1', razorpay_payment_id: 'pay_TEST_abc', razorpay_signature: 'f'.repeat(64) };
const VERIFIED = {
  status: 'ok',
  payment_status: 'paid',
  grand_total: 417,
  orders: [{ order_id: 'o1', order_number: 'DW1024', restaurant: 'Udupi Vihar', branch_label: 'Madhapur', status: 'placed', total: 417 }],
};

type Call = { method: string; path: string; body: Record<string, unknown> | undefined };
type Reply = { status: number; body?: unknown } | 'network';
let calls: Call[];
let routes: Record<string, (c: Call) => Reply | Promise<Reply>>;
const on = (key: string, r: Reply | ((c: Call) => Reply | Promise<Reply>)) => {
  routes[key] = typeof r === 'function' ? r : () => r;
};

beforeEach(() => {
  mockStore.clear();
  mockStore.set(KEY, 'tok-A');
  calls = [];
  Object.values(mockRouter).forEach((f) => typeof f === 'function' && 'mockClear' in f && (f as jest.Mock).mockClear());
  routes = {};
  on('GET /me', { status: 200, body: ME });
  on('GET /cart', { status: 200, body: CONFIRMED });
  on('POST /payments/start', { status: 200, body: START });
  on('POST /payments/simulate', { status: 200, body: SIM_OK });
  on('POST /payments/verify', { status: 200, body: VERIFIED });
  (globalThis as unknown as { fetch: unknown }).fetch = jest.fn(async (url: string, init: RequestInit) => {
    const p = url.replace('http://localhost:8000', '');
    const c: Call = { method: init.method ?? 'GET', path: p, body: init.body ? JSON.parse(init.body as string) : undefined };
    calls.push(c);
    const h = routes[`${c.method} ${p.split('?')[0]}`];
    if (!h) throw new TypeError('Network request failed');
    const r = await h(c);
    if (r === 'network') throw new TypeError('Network request failed');
    return { ok: r.status < 300, status: r.status, text: async () => (r.body === undefined ? '' : JSON.stringify(r.body)) };
  });
});

let sessionApi: Session;
function Probe() {
  sessionApi = useSession();
  return <Text testID="s">{sessionApi.state.status}</Text>;
}
async function open() {
  const PaymentScreen = require('@/app/payment').default as React.ComponentType; // eslint-disable-line @typescript-eslint/no-require-imports
  await render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 360, height: 800 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
      <SessionProvider>
        <CartProvider>
          <Probe />
          <PaymentScreen />
        </CartProvider>
      </SessionProvider>
    </SafeAreaProvider>,
  );
}
const posts = (p: string) => calls.filter((c) => c.method === 'POST' && c.path === p);
const ready = async () => screen.findByRole('button', { name: 'Pay ₹417' });
const press = async (name: string | RegExp, role: 'button' | 'radio' = 'button') => fireEvent.press(await screen.findByRole(role, { name }));

describe('opening the payment', () => {
  test('it is opened for the confirmed cart with the cart id only, and shows the SERVER amount (never the cart screen figure)', async () => {
    await open();
    await ready();
    expect(posts('/payments/start').map((c) => c.body)).toEqual([{ cart_id: 'c1' }]);
    expect(screen.getByLabelText('Amount to pay: ₹417')).toBeTruthy();
    expect(screen.queryByLabelText(/₹408/)).toBeNull();
  });
  test('the sheet says it is a test payment, in the notice and at the foot', async () => {
    expect(TEST_NOTICE).toBe('Test payment (simulated). No real money.');
    await open();
    await ready();
    expect(screen.getAllByText(TEST_NOTICE).length).toBeGreaterThanOrEqual(2);
  });
  test('a cart that is not confirmed never opens a payment', async () => {
    on('GET /cart', { status: 200, body: { ...CONFIRMED, cart_status: 'open' } });
    await open();
    expect(await screen.findByText(/nothing to pay yet/i)).toBeTruthy();
    expect(posts('/payments/start')).toHaveLength(0);
    expect(screen.queryByRole('button', { name: /^Pay/ })).toBeNull();
  });
  test('a cart held as confirmed that is open when read again on arrival never opens a payment', async () => {
    // The Cart tab already holds a confirmed cart (read 1); by the time the payment screen opens, the server says open (read 2).
    let n = 0;
    on('GET /cart', () => ({ status: 200, body: ++n === 1 ? CONFIRMED : { ...CONFIRMED, cart_status: 'open' } }));
    const PaymentScreen = require('@/app/payment').default as React.ComponentType; // eslint-disable-line @typescript-eslint/no-require-imports
    const tree = (show: boolean) => (
      <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 360, height: 800 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
        <SessionProvider>
          <CartProvider>
            <Probe />
            {show ? <PaymentScreen /> : null}
          </CartProvider>
        </SessionProvider>
      </SafeAreaProvider>
    );
    const r = await render(tree(false));
    await waitFor(() => expect(n).toBe(1));
    await r.rerender(tree(true));
    expect(await screen.findByText(/nothing to pay yet/i)).toBeTruthy();
    expect(posts('/payments/start')).toHaveLength(0);
  });
  test('an answer that is not "ok" never opens a payment, even if it carries an order id and an amount', async () => {
    on('POST /payments/start', { status: 200, body: { ...START, status: 'not_confirmed' } });
    await open();
    expect(await screen.findByText('Your cart changed. Please check it and confirm again.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /^Pay/ })).toBeNull();
  });
  test('a cart that changed since it was confirmed is refused by the server and the user is sent back', async () => {
    on('POST /payments/start', { status: 409, body: { status: 'quote_changed', message: 'Tell the user internal' } });
    await open();
    expect(await screen.findByText('Your cart changed. Please check it and confirm again.')).toBeTruthy();
    expect(screen.queryByText(/internal/)).toBeNull();
    expect(screen.queryByRole('button', { name: /^Pay/ })).toBeNull();
  });
  test('opening twice (a re-render) does not start twice', async () => {
    await open();
    await ready();
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50));
    });
    expect(posts('/payments/start')).toHaveLength(1);
  });
});

describe('paying: the exact requests', () => {
  test('Pay: simulate with the order id, a success outcome and the chosen test card, then verify with exactly what came back', async () => {
    await open();
    await ready();
    await press('Pay ₹417');
    expect(await screen.findByText(/DW1024 · Udupi Vihar · ₹417/)).toBeTruthy();
    expect(posts('/payments/simulate').map((c) => c.body)).toEqual([
      { razorpay_order_id: 'order_TEST1', outcome: 'success', method: 'card', card_number: '4111 1111 1111 1111' },
    ]);
    expect(posts('/payments/verify').map((c) => c.body)).toEqual([
      { razorpay_order_id: 'order_TEST1', razorpay_payment_id: 'pay_TEST_abc', razorpay_signature: 'f'.repeat(64) },
    ]);
    expect(screen.getByText(/Paid: ₹417/)).toBeTruthy();
    expect(screen.getAllByText(TEST_NOTICE).length).toBeGreaterThanOrEqual(1);
  });
  test('nothing about an amount, expiry, CVV, user or source is ever sent', async () => {
    await open();
    await ready();
    await press('Pay ₹417');
    await screen.findByText(/Paid:/);
    const sent = JSON.stringify(calls.filter((c) => c.path.startsWith('/payments')).map((c) => c.body));
    expect(sent).not.toMatch(/amount|cvv|expiry|exp_|user|source|price|total/i);
  });
  test('the success screen refreshes the cart (the server emptied it)', async () => {
    await open();
    await ready();
    const before = calls.filter((c) => c.path === '/cart').length;
    await press('Pay ₹417');
    await screen.findByText(/Paid:/);
    await waitFor(() => expect(calls.filter((c) => c.path === '/cart').length).toBeGreaterThan(before));
  });
  test('UPI sends the UPI id and no card number', async () => {
    await open();
    await ready();
    await press('UPI');
    await press(/Test UPI id, success@razorpay/, 'radio');
    await press('Pay ₹417');
    await screen.findByText(/Paid:/);
    expect(posts('/payments/simulate')[0].body).toEqual({ razorpay_order_id: 'order_TEST1', outcome: 'success', method: 'upi', upi_id: 'success@razorpay' });
  });
  test('"Simulate failed payment" asks for a failed payment with the same instrument', async () => {
    on('POST /payments/simulate', { status: 402, body: { status: 'payment_failed', message: 'x' } });
    await open();
    await ready();
    await press('Simulate failed payment');
    await screen.findByText(/didn't go through/);
    expect(posts('/payments/simulate')[0].body).toEqual({ razorpay_order_id: 'order_TEST1', outcome: 'failure', method: 'card', card_number: '4111 1111 1111 1111' });
  });
});

describe('what a failed payment must not do', () => {
  test('a declined payment never reaches verify, shows no order, and can be tried again', async () => {
    let n = 0;
    on('POST /payments/simulate', () => (++n === 1 ? { status: 402, body: { status: 'payment_failed' } } : { status: 200, body: SIM_OK }));
    await open();
    await ready();
    await press('Pay ₹417');
    expect(await screen.findByText(/Nothing was charged and no order was placed/)).toBeTruthy();
    expect(posts('/payments/verify')).toHaveLength(0);
    expect(screen.queryByText(/DW1024/)).toBeNull();
    await press('Pay ₹417');
    expect(await screen.findByText(/DW1024 · Udupi Vihar/)).toBeTruthy();
    expect(posts('/payments/verify')).toHaveLength(1);
  });
  test('the always-declined test card is declined by the server and nothing is verified', async () => {
    on('POST /payments/simulate', (c) => ((c.body as { card_number?: string }).card_number === '4000 0000 0000 0002' ? { status: 402, body: {} } : { status: 200, body: SIM_OK }));
    await open();
    await ready();
    await press(/Test card that is always declined/, 'radio');
    await press('Pay ₹417');
    await screen.findByText(/didn't go through/);
    expect(posts('/payments/verify')).toHaveLength(0);
  });
  test('a payment that went through but whose cart changed is a refund: no order, a clear message, a way back', async () => {
    on('POST /payments/verify', { status: 409, body: { status: 'needs_refund', amount: 417, message: 'internal' } });
    await open();
    await ready();
    await press('Pay ₹417');
    expect(await screen.findByText(/no order was placed. The test payment of ₹417 is refunded \(simulated\)/)).toBeTruthy();
    expect(screen.queryByText(/DW1024|Paid:/)).toBeNull();
    await press('Back to cart');
    expect(mockRouter.replace).toHaveBeenCalledWith('/cart');
  });
  test.each([
    ['a bad signature', { status: 422, body: { status: 'bad_signature' } }, /couldn't be confirmed, so no order was placed/],
    ['payments busy', { status: 503, body: { status: 'payment_unavailable' } }, /busy right now/],
    ['a conflicting payment', { status: 409, body: { status: 'payment_conflict' } }, /different payment is already recorded/],
  ])('verify answers %s: no order is shown', async (_n, reply, words) => {
    on('POST /payments/verify', reply as Reply);
    await open();
    await ready();
    await press('Pay ₹417');
    expect(await screen.findByText(words)).toBeTruthy();
    expect(screen.queryByText(/DW1024|Paid:/)).toBeNull();
  });
  test('a network error while verifying says the payment may have gone through and offers to finish; no order is claimed', async () => {
    on('POST /payments/verify', 'network');
    await open();
    await ready();
    await press('Pay ₹417');
    expect(await screen.findByText(/may have gone through/)).toBeTruthy();
    expect(screen.queryByText(/DW1024|Paid:/)).toBeNull();
  });
  test('an odd answer from verify (no orders) is never shown as paid', async () => {
    on('POST /payments/verify', { status: 200, body: { status: 'ok', orders: [], grand_total: 417 } });
    await open();
    await ready();
    await press('Pay ₹417');
    expect(await screen.findByText(/didn't work/)).toBeTruthy();
    expect(screen.queryByText(/Paid:/)).toBeNull();
  });
  test('the tool messages are never shown to the user', async () => {
    on('POST /payments/simulate', { status: 402, body: { status: 'payment_failed', message: 'SECRET-TOOL-TEXT for the model' } });
    await open();
    await ready();
    await press('Pay ₹417');
    await screen.findByText(/didn't go through/);
    expect(screen.queryByText(/SECRET-TOOL-TEXT/)).toBeNull();
  });
});

describe('one payment at a time, and identity', () => {
  test('pressing Pay twice quickly sends one payment', async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    on('POST /payments/simulate', async () => {
      await gate;
      return { status: 200, body: SIM_OK };
    });
    await open();
    const btn = await ready();
    await act(async () => {
      fireEvent.press(btn);
      fireEvent.press(btn);
      await new Promise((r) => setTimeout(r, 20));
    });
    expect(posts('/payments/simulate')).toHaveLength(1);
    await act(async () => {
      release();
      await new Promise((r) => setTimeout(r, 30));
    });
    expect(posts('/payments/verify')).toHaveLength(1);
  });
  test('a real 401 while paying signs the user out; nothing is shown as paid', async () => {
    on('POST /payments/simulate', { status: 401, body: { detail: 'expired' } });
    await open();
    await ready();
    await press('Pay ₹417');
    await waitFor(() => expect(sessionApi.state.status).toBe('signedOut'));
    expect(screen.queryByText(/Paid:/)).toBeNull();
  });
  test('a network error while paying does not sign the user out and verifies nothing', async () => {
    on('POST /payments/simulate', 'network');
    await open();
    await ready();
    await press('Pay ₹417');
    await screen.findByText(/Can't reach Dawat/);
    expect(sessionApi.state.status).toBe('signedIn');
    expect(posts('/payments/verify')).toHaveLength(0);
  });
});

describe('only the fixed test values', () => {
  test('the choices are exactly the contract’s test values, and nothing can be typed', async () => {
    expect(INSTRUMENTS.map((i) => i.value).sort()).toEqual(['4000 0000 0000 0002', '4111 1111 1111 1111', '5555 5555 5555 4444', 'failure@razorpay', 'success@razorpay'].sort());
    await open();
    await ready();
    expect(JSON.stringify(screen.toJSON())).not.toContain('"TextInput"');
    await press('UPI');
    expect(JSON.stringify(screen.toJSON())).not.toContain('"TextInput"');
  });
  test('the simulate body for a card or a UPI id holds only the instrument value', () => {
    const start = { razorpay_order_id: 'o', amount_rupees: 1, gateway: 'simulated', cart_id: 'c', quote_id: 'q' };
    expect(Object.keys(simulateBody(start, INSTRUMENTS[0], 'success')).sort()).toEqual(['card_number', 'method', 'outcome', 'razorpay_order_id']);
    expect(Object.keys(simulateBody(start, INSTRUMENTS[3], 'failure')).sort()).toEqual(['method', 'outcome', 'razorpay_order_id', 'upi_id']);
  });
});

describe('source rules for the payment code', () => {
  const dir = path.join(__dirname, '..', 'src');
  const files = ['lib/payments.ts', 'app/payment.tsx'];
  const src = (f: string) => fs.readFileSync(path.join(dir, f), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
  test('nothing about the payment is stored, logged or typed', () => {
    for (const f of files) {
      const s = src(f);
      expect(s).not.toMatch(/SecureStore|AsyncStorage|localStorage|console\./);
      expect(s).not.toMatch(/TextInput/);
      expect(s).not.toMatch(/cvv|expiry/i);
    }
  });
  test('no request body carries an amount', () => {
    for (const f of files) expect(src(f)).not.toMatch(/body:\s*\{[^}]*amount/);
    expect(src('lib/payments.ts')).not.toMatch(/amount\s*:\s*[^,}]*\bbody\b/);
  });
  test('the app never calls the order-creating routes itself', () => {
    for (const f of files) expect(src(f)).not.toMatch(/request(?:<[\s\S]*?>)?\(\s*['"`]\/(orders|cart\/confirm)/);
  });
});
