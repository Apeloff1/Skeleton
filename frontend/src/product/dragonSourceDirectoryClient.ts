import api from '../utils/apiClient';
import {getAuthToken} from '../auth/gameforgeAuth';

const ROOT='/api/dragon-academy/knowledge/game-corpus/source-directory';
const SHA=/^[0-9a-f]{64}$/;
const SLUG=/^[a-z0-9][a-z0-9-]{0,63}$/;
const CATEGORY=/^[a-z][a-z_]{0,31}$/;
const MODES=['text','image','video','audio','document','external'];
type Scope='game'|'franchise'|'multi_game_directory';
export type DirectoryGroup={id:string;domain:string;title:string|null;scope:Scope;leads:number;families:Record<string,number>;preset_game_id:string|null};
export type DirectorySummary={revision:string;groups:DirectoryGroup[];total_leads:number;distinct_origins:number;source_classes:number;families:number;catalogue_only:true;network_authorized:false;training_allowed:false};
export type DirectoryLead={lead_id:string;group:string;domain:string;label:string;url:string;provider:string;kind:string;family:string;view_mode:string;scope:Scope;verified:false;network_authorized:false};
export type DirectoryPage={revision:string;leads:DirectoryLead[];next_cursor:string|null;catalogue_only:true;network_authorized:false;training_allowed:false};
export type DirectoryBinding={batch_id:string;game_id:string;directory_revision:string;selected:number;total:number;replayed:boolean;network_executed:false;capture_granted:false;source_verified:false;training_allowed:false};
const fail=():never=>{throw Error('Source directory response invalid or unavailable.');};
const hash=(v:unknown):v is string=>typeof v==='string'&&SHA.test(v);
const slug=(v:unknown):v is string=>typeof v==='string'&&SLUG.test(v);
const category=(v:unknown):v is string=>typeof v==='string'&&CATEGORY.test(v);
const count=(v:unknown,max:number):v is number=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0&&v<=max;
const text=(x:unknown,max:number):x is string=>typeof x==='string'&&x.length>0&&x.length<=max;
const scope=(x:unknown):x is Scope=>x==='game'||x==='franchise'||x==='multi_game_directory';
const cursor=(x:unknown):x is string=>typeof x==='string'&&/^[0-9a-f]{64}:[0-9a-f]{64}$/.test(x);
function flags(x:{catalogue_only:unknown;network_authorized:unknown;training_allowed:unknown}){return x.catalogue_only===true&&x.network_authorized===false&&x.training_allowed===false;}
function validGroup(g:DirectoryGroup){
 return !!g&&slug(g.id)&&slug(g.domain)&&scope(g.scope)&&count(g.leads,20000)&&g.leads>0&&!!g.families&&typeof g.families==='object'&&!Array.isArray(g.families)&&Object.keys(g.families).length<=128&&Object.entries(g.families).every(([k,v])=>category(k)&&count(v,g.leads)&&v>0)&&Object.values(g.families).reduce((n,v)=>n+v,0)===g.leads&&
 (g.scope==='multi_game_directory'?g.title===null&&g.preset_game_id===null:text(g.title,256)&&hash(g.preset_game_id));
}
function validLead(x:DirectoryLead,g:DirectoryGroup){
 return !!x&&hash(x.lead_id)&&x.group===g.id&&x.domain===g.domain&&x.scope===g.scope&&text(x.label,160)&&text(x.url,2048)&&x.url.startsWith('https://')&&category(x.provider)&&category(x.kind)&&category(x.family)&&Object.hasOwn(g.families,x.family)&&MODES.includes(x.view_mode)&&x.verified===false&&x.network_authorized===false;
}
async function get<T>(path:string,signal?:AbortSignal):Promise<T>{
 const account=getAuthToken();const p=await api.get<T>(ROOT+path,{signal,retries:0,timeoutMs:15000,maxResponseChars:512*1024});
 if(!account||account!==getAuthToken()||signal?.aborted||!p.ok||p.data===null)return fail();
 return p.data;
}
export async function directorySummary(signal?:AbortSignal){
 const p=await get<DirectorySummary>('',signal);
 if(!p||!flags(p)||!hash(p.revision)||!count(p.total_leads,20000)||!count(p.distinct_origins,p.total_leads)||!count(p.source_classes,10000)||!count(p.families,128)||!Array.isArray(p.groups)||p.groups.length>256||p.groups.some(g=>!validGroup(g))||new Set(p.groups.map(g=>g.id)).size!==p.groups.length||p.groups.reduce((n,g)=>n+g.leads,0)!==p.total_leads)return fail();
 return p;
}
export async function directoryLeads(summary:DirectorySummary,group:DirectoryGroup,q:string,family:string,after?:string,signal?:AbortSignal){
 if(!validGroup(group)||!summary.groups.some(g=>g.id===group.id)||q.length>256||family&&(!category(family)||!Object.hasOwn(group.families,family))||after!==undefined&&!cursor(after))return fail();
 const params=new URLSearchParams({group:group.id,limit:'32'});
 if(q.trim())params.set('q',q.trim());if(family)params.set('family',family);if(after)params.set('after',after);
 const p=await get<DirectoryPage>('/leads?'+params,signal);
 if(!p||!flags(p)||p.revision!==summary.revision||!Array.isArray(p.leads)||p.leads.length>32||p.leads.some(x=>!validLead(x,group)||family&&x.family!==family)||new Set(p.leads.map(x=>x.lead_id)).size!==p.leads.length||p.next_cursor!==null&&(!cursor(p.next_cursor)||p.leads.length!==32||p.next_cursor.slice(65)!==p.leads[31].lead_id))return fail();
 return p;
}
export async function bindDirectoryLeads(summary:DirectorySummary,group:DirectoryGroup,leads:DirectoryLead[],operation:string,target:{game:string|null;usePreset:boolean},signal?:AbortSignal){
 if(!validGroup(group)||!text(operation,128)||leads.length<1||leads.length>64||leads.some(x=>!validLead(x,group))||new Set(leads.map(x=>x.lead_id)).size!==leads.length||target.usePreset&&(target.game!==null||!group.preset_game_id)||!target.usePreset&&!hash(target.game))return fail();
 const account=getAuthToken(),body={operation,group:group.id,lead_ids:leads.map(x=>x.lead_id).sort(),game:target.game,use_preset:target.usePreset,acknowledged:true};
 const p=await api.post<DirectoryBinding>(ROOT+'/import',body,{signal,retries:0,timeoutMs:65000,idempotencyKey:operation});
 const x=p.data;
 if(!account||account!==getAuthToken()||signal?.aborted||!p.ok||!x||!hash(x.batch_id)||x.game_id!==(target.usePreset?group.preset_game_id:target.game)||x.directory_revision!==summary.revision||x.selected!==leads.length||!count(x.total,leads.length)||x.total<1||typeof x.replayed!=='boolean'||x.network_executed!==false||x.capture_granted!==false||x.source_verified!==false||x.training_allowed!==false)return fail();
 return x;
}
