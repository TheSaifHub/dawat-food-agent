"use client";

// The LOCAL dev login's browser side (D-059). Loaded only through lib/auth.ts's dynamic import inside a
// `DEV_LOGIN` branch, and DEV_LOGIN is false in every production build, so this module never ships to the deployed
// site (`npm run build` scans its output for the markers below and fails if they appear).
//
// It plays the part of supabase-js for the local backend's /dev/auth routes: a token kept in this browser's
// localStorage, sign-in / sign-out events, and the token for each backend call. When it expires (12 h) the visitor
// is simply signed out.

import { api } from "@/lib/api";

const STORAGE_KEY = "dawat-dev-login-session";       // also the build scan's marker

type Stored = { access_token: string; expires_at: number; user_id: string };
export type SeedUser = { user_id: string; display_name: string };

const listeners = new Set<() => void>();
let memory: Stored | null = null;              // when storage is blocked

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
    // storage blocked: the session lasts until the page is reloaded
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

/** Like supabase-js: called once soon after subscribing, then on every sign-in and sign-out. */
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

export function signInAnonymously() {
  return take("/dev/auth/anonymous");
}

export function signInSeedUser(userId: string) {
  return take("/dev/auth/seed-user", { user_id: userId });
}

export async function seedUsers(): Promise<SeedUser[] | null> {
  const res = await api<{ users: SeedUser[] }>("/dev/auth/users");
  return res.ok ? res.data.users : null;
}
