import * as SecureStore from 'expo-secure-store';
import {Platform} from 'react-native';

const webFallback = new Map<string, string | null>();

function browserStorage(): Storage | null {
  if (Platform.OS !== 'web') return null;
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

export async function getStoredItem(key: string): Promise<string | null> {
  if (Platform.OS === 'web') {
    if (webFallback.has(key)) return webFallback.get(key) ?? null;
    try {
      return browserStorage()?.getItem(key) ?? null;
    } catch {
      return null;
    }
  }
  return SecureStore.getItemAsync(key);
}

export async function setStoredItem(key: string, value: string): Promise<void> {
  if (Platform.OS === 'web') {
    try {
      const storage = browserStorage();
      if (!storage) throw new Error('Browser storage is unavailable');
      storage.setItem(key, value);
      webFallback.delete(key);
    } catch {
      webFallback.set(key, value);
    }
    return;
  }
  await SecureStore.setItemAsync(key, value);
}

export async function deleteStoredItem(key: string): Promise<void> {
  if (Platform.OS === 'web') {
    try {
      const storage = browserStorage();
      if (!storage) throw new Error('Browser storage is unavailable');
      storage.removeItem(key);
      webFallback.delete(key);
    } catch {
      webFallback.set(key, null);
    }
    return;
  }
  await SecureStore.deleteItemAsync(key);
}
