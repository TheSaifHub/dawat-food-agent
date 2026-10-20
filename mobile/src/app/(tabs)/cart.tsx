import { useCallback, useEffect, useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { useFocusEffect, useRouter } from 'expo-router';
import { Screen } from '@/components/Screen';
import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { Chip } from '@/components/Chip';
import { Tile } from '@/components/Tile';
import { AreaPicker } from '@/components/AreaPicker';
import { BranchBill, Card, DeliveryInfo, TotalTile, rupees } from '@/components/BillParts';
import { ErrorBox, Loading } from '@/components/LoadState';
import { QtyControl, VegMark } from '@/components/MenuParts';
import { useCart, type Unavailable } from '@/lib/cart';
import { useArea } from '@/lib/area';
import { useSession } from '@/lib/session';
import { MIN_TARGET, colors } from '@/theme/tokens';

type Address = { address_id: string; label: string; line1: string; area: string; is_default: boolean };

const REASON: Record<Unavailable['reason'], string> = {
  branch_closed: 'This branch is closed right now.',
  unavailable: 'Not available right now.',
  too_far: 'Too far from your delivery point.',
};

export default function CartScreen() {
  const router = useRouter();
  const { request } = useSession();
  const { cart, loading, loadError, refresh, add, remove, setDelivery } = useCart();
  const { area } = useArea();
  // The chat and other screens change the same cart: look again whenever this tab comes into view.
  useFocusEffect(
    useCallback(() => {
      void refresh();
    }, [refresh]),
  );
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<{ text: string; bad: boolean } | null>(null);
  const [picking, setPicking] = useState(false);
  const [addresses, setAddresses] = useState<Address[]>([]);

  useEffect(() => {
    let live = true;
    request<{ addresses?: Address[] }>('/me/addresses').then((r) => live && r.ok && setAddresses(r.data.addresses ?? []));
    return () => {
      live = false;
    };
  }, [request]);

  async function run(key: string, f: () => Promise<{ ok: boolean; message: string }>) {
    setBusy(key);
    const r = await f();
    setBusy(null);
    setNote({ text: r.message, bad: !r.ok });
  }

  if (loading) {
    return (
      <Screen>
        <AppText variant="display" weight={800} accessibilityRole="header">Your cart</AppText>
        <Loading slow={false} />
      </Screen>
    );
  }
  if (!cart && loadError) {
    return (
      <Screen>
        <AppText variant="display" weight={800} accessibilityRole="header">Your cart</AppText>
        <ErrorBox message={loadError} onRetry={refresh} />
      </Screen>
    );
  }

  // The server says status "empty" when nothing can be ordered, even if dishes are still in the cart (all too far,
  // say). Those dishes must stay visible so the user can remove them: empty means no dishes at all.
  const empty = !cart || (cart.branches.length === 0 && !cart.unavailable?.length);
  const confirmed = cart?.cart_status === 'confirmed';

  return (
    <Screen>
      <AppText variant="display" weight={800} accessibilityRole="header">Your cart</AppText>
      {empty ? (
        <Tile fill="butter" title="Your cart is empty" subtitle="Add dishes from a restaurant, or ask Dawat AI.">
          <Button label="Browse restaurants" onPress={() => router.navigate('/')} style={{ marginTop: 8 }} />
        </Tile>
      ) : cart ? (
        <>
          {note ? (
            <AppText accessibilityLiveRegion="polite" weight={600} style={note.bad ? { backgroundColor: colors.coralTint, padding: 10, borderRadius: 12 } : undefined}>
              {note.text}
            </AppText>
          ) : null}

          <DeliveryInfo delivery={cart.delivery} browsed={area} busy={busy === 'delivery'} onSwitch={() => area && run('delivery', () => setDelivery({ area: area.name }))} />
          <Card>
            {addresses.length > 0 ? (
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
                {addresses.map((a) => (
                  <Chip
                    key={a.address_id}
                    label={a.label}
                    selected={cart.delivery?.address_id === a.address_id}
                    onPress={() => run('delivery', () => setDelivery({ address_id: a.address_id }))}
                  />
                ))}
              </ScrollView>
            ) : null}
            <Button label={cart.delivery ? 'Change area' : 'Pick area'} variant="secondary" onPress={() => setPicking(true)} />
          </Card>

          {cart.branches.map((b) => (
            <Card key={b.branch_id}>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`${b.restaurant}, ${b.branch_label}. Open menu`}
                onPress={() => router.push({ pathname: '/restaurant/[branchId]', params: { branchId: b.branch_id } })}
                style={{ minHeight: MIN_TARGET, justifyContent: 'center' }}
              >
                <AppText weight={800} variant="title">{b.restaurant}</AppText>
                <AppText variant="caption" color={colors.muted}>{b.branch_label}</AppText>
              </Pressable>
              {b.items.map((i) => (
                <View key={i.item_id} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                  <View style={{ flex: 1, gap: 2 }}>
                    <AppText weight={600}>{i.name}</AppText>
                    <View style={{ flexDirection: 'row', gap: 10, alignItems: 'center' }}>
                      <VegMark isVeg={i.is_veg} withLabel={false} />
                      <AppText variant="caption" color={colors.muted}>
                        {rupees(i.price)} × {i.qty} = {rupees(i.line_total)}
                      </AppText>
                    </View>
                  </View>
                  <QtyControl
                    qty={i.qty}
                    name={i.name}
                    busy={busy === i.item_id}
                    onAdd={() => run(i.item_id, () => add(i.item_id, b.branch_id, i.name))}
                    onMinus={() => run(i.item_id, () => remove(i.item_id, b.branch_id, 1))}
                  />
                </View>
              ))}
              <BranchBill b={b} />
            </Card>
          ))}

          {cart.unavailable?.length ? (
            <Tile fill="coralTint" title="Can't be ordered">
              {cart.unavailable.map((u) => (
                <View key={`${u.branch_id}-${u.item_id}`} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 44 }}>
                  <View style={{ flex: 1 }}>
                    <AppText weight={600}>{u.name} ({u.restaurant})</AppText>
                    <AppText variant="caption" color={colors.muted}>{REASON[u.reason]}</AppText>
                  </View>
                  <Button label="Remove" variant="secondary" onPress={() => run(u.item_id, () => remove(u.item_id, u.branch_id))} style={{ minHeight: 44, paddingHorizontal: 16 }} />
                </View>
              ))}
            </Tile>
          ) : null}

          {cart.status === 'ok' ? <TotalTile total={cart.grand_total} /> : null}

          {confirmed ? (
            <Tile fill="sage" title={`Confirmed: ${rupees(cart.confirmed_total ?? cart.grand_total)}`} subtitle="Next: pay with a test payment (no real money). Changing your cart re-opens it.">
              <Button label="Pay now" onPress={() => router.push('/payment')} style={{ marginTop: 8 }} />
            </Tile>
          ) : null}

          {/* One clear action: a confirmed cart is paid for, an unconfirmed one is reviewed. Never both. */}
          {confirmed ? null : (
            <>
              <Button
                label={cart.can_confirm === true && cart.grand_total !== null ? `Place order · ${rupees(cart.grand_total)}` : 'Place order'}
                disabled={cart.can_confirm !== true || cart.grand_total === null}
                onPress={() => router.push('/review-order')}
              />
              <AppText variant="caption" color={colors.muted}>
                {cart.status === 'needs_delivery_area'
                  ? 'Pick a delivery area to see your total.'
                  : cart.can_confirm
                    ? "You'll review and confirm next. Nothing is ordered yet."
                    : "This cart can't be ordered yet. Remove the items marked above, or change where to deliver."}
              </AppText>
            </>
          )}
        </>
      ) : null}

      <AreaPicker
        visible={picking}
        onClose={() => setPicking(false)}
        onPick={(a) => {
          setPicking(false);
          void run('delivery', () => setDelivery({ area: a.name }));
        }}
      />
    </Screen>
  );
}
