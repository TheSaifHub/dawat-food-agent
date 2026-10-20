'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { DawatLogo } from '@/components/DawatLogo';
import { authConfigured, signInWithGoogle } from '@/lib/auth';
import { useSession } from '@/lib/session';
import { ArrowRight, ShieldCheck } from 'lucide-react';

// Local dev mode only (npm run dev:local): a second, small link that signs in as a brand-new fake Google user, to
// see the first-time "Confirm your name" screen again. The inline condition lets the bundler drop it from production.
const LOCAL_DEV = process.env.NODE_ENV === 'development' && process.env.NEXT_PUBLIC_DAWAT_DEV_LOGIN === '1';

export default function LoginPage() {
  const router = useRouter();
  const { session, refresh } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const me = session.state === 'signed_in' ? session.me : null;

  // A confirmed user has nothing to do here (this is also where Google sends people back to). An unconfirmed one is
  // sent to the "Confirm your name" screen by the site-wide gate.
  useEffect(() => {
    if (me?.name_confirmed) router.replace('/');
  }, [me, router]);

  async function continueWithGoogle(newLocalUser = false) {
    setBusy(true);
    setError(null);
    const { error: err } = await signInWithGoogle({ newLocalUser });
    if (err) {
      setBusy(false);
      setError("Couldn't start Google sign-in right now. Please try again.");
      return;
    }
    if (LOCAL_DEV) {
      // The local fake Google user signs in without leaving the page.
      const next = await refresh();
      setBusy(false);
      if (next.state !== 'signed_in') setError("Signed in, but Dawat couldn't load your profile. Please try again.");
    }
    // In production the browser is now on its way to Google and comes back to this page.
  }

  if (!authConfigured) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 font-sans">
        <div className="max-w-md mx-auto space-y-8 text-center">
          <div className="flex justify-center">
            <DawatLogo variant="full" size="lg" />
          </div>
          <p role="alert" className="p-4 rounded-2xl border border-[#EADFCF] bg-white text-sm text-[#574652]">
            Sign-in isn&apos;t configured on this copy of Dawat. You can still browse restaurants and menus freely.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 font-sans">
      <div className="max-w-md mx-auto space-y-8">
        {/* Brand Emblem & Welcome */}
        <div className="text-center space-y-3">
          <div className="flex justify-center">
            <DawatLogo variant="full" size="lg" />
          </div>
          <h1 className="font-serif text-3xl font-bold text-[#22161F] pt-2">
            Welcome to the Dastarkhwan
          </h1>
          <p className="text-xs sm:text-sm text-[#574652] leading-relaxed">
            Sign in with your Google account to experience customized Nizami recommendations.
          </p>
        </div>

        {me && (
          <div className="p-3.5 rounded-xl bg-[#5B1E4E]/10 border border-[#5B1E4E]/20 text-[#5B1E4E] text-xs font-semibold">
            You are signed in as <strong>{me.display_name}</strong>.
          </div>
        )}

        {error && (
          <div role="alert" className="p-3.5 rounded-xl bg-[#C0392B]/10 border border-[#C0392B]/30 text-[#C0392B] text-xs font-semibold">
            {error}
          </div>
        )}

        <div className="bg-white rounded-3xl border border-[#EADFCF] p-6 shadow-xs space-y-4">
          <button
            type="button"
            disabled={busy}
            onClick={() => void continueWithGoogle()}
            className="w-full py-3 rounded-xl bg-[#5B1E4E] text-[#FAF6EF] hover:bg-[#3F1436] font-semibold text-xs tracking-wider uppercase transition-all min-h-[44px] flex items-center justify-center gap-2 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#5B1E4E]"
          >
            <span>{busy ? 'Please wait…' : 'Continue with Google'}</span>
            <ArrowRight className="w-4 h-4 text-[#FAF6EF]" aria-hidden="true" />
          </button>

          {LOCAL_DEV && (
            <button
              type="button"
              disabled={busy}
              onClick={() => void continueWithGoogle(true)}
              className="w-full text-[11px] text-[#5B1E4E] underline underline-offset-2 hover:text-[#3F1436] font-medium min-h-[44px] disabled:opacity-50"
            >
              Local test: sign in as a brand-new fake Google user
            </button>
          )}

          <div className="pt-2 flex items-center justify-center gap-1.5 text-[11px] text-[#574652]">
            <ShieldCheck className="w-3.5 h-3.5 text-[#2E7D32]" aria-hidden="true" />
            <span>Secure authentication &bull; Tokens stored locally</span>
          </div>
        </div>
      </div>
    </div>
  );
}
