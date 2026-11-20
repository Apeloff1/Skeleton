import api from '../utils/apiClient';
import {getAuthToken} from '../auth/gameforgeAuth';
const ROOT='/api/dragon-academy/knowledge/game-corpus';
const H=/^[a-f0-9]{64}$/;
function bounded(value:string,n:number){if(typeof value!=='string'||!value.trim()||value.length>n)throw Error('Invalid archive field.');return value;}
function id(value:string){if(!H.test(value))throw Error('Invalid archive identity.');return value;}
type Adapter='manifest'|'steam'|'rss_atom'|'sitemap'|'classified_sitemap'|'eve_sde';
export type Subscription={id:string;url:string;adapter:Adapter;interval_seconds:number;expires_at:number;enabled:number;due:number;failures:number;last_batch:string|null;reason:string|null};
export type SubscriptionInput={url:string;adapter:Adapter;provider?:string;external_id?:string;title?:string;interval_seconds:number;grant_seconds:number;rights_acknowledged:true};
export type DesignProfile={id:string;title:string;example:string;candidate_urls:number;design_load:Record<string,number>;network_authority:false;measured:false};
export type DatasetVersion={id:string;game:string;dataset:string;source:string;label:string;expected_rows:number;rows:number;next_page:number;chain:string;state:'building'|'sealed';created_at:number;expires_at:number};
export type DatasetRecord={key:string;record:Record<string,unknown>;sha256:string};
export type DatasetEdge={record_key:string;relation:string;target:string};
const num=(x:unknown):x is number=>typeof x==='number'&&Number.isSafeInteger(x)&&x>=0;
async function get<T>(path:string,signal?:AbortSignal){
 const token=getAuthToken(),p=await api.get<T>(ROOT+path,{signal,retries:0,maxResponseChars:2*1024*1024});
 if(!p.ok||p.data===null||token!==getAuthToken()||signal?.aborted)throw Error('Archive operation unavailable.');
 return p.data;
}
async function post<T>(path:string,body:unknown,signal?:AbortSignal){
 const token=getAuthToken(),p=await api.post<T>(ROOT+path,body,{signal,retries:0,timeoutMs:65000});
 if(!p.ok||p.data===null||token!==getAuthToken()||signal?.aborted)throw Error('Archive operation unavailable.');
 return p.data;
}
export async function getDesignProfiles(signal?:AbortSignal){
 const p=await get<{profiles:DesignProfile[];architectural_limits:Record<string,number>;production_capacity_verified:false}>('/design-profiles',signal);
 if(!p||p.production_capacity_verified!==false||!Array.isArray(p.profiles)||p.profiles.length>16||p.profiles.some(x=>!x||x.network_authority!==false||x.measured!==false||typeof x.id!=='string'||typeof x.title!=='string'||typeof x.example!=='string'||!num(x.candidate_urls)))throw Error('Invalid design profiles.');
 return p;
}
export async function importDesignProfile(profile:string,operation:string,signal?:AbortSignal){
 const p=await post<{batch_id:string;total:number;network_executed:false}>('/design-profiles/'+encodeURIComponent(bounded(profile,64))+'?operation='+encodeURIComponent(bounded(operation,128)),{},signal);
 if(!p||!H.test(p.batch_id)||!num(p.total)||p.network_executed!==false)throw Error('Invalid profile import.');
 return p;
}
export async function subscribeDiscovery(input:SubscriptionInput,signal?:AbortSignal){
 if(!input.rights_acknowledged||!input.url.startsWith('https://')||!num(input.interval_seconds)||!num(input.grant_seconds))throw Error('Explicit feed rights and HTTPS required.');
 const p=await post<{subscription_id:string;expires_at:number;capture_granted:false;network_executed:false}>('/discovery/subscriptions',input,signal);
 if(!p||!H.test(p.subscription_id)||!num(p.expires_at)||p.capture_granted!==false||p.network_executed!==false)throw Error('Invalid subscription receipt.');
 return p;
}
export async function subscriptions(after?:string,signal?:AbortSignal){
 const p=await get<{subscriptions:Subscription[];next_cursor:string|null;capture_granted:false}>('/discovery/subscriptions?limit=32'+(after?'&after='+id(after):''),signal);
 if(!p||p.capture_granted!==false||!Array.isArray(p.subscriptions)||p.subscriptions.length>32||p.subscriptions.some(x=>!x||!H.test(x.id)||typeof x.url!=='string'||!['manifest','steam','rss_atom','sitemap','classified_sitemap','eve_sde'].includes(x.adapter)||!num(x.expires_at)||!num(x.due)||!num(x.failures)||!num(x.interval_seconds)||![0,1].includes(x.enabled))||p.next_cursor!==null&&!H.test(p.next_cursor))throw Error('Invalid discovery status.');
 return p;
}
export async function revokeDiscovery(subscription:string,signal?:AbortSignal){
 const token=getAuthToken();
 const p=await api.delete<{revoked:boolean;capture_granted:false}> (ROOT+'/discovery/subscriptions/'+id(subscription),{signal,retries:0});
 if(!p.ok||!p.data||p.data.revoked!==true||p.data.capture_granted!==false||token!==getAuthToken())throw Error('Discovery revocation unavailable.');
}
export async function datasetVersions(game:string,after?:string,signal?:AbortSignal){
 const p=await get<{versions:DatasetVersion[];next_cursor:string|null;source_verified:false;training_allowed:false}>('/'+id(game)+'/datasets'+(after?'?after='+id(after):''),signal);
 if(!p||p.source_verified!==false||p.training_allowed!==false||!Array.isArray(p.versions)||p.versions.length>32||p.versions.some(x=>!x||!H.test(x.id)||x.game!==game||!H.test(x.source)||!H.test(x.chain)||typeof x.label!=='string'||typeof x.dataset!=='string'||!num(x.expected_rows)||!num(x.rows)||x.rows>x.expected_rows||!num(x.expires_at)||!['building','sealed'].includes(x.state))||p.next_cursor!==null&&!H.test(p.next_cursor))throw Error('Invalid dataset version listing.');
 return p;
}
export async function datasetRecords(game:string,version:string,query?:string,after?:string,signal?:AbortSignal){
 const params=new URLSearchParams({limit:'8'});if(query?.trim())params.set('q',bounded(query,256));if(after)params.set('after',bounded(after,128));
 const p=await get<{version:string;records:DatasetRecord[];next_cursor:string|null;label:string;source_verified:false;training_allowed:false}>('/'+id(game)+'/datasets/'+id(version)+'/records?'+params,signal);
 if(!p||p.version!==version||p.source_verified!==false||p.training_allowed!==false||!Array.isArray(p.records)||p.records.length>8||p.records.some(x=>!x||typeof x.key!=='string'||!H.test(x.sha256)||!x.record||typeof x.record!=='object'||Array.isArray(x.record))||p.next_cursor!==null&&typeof p.next_cursor!=='string')throw Error('Invalid dataset records.');
 return p;
}
export async function datasetEdges(game:string,version:string,record:string,reverse:boolean,signal?:AbortSignal){
 const p=await get<{edges:DatasetEdge[];truncated:boolean;source_verified:false}>('/'+id(game)+'/datasets/'+id(version)+'/relations/'+encodeURIComponent(bounded(record,128))+'?reverse='+reverse,signal);
 if(!p||p.source_verified!==false||typeof p.truncated!=='boolean'||!Array.isArray(p.edges)||p.edges.length>100||p.edges.some(x=>!x||typeof x.record_key!=='string'||typeof x.relation!=='string'||typeof x.target!=='string'))throw Error('Invalid dataset relations.');
 return p;
}
