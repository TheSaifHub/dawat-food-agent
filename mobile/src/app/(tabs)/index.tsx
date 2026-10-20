import { useState } from 'react';
import { Pressable, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Screen } from '@/components/Screen';
import { Wordmark } from '@/components/Wordmark';
import { AppText } from '@/components/AppText';
import { Tile } from '@/components/Tile';
import { Button } from '@/components/Button';
import { AreaPicker } from '@/components/AreaPicker';
import { RestaurantCard } from '@/components/RestaurantCard';
import { ErrorBox, Loading } from '@/components/LoadState';
import { OsmCredit } from '@/components/OsmCredit';
import { useSession } from '@/lib/session';
import { useArea } from '@/lib/area';
import { homePath, useLoad, type HomeData } from '@/lib/browse';
import { MIN_TARGET, colors, radii, type FillName } from '@/theme/tokens';

const CUISINE_FILLS: FillName[] = ['butter', 'sky', 'sage', 'surface'];

export default function Home() {
  const router = useRouter();
  const { state } = useSession();
  const { area, ready, setArea } = useArea();
  const [picking, setPicking] = useState(false);
  const first = state.status === 'signedIn' ? state.me.display_name.split(' ')[0] : '';
  const open = (params: Record<string, string> = {}) => router.push({ pathname: '/restaurants', params });

  return (
    <Screen>
      <Wordmark />
      <AppText variant="display" weight={800} accessibilityRole="header">
        {first ? `Hi, ${first}` : 'Hi'}
      </AppText>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={area ? `Delivery area ${area.name}. Change` : 'Pick your delivery area'}
        onPress={() => setPicking(true)}
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          gap: 8,
          minHeight: MIN_TARGET,
          alignSelf: 'flex-start',
          backgroundColor: colors.card,
          borderRadius: radii.pill,
          paddingHorizontal: 16,
        }}
      >
        <Ionicons name="location" size={18} color={colors.accent} />
        <AppText weight={700}>{area ? area.name : 'Pick your delivery area'}</AppText>
        <Ionicons name="chevron-down" size={16} color={colors.navy} />
      </Pressable>

      <Tile
        fill="sky"
        title="Ask Dawat AI"
        subtitle="e.g. biryani for 2, less spicy"
        onPress={() => router.navigate('/chat')}
        accessibilityLabel="Ask Dawat AI. Open the chat"
      />

      {!ready ? null : area ? <Browse areaId={area.area_id} open={open} /> : (
        <Tile fill="butter" title="Where should we deliver?" subtitle="Pick your area to see restaurants near you.">
          <Button label="Pick area" onPress={() => setPicking(true)} style={{ marginTop: 8 }} />
        </Tile>
      )}

      <OsmCredit />
      <AreaPicker
        visible={picking}
        onClose={() => setPicking(false)}
        onPick={(a) => {
          setArea(a);
          setPicking(false);
        }}
      />
    </Screen>
  );
}

function Browse({ areaId, open }: { areaId: string; open: (p?: Record<string, string>) => void }) {
  const router = useRouter();
  const home = useLoad<HomeData & { status: string }>(homePath(areaId));
  if (home.status === 'loading') return <Loading slow={home.slow} />;
  if (home.status === 'error') return <ErrorBox message={home.message} onRetry={home.reload} />;
  const { cuisines, chains, restaurants_in_range, area } = home.data;
  if (restaurants_in_range === 0) {
    return <Tile fill="coralTint" title="No restaurants deliver to this area yet" subtitle="Try a nearby area." />;
  }
  return (
    <>
      <View style={{ flexDirection: 'row', gap: 12 }}>
        <Tile fill="sage" title="Veg only" subtitle="Vegetarian restaurants" onPress={() => open({ veg: '1' })} style={{ flex: 1 }} />
        <Tile fill="surface" title="All" subtitle={`${restaurants_in_range} near ${area.name}`} onPress={() => open()} style={{ flex: 1 }} />
      </View>

      <AppText variant="title" weight={800} accessibilityRole="header">
        Cuisines
      </AppText>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
        {cuisines.map((c, i) => (
          <Tile
            key={c.cuisine}
            fill={CUISINE_FILLS[i % CUISINE_FILLS.length]}
            title={c.cuisine}
            subtitle={`${c.restaurants} restaurants`}
            onPress={() => open({ cuisine: c.cuisine })}
            style={{ width: '47.5%' }}
          />
        ))}
      </View>

      {chains.length > 0 ? (
        <>
          <AppText variant="title" weight={800} accessibilityRole="header">
            Chains near you
          </AppText>
          {chains.map((r) => (
            <RestaurantCard key={r.restaurant_id} r={r} onPress={() => router.push({ pathname: '/restaurant/[branchId]', params: { branchId: r.branch.branch_id } })} />
          ))}
        </>
      ) : null}
      <Button label="See all restaurants" onPress={() => open()} />
    </>
  );
}
