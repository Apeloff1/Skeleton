import api,{prepareApiRequest} from '../utils/apiClient';
import {API_BASE} from '../utils/apiBase';
import {getAuthToken} from '../auth/gameforgeAuth';

const ROOT='/api/dragon-academy/knowledge';
const SHA=/^[a-f0-9]{64}$/;
const MIMES=['video/mp4','video/webm','audio/mpeg','audio/ogg','audio/wav','image/png','image/jpeg','image/webp'] as const;
export type MediaMime=typeof MIMES[number];
export type MediaRecord={media_id:string;game_id:string;source_id:string;mime:MediaMime;total_bytes:number;sha256:string;state:'building'|'sealed';created_at:number;expires_at:number;local_user_supplied:true;source_verified:false;training_allowed:false};
export const BLOCK=2*1024*1024;
export const MAX_BROWSER_BYTES=64*1024*1024;
const id=(s:string)=>{if(!SHA.test(s))throw Error('Invalid media identity.');return s;};
export function allowedMediaMime(s:string):s is MediaMime{return (MIMES as readonly string[]).includes(s);}
function check(x:MediaRecord):MediaRecord{
 if(!x||!SHA.test(x.media_id)||!SHA.test(x.game_id)||!SHA.test(x.source_id)||!SHA.test(x.sha256)||!allowedMediaMime(x.mime)||
 !Number.isSafeInteger(x.total_bytes)||x.total_bytes<1||x.total_bytes>1024**3||
 !Number.isFinite(x.created_at)||!Number.isFinite(x.expires_at)||x.expires_at<=x.created_at||
 !['building','sealed'].includes(x.state)||x.local_user_supplied!==true||x.source_verified!==false||x.training_allowed!==false)throw Error('Invalid media receipt.');
 return x;
}
function absolute(path:string){
 const base=new URL(API_BASE);
 const target=new URL(API_BASE.replace(/\/$/,'')+ROOT+path);
 if(target.origin!==base.origin||target.protocol!=='https:'&&!(target.protocol==='http:'&&['localhost','127.0.0.1','[::1]'].includes(target.hostname)))throw Error('Media requires a trusted TLS or local backend.');
 return target.href;
}
async function raw(path:string,method:string,signal?:AbortSignal,body?:BodyInit,headers:Record<string,string>={}){
 const url=absolute(path);
 const session=await prepareApiRequest(url,headers,signal);
 try{
  if(!session.authenticated||!session.current())throw Error('Authentication required.');
  const response=await fetch(url,{method,body,headers:session.headers,signal:session.signal,redirect:'error',cache:'no-store',credentials:'omit'});
  if(!response.ok||!session.current())throw Error('Media operation unavailable ('+response.status+').');
  return {response,session};
 }catch(e){session.dispose();throw e;}
}
export async function listMedia(game:string,source:string,signal?:AbortSignal){
 const token=getAuthToken();
 const p=await api.get<{media:MediaRecord[];next_cursor:string|null}>(ROOT+'/game-corpus/'+id(game)+'/sources/'+id(source)+'/media',{signal,retries:0});
 if(token!==getAuthToken()||!p.ok||!p.data||!Array.isArray(p.data.media)||p.data.media.length>32)throw Error('Media library unavailable.');
 return p.data.media.map(x=>{const item=check(x);if(item.game_id!==game||item.source_id!==source)throw Error('Media source changed.');return item;});
}
export async function beginMedia(input:{game:string;source:string;observation_digest:string;operation:string;mime:MediaMime;total_bytes:number;sha256:string;rights_acknowledged:true;grant_seconds:number},signal?:AbortSignal){
 const token=getAuthToken();
 const p=await api.post<MediaRecord&{chunk_bytes:number}>(ROOT+'/media',input,{signal,retries:0,timeoutMs:65000});
 if(token!==getAuthToken()||!p.ok||!p.data||p.data.chunk_bytes!==BLOCK)throw Error('Media intake unavailable.');
 const x=check(p.data);if(x.game_id!==input.game||x.source_id!==input.source||x.sha256!==input.sha256||x.total_bytes!==input.total_bytes||x.mime!==input.mime)throw Error('Media intake mismatch.');
 return x;
}
export async function appendMedia(media:string,ordinal:number,bytes:Blob,signal?:AbortSignal){
 if(!Number.isInteger(ordinal)||ordinal<0||ordinal>=512||!bytes.size||bytes.size>BLOCK)throw Error('Invalid media block.');
 const {response,session}=await raw('/media/'+id(media)+'/chunks/'+ordinal,'PUT',signal,bytes,{'Content-Type':'application/octet-stream'});
 try{const body=await response.json();if(!session.current()||body.media_id!==media||body.ordinal!==ordinal||!SHA.test(body.sha256)||body.stored!==true)throw Error('Media block acknowledgement differs.');}
 finally{session.dispose();}
}
export async function sealMedia(media:string,signal?:AbortSignal){
 const token=getAuthToken();
 const p=await api.post<MediaRecord>(ROOT+'/media/'+id(media)+'/seal',{}, {signal,retries:0,timeoutMs:120000});
 if(token!==getAuthToken()||!p.ok||!p.data)throw Error('Media sealing unavailable.');
 const x=check(p.data);if(x.state!=='sealed'||x.media_id!==media)throw Error('Media seal mismatch.');return x;
}
export async function revokeMedia(media:string,signal?:AbortSignal){
 const {response,session}=await raw('/media/'+id(media),'DELETE',signal);
 try{const p=await response.json();if(!session.current()||p.revoked!==true)throw Error('Media revocation not confirmed.');}
 finally{session.dispose();}
}
export async function verifiedBrowserMedia(record:MediaRecord,signal?:AbortSignal){
 if(record.state!=='sealed'||record.total_bytes>MAX_BROWSER_BYTES||record.expires_at*1000<=Date.now())throw Error('Browser playback requires a live sealed item of at most 64 MiB.');
 const {response,session}=await raw('/media/'+id(record.media_id)+'/content','GET',signal);
 try{
  if(response.headers.get('Content-Type')?.split(';')[0]!==record.mime||Number(response.headers.get('Content-Length'))!==record.total_bytes||!response.body)throw Error('Media length or type differs.');
  const reader=response.body.getReader();let total=0;const pieces:Uint8Array[]=[];
  try{
   while(true){const {done,value}=await reader.read();if(done)break;if(!session.current()||!value||total+value.byteLength>record.total_bytes)throw Error('Media stream exceeded bound.');total+=value.byteLength;pieces.push(value);}
  }finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
  if(total!==record.total_bytes||!session.current()||record.expires_at*1000<=Date.now())throw Error('Media permission or length changed.');
  const data=new Uint8Array(total);let offset=0;for(const piece of pieces){data.set(piece,offset);offset+=piece.length;}
  const hash=Array.from(new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256',data))).map(x=>x.toString(16).padStart(2,'0')).join('');
  if(!session.current()||hash!==record.sha256)throw Error('Media integrity mismatch.');
  return new Blob([data],{type:record.mime});
 }finally{session.dispose();}
}
export function nativeMediaSource(record:MediaRecord){
 if(record.state!=='sealed'||record.expires_at*1000<=Date.now())throw Error('Local video is unavailable.');
 const token=getAuthToken();if(!token)throw Error('Authentication required.');
 return {uri:absolute('/media/'+id(record.media_id)+'/content'),headers:{Authorization:'Bearer '+token},useCaching:false};
}


export async function verifyMediaAuthority(record:MediaRecord,signal?:AbortSignal){
 const token=getAuthToken();
 const p=await api.get<MediaRecord>(ROOT+'/media/'+id(record.media_id)+'/metadata',{signal,retries:0,timeoutMs:8000});
 if(!p.ok||!p.data||token!==getAuthToken())throw Error('Media retention authority unavailable.');
 const x=check(p.data);
 if(x.media_id!==record.media_id||x.sha256!==record.sha256||x.mime!==record.mime||x.total_bytes!==record.total_bytes||x.game_id!==record.game_id||x.source_id!==record.source_id||x.state!=='sealed'||x.expires_at*1000<=Date.now())throw Error('Media authority changed.');
 return x;
}
