import { ActivityIndicator, View } from 'react-native';
import { AppText } from './AppText';
import { Button } from './Button';
import { Tile } from './Tile';
import { colors } from '@/theme/tokens';

/** Loading (with the cold-start message after 4 s), and error with a retry. Empty states are written by each screen. */
export function Loading({ slow }: { slow: boolean }) {
  return (
    <View style={{ alignItems: 'center', gap: 8, paddingVertical: 24 }} accessibilityLiveRegion="polite">
      <ActivityIndicator color={colors.navy} />
      <AppText weight={600}>{slow ? 'Waking up Dawat AI…' : 'Loading…'}</AppText>
      {slow ? (
        <AppText variant="caption" color={colors.muted} style={{ textAlign: 'center' }}>
          The free server sleeps when nobody uses it. This can take up to a minute.
        </AppText>
      ) : null}
    </View>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Tile fill="coralTint" title="Couldn't load this">
      <AppText accessibilityLiveRegion="polite">{message}</AppText>
      <Button label="Try again" onPress={onRetry} variant="secondary" style={{ marginTop: 8 }} />
    </Tile>
  );
}
