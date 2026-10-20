import { StyleSheet, Text, View } from 'react-native';
import { AppText } from './AppText';
import { colors, fontFamilies } from '@/theme/tokens';

/** The lowercase "dawat" wordmark with "Food, your way" under it, as in the design. */
export function Wordmark({ size = 40 }: { size?: number }) {
  return (
    <View accessible accessibilityRole="header" accessibilityLabel="Dawat. Food, your way.">
      <Text style={[styles.mark, { fontSize: size, lineHeight: Math.round(size * 1.15) }]}>dawat</Text>
      <AppText variant="caption" weight={600} color={colors.muted}>
        Food, your way
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  mark: { fontFamily: fontFamilies.wordmark, color: colors.navy, letterSpacing: -0.5 },
});
