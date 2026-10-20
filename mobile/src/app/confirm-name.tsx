import { useState } from 'react';
import { TextInput, View } from 'react-native';
import { Screen } from '@/components/Screen';
import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { useSession } from '@/lib/session';
import { colors, fontFamilies, radii } from '@/theme/tokens';

const MAX = 60;

/** First sign-in only (name_confirmed is false). The name is the user's to keep or change; the backend validates it too. */
export default function ConfirmName() {
  const { state, confirmName } = useSession();
  const account = state.status === 'signedIn' ? state.me.account_name ?? '' : '';
  const [name, setName] = useState(account);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trimmed = name.trim();
  const changed = trimmed !== account.trim();
  const tooLong = trimmed.length > MAX;
  const valid = trimmed.length > 0 && !tooLong;

  async function submit() {
    if (!valid || busy) return;
    setBusy(true);
    setError(null);
    // Unchanged: send nothing, so the backend keeps the account name it read from the token.
    const out = await confirmName(changed ? trimmed : null);
    if (!out.ok) setError(out.message);
    setBusy(false);
  }

  return (
    <Screen>
      <AppText variant="display" weight={800}>
        Confirm your name
      </AppText>
      <AppText color={colors.muted}>This is how Dawat will greet you. You can change it now.</AppText>
      <View>
        <AppText variant="caption" weight={600}>
          Your name
        </AppText>
        <TextInput
          value={name}
          onChangeText={setName}
          accessibilityLabel="Your name"
          autoCapitalize="words"
          autoCorrect={false}
          maxLength={MAX + 10}
          editable={!busy}
          onSubmitEditing={submit}
          returnKeyType="done"
          style={{
            minHeight: 52,
            borderRadius: radii.pill,
            borderWidth: 1.5,
            borderColor: colors.navy,
            backgroundColor: colors.card,
            paddingHorizontal: 20,
            color: colors.ink,
            fontFamily: fontFamilies.ui[500],
            fontSize: 16,
          }}
        />
      </View>
      {tooLong ? <AppText variant="caption">Please use 60 characters or fewer.</AppText> : null}
      {error ? (
        <AppText variant="caption" accessibilityLiveRegion="polite">
          {error}
        </AppText>
      ) : null}
      <Button label={changed ? 'Use this name' : 'Looks right'} onPress={submit} disabled={!valid} loading={busy} />
    </Screen>
  );
}
