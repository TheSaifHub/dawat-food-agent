import { View } from 'react-native';
import { AppText } from './AppText';
import { colors } from '@/theme/tokens';

/** Round initial avatar (the design has no photo). Ink on sage is allowed; the label is hidden from screen readers
 *  because the name is read next to it. */
export function Avatar({ name, size = 56 }: { name: string; size?: number }) {
  const initial = (name.trim()[0] ?? '?').toUpperCase();
  return (
    <View
      testID="avatar"
      importantForAccessibility="no-hide-descendants"
      accessibilityElementsHidden
      style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: colors.sage, alignItems: 'center', justifyContent: 'center' }}
    >
      <AppText variant="title" weight={700}>
        {initial}
      </AppText>
    </View>
  );
}
