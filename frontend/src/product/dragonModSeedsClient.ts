import api from '../utils/apiClient';
import {getAuthToken} from '../auth/gameforgeAuth';

const ROOT='/api/dragon-academy/knowledge/game-corpus/mod-seeds';
const HASH=/^[0-9a-f]{64}$/;
const APP=/^[1-9][0-9]{1,11}$/;
const CURSOR=/^[0-9a-f]{64}:[0-9a-f]{64}$/;
const GROUP=/^[a-z][a-z0-9_-]{0,63}$/;
const LANES=['game_surfaces','mod_platforms','tool_repositories','specialist_sites'] as const;
export type SeedLane=typeof LANES[number];
export type SeedSummary={revision:string;legacy_records:number;legacy_unique_locators:number;expanded_records:number;overlap_with_legacy:number;total_unique_locators:number;distinct_hosts:number;mod_related_records:number;curated_locator_records:number;generated_route_records:number;candidate_apps:number;candidate_repositories:number;candidate_community_slugs:number;duplicate_routes_elided:number;lanes:Record<SeedLane,number>;providers:Record<string,number>;groups:Record<string,number>;catalogue_only:true;network_authorized:false;source_verified:false;training_allowed:false;physical_capacity_verified:false};
export type SeedApp={appid:string;title:string;group:string;candidate_game_id:string;seeds:number;mod_related_seeds:number;verified:false};
export type SeedLocator={seed_id:string;lane:SeedLane;group:string;title:string;label:string;url:string;provider:string;kind:string;family:string;view_mode:string;basis:'generated_provider_route'|'generated_repository_route'|'curated_locator';appid:string|null;candidate_game_id:string|null;mod_related:boolean;verified:false;network_authorized:false;provider_identity_verified:false};
type Flags={catalogue_only:true;network_authorized:false;source_verified:false;training_allowed:false};
type Receipt={batch_id:string;total:number;replayed:boolean;network_executed:false;revision:string;selected:number;capture_granted:false;source_verified:false;training_allowed:false};
export type AppReceipt=Receipt&{applications:{appid:string;game_id:string;seeds:number}[]};
export type AttachReceipt=Receipt&{game_id:string};
const fail=():never=>{throw Error('Mod seed catalogue response invalid or unavailable.');};
const hash=(x:unknown):x is string=>typeof x==='string'&&HASH.test(x);
const app=(x:unknown):x is string=>typeof x==='string'&&APP.test(x);
const id=(x:unknown):x is string=>typeof x==='string'&&GROUP.test(x);
const count=(x:unknown,max=100000):x is number=>typeof x==='number'&&Number.isSafeInteger(x)&&x>=0&&x<=max;
const text=(x:unknown,max:number):x is string=>typeof x==='string'&&x.length>0&&x.length<=max;
const flags=(x:Flags)=>!!x&&x.catalogue_only===true&&x.network_authorized===false&&x.source_verified===false&&x.training_allowed===false;
const cursor=(x:unknown):x is string=>typeof x==='string'&&CURSOR.test(x);
function url(x:unknown){if(!text(x,2048)||!x.startsWith('https://')||/[\s\\?#]/.test(x))return false;try{const u=new URL(x);return u.protocol==='https:'&&u.port===''&&!u.username&&!u.password&&u.hostname.includes('.');}catch{return false;}}
function counts(x:unknown,total:number){return !!x&&typeof x==='object'&&!Array.isArray(x)&&Object.keys(x).length<=128&&Object.entries(x).every(([k,v])=>id(k)&&count(v,total))&&Object.values(x).reduce((s,n)=>s+Number(n),0)===total;}
async function get<T>(path:string,signal?:AbortSignal):Promise<T>{
 const token=getAuthToken(),p=await api.get<T>(ROOT+path,{signal,retries:0,timeoutMs:20000,maxResponseChars:512*1024});
 if(!token||token!==getAuthToken()||signal?.aborted||!p.ok||!p.data)return fail();return p.data;
}
async function post<T>(path:string,body:Record<string,unknown>,operation:string,signal?:AbortSignal):Promise<T>{
 const token=getAuthToken(),p=await api.post<T>(ROOT+path,body,{signal,retries:0,timeoutMs:65000,idempotencyKey:operation});
 if(!token||token!==getAuthToken()||signal?.aborted||!p.ok||!p.data)return fail();return p.data;
}
export async function seedSummary(signal?:AbortSignal){
 const x=await get<SeedSummary>('',signal);
 if(!flags(x)||!hash(x.revision)||x.physical_capacity_verified!==false||
 !count(x.legacy_records)||!count(x.legacy_unique_locators,x.legacy_records)||!count(x.expanded_records)||!count(x.overlap_with_legacy,x.legacy_unique_locators)||
 !count(x.total_unique_locators,120000)||x.total_unique_locators!==x.legacy_unique_locators+x.expanded_records-x.overlap_with_legacy||
 !count(x.distinct_hosts,x.total_unique_locators)||!count(x.mod_related_records,x.expanded_records)||!count(x.curated_locator_records,x.expanded_records)||
 !count(x.generated_route_records,x.expanded_records)||x.generated_route_records+x.curated_locator_records!==x.expanded_records||
 !count(x.candidate_apps,8192)||!count(x.candidate_repositories,8192)||!count(x.candidate_community_slugs,8192)||!count(x.duplicate_routes_elided)||
 !counts(x.lanes,x.expanded_records)||!counts(x.groups,x.expanded_records)||!counts(x.providers,x.expanded_records)||
 Object.keys(x.lanes).some(k=>!LANES.includes(k as SeedLane)))return fail();
 return x;
}
function validApp(a:SeedApp){
 return !!a&&app(a.appid)&&text(a.title,256)&&id(a.group)&&hash(a.candidate_game_id)&&count(a.seeds,64)&&a.seeds>0&&count(a.mod_related_seeds,a.seeds)&&a.verified===false;
}
function validSeed(s:SeedLocator){
 return !!s&&hash(s.seed_id)&&LANES.includes(s.lane)&&id(s.group)&&text(s.title,256)&&text(s.label,160)&&url(s.url)&&id(s.provider)&&id(s.kind)&&id(s.family)&&['text','image','video','audio','document','external'].includes(s.view_mode)&&['generated_provider_route','generated_repository_route','curated_locator'].includes(s.basis)&&
 (s.appid===null?s.candidate_game_id===null:app(s.appid)&&hash(s.candidate_game_id))&&typeof s.mod_related==='boolean'&&s.verified===false&&s.network_authorized===false&&s.provider_identity_verified===false;
}
function next(x:string|null,rows:string[]){return x===null||cursor(x)&&rows.length===32&&x.slice(65)===rows[rows.length-1];}
export async function seedApps(summary:SeedSummary,q:string,after?:string,signal?:AbortSignal){
 if(q.length>256||after!==undefined&&!cursor(after))return fail();
 const params=new URLSearchParams({limit:'32'});if(q.trim())params.set('q',q.trim());if(after)params.set('after',after);
 const p=await get<Flags&{revision:string;applications:SeedApp[];next_cursor:string|null}>('/applications?'+params,signal);
 if(!flags(p)||p.revision!==summary.revision||!Array.isArray(p.applications)||p.applications.length>32||p.applications.some(a=>!validApp(a))||
 new Set(p.applications.map(a=>a.appid)).size!==p.applications.length||!next(p.next_cursor,p.applications.map(a=>a.candidate_game_id)))return fail();
 return p;
}
export type SeedFilter={q:string;lane:SeedLane|'';provider:string;appid?:string;modOnly:boolean};
export async function seedLocators(summary:SeedSummary,f:SeedFilter,after?:string,signal?:AbortSignal){
 if(f.q.length>256||f.lane&&!LANES.includes(f.lane)||f.provider&&!Object.prototype.hasOwnProperty.call(summary.providers,f.provider)||f.appid!==undefined&&!app(f.appid)||after!==undefined&&!cursor(after))return fail();
 const params=new URLSearchParams({limit:'32',mod_only:String(f.modOnly)});
 if(f.q.trim())params.set('q',f.q.trim());if(f.lane)params.set('lane',f.lane);if(f.provider)params.set('provider',f.provider);if(f.appid)params.set('appid',f.appid);if(after)params.set('after',after);
 const p=await get<Flags&{revision:string;seeds:SeedLocator[];next_cursor:string|null}>('/locators?'+params,signal);
 if(!flags(p)||p.revision!==summary.revision||!Array.isArray(p.seeds)||p.seeds.length>32||p.seeds.some(s=>!validSeed(s)||f.lane&&s.lane!==f.lane||f.provider&&s.provider!==f.provider||f.appid&&s.appid!==f.appid||f.modOnly&&!s.mod_related)||
 new Set(p.seeds.map(s=>s.seed_id)).size!==p.seeds.length||!next(p.next_cursor,p.seeds.map(s=>s.seed_id)))return fail();
 return p;
}
function receipt(p:Receipt,summary:SeedSummary,selected:number){
 return !!p&&p.revision===summary.revision&&hash(p.batch_id)&&p.selected===selected&&count(p.total,selected)&&p.total>0&&typeof p.replayed==='boolean'&&p.capture_granted===false&&p.network_executed===false&&p.source_verified===false&&p.training_allowed===false;
}
export async function importSeedApps(summary:SeedSummary,apps:SeedApp[],modOnly:boolean,operation:string,signal?:AbortSignal){
 if(!text(operation,128)||apps.length<1||apps.length>128||apps.some(a=>!validApp(a))||new Set(apps.map(x=>x.appid)).size!==apps.length)return fail();
 const ids=apps.map(x=>x.appid).sort(),amount=apps.reduce((n,x)=>n+(modOnly?x.mod_related_seeds:x.seeds),0);
 const p=await post<AppReceipt>('/import-applications',{revision:summary.revision,operation,appids:ids,mod_only:modOnly,acknowledged:true},operation,signal);
 if(!receipt(p,summary,amount)||!Array.isArray(p.applications)||p.applications.length!==apps.length||
 p.applications.some((r,i)=>r.appid!==ids[i]||!apps.some(a=>a.appid===r.appid&&r.game_id===a.candidate_game_id&&r.seeds===(modOnly?a.mod_related_seeds:a.seeds))))return fail();
 return p;
}
export async function attachSeedSources(summary:SeedSummary,game:string,seeds:SeedLocator[],operation:string,signal?:AbortSignal){
 if(!hash(game)||!text(operation,128)||seeds.length<1||seeds.length>256||new Set(seeds.map(s=>s.seed_id)).size!==seeds.length||seeds.some(s=>!validSeed(s)||s.candidate_game_id!==null&&s.candidate_game_id!==game))return fail();
 const p=await post<AttachReceipt>('/attach',{revision:summary.revision,operation,game,seed_ids:seeds.map(x=>x.seed_id).sort(),acknowledged:true},operation,signal);
 if(!receipt(p,summary,seeds.length)||p.game_id!==game)return fail();return p;
}
