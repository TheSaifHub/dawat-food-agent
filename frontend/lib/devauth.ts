"use client";

// The LOCAL dev login's browser side (D-059). Loaded only through lib/auth.ts's dynamic import inside a
// `DEV_LOGIN` branch, and DEV_LOGIN is false in every production build.

import { api } from "@/lib/api";

const STORAGE_KEY = "dawat-dev-login-session";

type Stored = { access_token: string; expires_at: number; user_id: string };

const listeners = new Set<() => void>();
let memory: Stored | null = null;

function read(): Stored | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const s = raw ? (JSON.parse(raw) as Stored) : null;
    return s && typeof s.access_token === "string" && typeof s.expires_at === "number" ? s : null;
  } catch {
    return null;
  }
}

function write(s: Stored | null) {
  try {
    if (s) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // storage blocked
  }
  memory = s;
  listeners.forEach((cb) => cb());
}

export async function accessToken(): Promise<string | null> {
  const s = read() ?? memory;
  if (!s) return null;
  if (s.expires_at * 1000 <= Date.now() + 30_000) {
    write(null);
    return null;
  }
  return s.access_token;
}

export function onAuthChange(cb: () => void): () => void {
  listeners.add(cb);
  const first = setTimeout(cb, 0);
  return () => {
    clearTimeout(first);
    listeners.delete(cb);
  };
}

export async function signOut(): Promise<void> {
  write(null);
}

async function take(path: string, body?: unknown): Promise<{ error: null | { status: number } }> {
  const res = await api<Stored>(path, { method: "POST", body });
  if (!res.ok) return { error: { status: res.status } };
  write(res.data);
  return { error: null };
}

export function signInGoogle(newUser: boolean) {
  return take("/dev/auth/google", newUser ? { new_user: true } : undefined);
}
