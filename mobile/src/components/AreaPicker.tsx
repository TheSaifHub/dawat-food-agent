import { useEffect, useMemo, useState } from 'react';
import { FlatList, Modal, Pressable, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AppText } from './AppText';
import { Loading, ErrorBox } from './LoadState';
import { DemoBanner } from './DemoBanner';
import { MIN_TARGET, colors, radii } from '@/theme/tokens';
import { useLoad, type Area } from '@/lib/browse';
import type { PickedArea } from '@/lib/area';

/** Pick the delivery area from GET /areas. Search by English or Telugu name. The Android back button closes it. */
export function AreaPicker({ visible, onClose, onPick }: { visible: boolean; onClose: () => void; onPick: (a: PickedArea) => void }) {
  const load = useLoad<{ status: string; areas: Area[] }>(visible ? '/areas' : null);
  const [q, setQ] = useState('');
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- clears the search box when the picker closes
    if (!visible) setQ('');
  }, [visible]);
  const shown = useMemo(() => {
    if (load.status !== 'ok') return [];
    const n = q.trim().toLowerCase();
    return n ? load.data.areas.filter((a) => a.name.toLowerCase().includes(n) || (a.name_te ?? '').includes(q.trim())) : load.data.areas;
  }, [load, q]);

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.page }} edges={['top', 'left', 'right', 'bottom']}>
        <DemoBanner />
        <View style={{ padding: 16, gap: 12, flex: 1 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <AppText variant="title" weight={800} accessibilityRole="header">
              Delivery area
            </AppText>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Close"
              onPress={onClose}
              style={{ minHeight: MIN_TARGET, minWidth: MIN_TARGET, justifyContent: 'center', alignItems: 'center' }}
            >
              <AppText weight={700} color={colors.navy}>
                Close
              </AppText>
            </Pressable>
          </View>
          <TextInput
            value={q}
            onChangeText={setQ}
            placeholder="Search your area"
            placeholderTextColor={colors.muted}
            accessibilityLabel="Search your area"
            autoCorrect={false}
            style={{
              minHeight: MIN_TARGET,
              borderRadius: radii.pill,
              backgroundColor: colors.card,
              paddingHorizontal: 18,
              color: colors.ink,
              fontSize: 15,
              borderWidth: 1.5,
              borderColor: colors.navy,
            }}
          />
          {load.status === 'loading' ? <Loading slow={load.slow} /> : null}
          {load.status === 'error' ? <ErrorBox message={load.message} onRetry={load.reload} /> : null}
          {load.status === 'ok' ? (
            <FlatList
              data={shown}
              keyExtractor={(a) => a.area_id}
              keyboardShouldPersistTaps="always"
              keyboardDismissMode="on-drag"
              ListEmptyComponent={<AppText color={colors.muted}>No area matches &quot;{q.trim()}&quot;. Try another spelling.</AppText>}
              renderItem={({ item }) => (
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={item.name}
                  onPress={() => onPick({ area_id: item.area_id, name: item.name })}
                  style={{ minHeight: MIN_TARGET, justifyContent: 'center', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors.surface }}
                >
                  <AppText weight={600}>{item.name}</AppText>
                  {item.name_te ? (
                    <AppText variant="caption" color={colors.muted}>
                      {item.name_te}
                    </AppText>
                  ) : null}
                </Pressable>
              )}
            />
          ) : null}
        </View>
      </SafeAreaView>
    </Modal>
  );
}
