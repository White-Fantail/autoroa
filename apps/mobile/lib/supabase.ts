import {createClient} from '@supabase/supabase-js';
import {deleteStoredItem,getStoredItem,setStoredItem} from './storage';

let client: ReturnType<typeof createClient> | undefined;

export function supabase() {
  if (client) return client;

  const url = process.env.EXPO_PUBLIC_SUPABASE_URL;
  const key = process.env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) throw new Error('Supabase is not configured');

  client = createClient(url, key, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: false,
      storage: {
        getItem: getStoredItem,
        setItem: setStoredItem,
        removeItem: deleteStoredItem,
      },
    },
  });
  return client;
}
