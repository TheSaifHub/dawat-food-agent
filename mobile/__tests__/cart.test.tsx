import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { Text } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { SessionProvider, useSession, type Session } from '@/lib/session';
import { AreaProvider } from '@/lib/area';
import { CartProvider, countItems, qtyInCart, sayWhy, useCart, type Cart } from '@/lib/cart';

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
  // runs the callback once when the screen mounts, like a screen coming into focus
  useFocusEffect: (cb: () => void) => require('react').useEffect(cb, []), // eslint-disable-line @typescript-eslint/no-require-imports
}));

const KEY = 'dawat.access_token';
const ME = (id: string) => ({ user_id: id, display_name: 'Tester', is_demo: false, name_confirmed: true, account_name: 'Tester' });

const MADHAPUR = { area_id: 'madhapur', name: 'Madhapur' };
const BORABANDA = { area_id: 'borabanda', area: 'Borabanda', address_id: null, address_label: null };
const LINE = { item_id: 'i1', name: 'Idli', price: 70, qty: 2, line_total: 140, is_veg: true, spice_level: 0, serves: 1 };
// Deliberately NOT adding up (items 140 + fee 25 + GST 7 would be 172): the app must show what the server says.
const CART = (over: Partial<Cart> = {}): Cart => ({
  status: 'ok',
  cart_id: 'c1',
  cart_status: 'open',
  delivery: { area_id: 'madhapur', area: 'Madhapur', address_id: null, address_label: null },
  branches: [
    { branch_id: 'b1', restaurant: 'Udupi Vihar', branch_label: 'Madhapur', branch_area: 'Madhapur', items: [LINE], items_total: 140, delivery_fee: 25, free_delivery: false, taxes: 9, total: 999 },
  ],
  items_total: 140,
  delivery_total: 25,
  taxes_total: 9,
  grand_total: 4242,
  can_confirm: true,
  quote_id: 'q1',
  ...over,
});

type Call = { method: string; path: string; body: unknown; auth: string | null };
let calls: Call[];
type Handler = (c: Call) => { status: number; body?: unknown } | Promise<{ status: number; body?: unknown }> | 'network';
let handlers: Record<string, Handler>;
const on = (key: string, h: Handler) => {
  handlers[key] = h;
};

beforeEach(() => {
  mockStore.clear();
  mockStore.set(KEY, 'tok-A');
  calls = [];
  handlers = {};
  on('GET /me', (c) => ({ status: 200, body: ME(c.auth === 'Bearer tok-B' ? 'user-B' : 'user-A') }));
  (globalThis as unknown as { fetch: unknown }).fetch = jest.fn(async (url: string, init: RequestInit) => {
    const p = url.replace('http://localhost:8000', '');
    const c: Call = {
      method: init.method ?? 'GET',
      path: p,
      body: init.body ? JSON.parse(init.body as string) : undefined,
      auth: ((init.headers ?? {}) as Record<string, string>).Authorization ?? null,
    };
    calls.push(c);
    const h = handlers[`${c.method} ${p.split('?')[0]}`];
    if (!h) throw new TypeError('Network request failed');
    const r = await h(c);
    if (r === 'network') throw new TypeError('Network request failed');
    return { ok: r.status < 300, status: r.status, text: async () => (r.body === undefined ? '' : JSON.stringify(r.body)) };
  });
});

let cartApi: ReturnType<typeof useCart>;
let sessionApi: Session;
function Probe() {
  cartApi = useCart();
  sessionApi = useSession();
  return (
    <>
      <Text testID="total">{String(cartApi.cart?.grand_total ?? 'none')}</Text>
      <Text testID="count">{String(cartApi.itemCount)}</Text>
    </>
  );
}
const total = () => screen.getByTestId('total').props.children;
async function mount() {
  await render(
    <SessionProvider>
      <CartProvider>
        <Probe />
      </CartProvider>
    </SessionProvider>,
  );
  await waitFor(() => expect(cartApi.loading).toBe(false));
}
const bodiesOf = (m: string) => calls.filter((c) => c.method === m).map((c) => c.body);

describe('loading and showing the server cart', () => {
  test('the cart is fetched with the sign-in token, and shown exactly as the server sent it (never recomputed)', async () => {
    on('GET /cart', () => ({ status: 200, body: CART() }));
    await mount();
    expect(calls.find((c) => c.path === '/cart')?.auth).toBe('Bearer tok-A');
    expect(total()).toBe('4242'); // 140 + 25 + 9 would be 174: the app shows the server's number
    expect(cartApi.cart?.branches[0].total).toBe(999);
  });
  test('a failed load says so (and keeps no stale cart)', async () => {
    on('GET /cart', () => 'network');
    await mount();
    expect(cartApi.cart).toBeNull();
    expect(cartApi.loadError).toMatch(/Can't reach Dawat/);
  });
});

describe('what is sent', () => {
  test('add sends the ids and a quantity of 1, nothing else: never a price, a user id or a source', async () => {
    on('GET /cart', () => ({ status: 200, body: { status: 'empty', cart_id: null, delivery: null, branches: [], grand_total: null } }));
    on('POST /cart/items', () => ({ status: 200, body: { status: 'ok', cart: CART() } }));
    await mount();
    await act(async () => {
      await cartApi.add('i1', 'b1', 'Idli');
    });
    expect(bodiesOf('POST')).toEqual([{ item_id: 'i1', branch_id: 'b1', qty: 1 }]);
    const everything = JSON.stringify(calls.map((c) => [c.path, c.body]));
    expect(everything).not.toMatch(/price|total|user|source|amount|fee/i);
  });
  test('the cart in the answer replaces the screen cart', async () => {
    on('GET /cart', () => ({ status: 200, body: { status: 'empty', cart_id: null, delivery: null, branches: [], grand_total: null } }));
    on('POST /cart/items', () => ({ status: 200, body: { status: 'ok', cart: CART({ grand_total: 777 }) } }));
    await mount();
    await act(async () => {
      await cartApi.add('i1', 'b1', 'Idli');
    });
    expect(total()).toBe('777');
    expect(screen.getByTestId('count').props.children).toBe('2');
  });
  test('a brand-new cart with no delivery point gets the browsed area; one that has a point keeps it', async () => {
    on('GET /cart', () => ({ status: 200, body: { status: 'empty', cart_id: null, delivery: null, branches: [], grand_total: null } }));
    on('POST /cart/items', () => ({ status: 200, body: { status: 'ok', cart: CART() } }));
    on('PUT /cart/delivery', () => ({ status: 200, body: { status: 'ok', cart: { status: 'empty', cart_id: 'c1', delivery: CART().delivery, branches: [], grand_total: 0 } } }));
    await mount();
    await act(async () => {
      await cartApi.add('i1', 'b1', 'Idli', MADHAPUR);
    });
    expect(calls.filter((c) => c.method === 'PUT').map((c) => c.body)).toEqual([{ area: 'Madhapur' }]);
    calls.length = 0;
    on('POST /cart/items', () => ({ status: 200, body: { status: 'ok', cart: CART() } }));
    await act(async () => {
      await cartApi.add('i1', 'b1', 'Idli', MADHAPUR);
    });
    expect(calls.filter((c) => c.method === 'PUT')).toHaveLength(0);
  });
  test('remove: one carries qty=1, a whole line carries none, and the branch is always named', async () => {
    on('GET /cart', () => ({ status: 200, body: CART() }));
    on('DELETE /cart/items/i%2F1', () => ({ status: 200, body: { status: 'ok', cart: CART() } }));
    await mount();
    await act(async () => {
      await cartApi.remove('i/1', 'b1', 1);
      await cartApi.remove('i/1', 'b1');
    });
    expect(calls.filter((c) => c.method === 'DELETE').map((c) => c.path)).toEqual([
      '/cart/items/i%2F1?branch_id=b1&qty=1',
      '/cart/items/i%2F1?branch_id=b1',
    ]);
  });
  test('a refused add shows the app’s own words, never the tool’s message, and refreshes the cart', async () => {
    on('GET /cart', () => ({ status: 200, body: CART() }));
    on('POST /cart/items', () => ({ status: 409, body: { status: 'qty_limit', max_qty: 10, message: 'Tell the user the limit is hit. SECRET-TOOL-TEXT' } }));
    await mount();
    let out: { ok: boolean; message: string } | undefined;
    await act(async () => {
      out = await cartApi.add('i1', 'b1', 'Idli');
    });
    expect(out).toEqual({ ok: false, message: 'At most 10 of one dish per order.' });
    expect(calls.filter((c) => c.path === '/cart').length).toBeGreaterThanOrEqual(2);
  });
});

describe('which area a cart delivers to', () => {
  const EMPTY = { status: 'empty', cart_id: 'c0', delivery: BORABANDA, branches: [], grand_total: 0 };
  test('the first dish in an empty cart delivers to the browsed area, not the backend default', async () => {
    on('GET /cart', () => ({ status: 200, body: EMPTY }));
    let point = 'borabanda';
    on('PUT /cart/delivery', (c) => {
      point = (c.body as { area: string }).area.toLowerCase();
      return { status: 200, body: { status: 'ok', cart: { ...EMPTY, delivery: { ...BORABANDA, area_id: point, area: 'Madhapur' } } } };
    });
    // like the real backend: a dish beyond range of the cart's CURRENT delivery point is refused
    on('POST /cart/items', () => (point === 'madhapur' ? { status: 200, body: { status: 'ok', cart: CART() } } : { status: 409, body: { status: 'too_far', distance_km: 13.4, max_km: 8 } }));
    await mount();
    await act(async () => {
      await cartApi.add('i1', 'b1', 'Idli', MADHAPUR);
    });
    expect(cartApi.cart?.delivery?.area).toBe('Madhapur');
    // the delivery point is set BEFORE the dish is added (the backend refuses a dish beyond range of the old point)
    const writes = calls.filter((c) => c.method !== 'GET').map((c) => `${c.method} ${c.path}`);
    expect(writes).toEqual(['PUT /cart/delivery', 'POST /cart/items']);
    expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({ area: 'Madhapur' });
  });
  test('a cart that already has dishes keeps its delivery point, even when another area is browsed', async () => {
    on('GET /cart', () => ({ status: 200, body: CART({ delivery: BORABANDA }) }));
    on('POST /cart/items', () => ({ status: 200, body: { status: 'ok', cart: CART({ delivery: BORABANDA }) } }));
    await mount();
    await act(async () => {
      await cartApi.add('i2', 'b1', 'Dosa', MADHAPUR);
    });
    expect(calls.filter((c) => c.method === 'PUT')).toHaveLength(0);
    expect(cartApi.cart?.delivery?.area).toBe('Borabanda');
  });
  test('nothing is changed when the cart already delivers to the browsed area', async () => {
    on('GET /cart', () => ({ status: 200, body: { ...EMPTY, delivery: { ...BORABANDA, area_id: 'madhapur', area: 'Madhapur' } } }));
    on('POST /cart/items', () => ({ status: 200, body: { status: 'ok', cart: CART() } }));
    await mount();
    await act(async () => {
      await cartApi.add('i1', 'b1', 'Idli', MADHAPUR);
    });
    expect(calls.filter((c) => c.method === 'PUT')).toHaveLength(0);
  });
  test('a user who is not browsing any area does not change the backend default', async () => {
    on('GET /cart', () => ({ status: 200, body: EMPTY }));
    on('POST /cart/items', () => ({ status: 200, body: { status: 'ok', cart: CART({ delivery: BORABANDA }) } }));
    await mount();
    await act(async () => {
      await cartApi.add('i1', 'b1', 'Idli', null);
    });
    expect(calls.filter((c) => c.method === 'PUT')).toHaveLength(0);
  });
  test('if setting the area fails, the dish is still tried and the user is told', async () => {
    on('GET /cart', () => ({ status: 200, body: EMPTY }));
    on('POST /cart/items', () => ({ status: 200, body: { status: 'ok', cart: CART({ delivery: BORABANDA }) } }));
    on('PUT /cart/delivery', () => ({ status: 422, body: { status: 'unknown_area' } }));
    await mount();
    let out: { ok: boolean; message: string } | undefined;
    await act(async () => {
      out = await cartApi.add('i1', 'b1', 'Idli', MADHAPUR);
    });
    expect(out?.ok).toBe(true);
    expect(out?.message).toMatch(/could not set delivery to Madhapur/);
  });
});

describe('writes go one at a time, in tap order', () => {
  test('a second tap waits for the first; the last answer wins even if the first is slow', async () => {
    on('GET /cart', () => ({ status: 200, body: CART({ grand_total: 1 }) }));
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    let n = 0;
    on('POST /cart/items', async () => {
      n += 1;
      if (n === 1) await gate;
      return { status: 200, body: { status: 'ok', cart: CART({ grand_total: n === 1 ? 111 : 222 }) } };
    });
    await mount();
    let p1!: Promise<unknown>, p2!: Promise<unknown>;
    await act(async () => {
      p1 = cartApi.add('i1', 'b1', 'Idli');
      p2 = cartApi.add('i2', 'b1', 'Dosa');
      await new Promise((r) => setTimeout(r, 20));
      expect(calls.filter((c) => c.method === 'POST')).toHaveLength(1); // the second has not been sent yet
      release();
      await Promise.all([p1, p2]);
    });
    expect(bodiesOf('POST')).toEqual([
      { item_id: 'i1', branch_id: 'b1', qty: 1 },
      { item_id: 'i2', branch_id: 'b1', qty: 1 },
    ]);
    expect(total()).toBe('222');
  });
});

describe('whose cart it is', () => {
  test('signing out empties the cart at once, and a late answer cannot bring it back', async () => {
    on('GET /cart', () => ({ status: 200, body: CART() }));
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    on('POST /cart/items', async () => {
      await gate;
      return { status: 200, body: { status: 'ok', cart: CART({ grand_total: 555 }) } };
    });
    await mount();
    let p!: Promise<unknown>;
    await act(async () => {
      p = cartApi.add('i1', 'b1', 'Idli');
      await new Promise((r) => setTimeout(r, 10));
      await sessionApi.signOut();
    });
    expect(total()).toBe('none');
    await act(async () => {
      release();
      await p;
    });
    expect(total()).toBe('none');
  });
  test('another user signing in never sees the first user’s cart', async () => {
    on('GET /cart', (c) => ({ status: 200, body: c.auth === 'Bearer tok-A' ? CART({ grand_total: 1111 }) : { status: 'empty', cart_id: null, delivery: null, branches: [], grand_total: null } }));
    await mount();
    expect(total()).toBe('1111');
    await act(async () => {
      await sessionApi.signOut();
    });
    expect(total()).toBe('none');
    await act(async () => {
      await sessionApi.signInWithToken('tok-B');
    });
    await waitFor(() => expect(cartApi.loading).toBe(false));
    expect(total()).toBe('none');
    expect(calls.filter((c) => c.path === '/cart').pop()?.auth).toBe('Bearer tok-B');
  });
  test('a real 401 on a cart call signs the user out and clears the cart', async () => {
    on('GET /cart', () => ({ status: 200, body: CART() }));
    on('POST /cart/items', () => ({ status: 401, body: { detail: 'Invalid token' } }));
    await mount();
    await act(async () => {
      await cartApi.add('i1', 'b1', 'Idli');
    });
    expect(sessionApi.state.status).toBe('signedOut');
    expect(total()).toBe('none');
  });
});

describe('the confirm step: exactly the quote on screen, no order, no payment', () => {
  test('sends the cart id and quote id of the cart on screen, and only that', async () => {
    on('GET /cart', () => ({ status: 200, body: CART({ quote_id: 'Q-ON-SCREEN' }) }));
    on('POST /cart/confirm', () => ({ status: 200, body: { status: 'ok', cart: CART({ cart_status: 'confirmed', confirmed_total: 4242 }) } }));
    await mount();
    let out: unknown;
    await act(async () => {
      out = await cartApi.confirm();
    });
    expect(out).toEqual({ ok: true, confirmedTotal: 4242 });
    expect(bodiesOf('POST')).toEqual([{ cart_id: 'c1', quote_id: 'Q-ON-SCREEN' }]);
    expect(calls.filter((c) => /\/orders|\/payments/.test(c.path))).toHaveLength(0);
  });
  test.each([
    ['can_confirm is false', { can_confirm: false }],
    ['there is no quote', { quote_id: undefined }],
    ['the total is unknown', { grand_total: null }],
    ['there is no cart id', { cart_id: null }],
  ])('nothing is sent when %s', async (_n, over) => {
    on('GET /cart', () => ({ status: 200, body: CART(over as Partial<Cart>) }));
    await mount();
    let out: { ok: boolean } | undefined;
    await act(async () => {
      out = await cartApi.confirm();
    });
    expect(out?.ok).toBe(false);
    expect(calls.filter((c) => c.path === '/cart/confirm')).toHaveLength(0);
  });
  test('a stale quote is refused by the server: the user is told, and the new bill is fetched to be read again', async () => {
    let n = 0;
    on('GET /cart', () => ({ status: 200, body: CART({ grand_total: ++n === 1 ? 4242 : 5000, quote_id: n === 1 ? 'q1' : 'q2' }) }));
    on('POST /cart/confirm', () => ({ status: 409, body: { status: 'stale_quote', message: 'internal text' } }));
    await mount();
    let out: { ok: boolean; message?: string } | undefined;
    await act(async () => {
      out = await cartApi.confirm();
    });
    expect(out?.ok).toBe(false);
    expect(out?.message).toMatch(/changed/);
    await waitFor(() => expect(total()).toBe('5000'));
  });
});

describe('helpers', () => {
  test('qtyInCart is per branch: the same dish id in two branches is counted apart', () => {
    const c = CART();
    c.branches.push({ ...c.branches[0], branch_id: 'b2', items: [{ ...LINE, qty: 5 }] });
    expect(qtyInCart(c, 'i1', 'b1')).toBe(2);
    expect(qtyInCart(c, 'i1', 'b2')).toBe(5);
    expect(qtyInCart(c, 'i1', 'b3')).toBe(0);
    expect(qtyInCart(null, 'i1', 'b1')).toBe(0);
  });
  test('countItems counts dishes, including ones that cannot be ordered', () => {
    const c = CART({ unavailable: [{ ...LINE, qty: 3, branch_id: 'b9', restaurant: 'X', reason: 'branch_closed' }] });
    expect(countItems(c)).toBe(5);
    expect(countItems(null)).toBe(0);
  });
  test('sayWhy never passes the tool text through', () => {
    const r = sayWhy({ ok: false, kind: 'http', status: 409, data: { status: 'unheard_of', message: 'Tell the user X' }, message: 'm' });
    expect(r).toBe("That didn't work. Please try again.");
  });
});

describe('screens', () => {
  jest.setTimeout(30_000); // the first screen import compiles a lot
  const wrap = (ui: React.ReactElement) => (
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 360, height: 800 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
      <SessionProvider>
        <AreaProvider>
          <CartProvider>{ui}</CartProvider>
        </AreaProvider>
      </SessionProvider>
    </SafeAreaProvider>
  );
  test('Place order is disabled when the server says the cart cannot be confirmed, and enabled otherwise', async () => {
    const CartScreen = require('@/app/(tabs)/cart').default as React.ComponentType;
    on('GET /me/addresses', () => ({ status: 200, body: { addresses: [] } }));
    on('GET /cart', () => ({ status: 200, body: CART({ can_confirm: false }) }));
    await render(wrap(<CartScreen />));
    const btn = await screen.findByRole('button', { name: 'Place order' }); // no amount on a button that cannot be used
    expect(btn.props.accessibilityState).toMatchObject({ disabled: true });
    fireEvent.press(btn);
    expect(mockRouter.push).not.toHaveBeenCalled();
  });
  test('a confirmed cart shows one action, Pay now, and no Place order', async () => {
    const CartScreen = require('@/app/(tabs)/cart').default as React.ComponentType;
    on('GET /me/addresses', () => ({ status: 200, body: { addresses: [] } }));
    on('GET /cart', () => ({ status: 200, body: CART({ cart_status: 'confirmed', confirmed_total: 4242 }) }));
    await render(wrap(<CartScreen />));
    const pay = await screen.findByRole('button', { name: 'Pay now' });
    expect(screen.queryByRole('button', { name: /Place order/ })).toBeNull();
    fireEvent.press(pay);
    expect(mockRouter.push).toHaveBeenCalledWith('/payment');
  });
  test('an unconfirmed cart shows Place order and no Pay now', async () => {
    const CartScreen = require('@/app/(tabs)/cart').default as React.ComponentType;
    on('GET /me/addresses', () => ({ status: 200, body: { addresses: [] } }));
    on('GET /cart', () => ({ status: 200, body: CART() }));
    await render(wrap(<CartScreen />));
    expect(await screen.findByRole('button', { name: /Place order/ })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Pay now' })).toBeNull();
  });
  test('the cart screen shows the server totals and does not add anything up', async () => {
    const CartScreen = require('@/app/(tabs)/cart').default as React.ComponentType;
    on('GET /me/addresses', () => ({ status: 200, body: { addresses: [] } }));
    on('GET /cart', () => ({ status: 200, body: CART() }));
    await render(wrap(<CartScreen />));
    expect(await screen.findByLabelText('Restaurant total: ₹999')).toBeTruthy();
    expect(screen.getByLabelText('Total: ₹4242')).toBeTruthy();
    expect(screen.getByLabelText('GST: ₹9')).toBeTruthy();
    expect(screen.getByLabelText('Delivery: ₹25')).toBeTruthy();
  });
  test('a cart whose dishes are all unavailable is not shown as empty: they are listed with a way to remove them', async () => {
    const CartScreen = require('@/app/(tabs)/cart').default as React.ComponentType;
    on('GET /me/addresses', () => ({ status: 200, body: { addresses: [] } }));
    on('GET /cart', () => ({
      status: 200,
      body: { status: 'empty', cart_id: 'c1', delivery: CART().delivery, branches: [], grand_total: 0, can_confirm: false, unavailable: [{ ...LINE, qty: 1, branch_id: 'b1', restaurant: 'Udupi Vihar', reason: 'too_far' }] },
    }));
    await render(wrap(<CartScreen />));
    expect(await screen.findByText("Can't be ordered")).toBeTruthy();
    expect(screen.getByText('Too far from your delivery point.')).toBeTruthy();
    expect(screen.queryByText('Your cart is empty')).toBeNull();
    expect(screen.getByRole('button', { name: 'Remove' })).toBeTruthy();
  });
  test('the cart says where it delivers, and says so plainly when that differs from the browsed area', async () => {
    mockStore.set('dawat.area', JSON.stringify({ area_id: 'madhapur', name: 'Madhapur' }));
    const CartScreen = require('@/app/(tabs)/cart').default as React.ComponentType;
    on('GET /me/addresses', () => ({ status: 200, body: { addresses: [] } }));
    on('GET /cart', () => ({ status: 200, body: CART({ delivery: BORABANDA }) }));
    on('PUT /cart/delivery', () => ({ status: 200, body: { status: 'ok', cart: CART() } }));
    await render(wrap(<CartScreen />));
    expect(await screen.findByLabelText('Delivering to Borabanda')).toBeTruthy();
    expect(screen.getByText(/You are browsing Madhapur, but this cart delivers to Borabanda/)).toBeTruthy();
    fireEvent.press(screen.getByRole('button', { name: 'Deliver to Madhapur' }));
    await waitFor(() => expect(calls.filter((c) => c.method === 'PUT').map((c) => c.body)).toEqual([{ area: 'Madhapur' }]));
  });
  test('no warning when the cart delivers to the browsed area', async () => {
    mockStore.set('dawat.area', JSON.stringify({ area_id: 'madhapur', name: 'Madhapur' }));
    const CartScreen = require('@/app/(tabs)/cart').default as React.ComponentType;
    on('GET /me/addresses', () => ({ status: 200, body: { addresses: [] } }));
    on('GET /cart', () => ({ status: 200, body: CART() }));
    await render(wrap(<CartScreen />));
    expect(await screen.findByLabelText('Delivering to Madhapur')).toBeTruthy();
    expect(screen.queryByText(/You are browsing/)).toBeNull();
  });
  test('a saved address chip asks for that address and nothing else', async () => {
    const CartScreen = require('@/app/(tabs)/cart').default as React.ComponentType;
    on('GET /me/addresses', () => ({ status: 200, body: { addresses: [{ address_id: 'a1', label: 'Home', line1: 'x', area: 'Madhapur', is_default: true }] } }));
    on('GET /cart', () => ({ status: 200, body: CART() }));
    on('PUT /cart/delivery', () => ({ status: 200, body: { status: 'ok', cart: CART() } }));
    await render(wrap(<CartScreen />));
    fireEvent.press(await screen.findByRole('button', { name: 'Home' }));
    await waitFor(() => expect(calls.filter((c) => c.method === 'PUT').map((c) => c.body)).toEqual([{ address_id: 'a1' }]));
  });
  test('the review screen shows the delivery area large, and the mismatch note without a switch button', async () => {
    mockStore.set('dawat.area', JSON.stringify({ area_id: 'madhapur', name: 'Madhapur' }));
    const Review = require('@/app/review-order').default as React.ComponentType;
    on('GET /cart', () => ({ status: 200, body: CART({ delivery: BORABANDA }) }));
    await render(wrap(<Review />));
    expect(await screen.findByLabelText('Delivering to Borabanda')).toBeTruthy();
    expect(screen.getByText(/this cart delivers to Borabanda/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Deliver to Madhapur' })).toBeNull();
  });
  test('the review screen reads the bill again on arrival: a stale held cart is never what the user confirms', async () => {
    const Review = require('@/app/review-order').default as React.ComponentType;
    let n = 0;
    on('GET /cart', () => ({ status: 200, body: ++n === 1 ? CART() : CART({ grand_total: 5555 }) }));
    const r = await render(wrap(<></>));
    await waitFor(() => expect(n).toBe(1)); // the cart tab already holds the first bill (4242)
    await r.rerender(wrap(<Review />));
    expect(await screen.findByLabelText('Total: ₹5555')).toBeTruthy();
    expect(screen.queryByLabelText('Total: ₹4242')).toBeNull();
    expect(n).toBeGreaterThanOrEqual(2);
  });
  test('the review screen: Yes confirms the quote once and offers payment; No goes back and sends nothing', async () => {
    const Review = require('@/app/review-order').default as React.ComponentType;
    on('GET /cart', () => ({ status: 200, body: CART() }));
    on('POST /cart/confirm', () => ({ status: 200, body: { status: 'ok', cart: CART({ cart_status: 'confirmed', confirmed_total: 4242 }) } }));
    await render(wrap(<Review />));
    fireEvent.press(await screen.findByRole('button', { name: 'No, go back' }));
    expect(calls.filter((c) => c.path === '/cart/confirm')).toHaveLength(0);
    fireEvent.press(screen.getByRole('button', { name: 'Yes, confirm this order' }));
    expect(await screen.findByText(/Confirmed: ₹4242/)).toBeTruthy();
    expect(screen.getByText(/nothing is ordered until you pay/)).toBeTruthy();
    await fireEvent.press(screen.getByRole('button', { name: 'Pay ₹4242' }));
    expect(mockRouter.push).toHaveBeenCalledWith('/payment');
    expect(bodiesOf('POST')).toEqual([{ cart_id: 'c1', quote_id: 'q1' }]);
    expect(calls.filter((c) => /\/orders|\/payments/.test(c.path))).toHaveLength(0);
  });
});

describe('source rules for the cart code', () => {
  const dir = path.join(__dirname, '..', 'src');
  const files = ['lib/cart.tsx', 'app/(tabs)/cart.tsx', 'app/review-order.tsx', 'app/restaurant/[branchId].tsx', 'components/BillParts.tsx', 'components/MenuParts.tsx'];
  const src = (f: string) => fs.readFileSync(path.join(dir, f), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
  test('no price, fee, tax or total is added, multiplied or summed on the device', () => {
    const money = '(price|line_total|items_total|grand_total|delivery_fee|delivery_total|taxes|taxes_total|gst_food|gst_delivery|total)';
    for (const f of files) {
      const s = src(f);
      expect(s).not.toMatch(new RegExp(`\\b${money}\\b\\s*[*+\\-/]\\s*[\\w(]`));
      expect(s).not.toMatch(new RegExp(`[\\w)]\\s*[*+/]\\s*\\w+\\.${money}\\b`));
      expect(s).not.toMatch(new RegExp(`reduce\\([^)]*${money}`));
    }
  });
  test('request bodies are built from ids and a quantity only', () => {
    const s = src('lib/cart.tsx');
    expect(s).not.toMatch(/body:\s*\{[^}]*(price|user|source|amount|total)/i);
  });
  test('the confirm step never touches orders or payments', () => {
    for (const f of ['lib/cart.tsx', 'app/review-order.tsx', 'app/(tabs)/cart.tsx']) expect(src(f)).not.toMatch(/['"`]\/(orders|payments)/);
  });
});
