// The one way the app talks to the Dawat backend (ported from frontend_old/src/lib/api.ts).
//
// Returns a result object and never throws, because a failed request often still carries something the screen must
// show (a tool's own message, FastAPI's {detail}). The three "no answer" kinds (network, timeout, aborted) are kept
// apart from real HTTP answers on purpose: only a real HTTP 401 means "your sign-in is not valid" (lib/session.tsx).
//
// Never send a price, a total, a user id or a source: the backend computes and decides those itself.
// Never log anything here: the Authorization header holds the sign-in token (tested: no console use in src/).

import { API_URL } from './config';

export type ApiResult<T> =
  | { ok: true; status: number; data: T }
  /** The backend answered with an error code. `data` is its body (a tool answer, or FastAPI's {detail}). */
  | { ok: false; kind: 'http'; status: number; data: unknown; message: string }
  /** No answer at all: offline, backend down or asleep past the timeout, or cancelled by the caller. */
  | { ok: false; kind: 'network' | 'timeout' | 'aborted'; status: 0; data: null; message: string };

export type ApiOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: unknown;
  /** The sign-in token, for routes that need a signed-in user. */
  token?: string | null;
  signal?: AbortSignal;
  /** The free backend can take ~50 s to wake from sleep, so the default is generous. */
  timeoutMs?: number;
  /** Called once if the request is still running after `slowAfterMs` (default 4 s): "Waking up Dawat AI…". */
  onSlow?: () => void;
  slowAfterMs?: number;
};

export const DEFAULT_TIMEOUT_MS = 70_000;
const DEFAULT_SLOW_MS = 4_000;

export const MESSAGES = {
  network: "Can't reach Dawat right now. Check your connection and try again.",
  timeout: 'Dawat is taking too long to answer. Please try again in a minute.',
  aborted: 'Cancelled.',
  signIn: 'Please sign in again.',
  server: 'Something went wrong on our side. Please try again.',
} as const;

/** The message for an error response: the tool's own message, FastAPI's detail text, or a generic one. */
export function errorMessage(status: number, data: unknown): string {
  if (status === 401) return MESSAGES.signIn;
  if (data && typeof data === 'object') {
    const body = data as { message?: unknown; detail?: unknown };
    if (typeof body.message === 'string' && body.message) return body.message;
    if (typeof body.detail === 'string' && body.detail) return body.detail;
  }
  return status >= 500 ? MESSAGES.server : "That didn't work. Please check and try again.";
}

export async function api<T = unknown>(path: string, options: ApiOptions = {}): Promise<ApiResult<T>> {
  const { method = 'GET', body, token, signal, timeoutMs = DEFAULT_TIMEOUT_MS, onSlow } = options;
  const controller = new AbortController();
  let timedOut = false;
  const onCallerAbort = () => controller.abort();
  signal?.addEventListener('abort', onCallerAbort, { once: true });
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const slowTimer = onSlow ? setTimeout(onSlow, options.slowAfterMs ?? DEFAULT_SLOW_MS) : undefined;

  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;

  try {
    const res = await fetch(API_URL + (path.startsWith('/') ? path : `/${path}`), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    const text = await res.text();
    let data: unknown = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = null; // a proxy's HTML error page: treat as no body
    }
    if (res.ok) return { ok: true, status: res.status, data: data as T };
    return { ok: false, kind: 'http', status: res.status, data, message: errorMessage(res.status, data) };
  } catch {
    const kind = timedOut ? 'timeout' : signal?.aborted ? 'aborted' : 'network';
    return { ok: false, kind, status: 0, data: null, message: MESSAGES[kind] };
  } finally {
    clearTimeout(timer);
    clearTimeout(slowTimer);
    signal?.removeEventListener('abort', onCallerAbort);
  }
}

/** The one thing that means "this token is not accepted": the backend answered 401. Nothing else qualifies. */
export function isRejectedToken<T>(r: ApiResult<T>): boolean {
  return !r.ok && r.kind === 'http' && r.status === 401;
}
