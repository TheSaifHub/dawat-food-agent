import { View } from 'react-native';
import { AppText } from './AppText';
import { colors, radii } from '@/theme/tokens';
import { Button } from './Button';
import type { Cart, CartBranch } from '@/lib/cart';

/** A label and a rupee amount the backend sent. Nothing here adds anything up. */
export function BillRow({ label, value, bold, onDark }: { label: string; value: string; bold?: boolean; onDark?: boolean }) {
  const color = onDark ? colors.white : colors.ink;
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12 }} accessible accessibilityLabel={`${label}: ${value}`}>
      <AppText weight={bold ? 700 : 400} color={color}>
        {label}
      </AppText>
      <AppText weight={bold ? 700 : 600} color={color}>
        {value}
      </AppText>
    </View>
  );
}

export const rupees = (n: number | null | undefined): string => (n === null || n === undefined ? '—' : `₹${n}`);

/** The bill for one restaurant, exactly as the server computed it. A figure the server didn't send is left out. */
export function BranchBill({ b }: { b: CartBranch }) {
  return (
    <View style={{ gap: 6, borderTopWidth: 1, borderTopColor: colors.surface, paddingTop: 10 }}>
      <BillRow label="Items" value={rupees(b.items_total)} />
      {b.delivery_fee !== undefined ? <BillRow label={b.free_delivery ? 'Delivery (free)' : 'Delivery'} value={b.free_delivery ? '₹0' : rupees(b.delivery_fee)} /> : null}
      {b.taxes !== undefined ? <BillRow label="GST" value={rupees(b.taxes)} /> : null}
      {b.total !== undefined ? <BillRow label="Restaurant total" value={rupees(b.total)} bold /> : null}
      {!b.free_delivery && b.add_for_free_delivery ? (
        <AppText variant="caption" color={colors.muted}>
          Add ₹{b.add_for_free_delivery} more food for free delivery.
        </AppText>
      ) : null}
    </View>
  );
}

export function Card({ children }: { children: React.ReactNode }) {
  return <View style={{ backgroundColor: colors.card, borderRadius: radii.md, padding: 14, gap: 10 }}>{children}</View>;
}

export function TotalTile({ total, label = 'Total' }: { total: number | null; label?: string }) {
  return (
    <View style={{ backgroundColor: colors.navy, borderRadius: radii.lg, padding: 16 }}>
      <BillRow label={label} value={rupees(total)} bold onDark />
    </View>
  );
}

/**
 * Where this cart is delivered, in plain large words. If the user is browsing a different area, it says so (the cart
 * keeps its own delivery point until the user changes it). `onSwitch` adds a one-tap "Deliver to <browsed area>".
 */
export function DeliveryInfo({
  delivery,
  browsed,
  onSwitch,
  busy,
  hint,
}: {
  delivery: Cart['delivery'];
  browsed: { area_id: string; name: string } | null;
  onSwitch?: () => void;
  busy?: boolean;
  hint?: string;
}) {
  const differs = !!(delivery && browsed && delivery.area_id !== browsed.area_id);
  return (
    <Card>
      <AppText weight={700} color={colors.muted}>
        Delivering to
      </AppText>
      <AppText variant="title" weight={800} accessibilityLabel={delivery ? `Delivering to ${delivery.area}` : 'No delivery area yet'}>
        {delivery ? `${delivery.address_label ? `${delivery.address_label} · ` : ''}${delivery.area}` : 'No delivery area yet'}
      </AppText>
      {differs && browsed && delivery ? (
        <View style={{ backgroundColor: colors.coralTint, borderRadius: radii.sm, padding: 10, gap: 8 }} accessibilityLiveRegion="polite">
          <AppText weight={600}>
            You are browsing {browsed.name}, but this cart delivers to {delivery.area}.{hint ? ` ${hint}` : ''}
          </AppText>
          {onSwitch ? <Button label={`Deliver to ${browsed.name}`} variant="secondary" onPress={onSwitch} loading={busy} /> : null}
        </View>
      ) : null}
    </Card>
  );
}
