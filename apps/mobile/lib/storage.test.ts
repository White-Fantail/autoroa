import {afterEach,describe,expect,it,vi} from 'vitest';

vi.mock('react-native', () => ({Platform: {OS: 'web'}}));
vi.mock('expo-secure-store', () => ({
  getItemAsync: vi.fn(() => Promise.reject(new Error('SecureStore must not be used on web'))),
  setItemAsync: vi.fn(() => Promise.reject(new Error('SecureStore must not be used on web'))),
  deleteItemAsync: vi.fn(() => Promise.reject(new Error('SecureStore must not be used on web'))),
}));

import {deleteStoredItem,getStoredItem,setStoredItem} from './storage';

afterEach(() => vi.unstubAllGlobals());

describe('shared storage on web', () => {
  it('delegates reads, writes, and removals to localStorage', async () => {
    const getItem = vi.fn(() => null);
    const setItem = vi.fn();
    const removeItem = vi.fn();
    vi.stubGlobal('localStorage', {getItem,setItem,removeItem});

    expect(await getStoredItem('session')).toBeNull();
    await setStoredItem('session', 'value');
    await deleteStoredItem('session');

    expect(getItem).toHaveBeenCalledWith('session');
    expect(setItem).toHaveBeenCalledWith('session', 'value');
    expect(removeItem).toHaveBeenCalledWith('session');
  });

  it('remains usable during SSR when localStorage is absent', async () => {
    vi.stubGlobal('localStorage', undefined);

    expect(await getStoredItem('ssr-session')).toBeNull();
    await setStoredItem('ssr-session', 'value');
    expect(await getStoredItem('ssr-session')).toBe('value');
    await deleteStoredItem('ssr-session');
    expect(await getStoredItem('ssr-session')).toBeNull();
  });
});
