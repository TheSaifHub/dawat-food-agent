// LOCAL-ONLY sign-in buttons (D-059). Imported ONLY from inside the inline build-time condition in app/welcome.tsx
// (`__DEV__ && process.env.EXPO_PUBLIC_DAWAT_DEV_LOGIN === '1'`), so a release build never contains this file.
// `npm run check:release` fails if the marker below, or the route it calls, appears in a release bundle.
// The marker string: dawat-dev-login-marker

import { useState } from 'react';
import { View } from 'react-native';
import { AppText } from './AppText';
import { Button } from './Button';
import { api } from '@/lib/api';
import { useSession } from '@/lib/session';
import { colors } from '@/theme/tokens';

type Grant = { access_token: string };

export function DevLoginPanel() {
  const { signInWithToken } = useSession();
  const [busy, setBusy] = useState<'same' | 'new' | 'seed' | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function go(newUser: boolean) {
    setBusy(newUser ? 'new' : 'same');
    setError(null);
    const r = await api<Grant>('/dev/auth/google', { method: 'POST', body: newUser ? { new_user: true } : {}, timeoutMs: 20_000 });
    if (!r.ok) {
      setBusy(null);
      return setError(r.message);
    }
    const out = await signInWithToken(r.data.access_token);
    if (!out.ok) setError(out.message);
    setBusy(null);
  }

  /** A seeded demo user (has a saved address and orders), to test the saved-address chips. */
  async function goSeed() {
    setBusy('seed');
    setError(null);
    const list = await api<{ users: { user_id: string; display_name: string }[] }>('/dev/auth/users', { timeoutMs: 20_000 });
    const pick = list.ok ? (list.data.users.find((u) => u.display_name.includes('Priya')) ?? list.data.users[0]) : undefined;
    if (!pick) {
      setBusy(null);
      return setError(list.ok ? 'No seed users in the local database.' : list.message);
    }
    const r = await api<Grant>('/dev/auth/seed-user', { method: 'POST', body: { user_id: pick.user_id }, timeoutMs: 20_000 });
    if (!r.ok) {
      setBusy(null);
      return setError(r.message);
    }
    const out = await signInWithToken(r.data.access_token);
    if (!out.ok) setError(out.message);
    setBusy(null);
  }

  return (
    <View style={{ gap: 8 }}>
      <Button label="Local sign-in (dev only)" onPress={() => go(false)} loading={busy === 'same'} disabled={busy !== null} />
      <Button
        label="New fake user (dev only)"
        variant="secondary"
        onPress={() => go(true)}
        loading={busy === 'new'}
        disabled={busy !== null}
        accessibilityLabel="New fake user, to test the first-time name screen. Dev only."
      />
      <Button
        label="Seed user with address (dev only)"
        variant="secondary"
        onPress={goSeed}
        loading={busy === 'seed'}
        disabled={busy !== null}
        accessibilityLabel="Sign in as a seeded demo user with a saved address. Dev only."
      />
      {error ? (
        <AppText variant="caption" color={colors.ink} accessibilityLiveRegion="polite">
          {error}
        </AppText>
      ) : null}
    </View>
  );
}
