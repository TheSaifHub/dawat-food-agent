import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { SessionProvider, useSession, type Session } from '@/lib/session';
import { ORDERS_LIMIT, PREF_KEYS, PREF_OPTIONS, orderHref, orderRows, placedLabel, prefBody, prefPath, statusLabel, type History } from '@/lib/account';

// eslint-disable-next-line @typescript-eslint/no-require-imports
const fs = require('fs');
// eslint-disable-next-line @typescript-eslint/no-require-imports
const path = require('path');
declare const __dirname: string;

const mockStore = new Map<string, string>();
jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(async (k: string) => mockStore.get(k) ?? null),
  setItemAsync: jest.fn(async (k: string, v: string) => void mockStore.set(k, v)),
  deleteItemAsync: jest.fn(async (k: string) => void mockStore.delete(k)),
}));
const mockRouter = { push: jest.fn(), replace: jest.fn(), navigate: jest.fn(), back: jest.fn(), canGoBack: () => true };
jest.mock('expo-router', () => ({
  useRouter: () => mockRouter,
  useFocusEffect: (cb: () => void | (() => void)) => require('react').useEffect(cb, [cb]), // eslint-disable-line @typescript-eslint/no-require-imports
}));

jest.setTimeout(30_000);

const USERS: Record<string, { user_id: string; display_name: string; is_demo: boolean; name_confirmed: boolean; account_name: string }> = {
  tokA: { user_id: 'uA', display_name: 'Asha Rao', is_demo: false, name_confirmed: true, account_name: 'Asha Rao' },
  tokB: { user_id: 'uB', display_name: 'Bilal Khan', is_demo: false, name_confirmed: true, account_name: 'Bilal Khan' },
};

const ORDER = (n: number, over: Record<string, unknown> = {}) => ({
  order_id: `o${n}`,
  order_number: `DW${n}`,
  is_sample: false,
  restaurant: `Restaurant ${n}`,
  branch_label: 'Madhapur',
  order_status: 'preparing',
  // the items add up to 120 on purpose: the total shown must be the server's 408, never a sum made on the phone
  items: [{ item_id: 'i1', name: 'Sambar', price_paid: 60, qty: 2, line_total: 120, is_veg: true }],
  total: 408,
  delivery_area: 'Madhapur',
  ...over,
});
const HISTORY = (...checkouts: { at: string; orders: ReturnType<typeof ORDER>[] }[]): History => ({
  status: 'ok',
  has_more: false,
  checkouts: checkouts.map((c, i) => ({ checkout_id: `c${i}`, placed_at: c.at, orders: c.orders, grand_total: c.orders.reduce((s, o) => s + o.total, 0) })),
});
const EMPTY = { status: 'empty', checkouts: [], has_more: false };

type Req = { path: string; method: string; auth: string | null; body: unknown };
type Reply = { status: number; body?: unknown };
let reqs: Req[];
let routes: Record<string, (r: Req) => Reply | Promise<Reply>>;

const PREFS = {
  status: 'ok',
  preferences: {
    diet: { value: 'vegetarian', label: 'Vegetarian', source: 'settings', how_saved: 'you set it in your settings', saved_at: '2026-10-01T10:00:00+00:00' },
    max_spice: { value: 1, label: 'Spice up to 1 of 3 (mild)', source: 'chat_confirmed', how_saved: 'you said yes when Dawat AI offered', saved_at: '2026-10-01T10:00:00+00:00' },
  },
};
const ADDRESSES = { status: 'ok', addresses: [{ address_id: 'a1', label: 'Home', line1: '12 Road No 2', area_id: 'madhapur', area: 'Madhapur', is_default: true }] };
const AREAS = { status: 'ok', areas: [{ area_id: 'madhapur', name: 'Madhapur', name_te: null }, { area_id: 'kondapur', name: 'Kondapur', name_te: null }] };

let session: Session;
function Probe() {
  session = useSession();
  return null;
}

beforeEach(() => {
  mockStore.clear();
  mockStore.set('dawat.access_token', 'tokA');
  Object.values(mockRouter).forEach((f) => typeof f === 'function' && 'mockClear' in f && (f as jest.Mock).mockClear());
  reqs = [];
  routes = {};
  (globalThis as unknown as { fetch: unknown }).fetch = jest.fn(async (url: string, init?: { method?: string; body?: string; headers?: Record<string, string> }) => {
    const p = url.replace('http://localhost:8000', '');
    const r: Req = { path: p, method: init?.method ?? 'GET', auth: init?.headers?.Authorization ?? null, body: init?.body ? JSON.parse(init.body) : undefined };
    reqs.push(r);
    let reply: Reply;
    if (p === '/me') {
      const u = r.auth ? USERS[r.auth.replace('Bearer ', '')] : undefined;
      reply = u ? { status: 200, body: u } : { status: 401, body: { detail: 'no' } };
    } else {
      const key = `${r.method} ${p.split('?')[0]}`;
      const h = routes[key];
      reply = h ? await h(r) : { status: 404, body: { detail: 'unrouted' } };
    }
    return { ok: reply.status < 300, status: reply.status, text: async () => JSON.stringify(reply.body) };
  });
});

const wrap = (ui: React.ReactElement) => (
  <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 360, height: 800 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
    <SessionProvider>
      <Probe />
      {ui}
    </SessionProvider>
  </SafeAreaProvider>
);
const OrdersScreen = () => require('@/app/(tabs)/orders').default as React.ComponentType; // eslint-disable-line @typescript-eslint/no-require-imports
const ProfileScreen = () => require('@/app/(tabs)/profile').default as React.ComponentType; // eslint-disable-line @typescript-eslint/no-require-imports
const text = () => JSON.stringify(screen.toJSON());
const changes = () => reqs.filter((r) => r.method !== 'GET');

describe('the pure helpers', () => {
  test('orderRows: one row per order, newest checkout first, a checkout keeps its own order', () => {
    const h = HISTORY(
      { at: '2026-10-10T10:00:00+00:00', orders: [ORDER(1)] },
      { at: '2026-10-16T10:00:00+00:00', orders: [ORDER(3), ORDER(2)] },
    );
    expect(orderRows(h).map((o) => o.order_number)).toEqual(['DW3', 'DW2', 'DW1']);
  });
  test('orderRows keeps the server order when a time cannot be read, and copes with nothing', () => {
    const h = HISTORY({ at: 'garbage', orders: [ORDER(1)] }, { at: '2026-10-16T10:00:00+00:00', orders: [ORDER(2)] });
    expect(orderRows(h).map((o) => o.order_number)).toEqual(['DW1', 'DW2']);
    expect(orderRows(null)).toEqual([]);
    expect(orderRows(EMPTY as History)).toEqual([]);
  });
  test('statusLabel words the six statuses and never invents one', () => {
    expect(['placed', 'confirmed', 'preparing', 'picked_up', 'on_the_way', 'delivered'].map(statusLabel)).toEqual(['Placed', 'Confirmed', 'Preparing', 'Picked up', 'On the way', 'Delivered']);
    expect(statusLabel('cancelled')).toBe('Status unavailable');
    expect(statusLabel('whatever')).toBe('Status unavailable');
  });
  test('placedLabel, orderHref, prefBody, prefPath', () => {
    expect(placedLabel('nonsense')).toBe('');
    expect(placedLabel('2026-10-16T14:30:00+00:00')).toMatch(/Oct/);
    expect(orderHref('DW1042')).toBe('/orders/DW1042');
    expect(prefBody('eggetarian')).toEqual({ value: 'eggetarian' });
    expect(prefBody(2)).toEqual({ value: 2 });
    expect(prefPath('max_spice')).toBe('/me/preferences/max_spice');
    expect(ORDERS_LIMIT).toBe(20);
  });
  test('the choices are exactly the values the backend accepts, and the four keys are the supported ones', () => {
    expect([...PREF_KEYS]).toEqual(['diet', 'max_spice', 'default_area', 'language']);
    expect(PREF_OPTIONS.diet.map((o) => o.value)).toEqual(['vegetarian', 'eggetarian', 'non_vegetarian']);
    expect(PREF_OPTIONS.max_spice.map((o) => o.value)).toEqual([0, 1, 2, 3]);
    expect(PREF_OPTIONS.language.map((o) => o.value)).toEqual(['en', 'hinglish', 'te']);
  });
});

describe('the Orders tab', () => {
  test('lists the orders newest first with #DW numbers, status and the SERVER total', async () => {
    routes['GET /orders'] = () => ({
      status: 200,
      body: HISTORY(
        { at: '2026-10-16T10:00:00+00:00', orders: [ORDER(1042, { order_status: 'on_the_way' })] },
        { at: '2026-10-10T10:00:00+00:00', orders: [ORDER(1030, { order_status: 'delivered', total: 355 })] },
      ),
    });
    const S = OrdersScreen();
    await render(wrap(<S />));
    expect(await screen.findByText('#DW1042')).toBeTruthy();
    expect(screen.getByText('#DW1030')).toBeTruthy();
    expect(screen.getByText('On the way')).toBeTruthy();
    expect(screen.getByText('Delivered')).toBeTruthy();
    expect(screen.getByText('₹408')).toBeTruthy();
    expect(screen.getByText('₹355')).toBeTruthy();
    expect(text()).not.toContain('₹120'); // never a total made from the lines
    expect(text().indexOf('DW1042')).toBeLessThan(text().indexOf('DW1030'));
    expect(screen.getAllByText('2 × Sambar')).toHaveLength(2);
    expect(screen.getByText('Demo project. Menus, prices and orders are simulated. Not affiliated with any restaurant.')).toBeTruthy();
  });

  test('asks for the orders with the token and nothing else: no user id, no price, no source', async () => {
    routes['GET /orders'] = () => ({ status: 200, body: EMPTY });
    const S = OrdersScreen();
    await render(wrap(<S />));
    await screen.findByText('No orders yet');
    const call = reqs.find((r) => r.path.startsWith('/orders'))!;
    expect(call.path).toBe(`/orders?limit=${ORDERS_LIMIT}`);
    expect(call.auth).toBe('Bearer tokA');
    expect(call.body).toBeUndefined();
    expect(changes()).toEqual([]);
  });

  test('tapping an order opens its tracking screen by the #DW number', async () => {
    routes['GET /orders'] = () => ({ status: 200, body: HISTORY({ at: '2026-10-16T10:00:00+00:00', orders: [ORDER(1042)] }) });
    const S = OrdersScreen();
    await render(wrap(<S />));
    fireEvent.press(await screen.findByRole('button', { name: /^Order DW1042,/ }));
    expect(mockRouter.push).toHaveBeenCalledWith('/orders/DW1042');
  });

  test('the empty state offers to browse; an unreadable status is not guessed; no Cancelled anywhere', async () => {
    routes['GET /orders'] = () => ({ status: 200, body: EMPTY });
    const S = OrdersScreen();
    await render(wrap(<S />));
    expect(await screen.findByText('No orders yet')).toBeTruthy();
    fireEvent.press(screen.getByRole('button', { name: 'Browse restaurants' }));
    expect(mockRouter.navigate).toHaveBeenCalledWith('/');
    expect(text()).not.toMatch(/cancel/i);
  });

  test('an order the server calls cancelled is shown as "Status unavailable", not as a Cancelled status', async () => {
    routes['GET /orders'] = () => ({ status: 200, body: HISTORY({ at: '2026-10-16T10:00:00+00:00', orders: [ORDER(7, { order_status: 'cancelled' })] }) });
    const S = OrdersScreen();
    await render(wrap(<S />));
    await screen.findByText('#DW7');
    expect(screen.getByText('Status unavailable')).toBeTruthy();
    expect(text()).not.toMatch(/cancel/i);
  });

  test('a failed load shows the message with a retry, and retry loads again', async () => {
    let n = 0;
    routes['GET /orders'] = () => (++n === 1 ? { status: 500, body: { detail: 'x' } } : { status: 200, body: HISTORY({ at: '2026-10-16T10:00:00+00:00', orders: [ORDER(5)] }) });
    const S = OrdersScreen();
    await render(wrap(<S />));
    fireEvent.press(await screen.findByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('#DW5')).toBeTruthy();
  });

  test('says when only the latest orders are shown', async () => {
    routes['GET /orders'] = () => ({ status: 200, body: { ...HISTORY({ at: '2026-10-16T10:00:00+00:00', orders: [ORDER(5)] }), has_more: true } });
    const S = OrdersScreen();
    await render(wrap(<S />));
    expect(await screen.findByText(`Showing your latest ${ORDERS_LIMIT} orders.`)).toBeTruthy();
  });
});

describe("one user's orders never show for another", () => {
  const A_ORDERS = HISTORY({ at: '2026-10-16T10:00:00+00:00', orders: [ORDER(1001, { restaurant: 'Asha Only Kitchen' })] });
  const B_ORDERS = HISTORY({ at: '2026-10-16T11:00:00+00:00', orders: [ORDER(2002, { restaurant: 'Bilal Only Dhaba' })] });

  test("after sign-out and a new sign-in, the first user's rows are gone and only the second user's show", async () => {
    routes['GET /orders'] = (r) => ({ status: 200, body: r.auth === 'Bearer tokA' ? A_ORDERS : B_ORDERS });
    const S = OrdersScreen();
    await render(wrap(<S />));
    expect(await screen.findByText('#DW1001')).toBeTruthy();
    await act(async () => {
      await session.signOut();
    });
    expect(text()).not.toContain('DW1001');
    await act(async () => {
      await session.signInWithToken('tokB');
    });
    expect(await screen.findByText('#DW2002')).toBeTruthy();
    expect(text()).not.toContain('Asha Only Kitchen');
    expect(text()).not.toContain('DW1001');
  });

  test("a late answer for the first user, arriving after the second user signed in, is dropped", async () => {
    let releaseA!: () => void;
    const gateA = new Promise<void>((res) => (releaseA = res));
    routes['GET /orders'] = async (r) => {
      if (r.auth === 'Bearer tokA') {
        await gateA;
        return { status: 200, body: A_ORDERS };
      }
      return { status: 200, body: B_ORDERS };
    };
    const S = OrdersScreen();
    await render(wrap(<S />));
    await waitFor(() => expect(reqs.some((r) => r.path.startsWith('/orders') && r.auth === 'Bearer tokA')).toBe(true));
    await act(async () => {
      await session.signOut();
      await session.signInWithToken('tokB');
    });
    expect(await screen.findByText('#DW2002')).toBeTruthy();
    await act(async () => {
      releaseA();
      await new Promise((r) => setTimeout(r, 30));
    });
    expect(text()).not.toContain('Asha Only Kitchen');
    expect(text()).not.toContain('DW1001');
    expect(screen.getByText('#DW2002')).toBeTruthy();
  });

  test("a failed load for the second user does not fall back to showing the first user's rows", async () => {
    routes['GET /orders'] = (r) => (r.auth === 'Bearer tokA' ? { status: 200, body: A_ORDERS } : { status: 500, body: { detail: 'x' } });
    const S = OrdersScreen();
    await render(wrap(<S />));
    await screen.findByText('#DW1001');
    await act(async () => {
      await session.signOut();
      await session.signInWithToken('tokB');
    });
    expect(await screen.findByRole('button', { name: 'Try again' })).toBeTruthy();
    expect(text()).not.toContain('DW1001');
  });

  test("the profile's preferences and addresses are per user too", async () => {
    routes['GET /me/preferences'] = (r) => ({ status: 200, body: r.auth === 'Bearer tokA' ? PREFS : { status: 'ok', preferences: {} } });
    routes['GET /me/addresses'] = (r) => ({ status: 200, body: r.auth === 'Bearer tokA' ? ADDRESSES : { status: 'empty', addresses: [] } });
    const S = ProfileScreen();
    await render(wrap(<S />));
    expect(await screen.findByText('12 Road No 2')).toBeTruthy();
    expect(screen.getAllByText('Vegetarian').length).toBeGreaterThan(0);
    await act(async () => {
      await session.signOut();
      await session.signInWithToken('tokB');
    });
    expect(await screen.findByText('No saved addresses.')).toBeTruthy();
    expect(text()).not.toContain('12 Road No 2');
    expect(text()).not.toContain('Spice up to 1 of 3');
    expect(text()).not.toContain('Asha Rao');
  });
});

describe('the Profile tab', () => {
  beforeEach(() => {
    routes['GET /me/preferences'] = () => ({ status: 200, body: PREFS });
    routes['GET /me/addresses'] = () => ({ status: 200, body: ADDRESSES });
  });

  test('shows the name, the Google note, the saved preferences as the server worded them, and read-only addresses', async () => {
    const S = ProfileScreen();
    await render(wrap(<S />));
    expect(await screen.findByText('Asha Rao')).toBeTruthy();
    expect(screen.getByText('Signed in with Google')).toBeTruthy();
    expect(await screen.findByText('Spice up to 1 of 3 (mild)')).toBeTruthy();
    // each saved one just says "Saved"; the backend's own wording of how it was saved is never shown
    expect(screen.getAllByText('Saved')).toHaveLength(2);
    expect(screen.queryByText(/you said yes|you set it|demo account/i)).toBeNull();
    // the two the user never saved say so, and offer Add
    expect(screen.getAllByText('Not saved')).toHaveLength(2);
    expect(screen.getByRole('button', { name: 'Add Language' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Add Default delivery area' })).toBeTruthy();
    // addresses: shown, but nothing to edit or forget
    expect(await screen.findByText('12 Road No 2')).toBeTruthy();
    expect(screen.getByText('Home · Default')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /address/i })).toBeNull();
    expect(screen.getByText('© OpenStreetMap contributors')).toBeTruthy();
    expect(screen.getByText('Demo project. Menus, prices and orders are simulated. Not affiliated with any restaurant.')).toBeTruthy();
  });

  test('leaves out what the backend cannot do', async () => {
    const S = ProfileScreen();
    await render(wrap(<S />));
    await screen.findByText('Asha Rao');
    expect(text()).not.toMatch(/payment method|wallet|notification|favourite|favorite|cancel|rating|\bETA\b/i);
  });

  test('Edit diet: choosing a value PUTs {value} only, then reads the list again', async () => {
    let saved = PREFS;
    routes['GET /me/preferences'] = () => ({ status: 200, body: saved });
    routes['PUT /me/preferences/diet'] = (r) => {
      saved = { ...PREFS, preferences: { ...PREFS.preferences, diet: { ...PREFS.preferences.diet, value: (r.body as { value: string }).value, label: 'Eggetarian (vegetarian + egg)' } } };
      return { status: 200, body: { status: 'ok' } };
    };
    const S = ProfileScreen();
    await render(wrap(<S />));
    fireEvent.press(await screen.findByRole('button', { name: 'Edit Diet' }));
    fireEvent.press(await screen.findByRole('button', { name: 'Eggetarian' }));
    expect(await screen.findByText('Eggetarian (vegetarian + egg)')).toBeTruthy();
    const put = changes();
    expect(put).toHaveLength(1);
    expect(put[0]).toMatchObject({ method: 'PUT', path: '/me/preferences/diet', body: { value: 'eggetarian' }, auth: 'Bearer tokA' });
    expect(Object.keys(put[0].body as object)).toEqual(['value']);
  });

  test('Spice is sent as a whole number, and Language as its code', async () => {
    routes['PUT /me/preferences/max_spice'] = () => ({ status: 200, body: { status: 'ok' } });
    routes['PUT /me/preferences/language'] = () => ({ status: 200, body: { status: 'ok' } });
    const S = ProfileScreen();
    await render(wrap(<S />));
    fireEvent.press(await screen.findByRole('button', { name: 'Edit Spice' }));
    fireEvent.press(await screen.findByRole('button', { name: 'Medium' }));
    await waitFor(() => expect(changes()).toHaveLength(1));
    fireEvent.press(await screen.findByRole('button', { name: 'Add Language' }));
    fireEvent.press(await screen.findByRole('button', { name: 'Telugu' }));
    await waitFor(() => expect(changes()).toHaveLength(2));
    expect(changes()[0].body).toEqual({ value: 2 });
    expect(typeof (changes()[0].body as { value: unknown }).value).toBe('number');
    expect(changes()[1]).toMatchObject({ path: '/me/preferences/language', body: { value: 'te' } });
  });

  test('Default delivery area: pick an area and its NAME is saved', async () => {
    routes['GET /areas'] = () => ({ status: 200, body: AREAS });
    routes['PUT /me/preferences/default_area'] = () => ({ status: 200, body: { status: 'ok' } });
    const S = ProfileScreen();
    await render(wrap(<S />));
    fireEvent.press(await screen.findByRole('button', { name: 'Add Default delivery area' }));
    fireEvent.press(await screen.findByRole('button', { name: 'Kondapur' }));
    await waitFor(() => expect(changes()).toHaveLength(1));
    expect(changes()[0]).toMatchObject({ method: 'PUT', path: '/me/preferences/default_area', body: { value: 'Kondapur' } });
  });

  test('Forget DELETEs that one key with no body and no extra confirmation, then reads the list again', async () => {
    let saved: typeof PREFS = PREFS;
    routes['GET /me/preferences'] = () => ({ status: 200, body: saved });
    routes['DELETE /me/preferences/max_spice'] = () => {
      saved = { ...PREFS, preferences: { diet: PREFS.preferences.diet } } as typeof PREFS;
      return { status: 200, body: { status: 'ok' } };
    };
    const S = ProfileScreen();
    await render(wrap(<S />));
    fireEvent.press(await screen.findByRole('button', { name: 'Forget Spice' }));
    await waitFor(() => expect(screen.queryByText('Spice up to 1 of 3 (mild)')).toBeNull());
    expect(changes()).toHaveLength(1);
    expect(changes()[0]).toMatchObject({ method: 'DELETE', path: '/me/preferences/max_spice', body: undefined });
    expect(screen.getByText('Vegetarian')).toBeTruthy(); // the other one is untouched
  });

  test('a refusal from the server is shown and the saved value is not changed on screen', async () => {
    routes['PUT /me/preferences/diet'] = () => ({ status: 422, body: { status: 'invalid_input', message: 'diet must be vegetarian, eggetarian or non_vegetarian' } });
    const S = ProfileScreen();
    await render(wrap(<S />));
    fireEvent.press(await screen.findByRole('button', { name: 'Edit Diet' }));
    fireEvent.press(await screen.findByRole('button', { name: 'Non-vegetarian' }));
    expect(await screen.findByText('diet must be vegetarian, eggetarian or non_vegetarian')).toBeTruthy();
    expect(screen.getAllByText('Vegetarian')).toHaveLength(2); // the saved value and its chip: still Vegetarian
  });

  test('a 200 whose body says nothing was saved is shown as a problem, not as success', async () => {
    routes['PUT /me/preferences/diet'] = () => ({ status: 200, body: { status: 'not_saved', message: 'Nothing was saved.' } });
    const S = ProfileScreen();
    await render(wrap(<S />));
    fireEvent.press(await screen.findByRole('button', { name: 'Edit Diet' }));
    fireEvent.press(await screen.findByRole('button', { name: 'Eggetarian' }));
    expect(await screen.findByText('Nothing was saved.')).toBeTruthy();
  });

  test('a network failure on Forget is shown, and nobody is signed out by it', async () => {
    routes['DELETE /me/preferences/diet'] = () => {
      throw new TypeError('Network request failed');
    };
    const S = ProfileScreen();
    await render(wrap(<S />));
    fireEvent.press(await screen.findByRole('button', { name: 'Forget Diet' }));
    expect(await screen.findByText(/Can't reach Dawat/)).toBeTruthy();
    expect(screen.getByText('Asha Rao')).toBeTruthy();
  });

  test('only a real 401 signs out: a 401 on Forget signs the user out', async () => {
    routes['DELETE /me/preferences/diet'] = () => ({ status: 401, body: { detail: 'no' } });
    const S = ProfileScreen();
    await render(wrap(<S />));
    fireEvent.press(await screen.findByRole('button', { name: 'Forget Diet' }));
    await waitFor(() => expect(session.state.status).toBe('signedOut'));
  });

  test('every change the Profile makes carries only {value}: never a source, a user id, a price or a token', async () => {
    routes['PUT /me/preferences/diet'] = () => ({ status: 200, body: { status: 'ok' } });
    routes['DELETE /me/preferences/max_spice'] = () => ({ status: 200, body: { status: 'ok' } });
    const S = ProfileScreen();
    await render(wrap(<S />));
    fireEvent.press(await screen.findByRole('button', { name: 'Edit Diet' }));
    fireEvent.press(await screen.findByRole('button', { name: 'Eggetarian' }));
    await waitFor(() => expect(changes()).toHaveLength(1));
    fireEvent.press(await screen.findByRole('button', { name: 'Forget Spice' }));
    await waitFor(() => expect(changes()).toHaveLength(2));
    for (const r of changes()) {
      expect(JSON.stringify(r.body ?? {})).not.toMatch(/source|user|price|total|token|uA/i);
      expect(r.path).not.toMatch(/uA|user/i);
    }
    expect(reqs.filter((r) => r.path.includes('address') && r.method !== 'GET')).toEqual([]);
  });

  test('Sign out signs out', async () => {
    const S = ProfileScreen();
    await render(wrap(<S />));
    fireEvent.press(await screen.findByRole('button', { name: 'Sign out' }));
    await waitFor(() => expect(session.state.status).toBe('signedOut'));
  });
});

describe('the source files', () => {
  const read = (p: string) => fs.readFileSync(path.join(__dirname, '..', 'src', p), 'utf8') as string;
  const files = ['lib/account.ts', 'lib/userload.ts', 'app/(tabs)/orders.tsx', 'app/(tabs)/profile.tsx'];
  test('no console use, no AsyncStorage, no "source" field and no user id in any of them', () => {
    for (const f of files) {
      const code = read(f).replace(/\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '');
      expect(code).not.toMatch(/console\./);
      expect(code).not.toMatch(/AsyncStorage/);
      expect(code).not.toMatch(/\bsource\s*:\s*['"`]/); // Pref.source is only read; no source value is ever set
      // userload.ts reads the signed-in id only to key what it holds; it never puts it in a request
      if (f !== 'lib/userload.ts') expect(code).not.toMatch(/user_id|userId/);
    }
  });
  test('the screens never add prices up and never say Cancelled', () => {
    for (const f of ['app/(tabs)/orders.tsx', 'app/(tabs)/profile.tsx']) {
      const code = read(f);
      expect(code).not.toMatch(/\.reduce\(|price_paid|line_total/);
      expect(code).not.toMatch(/Cancelled/);
    }
  });
});
