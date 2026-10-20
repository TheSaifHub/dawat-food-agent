// The one way the website talks to the Dawat backend.
//
// The backend returns each tool's JSON unchanged, with an HTTP status taken from its `status` field.
// Never send a price or a total: the backend computes every amount itself and refuses extra fields.

import { API_URL } from "@/lib/config";

/** What every tool answer looks like: a status word, maybe a message, and the tool's own fields. */
export type ToolBody = { status: string; message?: string; [key: string]: unknown };

export type ApiResult<T> =
  | { ok: true; status: number; data: T }
  /** The backend answered with an error code. `data` is its body (a tool answer, or FastAPI's {detail}). */
  | { ok: false; kind: "http"; status: number; data: unknown; message: string }
  /** No answer at all: offline, CORS refused, server down or asleep past the timeout, or aborted by the caller. */
  | { ok: false; kind: "network" | "timeout" | "aborted"; status: 0; data: null; message: string };

export type ApiOptions = {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  /** JSON body (POST/PUT). */
  body?: unknown;
  /** The Supabase access token, for routes that need a signed-in user. */
  token?: string | null;
  /** Query parameters; null/undefined/"" values are left out. */
  query?: Record<string, string | number | boolean | null | undefined>;
  signal?: AbortSignal;
  /** Give up after this long. The free backend can take ~50 s to wake from sleep, so the default is generous. */
  timeoutMs?: number;
  /** Called once if the request is still running after `slowAfterMs` (default 4 s): show "Waking up Dawat…". */
  onSlow?: () => void;
  slowAfterMs?: number;
};

const DEFAULT_TIMEOUT_MS = 70_000;
const DEFAULT_SLOW_MS = 4_000;

export const MESSAGES = {
  network: "Can't reach Dawat right now. Check your connection and try again.",
  timeout: "Dawat is taking too long to answer. Please try again in a minute.",
  aborted: "Cancelled.",
  signIn: "Please sign in again.",
  server: "Something went wrong on our side. Please try again.",
} as const;

export function apiUrl(path: string, query?: ApiOptions["query"]): string {
  const url = new URL(API_URL + (path.startsWith("/") ? path : `/${path}`));
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== null && value !== undefined && value !== "") url.searchParams.set(key, String(value));
  }
  return url.toString();
}

/** The message to show for an error response: the tool's own message, FastAPI's detail text, or a generic one. */
export function errorMessage(status: number, data: unknown): string {
  if (status === 401) return MESSAGES.signIn;
  if (data && typeof data === "object") {
    const body = data as { message?: unknown; detail?: unknown };
    if (typeof body.message === "string" && body.message) return body.message;
    if (typeof body.detail === "string" && body.detail) return body.detail;
  }
  return status >= 500 ? MESSAGES.server : "That didn't work. Please check and try again.";
}

export async function api<T = ToolBody>(path: string, options: ApiOptions = {}): Promise<ApiResult<T>> {
  const { method = "GET", body, token, query, signal, timeoutMs = DEFAULT_TIMEOUT_MS, onSlow } = options;
  const controller = new AbortController();
  let timedOut = false;
  const onCallerAbort = () => controller.abort();
  signal?.addEventListener("abort", onCallerAbort, { once: true });
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const slowTimer = onSlow ? setTimeout(onSlow, options.slowAfterMs ?? DEFAULT_SLOW_MS) : undefined;

  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;

  try {
    const res = await fetch(apiUrl(path, query), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
      cache: "no-store",
    });
    const text = await res.text();
    let data: unknown = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = null; // a proxy's HTML error page: treat as no body
    }
    if (res.ok) return { ok: true, status: res.status, data: data as T };
    return { ok: false, kind: "http", status: res.status, data, message: errorMessage(res.status, data) };
  } catch {
    const kind = timedOut ? "timeout" : signal?.aborted ? "aborted" : "network";
    return { ok: false, kind, status: 0, data: null, message: MESSAGES[kind] };
  } finally {
    clearTimeout(timer);
    clearTimeout(slowTimer);
    signal?.removeEventListener("abort", onCallerAbort);
  }
}

// ─── Response shapes used across pages (only the fields the website reads) ─────────────────────────────

export type Area = { area_id: string; name: string; name_te: string | null };
export type AreasResponse = { status: "ok"; areas: Area[] };
export type Health = { status: string; version: string };
