"use client";

// The LOCAL dev login's sign-in section (D-059): sign in as a seed user. Loaded only by LoginPanel under the inline
// build-time condition, so it is never part of a production build.

import { useEffect, useState } from "react";

import type { Busy } from "@/components/auth/LoginPanel";
import { Button } from "@/components/ui/button";
import { devSeedUsers, devSignInSeedUser } from "@/lib/auth";

/** Local development only (D-059; never in a production build, see lib/auth.ts): sign in as a seed user. */
export default function DevSignIn({ busy, setBusy, setError, onSignedIn }: {
  busy: Busy;
  setBusy: (b: Busy) => void;
  setError: (e: string | null) => void;
  onSignedIn: () => Promise<void>;
}) {
  const [users, setUsers] = useState<{ user_id: string; display_name: string }[] | null | undefined>(undefined);

  useEffect(() => {
    let live = true;
    void devSeedUsers().then((u) => { if (live) setUsers(u); });
    return () => { live = false; };
  }, []);

  async function signIn(userId: string) {
    setBusy("email");
    setError(null);
    const ok = await devSignInSeedUser(userId);
    setBusy(null);
    if (ok) await onSignedIn();
    else setError("Couldn't sign in. Is the backend running in local mode (dev_server.py start)?");
  }

  return (
    <section aria-labelledby="dev-heading" className="flex flex-col gap-4 border-t border-border pt-8">
      <div>
        <h2 id="dev-heading" className="font-display text-2xl font-semibold text-plum">Local development sign-in</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Local data only. Email sign-in uses Supabase, so it&apos;s off in this mode.
        </p>
      </div>
      {users === undefined ? <p>Loading the seed users…</p> : users === null ? (
        <p role="alert" className="text-destructive">The backend has no local dev sign-in. Start it with dev_server.py start.</p>
      ) : (
        <ul className="flex flex-wrap gap-3">
          {users.map((u) => (
            <li key={u.user_id}>
              <Button variant="outline" className="h-11 border-input" disabled={busy !== null} onClick={() => void signIn(u.user_id)}>
                Sign in as {u.display_name}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
