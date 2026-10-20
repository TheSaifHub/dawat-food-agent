import { useEffect, useState } from 'react';
import { Pressable, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Screen } from '@/components/Screen';
import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { Tile } from '@/components/Tile';
import { BranchBill, Card, DeliveryInfo, TotalTile, rupees } from '@/components/BillParts';
import { Loading } from '@/components/LoadState';
import { useCart } from '@/lib/cart';
import { useArea } from '@/lib/area';
import { MIN_TARGET, colors } from '@/theme/tokens';

/**
 * The confirm step. The user reads the server's bill and says yes or no. "Yes" confirms exactly the quote on screen
 * (POST /cart/confirm). It places no order and takes no payment: payment is a later module. If anything changed
 * since the bill was fetched, the server refuses (stale quote), the new bill is shown, and the user decides again.
 */
export default function ReviewOrder() {
  const router = useRouter();
  const { cart, refresh, confirm } = useCart();
  const { area } = useArea();
  const [fresh, setFresh] = useState(false);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [done, setDone] = useState<number | null | undefined>(undefined);

  // Always read the bill again when this screen opens, so the user never confirms an old one.
  useEffect(() => {
    void refresh().finally(() => setFresh(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once on open
  }, []);

  const back = () => (router.canGoBack() ? router.back() : router.replace('/cart'));
  const header = (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
      <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={back} style={{ minHeight: MIN_TARGET, minWidth: MIN_TARGET, justifyContent: 'center', alignItems: 'center' }}>
        <Ionicons name="arrow-back" size={24} color={colors.navy} />
      </Pressable>
      <AppText variant="title" weight={800} accessibilityRole="header" style={{ flex: 1 }}>Review your order</AppText>
    </View>
  );

  if (!fresh) return <Screen>{header}<Loading slow={false} /></Screen>;

  const already = cart?.cart_status === 'confirmed';
  if (done !== undefined || already) {
    const total = done ?? cart?.confirmed_total ?? cart?.grand_total ?? null;
    return (
      <Screen>
        {header}
        <Tile fill="sage" title={`Confirmed: ${rupees(total)}`} subtitle="Next: pay with a test payment. No real money moves, and nothing is ordered until you pay.">
          <Button label={`Pay ${rupees(total)}`} onPress={() => router.push('/payment')} style={{ marginTop: 8 }} />
          <Button label="Back to cart" variant="secondary" onPress={() => router.replace('/cart')} style={{ marginTop: 8 }} />
        </Tile>
      </Screen>
    );
  }

  if (!cart || cart.branches.length === 0) {
    return (
      <Screen>
        {header}
        <Tile fill="butter" title="Your cart is empty" subtitle="Add dishes first.">
          <Button label="Back to cart" onPress={() => router.replace('/cart')} style={{ marginTop: 8 }} />
        </Tile>
      </Screen>
    );
  }

  const canConfirm = cart.can_confirm === true && cart.grand_total !== null && !!cart.quote_id;

  return (
    <Screen>
      {header}
      {message ? (
        <AppText accessibilityLiveRegion="polite" weight={600} style={{ backgroundColor: colors.coralTint, padding: 10, borderRadius: 12 }}>
          {message}
        </AppText>
      ) : null}
      <DeliveryInfo delivery={cart.delivery} browsed={area} hint="Go back if you want to change it." />
      {cart.branches.map((b) => (
        <Card key={b.branch_id}>
          <AppText weight={800} variant="title">{b.restaurant}</AppText>
          <AppText variant="caption" color={colors.muted}>{b.branch_label}</AppText>
          {b.items.map((i) => (
            <View key={i.item_id} style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12 }}>
              <AppText style={{ flex: 1 }}>{i.qty} × {i.name}</AppText>
              <AppText weight={600}>{rupees(i.line_total)}</AppText>
            </View>
          ))}
          <BranchBill b={b} />
        </Card>
      ))}
      <TotalTile total={cart.grand_total} />
      <AppText weight={700}>Confirm this order for {rupees(cart.grand_total)}?</AppText>
      <Button
        label="Yes, confirm this order"
        loading={working}
        disabled={!canConfirm}
        onPress={async () => {
          setWorking(true);
          setMessage(null);
          const r = await confirm();
          setWorking(false);
          if (r.ok) setDone(r.confirmedTotal);
          else setMessage(r.message);
        }}
      />
      <Button label="No, go back" variant="secondary" onPress={back} />
      <AppText variant="caption" color={colors.muted}>Nothing is charged yet. Payment is the next step.</AppText>
    </Screen>
  );
}
