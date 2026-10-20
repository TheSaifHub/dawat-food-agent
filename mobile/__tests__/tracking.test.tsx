import { act, render, screen, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { SessionProvider } from '@/lib/session';
import { MIN_POLL_MS, STEPS, nextPollDelayMs, projectPoints, reachedAt, type Track } from '@/lib/orders';
import { MAP_USER_AGENT, OSM_ATTRIBUTION_HTML, OSM_TILE_URL, leafletHtml } from '@/lib/osm';

// eslint-disable-next-line @typescript-eslint/no-require-imports
const fs = require('fs');
// eslint-disable-next-line @typescript-eslint/no-require-imports
const path = require('path');
declare const __dirname: string;

const mockStore = new Map<string, string>();
jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(async (k: string) => mockStore.get(k) ?? null),
  setItemAsync: jest.fn(async () => undefined),
  deleteItemAsync: jest.fn(async () => undefined),
}));
const mockRouter = { push: jest.fn(), replace: jest.fn(), navigate: jest.fn(), back: jest.fn(), canGoBack: () => true };
jest.mock('expo-router', () => ({
  useRouter: () => mockRouter,
  useLocalSearchParams: () => ({ orderNo: 'DW1024' }),
  useFocusEffect: (cb: () => void | (() => void)) => require('react').useEffect(cb, [cb]), // eslint-disable-line @typescript-eslint/no-require-imports
}));
const mockWeb: { props: Record<string, unknown> | null; inject: jest.Mock } = { props: null, inject: jest.fn() };
jest.mock('react-native-webview', () => {
  const React = require('react'); // eslint-disable-line @typescript-eslint/no-require-imports
  const WebView = React.forwardRef((props: Record<string, unknown>, ref: unknown) => {
    mockWeb.props = props;
    React.useImperativeHandle(ref, () => ({ injectJavaScript: mockWeb.inject }));
    return null;
  });
  return { WebView };
});

jest.setTimeout(30_000);
const ME = { user_id: 'u1', display_name: 'Tester', is_demo: false, name_confirmed: true, account_name: 'Tester' };
const T0 = '2026-10-16T12:00:00+00:00';
const ORDER = (over: Partial<Track> = {}): Track => ({
  status: 'ok',
  order_id: 'o1',
  order_number: 'DW1024',
  order_status: 'placed',
  payment_status: 'paid',
  restaurant: 'Udupi Vihar',
  branch_label: 'Madhapur',
  delivery_area: 'Madhapur',
  is_sample: false,
  items: [{ item_id: 'i1', dish_name: 'Sambar', unit_price: 60, qty: 6, is_veg: true }],
  items_total: 360,
  delivery_fee: 25,
  taxes: 23,
  total: 408,
  placed_at: T0,
  timeline: [{ status: 'placed', at: T0 }],
  simulated_tracking: true,
  route: { from: { lat: 17.4412, lon: 78.3913 }, to: { lat: 17.4409, lon: 78.3916 } },
  rider: null,
  next_update_in_s: 58,
  ...over,
});

describe('when to ask the server again', () => {
  test.each([
    ['placed, next change in 58 s', {}, 58_000],
    ['placed, next change in 1 s: never sooner than 5 s', { next_update_in_s: 1 }, MIN_POLL_MS],
    ['on the way: every 5 s whatever the countdown', { order_status: 'on_the_way', rider: { lat: 1, lon: 2, stage: 'on_the_way' }, next_update_in_s: 90 }, MIN_POLL_MS],
    ['delivered: stop', { order_status: 'delivered', next_update_in_s: null }, null],
    ['cancelled: stop', { order_status: 'cancelled' }, null],
    ['not simulated (sample or unpaid): stop', { simulated_tracking: false }, null],
    ['no countdown: stop', { next_update_in_s: null }, null],
  ] as [string, Partial<Track>, number | null][])('%s', (_n, over, expected) => {
    expect(nextPollDelayMs(ORDER(over))).toBe(expected);
  });
  test('a delivered order is never polled even if the rider says on_the_way', () => {
    expect(nextPollDelayMs(ORDER({ order_status: 'delivered', rider: { lat: 1, lon: 2, stage: 'on_the_way' } }))).toBeNull();
  });
});

describe('the timeline words', () => {
  test('the steps are the six statuses in order', () => {
    expect(STEPS.map((s) => s.status)).toEqual(['placed', 'confirmed', 'preparing', 'picked_up', 'on_the_way', 'delivered']);
  });
  test('a time appears only for a status the server reports', () => {
    const o = ORDER({ timeline: [{ status: 'placed', at: T0 }, { status: 'confirmed', at: '2026-10-16T12:01:00+00:00' }] });
    expect(reachedAt(o, 'placed')).toMatch(/\d{1,2}:\d{2}/);
    expect(reachedAt(o, 'preparing')).toBeNull();
    expect(reachedAt(ORDER({ timeline: [{ status: 'placed', at: 'not a date' }] }), 'placed')).toBeNull();
  });
});

describe('the plain map and the tile page', () => {
  test('points are placed with one scale (north is up) inside the box', () => {
    const [a, b] = projectPoints([{ lat: 17.45, lon: 78.39 }, { lat: 17.44, lon: 78.4 }], 300, 200);
    expect(b.x).toBeGreaterThan(a.x); // east is to the right
    expect(b.y).toBeGreaterThan(a.y); // south is lower
    for (const p of [a, b]) expect(p.x >= 0 && p.x <= 300 && p.y >= 0 && p.y <= 200).toBe(true);
  });
  test('two points that coincide do not break it', () => {
    const [a, b] = projectPoints([{ lat: 17.4, lon: 78.4 }, { lat: 17.4, lon: 78.4 }], 300, 200);
    expect(Number.isFinite(a.x) && Number.isFinite(b.y)).toBe(true);
  });
  test('the tile page shows the OSM attribution, uses the OSM tile server, and nothing is prefetched', () => {
    const html = leafletHtml({ from: { lat: 1, lon: 2 }, to: { lat: 3, lon: 4 }, rider: null });
    expect(html).toContain(OSM_ATTRIBUTION_HTML);
    expect(html).toContain(OSM_TILE_URL);
    expect(html).toContain('attributionControl: true');
    expect(html).not.toMatch(/prefetch|preload|saveAs|offline/i);
    expect(MAP_USER_AGENT).toMatch(/^DawatDemoApp\//);
  });
});

describe('the tracking screen', () => {
  const OrderTracking = () => require('@/app/orders/[orderNo]').default as React.ComponentType; // eslint-disable-line @typescript-eslint/no-require-imports
  let calls: string[];
  let answers: (() => { status: number; body?: unknown } | 'network')[];
  beforeEach(() => {
    mockStore.clear();
    mockStore.set('dawat.access_token', 'tok');
    calls = [];
    answers = [];
    mockWeb.props = null;
    mockWeb.inject.mockClear();
    (globalThis as unknown as { fetch: unknown }).fetch = jest.fn(async (url: string) => {
      const p = url.replace('http://localhost:8000', '');
      calls.push(p);
      if (p === '/me') return { ok: true, status: 200, text: async () => JSON.stringify(ME) };
      const a = (answers.length > 1 ? answers.shift()! : answers[0])();
      if (a === 'network') throw new TypeError('Network request failed');
      return { ok: a.status < 300, status: a.status, text: async () => JSON.stringify(a.body) };
    });
  });
  const wrap = (ui: React.ReactElement) => (
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 360, height: 800 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
      <SessionProvider>{ui}</SessionProvider>
    </SafeAreaProvider>
  );
  const orderCalls = () => calls.filter((c) => c.startsWith('/orders/'));

  test('shows the order, the timeline, the bill and the demo notice from the server, with no delivery estimate', async () => {
    answers = [() => ({ status: 200, body: ORDER({ order_status: 'confirmed', timeline: [{ status: 'placed', at: T0 }, { status: 'confirmed', at: '2026-10-16T12:01:00+00:00' }] }) })];
    const Screen = OrderTracking();
    await render(wrap(<Screen />));
    expect(await screen.findByText('Order DW1024')).toBeTruthy();
    expect(screen.getByText('Demo: progress is simulated.')).toBeTruthy();
    expect(screen.getByLabelText(/^Placed, reached at/)).toBeTruthy();
    expect(screen.getByLabelText(/^Confirmed, reached at .*, now$/)).toBeTruthy();
    expect(screen.getByLabelText('Preparing, not yet')).toBeTruthy();
    expect(screen.getByLabelText('Total: ₹408')).toBeTruthy();
    expect(screen.getByText('6 × Sambar')).toBeTruthy();
    expect(screen.getByText('© OpenStreetMap contributors')).toBeTruthy();
    expect(JSON.stringify(screen.toJSON())).not.toMatch(/\bETA\b|arrives? in|minutes? away|estimated/i);
    expect(orderCalls()).toEqual(['/orders/DW1024']);
  });

  test('polls every 5 s while the rider is on the way, hands the server position to the map, and stops when delivered', async () => {
    jest.useFakeTimers({ doNotFake: ['setImmediate', 'nextTick'] });
    try {
      const way = (lat: number) => () => ({ status: 200, body: ORDER({ order_status: 'on_the_way', rider: { lat, lon: 78.39, stage: 'on_the_way' }, next_update_in_s: 90 }) });
      answers = [way(17.441), way(17.4411), () => ({ status: 200, body: ORDER({ order_status: 'delivered', next_update_in_s: null, rider: { lat: 17.4409, lon: 78.3916, stage: 'delivered' } }) })];
      const Screen = OrderTracking();
      await render(wrap(<Screen />));
      await act(async () => {
        await jest.advanceTimersByTimeAsync(100);
      });
      expect(orderCalls()).toHaveLength(1);
      await act(async () => {
        (mockWeb.props as { onMessage: (e: { nativeEvent: { data: string } }) => void }).onMessage({ nativeEvent: { data: JSON.stringify({ type: 'tiles', ok: 1, err: 0 }) } });
      });
      await act(async () => {
        await jest.advanceTimersByTimeAsync(5_100);
      });
      expect(orderCalls()).toHaveLength(2);
      await act(async () => {
        await jest.advanceTimersByTimeAsync(5_100);
      });
      expect(orderCalls()).toHaveLength(3); // the delivered answer
      await act(async () => {
        await jest.advanceTimersByTimeAsync(60_000);
      });
      expect(orderCalls()).toHaveLength(3); // and then nothing more
      expect(mockWeb.inject).toHaveBeenCalledWith(expect.stringContaining('setRider(17.4409, 78.3916)'));
    } finally {
      jest.useRealTimers();
    }
  });

  test('leaving the screen stops the polling', async () => {
    jest.useFakeTimers({ doNotFake: ['setImmediate', 'nextTick'] });
    try {
      answers = [() => ({ status: 200, body: ORDER({ next_update_in_s: 6 }) })];
      const Screen = OrderTracking();
      let setShow!: (v: boolean) => void;
      function Host() {
        const [show, set] = require('react').useState(true) as [boolean, (v: boolean) => void]; // eslint-disable-line @typescript-eslint/no-require-imports
        setShow = set;
        return show ? <Screen /> : null;
      }
      await render(wrap(<Host />));
      await act(async () => {
        await jest.advanceTimersByTimeAsync(100);
      });
      expect(orderCalls()).toHaveLength(1);
      await act(async () => {
        setShow(false); // the user leaves the screen
      });
      await act(async () => {
        await jest.advanceTimersByTimeAsync(60_000);
      });
      expect(orderCalls()).toHaveLength(1);
    } finally {
      jest.useRealTimers();
    }
  });

  test('a network error keeps the last update on screen and tries again; the user stays signed in', async () => {
    jest.useFakeTimers({ doNotFake: ['setImmediate', 'nextTick'] });
    try {
      answers = [() => ({ status: 200, body: ORDER({ next_update_in_s: 6 }) }), () => 'network', () => ({ status: 200, body: ORDER({ order_status: 'confirmed', next_update_in_s: null }) })];
      const Screen = OrderTracking();
      await render(wrap(<Screen />));
      await act(async () => {
        await jest.advanceTimersByTimeAsync(100);
      });
      await act(async () => {
        await jest.advanceTimersByTimeAsync(6_100);
      });
      expect(screen.getByText('Order DW1024')).toBeTruthy(); // still there
      expect(screen.getByText(/Showing the last update/)).toBeTruthy();
      await act(async () => {
        await jest.advanceTimersByTimeAsync(10_100);
      });
      expect(orderCalls()).toHaveLength(3);
      expect(screen.queryByText(/Showing the last update/)).toBeNull();
    } finally {
      jest.useRealTimers();
    }
  });

  test('an order that is not this user’s (404) says so and is not asked for again', async () => {
    jest.useFakeTimers({ doNotFake: ['setImmediate', 'nextTick'] });
    try {
      answers = [() => ({ status: 404, body: { status: 'not_found' } })];
      const Screen = OrderTracking();
      await render(wrap(<Screen />));
      expect(await screen.findByText("We couldn't find that order")).toBeTruthy();
      await act(async () => {
        await jest.advanceTimersByTimeAsync(60_000);
      });
      expect(orderCalls()).toHaveLength(1);
    } finally {
      jest.useRealTimers();
    }
  });

  test('if the tiles never load, the plain map replaces the WebView and the credit stays', async () => {
    answers = [() => ({ status: 200, body: ORDER() })];
    const Screen = OrderTracking();
    await render(wrap(<Screen />));
    await screen.findByText('Order DW1024');
    await waitFor(() => expect(mockWeb.props).not.toBeNull());
    const props = mockWeb.props as { source: { html: string; baseUrl: string }; userAgent: string; onMessage: (e: { nativeEvent: { data: string } }) => void };
    expect(props.userAgent).toBe(MAP_USER_AGENT);
    expect(props.source.baseUrl).toMatch(/^https:\/\//);
    await act(async () => {
      for (let i = 1; i <= 4; i++) props.onMessage({ nativeEvent: { data: JSON.stringify({ type: 'tiles', ok: 0, err: i }) } });
    });
    expect(await screen.findByText(/Map tiles are not available right now/)).toBeTruthy();
    expect(screen.getByText('© OpenStreetMap contributors')).toBeTruthy();
  });
});

describe('source rules for tracking', () => {
  const dir = path.join(__dirname, '..', 'src');
  const src = (f: string) => fs.readFileSync(path.join(dir, f), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
  test('no estimate and no price arithmetic in the tracking code', () => {
    for (const f of ['lib/orders.ts', 'app/orders/[orderNo].tsx', 'components/TrackingMap.tsx']) {
      expect(src(f)).not.toMatch(/\bETA\b|estimat|arrives? in/i);
      expect(src(f)).not.toMatch(/\b(total|taxes|delivery_fee|items_total|unit_price)\b\s*[*+\-/]\s*[\w(]/);
    }
  });
});
