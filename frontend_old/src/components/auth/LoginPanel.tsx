"use client";

// The sign-in screen (Phase 7b, D-048/D-049). The demo personas come first: they are the main way in, one click, no
// email. Email sign-in and sign-up stay for anyone who wants their own account.

import { useRouter } from "next/navigation";
import { lazy, Suspense, useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { authConfigured } from "@/lib/auth";
import { PERSONA_CARDS, tryAs } from "@/lib/demo";
import { useSession, type Persona } from "@/lib/session";
import { supabase } from "@/lib/supabase";

export type Busy = Persona | "email" | null;

// D-059: the local dev sign-in. The import sits INSIDE the inline build-time condition, so a production build has
// neither the import nor the component (npm run build's scan checks this).
const DevSignIn = process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_DAWAT_DEV_LOGIN === "1"
  ? lazy(() => import("@/components/auth/DevSignIn"))
  : null;

export function LoginPanel() {
  const router = useRouter();
  const { session, refresh } = useSession();
  const [busy, setBusy] = useState<Busy>(null);
  const [waking, setWaking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const me = session.state === "signed_in" ? session.me : null;

  async function startPersona(persona: Persona) {
    setBusy(persona);
    setError(null);
    setNotice(null);
    setWaking(false);
    const result = await tryAs(persona, me, () => setWaking(true));
    const next = await refresh();
    setBusy(null);
    setWaking(false);
    if (result.ok && next.state === "signed_in") router.push("/");
    else setError(result.ok ? "Signed in, but Dawat couldn't load your profile. Please try again." : result.message);
  }

  if (!authConfigured) {
    return (
      <p role="alert" className="rounded-lg border border-input bg-card p-4">
        Sign-in isn&apos;t set up on this copy of Dawat. You can still browse restaurants and menus.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-10">
      {me ? (
        <p className="rounded-lg bg-secondary px-4 py-3 text-secondary-foreground">
          You&apos;re signed in as <strong>{me.display_name}</strong>. Choosing a demo below signs you out first.
        </p>
      ) : null}

      <section aria-labelledby="demo-heading" className="flex flex-col gap-4">
        <div>
          <h2 id="demo-heading" className="font-display text-3xl font-semibold text-plum">Try Dawat as…</h2>
          <p className="mt-1 text-muted-foreground">
            A private demo account just for you, with saved preferences and a few sample past orders. No email needed.
          </p>
        </div>
        <ul className="grid gap-4 sm:grid-cols-2">
          {(Object.keys(PERSONA_CARDS) as Persona[]).map((persona) => {
            const card = PERSONA_CARDS[persona];
            const current = me?.demo_persona === persona;
            return (
              <li key={persona} className="flex flex-col gap-3 rounded-xl border border-border bg-card p-5 shadow-sm">
                <h3 className="font-display text-2xl font-semibold">{card.name}</h3>
                <p>{card.blurb}</p>
                <ul className="flex flex-wrap gap-2 text-sm" aria-label={`${card.name}'s saved preferences`}>
                  {card.facts.map((fact) => (
                    <li key={fact} className="rounded-full bg-muted px-3 py-1 text-muted-foreground">{fact}</li>
                  ))}
                </ul>
                <Button
                  size="lg"
                  className="mt-auto h-11 text-base"
                  disabled={busy !== null}
                  onClick={() => (current ? router.push("/") : void startPersona(persona))}
                >
                  {busy === persona ? `Setting up ${card.name}…` : current ? `Continue as ${card.name}` : `Try as ${card.name}`}
                </Button>
              </li>
            );
          })}
        </ul>
        <div aria-live="polite" className="min-h-6 text-sm">
          {waking ? <p>Waking up Dawat AI… the free server sleeps when idle, this can take up to a minute.</p> : null}
        </div>
      </section>

      {DevSignIn ? (
        <Suspense fallback={<p>Loading the local sign-in…</p>}>
          <DevSignIn busy={busy} setBusy={setBusy} setError={setError}
                     onSignedIn={async () => {
                       const next = await refresh();
                       if (next.state === "signed_in") router.push("/");
                       else setError("Signed in, but Dawat couldn't load your profile. Please try again.");
                     }} />
        </Suspense>
      ) : (
        <EmailForm busy={busy} setBusy={setBusy} setError={setError} setNotice={setNotice}
                   onSignedIn={async () => {
                     const next = await refresh();
                     if (next.state === "signed_in") router.push("/");
                     else setError("Signed in, but Dawat couldn't load your profile. Please try again.");
                   }} />
      )}

      {error ? <p role="alert" className="rounded-lg border border-destructive px-4 py-3 text-destructive">{error}</p> : null}
      {notice ? <p role="status" className="rounded-lg bg-secondary px-4 py-3 text-secondary-foreground">{notice}</p> : null}
    </div>
  );
}

function EmailForm({ busy, setBusy, setError, setNotice, onSignedIn }: {
  busy: Busy;
  setBusy: (b: Busy) => void;
  setError: (e: string | null) => void;
  setNotice: (n: string | null) => void;
  onSignedIn: () => Promise<void>;
}) {
  const [mode, setMode] = useState<"sign_in" | "sign_up">("sign_in");
  const emailId = useId();
  const passwordId = useId();

  async function submit(form: FormData) {
    const sb = supabase();
    if (!sb) return;
    const email = String(form.get("email") ?? "").trim();
    const password = String(form.get("password") ?? "");
    setBusy("email");
    setError(null);
    setNotice(null);
    if (mode === "sign_in") {
      const { error } = await sb.auth.signInWithPassword({ email, password });
      setBusy(null);
      if (error) setError(error.status === 400 ? "That email and password don't match an account." : "Couldn't sign in right now. Please try again.");
      else await onSignedIn();
      return;
    }
    const { data, error } = await sb.auth.signUp({
      email, password, options: { emailRedirectTo: `${window.location.origin}/login` },
    });
    setBusy(null);
    if (error) setError(error.message || "Couldn't create the account. Please try again.");
    else if (data.session) await onSignedIn();
    else setNotice("Check your email for a link to confirm your account, then sign in here.");
  }

  const inputClass = "h-11 rounded-lg border border-input bg-card px-3 text-base outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background";
  return (
    <section aria-labelledby="email-heading" className="flex flex-col gap-4 border-t border-border pt-8">
      <div>
        <h2 id="email-heading" className="font-display text-2xl font-semibold text-plum">
          {mode === "sign_in" ? "Or sign in with email" : "Create an account"}
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">Your own account, kept separate from the demo ones.</p>
      </div>
      <form action={submit} className="flex max-w-sm flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor={emailId} className="text-sm font-medium">Email</label>
          <input id={emailId} name="email" type="email" required autoComplete="email" className={inputClass} />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={passwordId} className="text-sm font-medium">Password</label>
          <input id={passwordId} name="password" type="password" required minLength={mode === "sign_up" ? 8 : undefined}
                 autoComplete={mode === "sign_in" ? "current-password" : "new-password"} className={inputClass}
                 aria-describedby={mode === "sign_up" ? `${passwordId}-hint` : undefined} />
          {mode === "sign_up" ? <p id={`${passwordId}-hint`} className="text-sm text-muted-foreground">At least 8 characters.</p> : null}
        </div>
        <Button type="submit" size="lg" className="h-11 text-base" disabled={busy !== null}>
          {busy === "email" ? "Please wait…" : mode === "sign_in" ? "Sign in" : "Create account"}
        </Button>
      </form>
      <p className="text-sm">
        {mode === "sign_in" ? "New here? " : "Already have an account? "}
        <button type="button" className="inline-block py-1 text-plum underline underline-offset-2"
                onClick={() => { setMode(mode === "sign_in" ? "sign_up" : "sign_in"); setError(null); setNotice(null); }}>
          {mode === "sign_in" ? "Create an account" : "Sign in instead"}
        </button>
      </p>
    </section>
  );
}
