'use client';

import React, { useEffect, useId, useState } from 'react';
import { useRouter } from 'next/navigation';
import { DawatLogo } from '@/components/DawatLogo';
import { api } from '@/lib/api';
import { accessToken } from '@/lib/auth';
import { useSession } from '@/lib/session';
import { ArrowRight, User } from 'lucide-react';

const NAME_MAX = 60;

export default function ConfirmNamePage() {
  const router = useRouter();
  const { session, refresh } = useSession();
  const nameId = useId();
  const me = session.state === 'signed_in' ? session.me : null;
  const accountName = me?.account_name ?? '';
  const [edited, setEdited] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const value = edited ?? accountName;

  // Signed out → sign in first. Already confirmed (a returning user) → straight to the home page.
  useEffect(() => {
    if (session.state === 'signed_out') router.replace('/login');
    else if (me?.name_confirmed) router.replace('/');
  }, [session.state, me, router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    // Unchanged → "keep": the backend then uses the name from the verified Google token. Changed → the new name,
    // which the backend trims and validates. The browser never sends a user id.
    const changed = edited !== null && edited.trim() !== accountName;
    const res = await api('/me/name', {
      method: 'POST',
      body: changed ? { name: edited } : {},
      token: await accessToken(),
    });
    if (!res.ok) {
      setBusy(false);
      setError(res.message);
      return;
    }
    await refresh();
    router.replace('/');
  }

  if (!me || me.name_confirmed) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 font-sans">
        <p role="status" className="text-center text-xs text-[#574652]">Loading…</p>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 font-sans">
      <div className="max-w-md mx-auto space-y-8">
        <div className="text-center space-y-3">
          <div className="flex justify-center">
            <DawatLogo variant="full" size="lg" />
          </div>
          <h1 className="font-serif text-3xl font-bold text-[#22161F] pt-2">Confirm your name</h1>
          <p className="text-xs sm:text-sm text-[#574652] leading-relaxed">
            {accountName ? (
              <>
                Your Google account name is <strong>{accountName}</strong>. Keep it, or change it?
              </>
            ) : (
              <>Your Google account didn&apos;t share a name. What should Dawat call you?</>
            )}
          </p>
        </div>

        {error && (
          <div role="alert" className="p-3.5 rounded-xl bg-[#C0392B]/10 border border-[#C0392B]/30 text-[#C0392B] text-xs font-semibold">
            {error}
          </div>
        )}

        <div className="bg-white rounded-3xl border border-[#EADFCF] p-6 shadow-xs space-y-4">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor={nameId} className="block text-xs font-semibold text-[#574652] mb-1.5">
                Your name
              </label>
              <div className="relative">
                <User className="w-4 h-4 text-[#877682] absolute left-3.5 top-1/2 -translate-y-1/2" aria-hidden="true" />
                <input
                  id={nameId}
                  type="text"
                  value={value}
                  onChange={(e) => setEdited(e.target.value)}
                  maxLength={NAME_MAX}
                  required
                  autoComplete="name"
                  className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-[#EADFCF] bg-[#FAF6EF]/50 text-xs sm:text-sm text-[#22161F] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#5B1E4E] min-h-[44px]"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={busy}
              className="w-full py-3 rounded-xl bg-[#5B1E4E] text-[#FAF6EF] hover:bg-[#3F1436] font-semibold text-xs tracking-wider uppercase transition-all min-h-[44px] flex items-center justify-center gap-2 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#5B1E4E]"
            >
              <span>{busy ? 'Please wait…' : 'Continue'}</span>
              <ArrowRight className="w-4 h-4 text-[#FAF6EF]" aria-hidden="true" />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
