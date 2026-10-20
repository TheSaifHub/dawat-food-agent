import { useEffect, useState } from 'react';
import { Keyboard, Pressable, StyleSheet, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { AppText } from './AppText';
import { MIN_TARGET, colors, radii } from '@/theme/tokens';

type IconName = keyof typeof Ionicons.glyphMap;

/** Route name -> label and icons. The five tabs of the design. */
export const TABS: Record<string, { label: string; icon: IconName; iconActive: IconName }> = {
  index: { label: 'Home', icon: 'home-outline', iconActive: 'home' },
  chat: { label: 'Dawat AI', icon: 'chatbubble-ellipses-outline', iconActive: 'chatbubble-ellipses' },
  cart: { label: 'Cart', icon: 'cart-outline', iconActive: 'cart' },
  orders: { label: 'Orders', icon: 'receipt-outline', iconActive: 'receipt' },
  profile: { label: 'Profile', icon: 'person-outline', iconActive: 'person' },
};

// The parts of React Navigation's tab-bar props that we use (kept structural so tests need no navigator).
export type TabBarProps = {
  state: { index: number; routes: { key: string; name: string }[] };
  descriptors: Record<string, { options: { tabBarBadge?: string | number } }>;
  navigation: {
    emit: (e: { type: 'tabPress'; target: string; canPreventDefault: true }) => { defaultPrevented: boolean };
    navigate: (name: string) => void;
  };
};

/** Label read aloud for a tab, e.g. "Cart, 2 items". */
export function tabLabel(label: string, badge?: string | number): string {
  if (badge === undefined || badge === '' || badge === 0) return label;
  return `${label}, ${badge} ${Number(badge) === 1 ? 'item' : 'items'}`;
}

/** True while the on-screen keyboard is open: the bar steps aside so it does not float above the keys. */
export function useKeyboardOpen(): boolean {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const show = Keyboard.addListener('keyboardDidShow', () => setOpen(true));
    const hide = Keyboard.addListener('keyboardDidHide', () => setOpen(false));
    return () => {
      show.remove();
      hide.remove();
    };
  }, []);
  return open;
}

export function TabBar({ state, descriptors, navigation }: TabBarProps) {
  const insets = useSafeAreaInsets();
  const keyboardOpen = useKeyboardOpen();
  if (keyboardOpen) return null;
  return (
    <View style={[styles.bar, { paddingBottom: Math.max(insets.bottom, 8) }]} accessibilityRole="tablist">
      {state.routes.map((route, index) => {
        const meta = TABS[route.name];
        if (!meta) return null;
        const focused = state.index === index;
        const badge = descriptors[route.key]?.options.tabBarBadge;
        const onPress = () => {
          const event = navigation.emit({ type: 'tabPress', target: route.key, canPreventDefault: true });
          if (!focused && !event.defaultPrevented) navigation.navigate(route.name);
        };
        return (
          <Pressable
            key={route.key}
            accessibilityRole="tab"
            accessibilityLabel={tabLabel(meta.label, badge)}
            accessibilityState={{ selected: focused }}
            onPress={onPress}
            style={styles.tab}
          >
            <View style={[styles.iconWrap, focused && styles.raised]}>
              {focused ? <Ionicons name="ellipse" size={48} color={colors.sky} style={styles.circle} testID="tab-active-circle" /> : null}
              <Ionicons
                name={focused ? meta.iconActive : meta.icon}
                size={24}
                // navy on the white raised circle and on the white bar is 12.4:1
                color={colors.navy}
              />
              {badge !== undefined && badge !== 0 && badge !== '' ? (
                <View style={styles.badge} testID="tab-badge">
                  <AppText variant="caption" weight={700} color={colors.ink} style={styles.badgeText}>
                    {String(badge)}
                  </AppText>
                </View>
              ) : null}
            </View>
            <AppText variant="caption" weight={focused ? 700 : 500} color={focused ? colors.ink : colors.muted} numberOfLines={1} maxFontSizeMultiplier={1}>
              {meta.label}
            </AppText>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: 'row',
    backgroundColor: colors.card,
    borderTopLeftRadius: radii.lg,
    borderTopRightRadius: radii.lg,
    paddingTop: 8,
    paddingHorizontal: 8,
    elevation: 8,
    shadowColor: colors.navy,
    shadowOpacity: 0.1,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: -2 },
  },
  tab: { flex: 1, alignItems: 'center', justifyContent: 'center', minHeight: MIN_TARGET + 20, gap: 2 },
  iconWrap: { width: 48, height: 48, alignItems: 'center', justifyContent: 'center' },
  raised: { transform: [{ translateY: -8 }] },
  // Raised sky circle (navy icon on sky is 7+:1). Drawn as a glyph: a View with borderRadius rendered as a hard square on the Oppo (Expo Go, Android 14).
  circle: { position: 'absolute', top: 0, left: 0 },
  badge: {
    position: 'absolute',
    top: -2,
    right: -4,
    minWidth: 20,
    minHeight: 20,
    borderRadius: 10,
    paddingHorizontal: 4,
    backgroundColor: colors.accent,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeText: { lineHeight: 16 },
});
