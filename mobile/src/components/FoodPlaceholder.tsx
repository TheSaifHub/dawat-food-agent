import { View } from 'react-native';
import { AppText } from './AppText';
import { colors } from '@/theme/tokens';

const FILLS = [colors.sky, colors.butter, colors.sage] as const;

/** A round food-photo placeholder (no photos in v1): the restaurant's initial on a soft fill. Decorative. */
export function FoodPlaceholder({ name, size = 56 }: { name: string; size?: number }) {
  const initial = (name.trim()[0] ?? '?').toUpperCase();
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) % 997;
  return (
    <View
      importantForAccessibility="no-hide-descendants"
      accessibilityElementsHidden
      style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: FILLS[h % FILLS.length], alignItems: 'center', justifyContent: 'center' }}
    >
      <AppText variant="title" weight={800} color={colors.ink}>
        {initial}
      </AppText>
    </View>
  );
}
