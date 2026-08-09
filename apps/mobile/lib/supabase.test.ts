import {beforeEach,describe,expect,it,vi} from 'vitest';
import {supabase} from './supabase';

const {createClient,getStoredItem} = vi.hoisted(() => ({
  createClient: vi.fn((_url: string, _key: string, _options: any) => ({auth: {}})),
  getStoredItem: vi.fn(() => Promise.resolve(null)),
}));

vi.mock('@supabase/supabase-js', () => ({createClient}));
vi.mock('./storage', () => ({
  getStoredItem,
  setStoredItem: vi.fn(),
  deleteStoredItem: vi.fn(),
}));

describe('supabase client', () => {
  beforeEach(() => {
    createClient.mockClear();
    getStoredItem.mockClear();
    process.env.EXPO_PUBLIC_SUPABASE_URL = 'https://example.supabase.co';
    process.env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY = 'test-key';
  });

  it('reuses a persistent client backed by app storage', async () => {
    const first = supabase();
    const second = supabase();

    expect(first).toBe(second);
    expect(createClient).toHaveBeenCalledTimes(1);
    expect(createClient).toHaveBeenCalledWith(
      'https://example.supabase.co',
      'test-key',
      expect.objectContaining({
        auth: expect.objectContaining({
          persistSession: true,
          autoRefreshToken: true,
          storage: expect.objectContaining({
            getItem: expect.any(Function),
            setItem: expect.any(Function),
            removeItem: expect.any(Function),
          }),
        }),
      }),
    );
    const options = createClient.mock.calls[0]?.[2];
    expect(await options?.auth?.storage?.getItem('supabase-session')).toBeNull();
    expect(getStoredItem).toHaveBeenCalledWith('supabase-session');
  });
});
