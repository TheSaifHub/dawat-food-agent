// The sign-in token lives only in the platform keystore (expo-secure-store), never in AsyncStorage, never logged.
// A keystore failure is treated as "no token" on read (the user signs in again) and as a failed save on write.

import * as SecureStore from 'expo-secure-store';

const KEY = 'dawat.access_token';

export async function readToken(): Promise<string | null> {
  try {
    return (await SecureStore.getItemAsync(KEY)) || null;
  } catch {
    return null;
  }
}

/** True if the token was saved. */
export async function saveToken(token: string): Promise<boolean> {
  try {
    await SecureStore.setItemAsync(KEY, token);
    return true;
  } catch {
    return false;
  }
}

export async function clearToken(): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(KEY);
  } catch {
    // nothing more to do; the in-memory session is already cleared by the caller
  }
}
