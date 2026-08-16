import {createApiClient} from '../../../packages/api-client/src';
import {deleteStoredItem,getStoredItem,setStoredItem} from './storage';
import {extractGpsFromImageBytes,injectGpsIntoJpeg,sniffImageMime} from './photo-metadata';
const base=process.env.EXPO_PUBLIC_API_URL??'http://localhost:8000/api/v1';
export const api=createApiClient(base,()=>getStoredItem('autoroa_access_token'));
export async function setAccessToken(token:string|null){if(token)await setStoredItem('autoroa_access_token',token);else await deleteStoredItem('autoroa_access_token')}

const supportedImageMimes=new Set(['image/jpeg','image/png','image/webp']);

export async function imageUploadBlob(uri:string,jpegBase64?:string|null){
  const originalResponse=await fetch(uri);
  if(!originalResponse.ok)throw new Error('The selected photo could not be read.');
  const original=await originalResponse.blob();
  const actualMime=await sniffImageMime(original);
  if(supportedImageMimes.has(actualMime))return new Blob([original],{type:actualMime});
  if(!jpegBase64)throw new Error(`Unsupported photo format${actualMime?` (${actualMime})`:''}. Choose or export a JPEG, PNG, or WebP image.`);
  const gps=extractGpsFromImageBytes(await original.arrayBuffer());
  const jpegResponse=await fetch(`data:image/jpeg;base64,${jpegBase64}`);
  if(!jpegResponse.ok)throw new Error('The iPhone photo could not be converted to JPEG.');
  const jpeg=await jpegResponse.blob();
  const normalized=injectGpsIntoJpeg(new Blob([jpeg],{type:'image/jpeg'}),gps);
  if(await sniffImageMime(normalized)!=='image/jpeg')throw new Error('The converted photo is not valid JPEG data.');
  return normalized;
}
export async function uploadImage(uri:string,type:'RECEIPT'|'ODOMETER',jpegBase64?:string|null){
  const blob=await imageUploadBlob(uri,jpegBase64);
  const mimeType=await sniffImageMime(blob);
  if(!supportedImageMimes.has(mimeType))throw new Error('The photo was not uploaded because its actual image format is unsupported.');
  const prepared=await api.post<{storage_token:string;upload_url:string}>('/media/upload-url',{type,mime_type:mimeType,file_size:blob.size});
  const localUpload=prepared.upload_url.startsWith('/');const token=localUpload?await getStoredItem('autoroa_access_token'):null;
  const sent=await fetch(localUpload?`${base}${prepared.upload_url.replace('/api/v1','')}`:prepared.upload_url,{method:'PUT',headers:{'content-type':mimeType,...(token?{authorization:`Bearer ${token}`}:{})},body:blob});if(!sent.ok)throw new Error(`Image upload failed (${sent.status})`)
  return api.post<{id:string}>('/media/complete',{storage_token:prepared.storage_token,type,mime_type:mimeType,file_size:blob.size});
}
