"use client";

// Your profile (Phase 7g): the account, saved preferences and addresses.
//
// Preferences (D-027): this is the settings screen, an explicit source by nature, so a change saves straight away
// (7g choice 5) through PUT/DELETE /me/preferences, stored with source "settings". The backend checks and normalises
// every value and says how each one was saved ("how_saved"); the page shows that line as given. Dawat AI's chat uses
// the same preferences, with its own two-step confirmation (D-045). Addresses are read-only for now (7g choice 4).

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

import { AreaPicker } from "@/components/browse/AreaPicker";
import { Announcer, ErrorNote, Loading } from "@/components/common/Loading";
import { signInLink, textLink } from "@/components/orders/OrdersView";
import { api } from "@/lib/api";
import { accessToken } from "@/lib/auth";
import { useSession, type Me } from "@/lib/session";

type PrefKey = "diet" | "max_spice" | "default_area" | "language";
type Saved = { value: string | number; label: string; source: string; how_saved: string; saved_at: string };
type Prefs = Partial<Record<PrefKey, Saved>>;
type Address = { address_id: string; label: string; line1: string; area: string; is_default: boolean };

const KEYS: { key: PrefKey; title: string }[] = [
  { key: "diet", title: "Diet" },
  { key: "max_spice", title: "Spice" },
  { key: "default_area", title: "Default delivery area" },
  { key: "language", title: "Chat language" },
];

// The values the backend accepts (app/tools/preferences.py), with the words people see.
const CHOICES: Record<Exclude<PrefKey, "default_area">, { value: string | number; text: string }[]> = {
  diet: [
    { value: "vegetarian", text: "Vegetarian" },
    { value: "eggetarian", text: "Eggetarian (vegetarian + egg)" },
    { value: "non_vegetarian", text: "Non-vegetarian" },
  ],
  max_spice: [
    { value: 0, text: "No spice" },
    { value: 1, text: "Mild" },
    { value: 2, text: "Medium" },
    { value: 3, text: "Very spicy" },
  ],
  language: [
    { value: "en", text: "English" },
    { value: "hinglish", text: "Hinglish" },
    { value: "te", text: "Telugu" },
  ],
};

type State =
  | { kind: "loading"; slow: boolean }
  | { kind: "ok"; prefs: Prefs; addresses: Address[] }
  | { kind: "error"; message: string };

export function ProfileView() {
  const { session } = useSession();
  const [state, setState] = useState<State>({ kind: "loading", slow: false });
  const [attempt, setAttempt] = useState(0);
  const [note, setNote] = useState<{ text: string; ok: boolean; seq: number } | null>(null);
  const signedIn = session.state === "signed_in";

  useEffect(() => {
    if (!signedIn) return;
    const controller = new AbortController();
    queueMicrotask(() => setState({ kind: "loading", slow: false }));
    const onSlow = () => setState((s) => (s.kind === "loading" ? { kind: "loading", slow: true } : s));
    void (async () => {
      const token = await accessToken();
      const [prefs, addresses] = await Promise.all([
        api<{ preferences: Prefs }>("/me/preferences", { token, signal: controller.signal, onSlow }),
        api<{ addresses: Address[] }>("/me/addresses", { token, signal: controller.signal }),
      ]);
      if (controller.signal.aborted) return;
      if (prefs.ok && addresses.ok) setState({ kind: "ok", prefs: prefs.data.preferences, addresses: addresses.data.addresses });
      else setState({ kind: "error", message: prefs.ok ? (addresses as { message: string }).message : prefs.message });
    })();
    return () => controller.abort();
  }, [signedIn, attempt]);

  const say = (text: string, ok: boolean) => setNote((n) => ({ text, ok, seq: (n?.seq ?? 0) + 1 }));

  async function change(key: PrefKey, value: string | number | null): Promise<boolean> {
    const token = await accessToken();
    type Answer = { preferences: Prefs; label?: string };
    const res = value === null
      ? await api<Answer>(`/me/preferences/${key}`, { method: "DELETE", token })
      : await api<Answer>(`/me/preferences/${key}`, { method: "PUT", body: { value }, token });
    if (!res.ok) {
      say(res.message, false);
      return false;
    }
    setState((s) => (s.kind === "ok" ? { ...s, prefs: res.data.preferences } : s));
    const title = KEYS.find((k) => k.key === key)?.title ?? key;
    say(value === null ? `${title} forgotten.` : `Saved: ${res.data.label ?? title}.`, true);
    return true;
  }

  if (session.state === "loading") return <Loading what="your profile" slow={false} />;
  if (!signedIn) {
    return (
      <div className="flex flex-col items-start gap-4">
        <p>Sign in to see your profile.</p>
        <Link href="/login" className={signInLink}>Sign in</Link>
      </div>
    );
  }
  const me = session.me;
  return (
    <div className="flex flex-col gap-8">
      <Announcer text={note?.text ?? ""} seq={note?.seq} />
      <AccountCard me={me} />
      {state.kind === "loading" ? <Loading what="your preferences" slow={state.slow} />
        : state.kind === "error" ? <ErrorNote message={state.message} onRetry={() => setAttempt((a) => a + 1)} />
        : (
          <>
            <section aria-labelledby="prefs-heading" className="flex flex-col gap-3">
              <div>
                <h2 id="prefs-heading" className="font-display text-3xl font-semibold">Saved preferences</h2>
                <p className="text-muted-foreground">
                  Dawat AI uses these when it plans and suggests food. Changes here save straight away.
                </p>
              </div>
              {note && !note.ok ? <p role="alert" className="rounded-lg border border-destructive px-4 py-3 text-destructive">{note.text}</p> : null}
              <ul className="flex flex-col divide-y divide-border rounded-xl border border-border bg-card">
                {KEYS.map(({ key, title }) => (
                  <PreferenceRow key={key} prefKey={key} title={title} saved={state.prefs[key]} onChange={change} />
                ))}
              </ul>
            </section>
            <Addresses addresses={state.addresses} />
          </>
        )}
      <div className="border-t border-border pt-6">
        <SignOutButton />
      </div>
    </div>
  );
}

function SignOutButton() {
  const { signOut } = useSession();
  const router = useRouter();
  return (
    <button type="button" onClick={async () => { await signOut(); router.push("/"); }}
            className="inline-flex h-11 items-center rounded-lg border border-plum bg-card px-5 font-semibold text-plum hover:bg-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
      Sign out
    </button>
  );
}

function AccountCard({ me }: { me: Me }) {
  const kind = me.demo_persona
    ? `Demo account (${me.demo_persona === "priya" ? "Priya" : "Arjun"}), private to this browser`
    : me.is_anonymous ? "Guest account" : me.is_demo ? "Demo seed account" : "Your account";
  return (
    <section aria-labelledby="account-heading" className="flex flex-col gap-1">
      <h2 id="account-heading" className="font-display text-3xl font-semibold">{me.display_name}</h2>
      <p className="text-muted-foreground">{kind}</p>
      <p><Link href="/orders" className={textLink}>Your orders</Link></p>
    </section>
  );
}

function PreferenceRow({ prefKey, title, saved, onChange }: {
  prefKey: PrefKey;
  title: string;
  saved: Saved | undefined;
  onChange: (key: PrefKey, value: string | number | null) => Promise<boolean>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const selectId = useId();
  const formRef = useRef<HTMLFormElement>(null);
  const mainButton = useRef<HTMLButtonElement>(null);
  const wasEditing = useRef(false);
  const hadSaved = useRef(Boolean(saved));

  // The buttons and the form swap places, so focus would fall to the page body: into the form's list on Change, back
  // to the Change/Set button after Save, Cancel or Forget.
  useEffect(() => {
    if (editing) formRef.current?.querySelector("select")?.focus();
    else if (wasEditing.current || (hadSaved.current && !saved)) mainButton.current?.focus();
    wasEditing.current = editing;
    hadSaved.current = Boolean(saved);
  }, [editing, saved]);
  const action = "inline-flex h-10 items-center rounded-lg border border-plum bg-card px-4 font-semibold text-plum hover:bg-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60";

  function startEditing() {
    setDraft(saved ? String(saved.value) : "");
    setEditing(true);
  }

  async function save() {
    if (draft === "") return;
    setBusy(true);
    const ok = await onChange(prefKey, prefKey === "max_spice" ? Number(draft) : draft);
    setBusy(false);
    if (ok) setEditing(false);
  }

  return (
    <li className="flex flex-col gap-3 px-4 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-sans text-base font-semibold">{title}</h3>
          <p>{saved ? saved.label.replace(/^Default delivery area: /, "") : <span className="text-muted-foreground">Not set</span>}</p>
          {saved ? <p className="text-sm text-muted-foreground">How it was saved: {saved.how_saved}.</p> : null}
        </div>
        {editing ? null : (
          <div className="flex gap-2">
            <button type="button" ref={mainButton} className={action} onClick={startEditing}>
              {saved ? "Change" : "Set"}<span className="sr-only"> {title.toLowerCase()}</span>
            </button>
            {saved ? (
              <button type="button" className={action} disabled={busy}
                      onClick={async () => { setBusy(true); await onChange(prefKey, null); setBusy(false); }}>
                Forget<span className="sr-only"> {title.toLowerCase()}</span>
              </button>
            ) : null}
          </div>
        )}
      </div>
      {editing ? (
        <form ref={formRef} className="flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); void save(); }}
              onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); setEditing(false); } }}>
          {prefKey === "default_area" ? (
            <AreaPicker value={draft} onChange={setDraft} label={title} focusWhenReady />
          ) : (
            <div className="flex flex-col gap-1.5">
              <label htmlFor={selectId} className="text-sm font-medium">{title}</label>
              <select id={selectId} value={draft} onChange={(e) => setDraft(e.target.value)}
                      className="h-11 min-w-56 rounded-lg border border-input bg-card px-3 text-base outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background">
                <option value="" disabled>Choose…</option>
                {CHOICES[prefKey].map((c) => <option key={c.value} value={String(c.value)}>{c.text}</option>)}
              </select>
            </div>
          )}
          <button type="submit" disabled={busy || draft === ""}
                  className="inline-flex h-11 items-center rounded-lg bg-plum px-5 font-semibold text-ivory focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60">
            {busy ? "Saving…" : "Save"}<span className="sr-only"> {title.toLowerCase()}</span>
          </button>
          <button type="button" className={action + " h-11"} onClick={() => setEditing(false)}>Cancel<span className="sr-only"> changing {title.toLowerCase()}</span></button>
        </form>
      ) : null}
    </li>
  );
}

function Addresses({ addresses }: { addresses: Address[] }) {
  return (
    <section aria-labelledby="addresses-heading" className="flex flex-col gap-3">
      <h2 id="addresses-heading" className="font-display text-3xl font-semibold">Addresses</h2>
      {addresses.length ? (
        <ul className="flex flex-col gap-3">
          {addresses.map((a) => (
            <li key={a.address_id} className="rounded-xl border border-border bg-card px-4 py-3">
              <p className="font-semibold">{a.label}{a.is_default ? <span className="ml-2 text-sm font-normal text-muted-foreground"><span className="sr-only">, </span>Default</span> : null}</p>
              <p>{a.line1}</p>
              <p className="text-sm text-muted-foreground">{a.area}</p>
            </li>
          ))}
        </ul>
      ) : <p>No saved addresses.</p>}
      <p className="text-sm text-muted-foreground">
        Adding addresses isn&apos;t available yet. You can deliver to any area: choose it in your cart.
      </p>
    </section>
  );
}
