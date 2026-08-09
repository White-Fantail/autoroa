const memoryOverrides = new Map<string, string | null>();

function browserStorage(): Storage | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

export async function getStoredItem(key: string): Promise<string | null> {
  if (memoryOverrides.has(key)) return memoryOverrides.get(key) ?? null;

  const storage = browserStorage();
  if (storage) {
    try {
      return storage.getItem(key);
    } catch {}
  }
  return null;
}

export async function setStoredItem(key: string, value: string): Promise<void> {
  const storage = browserStorage();
  if (storage) {
    try {
      storage.setItem(key, value);
      memoryOverrides.delete(key);
      return;
    } catch {}
  }
  memoryOverrides.set(key, value);
}

export async function deleteStoredItem(key: string): Promise<void> {
  const storage = browserStorage();
  if (storage) {
    try {
      storage.removeItem(key);
      memoryOverrides.delete(key);
      return;
    } catch {}
  }
  memoryOverrides.set(key, null);
}
