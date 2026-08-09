import * as SecureStore from 'expo-secure-store';

export async function getStoredItem(key: string): Promise<string | null> {
  return SecureStore.getItemAsync(key);
}

export async function setStoredItem(key: string, value: string): Promise<void> {
  await SecureStore.setItemAsync(key, value);
}

export async function deleteStoredItem(key: string): Promise<void> {
  await SecureStore.deleteItemAsync(key);
}
