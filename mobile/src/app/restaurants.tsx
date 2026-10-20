import { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Screen } from '@/components/Screen';
import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { Chip } from '@/components/Chip';
import { RestaurantCard } from '@/components/RestaurantCard';
import { ErrorBox, Loading } from '@/components/LoadState';
import { OsmCredit } from '@/components/OsmCredit';
import { Tile } from '@/components/Tile';
import { api } from '@/lib/api';
import { useArea } from '@/lib/area';
import { listPath, type Filters, type ListData, type RestaurantCardData, type Sort } from '@/lib/browse';
import { MIN_TARGET, colors } from '@/theme/tokens';

const SORTS: { key: Sort; label: string }[] = [
  { key: 'distance', label: 'Nearest' },
  { key: 'price', label: 'Price' },
  { key: 'name', label: 'Name' },
];

type View_ =
  | { s: 'loading'; slow: boolean }
  | { s: 'error'; message: string }
  | { s: 'ok'; items: RestaurantCardData[]; total: number; facets: ListData['cuisine_facets']; freeFrom: number; more: 'idle' | 'loading' | 'error' };

/** All restaurants for the picked area, with the veg-only, mild, cuisine and sort filters (all done by the backend). */
export default function Restaurants() {
  const router = useRouter();
  const params = useLocalSearchParams<{ cuisine?: string; veg?: string }>();
  const { area } = useArea();
  const [f, setF] = useState<Filters>({ cuisine: params.cuisine ?? null, vegOnly: params.veg === '1', mild: false, sort: 'distance' });
  const [v, setV] = useState<View_>({ s: 'loading', slow: false });
  const [tick, setTick] = useState(0);
  const run = useRef(0); // an older answer never replaces a newer one

  useEffect(() => {
    if (!area) return;
    const mine = ++run.current;
    const ctl = new AbortController();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- starts the loading state for a fetch that this effect runs
    setV({ s: 'loading', slow: false });
    api<ListData & { status: string }>(listPath(area.area_id, f, 0), {
      signal: ctl.signal,
      onSlow: () => setV((x) => (x.s === 'loading' ? { s: 'loading', slow: true } : x)),
    }).then((r) => {
      if (mine !== run.current || ctl.signal.aborted) return;
      if (!r.ok) return setV({ s: 'error', message: r.message });
      if (r.data.status !== 'ok') return setV({ s: 'error', message: "That didn't work. Please try again." });
      setV({ s: 'ok', items: r.data.restaurants, total: r.data.total, facets: r.data.cuisine_facets, freeFrom: r.data.free_delivery_from, more: 'idle' });
    });
    return () => ctl.abort();
  }, [area, f, tick]);

  const showMore = useCallback(async () => {
    if (!area || v.s !== 'ok') return;
    const mine = run.current;
    setV({ ...v, more: 'loading' });
    const r = await api<ListData & { status: string }>(listPath(area.area_id, f, v.items.length));
    if (mine !== run.current) return;
    if (!r.ok || r.data.status !== 'ok') return setV((x) => (x.s === 'ok' ? { ...x, more: 'error' } : x));
    const next = r.data.restaurants;
    setV((x) => (x.s === 'ok' ? { ...x, items: [...x.items, ...next.filter((n) => !x.items.some((o) => o.restaurant_id === n.restaurant_id))], more: 'idle' } : x));
  }, [area, f, v]);

  const back = () => (router.canGoBack() ? router.back() : router.replace('/'));

  return (
    <Screen>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Back"
          onPress={back}
          style={{ minHeight: MIN_TARGET, minWidth: MIN_TARGET, justifyContent: 'center', alignItems: 'center' }}
        >
          <Ionicons name="arrow-back" size={24} color={colors.navy} />
        </Pressable>
        <AppText variant="title" weight={800} accessibilityRole="header" style={{ flex: 1 }}>
          {area ? `Restaurants near ${area.name}` : 'Restaurants'}
        </AppText>
      </View>

      {!area ? (
        <Tile fill="butter" title="Pick your delivery area first" subtitle="Go back to Home and choose an area.">
          <Button label="Back to Home" onPress={back} style={{ marginTop: 8 }} />
        </Tile>
      ) : (
        <>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
            <Chip label="Veg only" selected={f.vegOnly} onPress={() => setF({ ...f, vegOnly: !f.vegOnly })} />
            <Chip label="Mild options" selected={f.mild} onPress={() => setF({ ...f, mild: !f.mild })} />
            {SORTS.map((s) => (
              <Chip key={s.key} label={`Sort: ${s.label}`} selected={f.sort === s.key} onPress={() => setF({ ...f, sort: s.key })} />
            ))}
          </ScrollView>
          {v.s === 'ok' ? (
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
              <Chip label="All cuisines" selected={f.cuisine === null} onPress={() => setF({ ...f, cuisine: null })} />
              {(f.cuisine && !v.facets.some((c) => c.cuisine === f.cuisine) ? [{ cuisine: f.cuisine, restaurants: 0 }, ...v.facets] : v.facets).map((c) => (
                <Chip key={c.cuisine} label={c.cuisine} selected={f.cuisine === c.cuisine} onPress={() => setF({ ...f, cuisine: f.cuisine === c.cuisine ? null : c.cuisine })} />
              ))}
            </ScrollView>
          ) : null}

          {v.s === 'loading' ? <Loading slow={v.slow} /> : null}
          {v.s === 'error' ? <ErrorBox message={v.message} onRetry={() => setTick((t) => t + 1)} /> : null}
          {v.s === 'ok' ? (
            <>
              <AppText variant="caption" color={colors.muted} accessibilityLiveRegion="polite">
                {v.total} {v.total === 1 ? 'restaurant' : 'restaurants'} · free delivery on food from ₹{v.freeFrom}
              </AppText>
              {v.items.length === 0 ? (
                <Tile
                  fill="coralTint"
                  title="Nothing matches these filters"
                  subtitle="Try removing a filter. Not many places near here are vegetarian-only or have mild options."
                >
                  <Button
                    label="Clear filters"
                    variant="secondary"
                    onPress={() => setF({ cuisine: null, vegOnly: false, mild: false, sort: 'distance' })}
                    style={{ marginTop: 8 }}
                  />
                </Tile>
              ) : (
                v.items.map((r) => (
                  <RestaurantCard key={r.restaurant_id} r={r} onPress={() => router.push({ pathname: '/restaurant/[branchId]', params: { branchId: r.branch.branch_id } })} />
                ))
              )}
              {v.items.length < v.total ? (
                <>
                  <Button label="Show more" variant="secondary" loading={v.more === 'loading'} onPress={showMore} />
                  {v.more === 'error' ? (
                    <AppText variant="caption" accessibilityLiveRegion="polite">
                      Couldn&apos;t load more. Try again.
                    </AppText>
                  ) : null}
                </>
              ) : null}
            </>
          ) : null}
        </>
      )}
      <OsmCredit />
    </Screen>
  );
}
