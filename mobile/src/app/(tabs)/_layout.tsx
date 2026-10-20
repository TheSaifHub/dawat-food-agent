import { Tabs } from 'expo-router';
import { TabBar, type TabBarProps } from '@/components/TabBar';
import { useCart } from '@/lib/cart';

export default function TabsLayout() {
  const { itemCount } = useCart(); // a count of items in the server cart, not a price
  return (
    <Tabs
      screenOptions={{ headerShown: false }}
      tabBar={(props) => <TabBar {...(props as unknown as TabBarProps)} />}
    >
      <Tabs.Screen name="index" options={{ title: 'Home' }} />
      <Tabs.Screen name="chat" options={{ title: 'Dawat AI' }} />
      <Tabs.Screen name="cart" options={{ title: 'Cart', tabBarBadge: itemCount > 0 ? itemCount : undefined }} />
      <Tabs.Screen name="orders" options={{ title: 'Orders' }} />
      <Tabs.Screen name="profile" options={{ title: 'Profile' }} />
    </Tabs>
  );
}
