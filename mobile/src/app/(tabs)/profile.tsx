import { useState } from 'react';
import { View } from 'react-native';
import { Screen } from '@/components/Screen';
import { AppText } from '@/components/AppText';
import { Avatar } from '@/components/Avatar';
import { Button } from '@/components/Button';
import { Chip } from '@/components/Chip';
import { AreaPicker } from '@/components/AreaPicker';
import { OsmCredit } from '@/components/OsmCredit';
import { Loading, ErrorBox } from '@/components/LoadState';
import { Card } from '@/components/BillParts';
import { useSession } from '@/lib/session';
import { useUserLoad } from '@/lib/userload';
import {
  PREF_KEYS,
  PREF_OPTIONS,
  PREF_TITLES,
  prefBody,
  prefPath,
  type Addresses,
  type Pref,
  type PrefKey,
  type Prefs,
} from '@/lib/account';
import { colors } from '@/theme/tokens';

type Answer = { status?: string; message?: string };

export default function Profile() {
  const { state, signOut, request } = useSession();
  const [busy, setBusy] = useState(false);
  const prefs = useUserLoad<Prefs>('/me/preferences', ['ok']);
  const addresses = useUserLoad<Addresses>('/me/addresses');
  const name = state.status === 'signedIn' ? state.me.display_name : '';

  // Settings saves are explicit (the user pressed a choice), so they go straight to the settings route. The body is
  // {value} only: no source, no user id. The server decides the rest; the list is re-read from the server afterwards.
  const change = async (key: PrefKey, value: string | number | null): Promise<string | null> => {
    const r =
      value === null
        ? await request<Answer>(prefPath(key), { method: 'DELETE' })
        : await request<Answer>(prefPath(key), { method: 'PUT', body: prefBody(value) });
    if (!r.ok) return r.message;
    if (r.data?.status && r.data.status !== 'ok') return r.data.message ?? "That didn't work. Please try again.";
    prefs.reload();
    return null;
  };

  return (
    <Screen>
      <AppText variant="display" weight={800} accessibilityRole="header">
        Profile
      </AppText>
      {name ? (
        <Card>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
            <Avatar name={name} />
            <View style={{ flex: 1 }}>
              <AppText variant="title" weight={700}>
                {name}
              </AppText>
              <AppText variant="caption" color={colors.muted}>
                Signed in with Google
              </AppText>
            </View>
          </View>
        </Card>
      ) : null}

      <AppText variant="title" weight={800} accessibilityRole="header">
        Saved preferences
      </AppText>
      <AppText variant="caption" color={colors.muted}>
        Dawat AI uses these when it plans and orders for you. It only saves one when you ask.
      </AppText>
      {prefs.status === 'loading' ? <Loading slow={prefs.slow} /> : null}
      {prefs.status === 'error' ? <ErrorBox message={prefs.message} onRetry={prefs.reload} /> : null}
      {prefs.status === 'ok'
        ? PREF_KEYS.map((key) => <PrefRow key={key} prefKey={key} saved={prefs.data.preferences?.[key]} change={change} />)
        : null}

      <AppText variant="title" weight={800} accessibilityRole="header">
        Addresses
      </AppText>
      {addresses.status === 'loading' ? <Loading slow={addresses.slow} /> : null}
      {addresses.status === 'error' ? <ErrorBox message={addresses.message} onRetry={addresses.reload} /> : null}
      {addresses.status === 'ok' && addresses.data.addresses.length === 0 ? <AppText color={colors.muted}>No saved addresses.</AppText> : null}
      {addresses.status === 'ok'
        ? addresses.data.addresses.map((a) => (
            <Card key={a.address_id}>
              <AppText weight={700}>
                {a.label}
                {a.is_default ? ' · Default' : ''}
              </AppText>
              <AppText>{a.line1}</AppText>
              <AppText variant="caption" color={colors.muted}>
                {a.area}
              </AppText>
            </Card>
          ))
        : null}
      {addresses.status === 'ok' ? (
        <AppText variant="caption" color={colors.muted}>
          Addresses cannot be edited in the app yet.
        </AppText>
      ) : null}

      <AppText variant="title" weight={800} accessibilityRole="header">
        About Dawat
      </AppText>
      <AppText variant="caption" color={colors.muted}>
        Dawat is a demo project. Menus, prices, orders and payments are simulated. Restaurant names and locations are from OpenStreetMap.
      </AppText>
      <OsmCredit />

      <Button
        label="Sign out"
        variant="secondary"
        loading={busy}
        onPress={async () => {
          setBusy(true);
          await signOut();
        }}
      />
    </Screen>
  );
}

/** One saved preference: what the server says is saved, how it was saved, and Edit / Forget. */
function PrefRow({ prefKey, saved, change }: { prefKey: PrefKey; saved: Pref | undefined; change: (k: PrefKey, v: string | number | null) => Promise<string | null> }) {
  const title = PREF_TITLES[prefKey];
  const [editing, setEditing] = useState(false);
  const [picking, setPicking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const run = async (value: string | number | null) => {
    setBusy(true);
    setProblem(null);
    const failed = await change(prefKey, value);
    setBusy(false);
    if (failed) setProblem(failed);
    else setEditing(false);
  };

  return (
    <Card>
      <AppText weight={700}>{title}</AppText>
      <AppText>{saved ? saved.label : 'Not saved'}</AppText>
      {saved ? (
        <AppText variant="caption" color={colors.muted}>
          Saved
        </AppText>
      ) : null}
      {editing && prefKey !== 'default_area' ? (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {PREF_OPTIONS[prefKey].map((o) => (
            <Chip key={String(o.value)} label={o.label} selected={saved?.value === o.value} onPress={() => void run(o.value)} />
          ))}
        </View>
      ) : null}
      {problem ? (
        <AppText color={colors.ink} accessibilityLiveRegion="polite">
          {problem}
        </AppText>
      ) : null}
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <Button
          label={editing && prefKey !== 'default_area' ? 'Cancel' : saved ? 'Edit' : 'Add'}
          accessibilityLabel={editing && prefKey !== 'default_area' ? `Cancel editing ${title}` : `${saved ? 'Edit' : 'Add'} ${title}`}
          variant="secondary"
          disabled={busy}
          onPress={() => {
            setProblem(null);
            if (prefKey === 'default_area') setPicking(true);
            else setEditing((e) => !e);
          }}
          style={{ flex: 1 }}
        />
        {saved ? (
          <Button label="Forget" accessibilityLabel={`Forget ${title}`} variant="secondary" loading={busy} onPress={() => void run(null)} style={{ flex: 1 }} />
        ) : null}
      </View>
      {prefKey === 'default_area' ? (
        <AreaPicker
          visible={picking}
          onClose={() => setPicking(false)}
          onPick={(a) => {
            setPicking(false);
            void run(a.name);
          }}
        />
      ) : null}
    </Card>
  );
}
