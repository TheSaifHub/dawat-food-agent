import { useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { AppText } from './AppText';
import { checkHealth, type Health } from '@/lib/health';
import { colors } from '@/theme/tokens';

const TEXT: Record<Health, string> = {
  checking: 'Checking Dawat AI…',
  waking: 'Waking up Dawat AI…',
  ok: 'Backend connected',
  down: "Can't reach Dawat AI. Check that the backend is running and the USB link is set up.",
};

/** Calls GET /health once. Dot colour is never the only signal: the words say the state. */
export function BackendStatus() {
  const [state, setState] = useState<Health>('checking');
  useEffect(() => {
    let live = true;
    checkHealth(() => live && setState((s) => (s === 'checking' ? 'waking' : s))).then((r) => live && setState(r));
    return () => {
      live = false;
    };
  }, []);
  return (
    <View style={styles.row} accessibilityLiveRegion="polite">
      <View style={[styles.dot, { backgroundColor: state === 'ok' ? colors.sage : state === 'down' ? colors.accent : colors.butter }]} />
      <AppText variant="caption" weight={500} color={colors.muted} style={styles.text}>
        {TEXT[state]}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  dot: { width: 10, height: 10, borderRadius: 5, borderWidth: 1, borderColor: colors.navy },
  text: { flex: 1 },
});
