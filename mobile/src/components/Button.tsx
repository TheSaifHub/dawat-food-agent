import { ActivityIndicator, Pressable, StyleSheet, type StyleProp, type ViewStyle } from 'react-native';
import { AppText } from './AppText';
import { MIN_TARGET, colors, radii } from '@/theme/tokens';

type Props = {
  label: string;
  onPress: () => void;
  /** primary = navy with white text (the only call-to-action fill; white on coral fails contrast). */
  variant?: 'primary' | 'secondary';
  disabled?: boolean;
  loading?: boolean;
  accessibilityLabel?: string;
  style?: StyleProp<ViewStyle>;
};

export function Button({ label, onPress, variant = 'primary', disabled, loading, accessibilityLabel, style }: Props) {
  const primary = variant === 'primary';
  const inactive = disabled || loading;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityState={{ disabled: !!inactive, busy: !!loading }}
      disabled={inactive}
      onPress={onPress}
      style={({ pressed }) => [
        styles.base,
        primary ? styles.primary : styles.secondary,
        inactive && styles.inactive,
        pressed && styles.pressed,
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={primary ? colors.white : colors.navy} />
      ) : (
        <AppText weight={700} color={primary ? colors.white : colors.navy}>
          {label}
        </AppText>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: 52, // above the 44pt minimum
    minWidth: MIN_TARGET,
    paddingHorizontal: 24,
    paddingVertical: 10, // wrapped text at large text sizes must not touch the border
    borderRadius: radii.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primary: { backgroundColor: colors.navy },
  secondary: { backgroundColor: colors.card, borderWidth: 1.5, borderColor: colors.navy },
  inactive: { opacity: 0.55 },
  pressed: { opacity: 0.85 },
});
