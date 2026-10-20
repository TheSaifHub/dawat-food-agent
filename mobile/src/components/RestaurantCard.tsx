import { Pressable, View } from 'react-native';
import { AppText } from './AppText';
import { FoodPlaceholder } from './FoodPlaceholder';
import { MIN_TARGET, colors, radii } from '@/theme/tokens';
import type { RestaurantCardData } from '@/lib/browse';

/** Everything on the card is the backend's own value: distance, fee and typical price are never computed here. */
export function cardSummary(r: RestaurantCardData): string {
  const km = r.branch.distance_km;
  const parts = [km < 0.1 ? 'Under 0.1 km' : `${km} km`, r.delivery_fee === 0 ? 'Free delivery' : `Delivery ₹${r.delivery_fee}`];
  if (r.price_for_one !== null) parts.push(`Typical main ₹${r.price_for_one}`);
  return parts.join(' · ');
}

export function RestaurantCard({ r, onPress }: { r: RestaurantCardData; onPress?: () => void }) {
  const more = r.more_branches_in_range > 0 ? `${r.more_branches_in_range} more branches nearby` : null;
  const label = [r.name, r.veg_only ? 'Vegetarian only' : null, r.cuisines.join(', '), r.branch.label, cardSummary(r), more]
    .filter(Boolean)
    .join('. ');
  return (
    <Pressable
      accessible
      accessibilityRole={onPress ? 'button' : undefined}
      accessibilityLabel={onPress ? `${label}. Open menu` : label}
      onPress={onPress}
      disabled={!onPress}
      style={{ minHeight: MIN_TARGET, flexDirection: 'row', gap: 12, backgroundColor: colors.card, borderRadius: radii.md, padding: 12, alignItems: 'center' }}
    >
      <FoodPlaceholder name={r.name} />
      <View style={{ flex: 1, gap: 2 }}>
        <AppText weight={700}>{r.name}</AppText>
        <AppText variant="caption" color={colors.muted}>
          {r.cuisines.join(' · ')} · {r.branch.label}
        </AppText>
        <AppText variant="caption" weight={600}>
          {cardSummary(r)}
        </AppText>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
          {r.veg_only ? <Badge text="Veg only" fill={colors.sage} /> : null}
          {r.mild_friendly ? <Badge text="Mild options" fill={colors.butter} /> : null}
          {more ? <Badge text={more} fill={colors.sky} /> : null}
        </View>
      </View>
    </Pressable>
  );
}

function Badge({ text, fill }: { text: string; fill: string }) {
  return (
    <View style={{ backgroundColor: fill, borderRadius: radii.md, paddingHorizontal: 12, paddingVertical: 6 }}>
      <AppText variant="caption" weight={700} color={colors.ink}>
        {text}
      </AppText>
    </View>
  );
}
