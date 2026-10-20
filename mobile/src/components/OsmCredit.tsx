import { AppText } from './AppText';
import { colors } from '@/theme/tokens';

/** Required on every screen that shows restaurant data or a map (CLAUDE.md, ODbL). */
export function OsmCredit() {
  return (
    <AppText variant="caption" color={colors.muted} style={{ textAlign: 'center' }}>
      © OpenStreetMap contributors
    </AppText>
  );
}
