import type { ReactNode } from 'react';
import { Pressable, StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';
import { AppText } from './AppText';
import { MIN_TARGET, colors, radii, subtleTextOn, textOn, type FillName } from '@/theme/tokens';

type Props = {
  fill: FillName;
  title: string;
  subtitle?: string;
  /** Right-hand decoration, such as a round food placeholder. */
  accessory?: ReactNode;
  children?: ReactNode;
  onPress?: () => void;
  accessibilityLabel?: string;
  style?: StyleProp<ViewStyle>;
};

/** A bento tile. Text colour comes from the fill, so contrast is decided in one place (tokens.ts). */
export function Tile({ fill, title, subtitle, accessory, children, onPress, accessibilityLabel, style }: Props) {
  const body = (
    <View style={styles.row}>
      <View style={styles.text}>
        <AppText variant="title" weight={700} color={textOn(fill)}>
          {title}
        </AppText>
        {subtitle ? (
          <AppText variant="caption" weight={500} color={subtleTextOn(fill)}>
            {subtitle}
          </AppText>
        ) : null}
        {children}
      </View>
      {accessory}
    </View>
  );
  const box = [styles.tile, { backgroundColor: colors[fill] }, style];
  if (!onPress) return <View style={box}>{body}</View>;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? (subtitle ? `${title}. ${subtitle}` : title)}
      onPress={onPress}
      style={({ pressed }) => [...box, pressed && styles.pressed]}
    >
      {body}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  tile: { borderRadius: radii.lg, padding: 16, minHeight: MIN_TARGET * 2 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  text: { flex: 1, gap: 4 },
  pressed: { opacity: 0.88 },
});
