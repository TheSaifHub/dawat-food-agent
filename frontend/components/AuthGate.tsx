'use client';

// Until a signed-in user has confirmed their name, every page except /confirm-name sends them there. A website
// flow only: the backend never needs the flag for orders, cart or chat (D-064).

import React, { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useSession } from '@/lib/session';

export const CONFIRM_PATH = '/confirm-name';

export function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { session } = useSession();

  const mustConfirm = session.state === 'signed_in' && !session.me.name_confirmed && pathname !== CONFIRM_PATH;

  useEffect(() => {
    if (mustConfirm) router.replace(CONFIRM_PATH);
  }, [mustConfirm, router]);

  // Don't flash the page the user is about to be sent away from.
  return mustConfirm ? null : <>{children}</>;
}
