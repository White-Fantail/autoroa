import { afterEach, describe, expect, it, vi } from 'vitest';
import { deleteStoredItem, getStoredItem, setStoredItem } from './storage.web';

const originalLocalStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');

afterEach(() => {
  vi.unstubAllGlobals();
  if (originalLocalStorage) Object.defineProperty(globalThis, 'localStorage', originalLocalStorage);
  else delete (globalThis as { localStorage?: Storage }).localStorage;
});

describe('web storage', () => {
  it('stores and deletes values in localStorage', async () => {
    const values = new Map<string, string>();
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    });

    await setStoredItem('token', 'secret');
    expect(await getStoredItem('token')).toBe('secret');

    await deleteStoredItem('token');
    expect(await getStoredItem('token')).toBeNull();
  });

  it('uses memory storage when browser storage is unavailable', async () => {
    vi.stubGlobal('localStorage', undefined);

    await setStoredItem('draft', 'saved');
    expect(await getStoredItem('draft')).toBe('saved');

    await deleteStoredItem('draft');
    expect(await getStoredItem('draft')).toBeNull();
  });

  it('uses memory storage when the localStorage getter throws', async () => {
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      get: () => {
        throw new Error('Storage access denied');
      },
    });

    await setStoredItem('token', 'secret');
    expect(await getStoredItem('token')).toBe('secret');

    await deleteStoredItem('token');
    expect(await getStoredItem('token')).toBeNull();
  });

  it('uses memory storage when localStorage methods throw', async () => {
    vi.stubGlobal('localStorage', {
      getItem: () => {
        throw new Error('Read denied');
      },
      setItem: () => {
        throw new Error('Write denied');
      },
      removeItem: () => {
        throw new Error('Delete denied');
      },
    });

    await setStoredItem('draft', 'saved');
    expect(await getStoredItem('draft')).toBe('saved');

    await deleteStoredItem('draft');
    expect(await getStoredItem('draft')).toBeNull();
  });

  it('prefers the memory override when browser writes fail', async () => {
    vi.stubGlobal('localStorage', {
      getItem: () => 'old-token',
      setItem: () => {
        throw new Error('Write denied');
      },
      removeItem: vi.fn(),
    });

    await setStoredItem('mixed-write', 'new-token');

    expect(await getStoredItem('mixed-write')).toBe('new-token');
  });

  it('keeps a deletion tombstone when browser deletes fail', async () => {
    vi.stubGlobal('localStorage', {
      getItem: () => 'stale-token',
      setItem: vi.fn(),
      removeItem: () => {
        throw new Error('Delete denied');
      },
    });

    await deleteStoredItem('mixed-delete');

    expect(await getStoredItem('mixed-delete')).toBeNull();
  });
});
