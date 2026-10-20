import { useEffect } from 'react';
import { Platform, StatusBar as RNStatusBar } from 'react-native';
import { Stack } from 'expo-router';
import { colors } from '@/theme/tokens';
import { StatusBar } from 'expo-status-bar';
import { useFonts } from 'expo-font';
import * as SplashScreen from 'expo-splash-screen';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { SessionProvider, useSession } from '@/lib/session';
import { AreaProvider } from '@/lib/area';
import { CartProvider } from '@/lib/cart';
import { ChatProvider } from '@/lib/chat-context';
import { Screen } from '@/components/Screen';
import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import {
  PlusJakartaSans_400Regular,
  PlusJakartaSans_500Medium,
  PlusJakartaSans_600SemiBold,
  PlusJakartaSans_700Bold,
  PlusJakartaSans_800ExtraBold,
} from '@expo-google-fonts/plus-jakarta-sans';
import { Outfit_700Bold } from '@expo-google-fonts/outfit';
import {
  NotoSansTelugu_400Regular,
  NotoSansTelugu_500Medium,
  NotoSansTelugu_600SemiBold,
  NotoSansTelugu_700Bold,
} from '@expo-google-fonts/noto-sans-telugu';

SplashScreen.preventAutoHideAsync().catch(() => {});

/** Chooses what the user can reach from who they are. Only a real 401 ever lands on Welcome after launch (lib/session.tsx). */
function Gate() {
  const { state, retry } = useSession();
  if (state.status === 'loading') {
    return (
      <Screen scroll={false}>
        <AppText variant="title" weight={700} accessibilityLiveRegion="polite">
          {state.slow ? 'Waking up Dawat AI…' : 'Loading…'}
        </AppText>
      </Screen>
    );
  }
  if (state.status === 'unreachable') {
    return (
      <Screen scroll={false}>
        <AppText variant="title" weight={700}>
          Can&apos;t reach Dawat
        </AppText>
        <AppText accessibilityLiveRegion="polite">{state.message}</AppText>
        <AppText variant="caption">You are still signed in. Check that the backend is running and the USB link is set up.</AppText>
        <Button label="Try again" onPress={retry} />
      </Screen>
    );
  }
  const signedIn = state.status === 'signedIn';
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Protected guard={state.status === 'signedOut'}>
        <Stack.Screen name="welcome" />
      </Stack.Protected>
      <Stack.Protected guard={signedIn && !state.me.name_confirmed}>
        <Stack.Screen name="confirm-name" />
      </Stack.Protected>
      <Stack.Protected guard={signedIn && state.me.name_confirmed}>
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="restaurants" />
        <Stack.Screen name="restaurant/[branchId]" />
        <Stack.Screen name="review-order" />
        <Stack.Screen name="payment" />
        <Stack.Screen name="orders/[orderNo]" />
      </Stack.Protected>
    </Stack>
  );
}

export default function RootLayout() {
  const [loaded, error] = useFonts({
    PlusJakartaSans_400Regular,
    PlusJakartaSans_500Medium,
    PlusJakartaSans_600SemiBold,
    PlusJakartaSans_700Bold,
    PlusJakartaSans_800ExtraBold,
    Outfit_700Bold,
    NotoSansTelugu_400Regular,
    NotoSansTelugu_500Medium,
    NotoSansTelugu_600SemiBold,
    NotoSansTelugu_700Bold,
  });

  useEffect(() => {
    // Show the app even if a font fails to load (system font is the fallback).
    if (loaded || error) SplashScreen.hideAsync().catch(() => {});
  }, [loaded, error]);

  if (!loaded && !error) return null;
  return (
    <SafeAreaProvider>
      <StatusBar style="dark" />
      {/* Android, when the system draws the status-bar strip itself: butter (the demo banner colour) under dark icons, 13.95:1. Ignored when the app draws edge to edge. */}
      {Platform.OS === 'android' ? <RNStatusBar backgroundColor={colors.butter} barStyle="dark-content" /> : null}
      <SessionProvider>
        <AreaProvider>
          <CartProvider>
            <ChatProvider>
              <Gate />
            </ChatProvider>
          </CartProvider>
        </AreaProvider>
      </SessionProvider>
    </SafeAreaProvider>
  );
}
