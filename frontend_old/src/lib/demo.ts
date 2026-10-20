"use client";

// "Try as Priya / Arjun" (D-048): a fresh, private anonymous account per visitor, seeded once by the backend.
//
//   1. Already this persona? Done.
//   2. Signed in as anyone else (an email account, or the other persona)? Sign out first: personas never mix with a
//      real account, and the backend refuses to turn one into a persona anyway.
//   3. signInAnonymously() (Supabase, or the local dev login: lib/auth.ts), then POST /demo/start {persona}.
// If step 3's backend call fails (asleep, offline), the anonymous session is kept and the button can simply be
// pressed again: /demo/start is safe to repeat (already_started).

import { api, type ToolBody } from "@/lib/api";
import type { Me, Persona } from "@/lib/session";
import { accessToken, authConfigured, signInAnonymously, signOut } from "@/lib/auth";

export type DemoResult = { ok: true } | { ok: false; message: string };

export const PERSONA_CARDS: Record<Persona, { name: string; blurb: string; facts: string[] }> = {
  priya: {
    name: "Priya",
    blurb: "Vegetarian, likes it mild, orders around Madhapur.",
    facts: ["Saved diet: vegetarian", "Spice: mild", "Chats in English"],
  },
  arjun: {
    name: "Arjun",
    blurb: "Loves spicy food, orders to the office in Gachibowli.",
    facts: ["Eats everything", "Spice: hot", "Chats in Hinglish"],
  },
};

export async function tryAs(persona: Persona, current: Me | null, onSlow?: () => void): Promise<DemoResult> {
  if (!authConfigured) return { ok: false, message: "Sign-in isn't set up on this copy of Dawat." };

  if (current?.demo_persona === persona) return { ok: true };
  const reuse = current?.is_anonymous && current.demo_persona === null;   // a guest from an earlier failed try
  if (current && !reuse) await signOut();

  if (!reuse) {
    const { error } = await signInAnonymously();
    if (error) {
      return {
        ok: false,
        message: error.status === 429
          ? "Too many demo accounts were started from this network. Please try again later."
          : "Couldn't start a demo account right now. Please try again.",
      };
    }
  }

  const res = await api<ToolBody>("/demo/start", { method: "POST", body: { persona }, token: await accessToken(), onSlow });
  if (res.ok) return { ok: true };
  return { ok: false, message: res.message };
}
