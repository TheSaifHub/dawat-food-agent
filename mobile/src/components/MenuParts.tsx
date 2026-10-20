import { Pressable, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { AppText } from './AppText';
import { FoodPlaceholder } from './FoodPlaceholder';
import { MIN_TARGET, colors, radii } from '@/theme/tokens';

const VEG = '#1B7F3B'; // green mark: 5.3:1 on white
const NONVEG = '#B3261E'; // red mark: 6.5:1 on white

/** The Indian veg / non-veg mark. The words beside it carry the meaning too, so colour is never the only signal. */
export function VegMark({ isVeg, withLabel = true }: { isVeg: boolean; withLabel?: boolean }) {
  const c = isVeg ? VEG : NONVEG;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }} accessible accessibilityLabel={isVeg ? 'Vegetarian' : 'Non-vegetarian'}>
      <View style={{ width: 18, height: 18, borderWidth: 2, borderColor: c, borderRadius: 3, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.card }}>
        <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: c }} />
      </View>
      {withLabel ? (
        <AppText variant="caption" weight={600} color={colors.muted}>
          {isVeg ? 'Veg' : 'Non-veg'}
        </AppText>
      ) : null}
    </View>
  );
}

const SPICE = ['Not spicy', 'Mild', 'Medium', 'Hot'] as const;
export function spiceWord(level: number): string {
  return SPICE[Math.min(Math.max(Math.trunc(level), 0), 3)];
}

export function Spice({ level }: { level: number }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }} accessible accessibilityLabel={`Spice: ${spiceWord(level)}`}>
      {level > 0 ? <Ionicons name="flame" size={14} color={colors.accent} /> : null}
      <AppText variant="caption" weight={600} color={colors.muted}>
        {spiceWord(level)}
      </AppText>
    </View>
  );
}

/** "Add" before there is one in the cart; a − qty + stepper after. The count is the cart's, never the screen's own. */
export function QtyControl({
  qty,
  busy,
  name,
  onAdd,
  onMinus,
}: {
  qty: number;
  busy?: boolean;
  name: string;
  onAdd: () => void;
  onMinus: () => void;
}) {
  if (qty <= 0) {
    return (
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Add ${name}`}
        accessibilityState={{ disabled: !!busy }}
        disabled={busy}
        onPress={onAdd}
        style={{ minHeight: MIN_TARGET, minWidth: 84, borderRadius: radii.pill, borderWidth: 1.5, borderColor: colors.navy, backgroundColor: colors.card, alignItems: 'center', justifyContent: 'center', opacity: busy ? 0.55 : 1 }}
      >
        <AppText weight={700} color={colors.navy}>
          Add
        </AppText>
      </Pressable>
    );
  }
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: colors.navy, borderRadius: radii.pill, opacity: busy ? 0.55 : 1 }}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Remove one ${name}`}
        accessibilityState={{ disabled: !!busy }}
        disabled={busy}
        onPress={onMinus}
        style={{ minHeight: MIN_TARGET, minWidth: MIN_TARGET, alignItems: 'center', justifyContent: 'center' }}
      >
        <Ionicons name="remove" size={20} color={colors.white} />
      </Pressable>
      <AppText weight={700} color={colors.white} accessibilityLabel={`${qty} in cart`} style={{ minWidth: 24, textAlign: 'center' }}>
        {qty}
      </AppText>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Add one more ${name}`}
        accessibilityState={{ disabled: !!busy }}
        disabled={busy}
        onPress={onAdd}
        style={{ minHeight: MIN_TARGET, minWidth: MIN_TARGET, alignItems: 'center', justifyContent: 'center' }}
      >
        <Ionicons name="add" size={20} color={colors.white} />
      </Pressable>
    </View>
  );
}

export type MenuItem = {
  item_id: string;
  name: string;
  price: number;
  is_veg: boolean;
  spice_level: number;
  serves: number;
  category: string;
  course: string;
};

export function MenuItemRow({ item, qty, busy, onAdd, onMinus }: { item: MenuItem; qty: number; busy?: boolean; onAdd: () => void; onMinus: () => void }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: colors.card, borderRadius: radii.md, padding: 12 }}>
      <FoodPlaceholder name={item.name} size={48} />
      <View style={{ flex: 1, gap: 3 }}>
        <AppText weight={700}>{item.name}</AppText>
        <View style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', columnGap: 12, rowGap: 2 }}>
          <VegMark isVeg={item.is_veg} />
          <Spice level={item.spice_level} />
        </View>
        <AppText variant="caption" weight={600}>
          ₹{item.price}
          {item.serves > 1 ? ` · Serves ${item.serves}` : ''}
        </AppText>
      </View>
      <QtyControl qty={qty} busy={busy} name={item.name} onAdd={onAdd} onMinus={onMinus} />
    </View>
  );
}

const ORDER = ['biryani', 'starter', 'curry', 'bread', 'rice', 'dessert', 'drink'];
/** Category sections in a sensible order: the usual courses first, anything else A to Z after. */
export function orderCategories(cats: string[]): string[] {
  const set = [...new Set(cats)];
  return [...ORDER.filter((c) => set.includes(c)), ...set.filter((c) => !ORDER.includes(c)).sort()];
}
export function categoryLabel(c: string): string {
  return c.charAt(0).toUpperCase() + c.slice(1);
}
