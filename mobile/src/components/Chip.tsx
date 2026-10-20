import { Pressable } from 'react-native';
import { AppText } from './AppText';
import { MIN_TARGET, colors, radii } from '@/theme/tokens';

/** A filter chip. Selected = navy with white text; not selected = white with a navy outline. 44pt tall. */
export function Chip({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      accessibilityLabel={label}
      onPress={onPress}
      style={{
        minHeight: MIN_TARGET,
        paddingHorizontal: 16,
        paddingVertical: 8, // wrapped text at large sizes must not touch the border
        justifyContent: 'center',
        borderRadius: radii.pill,
        backgroundColor: selected ? colors.navy : colors.card,
        borderWidth: 1.5,
        borderColor: colors.navy,
      }}
    >
      <AppText weight={600} color={selected ? colors.white : colors.navy}>
        {label}
      </AppText>
    </Pressable>
  );
}
