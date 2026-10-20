import { useCallback, useMemo, useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Screen } from '@/components/Screen';
import { AppText } from '@/components/AppText';
import { Chip } from '@/components/Chip';
import { Tile } from '@/components/Tile';
import { ErrorBox, Loading } from '@/components/LoadState';
import { OsmCredit } from '@/components/OsmCredit';
import { MenuItemRow, categoryLabel, orderCategories, type MenuItem } from '@/components/MenuParts';
import { useArea } from '@/lib/area';
import { useLoad } from '@/lib/browse';
import { qtyInCart, useCart } from '@/lib/cart';
import { MIN_TARGET, colors, radii } from '@/theme/tokens';

type BranchData = {
  restaurant: { name: string; cuisines: string[]; veg_only: boolean; is_chain: boolean };
  branch: { branch_id: string; label: string; area: string; street: string | null };
  other_branches: { branch_id: string; label: string; area: string }[];
  free_delivery_from: number;
  max_delivery_km: number;
  delivery?: { status: string; distance_km?: number; delivery_fee?: number; message?: string };
};
type MenuData = { items: MenuItem[] };

export default function RestaurantPage() {
  const router = useRouter();
  const { branchId } = useLocalSearchParams<{ branchId: string }>();
  const { area } = useArea();
  const id = encodeURIComponent(String(branchId ?? ''));
  const info = useLoad<BranchData & { status: string }>(`/branches/${id}${area ? `?area=${encodeURIComponent(area.area_id)}` : ''}`);
  const menu = useLoad<MenuData & { status: string }>(`/branches/${id}/menu`);
  const { cart, add, remove, itemCount, refresh } = useCart();
  useFocusEffect(
    useCallback(() => {
      void refresh();
    }, [refresh]),
  );
  const [vegOnly, setVegOnly] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<{ text: string; bad: boolean } | null>(null);

  const back = () => (router.canGoBack() ? router.back() : router.replace('/'));
  const items = useMemo(() => (menu.status === 'ok' ? menu.data.items.filter((i) => !vegOnly || i.is_veg) : []), [menu, vegOnly]);
  const cats = useMemo(() => orderCategories(items.map((i) => i.category)), [items]);

  async function act(item: MenuItem, kind: 'add' | 'minus') {
    setBusy(item.item_id);
    const r = kind === 'add' ? await add(item.item_id, String(branchId), item.name, area ?? null) : await remove(item.item_id, String(branchId), 1);
    setBusy(null);
    setNote({ text: r.message, bad: !r.ok });
  }

  return (
    <Screen scroll={false}>
      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ gap: 12, paddingBottom: 24 }} keyboardShouldPersistTaps="handled">
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Back"
          onPress={back}
          style={{ minHeight: MIN_TARGET, minWidth: MIN_TARGET, justifyContent: 'center' }}
        >
          <Ionicons name="arrow-back" size={24} color={colors.navy} />
        </Pressable>

        {info.status === 'loading' ? <Loading slow={info.slow} /> : null}
        {info.status === 'error' ? <ErrorBox message={info.message} onRetry={info.reload} /> : null}
        {info.status === 'ok' ? <Header data={info.data} /> : null}

        {menu.status === 'loading' && info.status !== 'loading' ? <Loading slow={menu.slow} /> : null}
        {menu.status === 'error' ? <ErrorBox message={menu.message} onRetry={menu.reload} /> : null}
        {menu.status === 'ok' ? (
          <>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
              <Chip label="Veg only" selected={vegOnly} onPress={() => setVegOnly(!vegOnly)} />
            </ScrollView>
            {items.length === 0 ? (
              <Tile fill="coralTint" title={vegOnly ? 'No vegetarian dishes here' : 'No dishes available right now'} subtitle={vegOnly ? 'Turn off Veg only to see everything.' : 'Please try another restaurant.'} />
            ) : (
              cats.map((c) => (
                <View key={c} style={{ gap: 8 }}>
                  <AppText variant="title" weight={800} accessibilityRole="header">
                    {categoryLabel(c)}
                  </AppText>
                  {items
                    .filter((i) => i.category === c)
                    .map((i) => (
                      <MenuItemRow
                        key={i.item_id}
                        item={i}
                        qty={qtyInCart(cart, i.item_id, String(branchId))}
                        busy={busy === i.item_id}
                        onAdd={() => act(i, 'add')}
                        onMinus={() => act(i, 'minus')}
                      />
                    ))}
                </View>
              ))
            )}
          </>
        ) : null}
        <OsmCredit />
      </ScrollView>

      {note ? (
        <AppText
          accessibilityLiveRegion="polite"
          weight={600}
          style={{ backgroundColor: note.bad ? colors.coralTint : colors.card, padding: 10, borderRadius: radii.sm, marginBottom: 8 }}
        >
          {note.text}
        </AppText>
      ) : null}

      {itemCount > 0 ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`View cart, ${itemCount} ${itemCount === 1 ? 'item' : 'items'}`}
          onPress={() => router.navigate('/cart')}
          style={{ minHeight: 52, borderRadius: radii.pill, backgroundColor: colors.navy, alignItems: 'center', justifyContent: 'center', marginBottom: 8 }}
        >
          <AppText weight={700} color={colors.white}>
            View cart · {itemCount} {itemCount === 1 ? 'item' : 'items'}
          </AppText>
        </Pressable>
      ) : null}
    </Screen>
  );
}

function Header({ data }: { data: BranchData }) {
  const router = useRouter();
  const { restaurant: r, branch: b, delivery: d } = data;
  const where = [b.label, b.street].filter(Boolean).join(' · ');
  return (
    <View style={{ gap: 8 }}>
      <AppText variant="display" weight={800} accessibilityRole="header">
        {r.name}
      </AppText>
      <AppText color={colors.muted}>{r.cuisines.join(' · ')}</AppText>
      <AppText variant="caption" color={colors.muted}>
        Branch: {where}
      </AppText>
      {r.veg_only ? (
        <View style={{ alignSelf: 'flex-start', backgroundColor: colors.sage, borderRadius: radii.pill, paddingHorizontal: 10, paddingVertical: 3 }}>
          <AppText variant="caption" weight={700}>
            Veg only
          </AppText>
        </View>
      ) : null}
      {d?.status === 'ok' && d.delivery_fee !== undefined ? (
        <Tile fill="sky" title={`${d.distance_km} km away · Delivery ₹${d.delivery_fee}`} subtitle={`Free delivery on food from ₹${data.free_delivery_from}. We deliver up to ${data.max_delivery_km} km.`} />
      ) : (
        <AppText variant="caption" color={colors.muted}>
          Pick a delivery area on Home to see the distance and delivery fee.
        </AppText>
      )}
      {data.other_branches.length > 0 ? (
        <View style={{ gap: 6 }}>
          <AppText weight={700}>Other branches</AppText>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
            {data.other_branches.map((o) => (
              <Chip key={o.branch_id} label={o.label} selected={false} onPress={() => router.replace({ pathname: '/restaurant/[branchId]', params: { branchId: o.branch_id } })} />
            ))}
          </ScrollView>
        </View>
      ) : null}
    </View>
  );
}
