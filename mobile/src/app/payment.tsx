import { useEffect, useRef, useState } from 'react';
import { Pressable, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Screen } from '@/components/Screen';
import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { Chip } from '@/components/Chip';
import { Tile } from '@/components/Tile';
import { Loading } from '@/components/LoadState';
import { Card, TotalTile, rupees } from '@/components/BillParts';
import { useCart } from '@/lib/cart';
import { useSession } from '@/lib/session';
import { INSTRUMENTS, TEST_NOTICE, payAndVerify, startPayment, type Instrument, type Method, type PaidOrder, type Start } from '@/lib/payments';
import { MIN_TARGET, colors, radii } from '@/theme/tokens';

type Stage = { s: 'loading' } | { s: 'blocked'; message: string } | { s: 'ready'; start: Start } | { s: 'paid'; orders: PaidOrder[]; total: number };

/**
 * The simulated checkout sheet. The amount is the one the server returned when the payment was opened; this screen
 * sends no amount, and the instrument can only be one of the fixed test values (a choice, never typed text).
 */
export default function PaymentScreen() {
  const router = useRouter();
  const { request } = useSession();
  const { cart, loading, refresh } = useCart();
  const [stage, setStage] = useState<Stage>({ s: 'loading' });
  const [fresh, setFresh] = useState(false);
  const [method, setMethod] = useState<Method>('card');
  const [picked, setPicked] = useState<Instrument>(INSTRUMENTS[0]);
  const [busy, setBusy] = useState<'success' | 'failure' | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [refund, setRefund] = useState(false);
  const inFlight = useRef(false);
  const started = useRef(false);

  // Read the cart again first: a payment is only ever opened for the cart the server says is confirmed.
  useEffect(() => {
    void refresh().finally(() => setFresh(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once on open
  }, []);

  useEffect(() => {
    if (!fresh || loading || started.current) return; // wait until the cart has really been read
    started.current = true;
    if (!cart || cart.cart_status !== 'confirmed' || !cart.cart_id) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- shows the blocked notice when there is no confirmed cart
      setStage({ s: 'blocked', message: 'There is nothing to pay yet. Confirm your order from the cart first.' });
      return;
    }
    void startPayment(request, cart.cart_id).then((r) => setStage(r.ok ? { s: 'ready', start: r.start } : { s: 'blocked', message: r.message }));
  }, [fresh, loading, cart, request]);

  const toCart = () => router.replace('/cart');
  const back = () => (router.canGoBack() ? router.back() : toCart());

  async function pay(outcome: 'success' | 'failure') {
    if (stage.s !== 'ready' || inFlight.current) return; // one payment request at a time
    inFlight.current = true;
    setBusy(outcome);
    setMessage(null);
    const r = await payAndVerify(request, stage.start, picked, outcome);
    inFlight.current = false;
    setBusy(null);
    if (r.kind === 'paid') {
      setStage({ s: 'paid', orders: r.orders, total: r.grandTotal });
      void refresh(); // the server emptied the cart
    } else {
      setMessage(r.message);
      setRefund(r.kind === 'refund');
    }
  }

  const header = (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
      <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={back} style={{ minHeight: MIN_TARGET, minWidth: MIN_TARGET, justifyContent: 'center', alignItems: 'center' }}>
        <Ionicons name="arrow-back" size={24} color={colors.navy} />
      </Pressable>
      <AppText variant="title" weight={800} accessibilityRole="header" style={{ flex: 1 }}>
        Pay
      </AppText>
    </View>
  );
  const notice = (
    <View style={{ backgroundColor: colors.butter, borderRadius: radii.sm, padding: 12 }} accessible accessibilityLabel={TEST_NOTICE}>
      <AppText weight={700}>{TEST_NOTICE}</AppText>
    </View>
  );

  if (stage.s === 'loading') {
    return (
      <Screen>
        {header}
        <Loading slow={false} />
      </Screen>
    );
  }
  if (stage.s === 'blocked') {
    return (
      <Screen>
        {header}
        <Tile fill="butter" title="Can't start the payment" subtitle={stage.message}>
          <Button label="Back to cart" onPress={toCart} style={{ marginTop: 8 }} />
        </Tile>
      </Screen>
    );
  }
  if (stage.s === 'paid') {
    return (
      <Screen>
        {header}
        {notice}
        <Tile fill="sage" title={`Paid: ${rupees(stage.total)}`} subtitle="Your order is placed. This was a test payment and no real money moved.">
          {stage.orders.map((o) => (
            <View key={o.order_id} style={{ gap: 6, marginTop: 6 }}>
              <AppText weight={700}>
                {o.order_number} · {o.restaurant} · {rupees(o.total)}
              </AppText>
              <Button label={`Track ${o.order_number}`} onPress={() => router.push({ pathname: '/orders/[orderNo]', params: { orderNo: o.order_number } })} />
            </View>
          ))}
        </Tile>
        <Button label="Back to Home" variant="secondary" onPress={() => router.replace('/')} />
      </Screen>
    );
  }

  const list = INSTRUMENTS.filter((i) => i.method === method);
  return (
    <Screen>
      {header}
      {notice}
      <TotalTile total={stage.start.amount_rupees} label="Amount to pay" />

      <View style={{ flexDirection: 'row', gap: 8 }}>
        <Chip label="Card" selected={method === 'card'} onPress={() => { setMethod('card'); setPicked(INSTRUMENTS.find((i) => i.method === 'card')!); }} />
        <Chip label="UPI" selected={method === 'upi'} onPress={() => { setMethod('upi'); setPicked(INSTRUMENTS.find((i) => i.method === 'upi')!); }} />
      </View>
      <Card>
        <AppText weight={700}>Choose a test {method === 'card' ? 'card' : 'UPI id'}</AppText>
        {list.map((i) => (
          <Pressable
            key={i.id}
            accessibilityRole="radio"
            accessibilityState={{ checked: picked.id === i.id }}
            accessibilityLabel={`${i.label}, ${i.hint}`}
            onPress={() => setPicked(i)}
            style={{ minHeight: MIN_TARGET, flexDirection: 'row', alignItems: 'center', gap: 10 }}
          >
            <Ionicons name={picked.id === i.id ? 'radio-button-on' : 'radio-button-off'} size={22} color={colors.navy} />
            <View style={{ flex: 1 }}>
              <AppText weight={600}>{i.label}</AppText>
              <AppText variant="caption" color={colors.muted}>{i.hint}</AppText>
            </View>
          </Pressable>
        ))}
        <AppText variant="caption" color={colors.muted}>
          Only these fixed test values work. No card details are typed, saved or sent.
        </AppText>
      </Card>

      {message ? (
        <View style={{ backgroundColor: colors.coralTint, borderRadius: radii.sm, padding: 12, gap: 8 }} accessibilityLiveRegion="polite">
          <AppText weight={600}>{message}</AppText>
          {refund ? <Button label="Back to cart" variant="secondary" onPress={toCart} /> : null}
        </View>
      ) : null}

      <Button label={`Pay ${rupees(stage.start.amount_rupees)}`} loading={busy === 'success'} disabled={busy !== null} onPress={() => pay('success')} />
      <Button label="Simulate failed payment" variant="secondary" loading={busy === 'failure'} disabled={busy !== null} onPress={() => pay('failure')} />
      <AppText variant="caption" color={colors.muted}>
        {TEST_NOTICE}
      </AppText>
    </Screen>
  );
}
