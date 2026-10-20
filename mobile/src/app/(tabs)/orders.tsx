import { Pressable, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Screen } from '@/components/Screen';
import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { Pill } from '@/components/Pill';
import { Tile } from '@/components/Tile';
import { Loading, ErrorBox } from '@/components/LoadState';
import { Card, rupees } from '@/components/BillParts';
import { ORDERS_LIMIT, orderHref, orderRows, placedLabel, statusLabel, type History, type OrderRow } from '@/lib/account';
import { useUserLoad } from '@/lib/userload';
import { MIN_TARGET, colors } from '@/theme/tokens';

/** The signed-in user's orders, newest first, as the server recorded them. Totals and statuses are the server's. */
export default function Orders() {
  const router = useRouter();
  const load = useUserLoad<History>(`/orders?limit=${ORDERS_LIMIT}`);
  const rows = load.status === 'ok' ? orderRows(load.data) : [];
  return (
    <Screen>
      <AppText variant="display" weight={800} accessibilityRole="header">
        Your orders
      </AppText>
      {load.status === 'loading' ? <Loading slow={load.slow} /> : null}
      {load.status === 'error' ? <ErrorBox message={load.message} onRetry={load.reload} /> : null}
      {load.status === 'ok' && rows.length === 0 ? (
        <Tile fill="butter" title="No orders yet" subtitle="When you place an order it will show up here.">
          <Button label="Browse restaurants" onPress={() => router.navigate('/')} style={{ marginTop: 8 }} />
        </Tile>
      ) : null}
      {rows.map((o) => (
        <OrderCard key={o.order_id} order={o} onOpen={() => router.push(orderHref(o.order_number))} />
      ))}
      {load.status === 'ok' && load.data.has_more ? (
        <AppText variant="caption" color={colors.muted} style={{ textAlign: 'center' }}>
          Showing your latest {ORDERS_LIMIT} orders.
        </AppText>
      ) : null}
    </Screen>
  );
}

function OrderCard({ order, onOpen }: { order: OrderRow; onOpen: () => void }) {
  const when = placedLabel(order.placed_at);
  const items = order.items.map((i) => `${i.qty} × ${i.name}`).join(', ');
  const status = statusLabel(order.order_status);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Order ${order.order_number}, ${order.restaurant}, ${status}, total ₹${order.total}. Open tracking`}
      onPress={onOpen}
      style={{ minHeight: MIN_TARGET }}
    >
      <Card>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
          <AppText weight={800}>#{order.order_number}</AppText>
          <Pill label={status} />
        </View>
        <AppText weight={700}>
          {order.restaurant}
          {order.branch_label ? ` · ${order.branch_label}` : ''}
        </AppText>
        {items ? (
          <AppText variant="caption" color={colors.muted} numberOfLines={2}>
            {items}
          </AppText>
        ) : null}
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
          <AppText variant="caption" color={colors.muted}>
            {when}
            {order.is_sample ? `${when ? ' · ' : ''}Demo order` : ''}
          </AppText>
          <AppText weight={700}>{rupees(order.total)}</AppText>
        </View>
      </Card>
    </Pressable>
  );
}
