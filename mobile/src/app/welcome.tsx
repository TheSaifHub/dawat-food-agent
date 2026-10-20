import { useState } from 'react';
import { View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Screen } from '@/components/Screen';
import { Wordmark } from '@/components/Wordmark';
import { AppText } from '@/components/AppText';
import { Tile } from '@/components/Tile';
import { Button } from '@/components/Button';
import { useSession } from '@/lib/session';
import { colors } from '@/theme/tokens';

export default function Welcome() {
  const { state } = useSession();
  const [message, setMessage] = useState<string | null>(null);
  const notice = state.status === 'signedOut' ? state.notice : undefined;
  // The local dev login: one inline build-time condition, so Metro removes this branch (and the module it requires)
  // from every release build. Do not move the condition into a helper: the release scan relies on it being inline.
  const DevLogin: (() => React.ReactElement) | null =
    __DEV__ && process.env.EXPO_PUBLIC_DAWAT_DEV_LOGIN === '1'
      // eslint-disable-next-line @typescript-eslint/no-require-imports -- on purpose: the dev login panel is left out of any build where the switch is off
      ? require('@/components/DevLoginPanel').DevLoginPanel
      : null;

  return (
    <Screen>
      <Wordmark />
      <Tile fill="sky" title="Order by talking. Done when you say yes." subtitle="Tell Dawat what you're craving. Review your choices before ordering." />
      <Tile fill="sage" title="Nothing is ordered until you say yes.">
        <AppText>మీరు చెప్పే వరకు ఏది ఆర్డర్ కాదు.</AppText>
      </Tile>
      {notice ? (
        <AppText accessibilityLiveRegion="polite" weight={600}>
          {notice}
        </AppText>
      ) : null}
      {DevLogin ? (
        <DevLogin />
      ) : (
        <View style={{ gap: 8 }}>
          <Button
            label="Continue with Google"
            onPress={() => setMessage("Google sign-in isn't set up yet. It arrives with the deployed app.")}
          />
          {message ? (
            <AppText variant="caption" accessibilityLiveRegion="polite">
              {message}
            </AppText>
          ) : null}
        </View>
      )}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
        <Ionicons name="information-circle-outline" size={16} color={colors.muted} />
        <AppText variant="caption" color={colors.muted} style={{ flex: 1 }}>
          Menus, prices and orders are simulated.
        </AppText>
      </View>
    </Screen>
  );
}
