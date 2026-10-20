import { useCallback, useRef, useState } from 'react';
import { Pressable, View } from 'react-native';
import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Screen } from '@/components/Screen';
import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { Tile } from '@/components/Tile';
import { Loading } from '@/components/LoadState';
import { VegMark } from '@/components/MenuParts';
import { BillRow, Card, rupees } from '@/components/BillParts';
import { TrackingMap } from '@/components/TrackingMap';
import { useSession } from '@/lib/session';
import { STEPS, nextPollDelayMs, reachedAt, type Track } from '@/lib/orders';
import { MIN_TARGET, colors } from '@/theme/tokens';

const RETRY_MS = 10_000;

/** One order: its status timeline, the rider's position and the bill, all from the server. No delivery estimate. */
export default function OrderTracking() {
  const router = useRouter();
  const { request } = useSession();
  const { orderNo } = useLocalSearchParams<{ orderNo: string }>();
  const [order, setOrder] = useState<Track | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [missing, setMissing] = useState(false);
  const loaded = useRef(false);

  // Polls while the screen is in view and stops when it is not (and when the order is delivered or not simulated).
  useFocusEffect(
    useCallback(() => {
      let live = true;
      let timer: ReturnType<typeof setTimeout> | undefined;
      const tick = async () => {
        const r = await request<Track>(`/orders/${encodeURIComponent(String(orderNo ?? ''))}`);
        if (!live) return;
        if (r.ok && r.data.status === 'ok') {
          loaded.current = true;
          setOrder(r.data);
          setProblem(null);
          const wait = nextPollDelayMs(r.data);
          if (wait !== null) timer = setTimeout(tick, wait);
        } else if (!r.ok && r.kind === 'http' && r.status === 404) {
          setMissing(true);
        } else {
          setProblem(r.ok ? "That didn't work." : r.message);
          timer = setTimeout(tick, RETRY_MS);
        }
      };
      void tick();
      return () => {
        live = false;
        if (timer) clearTimeout(timer);
      };
    }, [orderNo, request]),
  );

  const back = () => (router.canGoBack() ? router.back() : router.replace('/'));
  const header = (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
      <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={back} style={{ minHeight: MIN_TARGET, minWidth: MIN_TARGET, justifyContent: 'center', alignItems: 'center' }}>
        <Ionicons name="arrow-back" size={24} color={colors.navy} />
      </Pressable>
      <AppText variant="title" weight={800} accessibilityRole="header" style={{ flex: 1 }}>
        {order ? `Order ${order.order_number}` : 'Order'}
      </AppText>
    </View>
  );

  if (missing) {
    return (
      <Screen>
        {header}
        <Tile fill="coralTint" title="We couldn't find that order" subtitle="It may belong to a different account.">
          <Button label="Back to Home" onPress={() => router.replace('/')} style={{ marginTop: 8 }} />
        </Tile>
      </Screen>
    );
  }
  if (!order) {
    return (
      <Screen>
        {header}
        {problem ? <AppText accessibilityLiveRegion="polite">{problem} Trying again…</AppText> : <Loading slow={false} />}
      </Screen>
    );
  }

  const cancelled = order.order_status === 'cancelled';
  const current = STEPS.findIndex((s) => s.status === order.order_status);
  return (
    <Screen>
      {header}
      {problem ? (
        <AppText accessibilityLiveRegion="polite" variant="caption" color={colors.muted}>
          {problem} Showing the last update. Trying again…
        </AppText>
      ) : null}
      <Tile fill="navy" title={cancelled ? 'Cancelled' : (STEPS[current]?.label ?? order.order_status)} subtitle={`${order.restaurant} · ${order.branch_label}`}>
        <AppText variant="caption" color={colors.white}>
          {order.simulated_tracking ? 'Demo: progress is simulated.' : 'Progress is not simulated for this order.'}
        </AppText>
      </Tile>

      <Card>
        <AppText weight={800} variant="title">Progress</AppText>
        {STEPS.map((s, i) => {
          const at = reachedAt(order, s.status);
          const done = at !== null;
          return (
            <View key={s.status} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 32 }} accessible accessibilityLabel={`${s.label}${done ? `, reached at ${at}` : ', not yet'}${i === current ? ', now' : ''}`}>
              <Ionicons name={done ? 'checkmark-circle' : 'ellipse-outline'} size={22} color={done ? colors.navy : colors.muted} />
              <AppText weight={i === current ? 800 : 400} color={done ? colors.ink : colors.muted} style={{ flex: 1 }}>
                {s.label}
              </AppText>
              {at ? <AppText variant="caption" color={colors.muted}>{at}</AppText> : null}
            </View>
          );
        })}
      </Card>

      <TrackingMap from={order.route.from} to={order.route.to} rider={order.rider ? { lat: order.rider.lat, lon: order.rider.lon } : null} />

      <Card>
        <AppText weight={800} variant="title">Your order</AppText>
        {order.items.map((i) => (
          <View key={i.item_id} style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
            <VegMark isVeg={i.is_veg} withLabel={false} />
            <AppText style={{ flex: 1 }}>{i.qty} × {i.dish_name}</AppText>
            <AppText variant="caption" color={colors.muted}>{rupees(i.unit_price)} each</AppText>
          </View>
        ))}
        <View style={{ gap: 6, borderTopWidth: 1, borderTopColor: colors.surface, paddingTop: 10 }}>
          <BillRow label="Items" value={rupees(order.items_total)} />
          <BillRow label="Delivery" value={rupees(order.delivery_fee)} />
          <BillRow label="GST" value={rupees(order.taxes)} />
          <BillRow label="Total" value={rupees(order.total)} bold />
        </View>
        {order.delivery_area ? <AppText variant="caption" color={colors.muted}>Delivering to {order.delivery_area}</AppText> : null}
      </Card>
    </Screen>
  );
}
