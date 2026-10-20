import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { SessionProvider } from '@/lib/session';

// No @types/node in this project: the two Node modules are loaded with require, and the globals are declared.
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

const KEY = 'dawat.access_token';
const ME = { user_id: 'u1', display_name: 'Local Tester', is_demo: false, name_confirmed: false, account_name: 'Google Person' };
type Call = { path: string; method: string; body: unknown };
let calls: Call[];
let answers: Record<string, { status: number; body: unknown }>;

beforeEach(() => {
  mockStore.clear();
  calls = [];
  answers = {};
  (globalThis as unknown as { fetch: unknown }).fetch = jest.fn(async (url: string, init: RequestInit) => {
    const p = url.replace('http://localhost:8000', '');
    calls.push({ path: p, method: init.method ?? 'GET', body: init.body ? JSON.parse(init.body as string) : undefined });
    const a = answers[p];
    if (!a) throw new TypeError('Network request failed');
    return { ok: a.status < 300, status: a.status, text: async () => JSON.stringify(a.body) };
  });
});

const wrap = (ui: React.ReactElement) => (
  <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 360, height: 800 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
    <SessionProvider>{ui}</SessionProvider>
  </SafeAreaProvider>
);

// The switch is read when Welcome renders, so a test sets it, renders, and puts it back.
function loadWelcome(devSwitch: string | undefined) {
  const Welcome = require('@/app/welcome').default as React.ComponentType;
  return function WelcomeWithSwitch() {
    if (devSwitch === undefined) delete process.env.EXPO_PUBLIC_DAWAT_DEV_LOGIN;
    else process.env.EXPO_PUBLIC_DAWAT_DEV_LOGIN = devSwitch;
    return <Welcome />;
  };
}

afterEach(() => {
  delete process.env.EXPO_PUBLIC_DAWAT_DEV_LOGIN;
});

describe('Welcome and the dev-login gate', () => {
  test.each([undefined, '', '0', 'true'])('with the switch = %p there is no dev login, only Continue with Google', async (v) => {
    const Welcome = loadWelcome(v);
    await render(wrap(<Welcome />));
    expect(screen.getByRole('button', { name: 'Continue with Google' })).toBeTruthy();
    expect(screen.queryByText(/dev only/i)).toBeNull();
    expect(screen.queryByText(/fake user/i)).toBeNull();
  });

  // Regression (Session 26): a saved sign-in the backend rejects (token expired after 12 h, or the dev database was
  // rebuilt so the account is gone) must say why on Welcome. A network failure must NOT sign out or show this.
  test('a saved sign-in rejected with 401 lands on Welcome with a short notice and the token is deleted', async () => {
    mockStore.set(KEY, 'stale-token-value');
    answers['/me'] = { status: 401, body: { detail: 'This account no longer exists. Please sign in again.' } };
    const Welcome = loadWelcome(undefined);
    await render(wrap(<Welcome />));
    await waitFor(() => expect(screen.getByText('Please sign in again.')).toBeTruthy());
    expect(mockStore.has(KEY)).toBe(false);
  });

  test('a fresh install shows no sign-in notice, and a network failure keeps the token and shows none', async () => {
    const Welcome = loadWelcome(undefined);
    await render(wrap(<Welcome />));
    expect(screen.queryByText('Please sign in again.')).toBeNull();
    mockStore.set(KEY, 'kept-token-value');
    await render(wrap(<Welcome />)); // /me has no answer: the fake fetch throws a network error
    await waitFor(() => expect(calls.some((c) => c.path === '/me')).toBe(true));
    expect(screen.queryByText('Please sign in again.')).toBeNull();
    expect(mockStore.get(KEY)).toBe('kept-token-value');
  });

  test('Continue with Google says plainly that it is not set up yet, and calls nothing', async () => {
    const Welcome = loadWelcome(undefined);
    await render(wrap(<Welcome />));
    await fireEvent.press(screen.getByRole('button', { name: 'Continue with Google' }));
    expect(screen.getByText(/isn't set up yet/)).toBeTruthy();
    expect(calls.filter((c) => c.path.startsWith('/dev'))).toHaveLength(0);
  });

  test('with the switch = 1 the two dev buttons are there', async () => {
    const Welcome = loadWelcome('1');
    await render(wrap(<Welcome />));
    expect(screen.getByText('Local sign-in (dev only)')).toBeTruthy();
    expect(screen.getByText('New fake user (dev only)')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Continue with Google' })).toBeNull();
  });

  test('"New fake user" asks for a brand-new user and the other button does not', async () => {
    answers['/dev/auth/google'] = { status: 200, body: { access_token: 'grant-1', expires_at: 1, user_id: 'u9' } };
    answers['/me'] = { status: 200, body: ME };
    const Welcome = loadWelcome('1');
    await render(wrap(<Welcome />));
    await fireEvent.press(screen.getByText('New fake user (dev only)'));
    await waitFor(() => expect(mockStore.get(KEY)).toBe('grant-1'));
    expect(calls.find((c) => c.path === '/dev/auth/google')).toEqual({ path: '/dev/auth/google', method: 'POST', body: { new_user: true } });

    calls.length = 0;
    await fireEvent.press(screen.getByText('Local sign-in (dev only)'));
    await waitFor(() => expect(calls.some((c) => c.path === '/dev/auth/google')).toBe(true));
    expect(calls.find((c) => c.path === '/dev/auth/google')!.body).toEqual({});
  });

  test('a failed dev sign-in shows a message and does not sign in', async () => {
    const Welcome = loadWelcome('1');
    await render(wrap(<Welcome />));
    await fireEvent.press(screen.getByText('Local sign-in (dev only)'));
    await waitFor(() => expect(screen.getByText(/Can't reach Dawat/)).toBeTruthy());
    expect(mockStore.has(KEY)).toBe(false);
  });
});

describe('Confirm your name screen', () => {
  async function open(me = ME) {
    mockStore.set(KEY, 'stored-value');
    answers['/me'] = { status: 200, body: me };
    const ConfirmName = require('@/app/confirm-name').default;
    // As in the app, the screen is only shown once the profile is loaded (see Gate in src/app/_layout.tsx).
    const { useSession } = require('@/lib/session');
    function Ready() {
      return useSession().state.status === 'signedIn' ? <ConfirmName /> : null;
    }
    await render(wrap(<Ready />));
    await waitFor(() => expect(screen.getByLabelText('Your name').props.value).toBe(me.account_name));
  }

  test('is prefilled with the account name; keeping it sends an empty body', async () => {
    await open();
    answers['/me/name'] = { status: 200, body: { status: 'ok', display_name: 'Google Person', name_confirmed: true } };
    await fireEvent.press(screen.getByRole('button', { name: 'Looks right' }));
    await waitFor(() => expect(calls.some((c) => c.path === '/me/name')).toBe(true));
    expect(calls.find((c) => c.path === '/me/name')!.body).toEqual({});
  });

  test('a changed name is sent trimmed', async () => {
    await open();
    answers['/me/name'] = { status: 200, body: { status: 'ok', display_name: 'Saif', name_confirmed: true } };
    await fireEvent.changeText(screen.getByLabelText('Your name'), '  Saif  ');
    await fireEvent.press(screen.getByRole('button', { name: 'Use this name' }));
    await waitFor(() => expect(calls.some((c) => c.path === '/me/name')).toBe(true));
    expect(calls.find((c) => c.path === '/me/name')!.body).toEqual({ name: 'Saif' });
  });

  test.each([['empty', ''], ['spaces only', '   '], ['61 characters', 'a'.repeat(61)]])('%s cannot be sent', async (_n, value) => {
    await open();
    await fireEvent.changeText(screen.getByLabelText('Your name'), value);
    const button = screen.getByRole('button', { name: /Use this name|Looks right/ });
    expect(button.props.accessibilityState.disabled).toBe(true);
    await fireEvent.press(button);
    expect(calls.some((c) => c.path === '/me/name')).toBe(false);
  });

  test('a server refusal is shown on the screen', async () => {
    await open();
    answers['/me/name'] = { status: 422, body: { detail: 'Names cannot contain symbols.' } };
    await fireEvent.changeText(screen.getByLabelText('Your name'), 'Saif!');
    await fireEvent.press(screen.getByRole('button', { name: 'Use this name' }));
    await waitFor(() => expect(screen.getByText('Names cannot contain symbols.')).toBeTruthy());
  });
});

describe('the token is never logged or kept in plain storage', () => {
  const SRC = path.join(__dirname, '..', 'src');
  const files: string[] = [];
  (function walk(dir: string) {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) walk(p);
      else if (/\.(ts|tsx)$/.test(e.name)) files.push(p);
    }
  })(SRC);

  test('no file in src/ uses console.* (so nothing there can print a token)', () => {
    const offenders = files.filter((f) => /\bconsole\s*\./.test(fs.readFileSync(f, 'utf8').replace(/\/\/.*$/gm, '')));
    expect(offenders.map((f) => path.relative(SRC, f))).toEqual([]);
  });

  test('AsyncStorage / localStorage are not used in src/ (the token lives only in the keystore)', () => {
    const offenders = files.filter((f) => /async-storage|AsyncStorage|localStorage/.test(fs.readFileSync(f, 'utf8').replace(/\/\/.*$/gm, '')));
    expect(offenders.map((f) => path.relative(SRC, f))).toEqual([]);
  });

  test('the sign-in value never appears in a URL or in the console during a full run', async () => {
    const spies = (['log', 'info', 'warn', 'error', 'debug'] as const).map((m) => jest.spyOn(console, m).mockImplementation(() => {}));
    mockStore.set(KEY, 'unit-test-string-77');
    answers['/me'] = { status: 401, body: { detail: 'Invalid token' } };
    const Welcome = loadWelcome(undefined);
    await render(wrap(<Welcome />));
    await waitFor(() => expect(mockStore.has(KEY)).toBe(false));
    const printed = spies.flatMap((s) => s.mock.calls).map((a) => JSON.stringify(a)).join('\n');
    expect(printed).not.toContain('unit-test-string-77');
    expect((globalThis.fetch as jest.Mock).mock.calls.map((c) => String(c[0])).join('\n')).not.toContain('unit-test-string-77');
    spies.forEach((s) => s.mockRestore());
  });
});
