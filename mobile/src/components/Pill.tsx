import { StyleSheet, View } from 'react-native';
import { AppText } from './AppText';
import { colors, radii } from '@/theme/tokens';

type Props = {
  label: string;
  /** A small colour dot tells "Best match" / "Best value" / "Variety" apart; the words do the real work. */
  dot?: 'accent' | 'sky' | 'butter';
};

/** Small label pill: navy with white text (12.4:1). Replaces the design's low-contrast white-on-colour pills. */
export function Pill({ label, dot }: Props) {
  return (
    <View style={styles.pill} accessible accessibilityLabel={label}>
      {dot ? <View style={[styles.dot, { backgroundColor: colors[dot] }]} /> : null}
      <AppText variant="caption" weight={700} color={colors.white}>
        {label}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: 6,
    backgroundColor: colors.navy,
    borderRadius: radii.pill,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  dot: { width: 8, height: 8, borderRadius: 4 },
});
