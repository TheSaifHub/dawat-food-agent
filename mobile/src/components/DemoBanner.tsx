import { StyleSheet, View } from 'react-native';
import { AppText } from './AppText';
import { colors } from '@/theme/tokens';

export const DEMO_BANNER_TEXT =
  'Demo project. Menus, prices and orders are simulated. Not affiliated with any restaurant.';

/** Shown on every screen (CLAUDE.md, Data rules). Ink on butter is 13.95:1. */
export function DemoBanner() {
  return (
    <View style={styles.banner} accessible accessibilityRole="text">
      <AppText variant="caption" weight={600} style={styles.text}>
        {DEMO_BANNER_TEXT}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: { backgroundColor: colors.butter, paddingHorizontal: 16, paddingVertical: 6 },
  text: { textAlign: 'center' },
});
