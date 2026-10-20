import type { ReactNode } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { DemoBanner } from './DemoBanner';
import { AppText } from './AppText';
import { colors } from '@/theme/tokens';

/** Every screen sits in this: safe areas, the demo banner, a "Local data" badge in dev. */
export function Screen({ children, scroll = true }: { children: ReactNode; scroll?: boolean }) {
  const insets = useSafeAreaInsets();
  // Screens without the tab bar (menu, review, payment) have nothing under them, so keep clear of the gesture / button bar.
  const content = [styles.content, { paddingBottom: Math.max(32, insets.bottom + 16) }];
  return (
    <SafeAreaView style={styles.root} edges={['top', 'left', 'right']}>
      <DemoBanner />
      {__DEV__ ? (
        <View style={styles.local} accessible accessibilityLabel="Local development: local data">
          <AppText variant="caption" weight={600} color={colors.white}>
            Local data
          </AppText>
        </View>
      ) : null}
      {scroll ? <ScrollView contentContainerStyle={content}>{children}</ScrollView> : <View style={[content, { flex: 1 }]}>{children}</View>}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.page },
  content: { padding: 16, paddingBottom: 32, gap: 12 },
  local: { alignSelf: 'flex-end', backgroundColor: colors.navy, paddingHorizontal: 10, paddingVertical: 3, marginTop: 6, marginRight: 12, borderRadius: 999 },
});
