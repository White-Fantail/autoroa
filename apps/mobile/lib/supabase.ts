import {createClient} from '@supabase/supabase-js';
export function supabase(){const url=process.env.EXPO_PUBLIC_SUPABASE_URL;const key=process.env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY;if(!url||!key)throw new Error('Supabase is not configured');return createClient(url,key,{auth:{persistSession:false,autoRefreshToken:true,detectSessionInUrl:false}})}
