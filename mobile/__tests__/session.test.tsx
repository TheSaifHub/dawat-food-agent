import { act, render, screen, waitFor } from '@testing-library/react-native';
import { Text } from 'react-native';
import { SessionProvider, useSession, type Session } from '@/lib/session';

// In-memory keystore with a switch to make it fail.
const mockStore = new Map<string, string>();
const mockFail = { get: false, set: false };
jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(async (k: string) => {
    if (mockFail.get) throw new Error('keystore down');
    return mockStore.get(k) ?? null;
  }),
  setItemAsync: jest.fn(async (k: string, v: string) => {
    if (mockFail.set) throw new Error('keystore full');
    mockStore.set(k, v);
  }),
  deleteItemAsync: jest.fn(async (k: string) => {
    mockStore.delete(k);
  }),
}));

const UNIQ = 'unit-test-string-9f3a7c';
const KEY = 'dawat.access_token';
const ME = { user_id: 'u1', display_name: 'Local Tester', is_demo: false, name_confirmed: true, account_name: 'Local Tester' };

type Reply = { status: number; body?: unknown } | 'network' | 'hang';
let replies: Record<string, Reply[]>;
let calls: { path: string; method: string; auth: string | null; body: unknown }[];

function reply(path: string, ...r: Reply[]) {
  replies[path] = r;
}

beforeEach(() => {
  mockStore.clear();
  mockFail.get = false;
  mockFail.set = false;
  replies = {};
  calls = [];
  (globalThis as unknown as { fetch: unknown }).fetch = jest.fn(async (url: string, init: RequestInit & { signal: AbortSignal }) => {
    const path = url.replace('http://localhost:8000', '');
    calls.push({
      path,
      method: init.method ?? 'GET',
      auth: (init.headers as Record<string, string>).Authorization ?? null,
      body: init.body ? JSON.parse(init.body as string) : undefined,
    });
    const queue = replies[path] ?? [];
    const next = queue.length > 1 ? queue.shift()! : queue[0];
    if (next === undefined || next === 'network') throw new TypeError('Network request failed');
    if (next === 'hang') {
      return new Promise((_, reject) => init.signal.addEventListener('abort', () => reject(new Error('aborted'))));
    }
    const text = next.body === undefined ? '' : JSON.stringify(next.body);
    return { ok: next.status >= 200 && next.status < 300, status: next.status, text: async () => text };
  });
});

let session: Session;
function Probe() {
  session = useSession();
  return <Text testID="status">{session.state.status}</Text>;
}
async function mount(timeoutMs = 70_000) {
  await render(
    <SessionProvider timeoutMs={timeoutMs}>
      <Probe />
    </SessionProvider>,
  );
}
const status = () => screen.getByTestId('status').props.children;
const waitStatus = (s: string) => waitFor(() => expect(status()).toBe(s));

describe('launch', () => {
  test('no saved token: signed out, and /me is never called', async () => {
    await mount();
    await waitStatus('signedOut');
    expect(calls).toHaveLength(0);
  });

  test('a saved token is sent as a Bearer header to /me; the user id is never sent', async () => {
    mockStore.set(KEY, UNIQ);
    reply('/me', { status: 200, body: ME });
    await mount();
    await waitStatus('signedIn');
    expect(calls).toEqual([{ path: '/me', method: 'GET', auth: `Bearer ${UNIQ}`, body: undefined }]);
  });

  test('a real 401 signs out and deletes the saved token', async () => {
    mockStore.set(KEY, UNIQ);
    reply('/me', { status: 401, body: { detail: 'Invalid token' } });
    await mount();
    await waitStatus('signedOut');
    expect(mockStore.has(KEY)).toBe(false);
  });

  // The identity rule: only a real 401 signs the user out.
  test.each<[string, Reply]>([
    ['a network error', 'network'],
    ['a 500', { status: 500, body: { detail: 'boom' } }],
    ['a 503 (sign-in keys unreachable)', { status: 503, body: { detail: 'try later' } }],
    ['a 403', { status: 403, body: { detail: 'no' } }],
    ['an HTML error page', { status: 502 }],
  ])('%s keeps the saved sign-in and shows "unreachable"', async (_name, r) => {
    mockStore.set(KEY, UNIQ);
    reply('/me', r);
    await mount();
    await waitStatus('unreachable');
    expect(mockStore.get(KEY)).toBe(UNIQ);
  });

  test('a timeout keeps the saved sign-in and shows "unreachable"', async () => {
    mockStore.set(KEY, UNIQ);
    reply('/me', 'hang');
    await mount(50);
    await waitStatus('unreachable');
    expect(mockStore.get(KEY)).toBe(UNIQ);
  });

  test('retry after a network error signs in with the same saved value', async () => {
    mockStore.set(KEY, UNIQ);
    reply('/me', 'network', { status: 200, body: ME });
    await mount();
    await waitStatus('unreachable');
    await act(async () => session.retry());
    await waitStatus('signedIn');
    expect(calls.map((c) => c.auth)).toEqual([`Bearer ${UNIQ}`, `Bearer ${UNIQ}`]);
  });

  test('retry that then gets a real 401 signs out', async () => {
    mockStore.set(KEY, UNIQ);
    reply('/me', 'network', { status: 401 });
    await mount();
    await waitStatus('unreachable');
    await act(async () => session.retry());
    await waitStatus('signedOut');
    expect(mockStore.has(KEY)).toBe(false);
  });

  test('a keystore that cannot be read means signed out, not a crash', async () => {
    mockFail.get = true;
    await mount();
    await waitStatus('signedOut');
  });
});

describe('sign in and out', () => {
  test('signInWithToken saves it, loads /me and signs in', async () => {
    reply('/me', { status: 200, body: ME });
    await mount();
    await waitStatus('signedOut');
    let out: unknown;
    await act(async () => {
      out = await session.signInWithToken(UNIQ);
    });
    expect(out).toEqual({ ok: true });
    await waitStatus('signedIn');
    expect(mockStore.get(KEY)).toBe(UNIQ);
  });

  test('if the keystore cannot save, the sign-in fails and nothing is signed in', async () => {
    await mount();
    await waitStatus('signedOut');
    mockFail.set = true;
    let out: { ok: boolean } | undefined;
    await act(async () => {
      out = await session.signInWithToken(UNIQ);
    });
    expect(out?.ok).toBe(false);
    expect(status()).toBe('signedOut');
    expect(calls).toHaveLength(0);
  });

  test('sign out clears the keystore and the in-memory value', async () => {
    mockStore.set(KEY, UNIQ);
    reply('/me', { status: 200, body: ME });
    await mount();
    await waitStatus('signedIn');
    await act(async () => session.signOut());
    expect(status()).toBe('signedOut');
    expect(mockStore.has(KEY)).toBe(false);
    reply('/x', { status: 200, body: {} });
    await act(async () => {
      await session.request('/x');
    });
    expect(calls[calls.length - 1].auth).toBeNull(); // nothing left to send
  });

  test('a late /me answer cannot undo a sign-out', async () => {
    mockStore.set(KEY, UNIQ);
    let release: (v: unknown) => void = () => {};
    (globalThis.fetch as jest.Mock).mockImplementationOnce(() => new Promise((res) => (release = res)));
    await mount();
    await waitFor(() => expect((globalThis.fetch as jest.Mock).mock.calls.length).toBe(1));
    await act(async () => session.signOut());
    await act(async () => release({ ok: true, status: 200, text: async () => JSON.stringify(ME) }));
    expect(status()).toBe('signedOut');
    expect(mockStore.has(KEY)).toBe(false);
  });
});

describe('signed-in calls', () => {
  async function signedIn() {
    mockStore.set(KEY, UNIQ);
    reply('/me', { status: 200, body: ME });
    await mount();
    await waitStatus('signedIn');
  }

  test('a real 401 on a later call signs the user out', async () => {
    await signedIn();
    reply('/cart', { status: 401 });
    await act(async () => {
      await session.request('/cart');
    });
    expect(status()).toBe('signedOut');
    expect(mockStore.has(KEY)).toBe(false);
  });

  test.each<[string, Reply]>([
    ['a network error', 'network'],
    ['a 500', { status: 500 }],
    ['a 503', { status: 503 }],
    ['a 422', { status: 422, body: { detail: 'bad' } }],
  ])('%s on a later call does not sign the user out', async (_n, r) => {
    await signedIn();
    reply('/cart', r);
    await act(async () => {
      await session.request('/cart');
    });
    expect(status()).toBe('signedIn');
    expect(mockStore.get(KEY)).toBe(UNIQ);
  });
});

describe('confirm your name', () => {
  const NEW = { ...ME, name_confirmed: false, account_name: 'Google Person' };
  async function newUser() {
    mockStore.set(KEY, UNIQ);
    reply('/me', { status: 200, body: NEW });
    await mount();
    await waitStatus('signedIn');
  }

  test('keeping the name sends an empty body (the backend reads the name from the sign-in)', async () => {
    await newUser();
    reply('/me/name', { status: 200, body: { status: 'ok', display_name: 'Google Person', name_confirmed: true } });
    await act(async () => {
      await session.confirmName(null);
    });
    const c = calls.find((x) => x.path === '/me/name')!;
    expect(c.method).toBe('POST');
    expect(c.body).toEqual({});
    expect(session.state.status === 'signedIn' && session.state.me.name_confirmed).toBe(true);
  });

  test('a changed name is sent as the only field, and the server answer is shown', async () => {
    await newUser();
    reply('/me/name', { status: 200, body: { status: 'ok', display_name: 'Saif', name_confirmed: true } });
    await act(async () => {
      await session.confirmName('Saif');
    });
    expect(calls.find((x) => x.path === '/me/name')!.body).toEqual({ name: 'Saif' });
    expect(session.state.status === 'signedIn' && session.state.me.display_name).toBe('Saif');
  });

  test('a 422 keeps the user on the name screen with the server message', async () => {
    await newUser();
    reply('/me/name', { status: 422, body: { detail: 'Please use letters only.' } });
    let out: { ok: boolean; message?: string } | undefined;
    await act(async () => {
      out = await session.confirmName('<b>');
    });
    expect(out).toEqual({ ok: false, message: 'Please use letters only.' });
    expect(session.state.status === 'signedIn' && session.state.me.name_confirmed).toBe(false);
  });

  test('a network error while saving the name does not sign the user out', async () => {
    await newUser();
    reply('/me/name', 'network');
    let out: { ok: boolean } | undefined;
    await act(async () => {
      out = await session.confirmName('Saif');
    });
    expect(out?.ok).toBe(false);
    expect(status()).toBe('signedIn');
    expect(mockStore.get(KEY)).toBe(UNIQ);
  });
});
