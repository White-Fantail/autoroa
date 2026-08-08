import * as SecureStore from 'expo-secure-store';
import {createApiClient} from '../../../packages/api-client/src';
const base=process.env.EXPO_PUBLIC_API_URL??'http://localhost:8000/api/v1';
export const api=createApiClient(base,()=>SecureStore.getItemAsync('carfolio_access_token'));
export async function setAccessToken(token:string|null){if(token)await SecureStore.setItemAsync('carfolio_access_token',token);else await SecureStore.deleteItemAsync('carfolio_access_token')}
export async function uploadImage(uri:string,type:'RECEIPT'|'ODOMETER'){
  const file=await fetch(uri);const blob=await file.blob();const prepared=await api.post<{storage_token:string;upload_url:string}>('/media/upload-url',{type,mime_type:blob.type||'image/jpeg',file_size:blob.size});
  if(!prepared.upload_url.startsWith('mock://')){const sent=await fetch(prepared.upload_url,{method:'PUT',headers:{'content-type':blob.type||'image/jpeg'},body:blob});if(!sent.ok)throw new Error('Image upload failed')}
  return api.post<{id:string}>('/media/complete',{storage_token:prepared.storage_token,type,mime_type:blob.type||'image/jpeg',file_size:blob.size});
}
