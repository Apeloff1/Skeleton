import api from '../utils/apiClient';
import {getAuthToken} from '../auth/gameforgeAuth';

const ROOT='/api/dragon-academy/knowledge/game-corpus';
const GRAPH='/lead-graph';
const HASH=/^[0-9a-f]{64}$/;
const CURSOR=/^[0-9a-f]{64}:[0-9a-f]{64}$/;
const SLUG=/^[a-z0-9][a-z0-9-]{0,63}$/;
const STAGES=['candidate','held','retired'] as const;
const PROJECTIONS=['steam','modrinth','locator'] as const;
export type LeadState=typeof STAGES[number];
export type Projection=typeof PROJECTIONS[number];
export type GraphStatus={enabled:0|1;bootstrap_revision:string|null;bootstrap_cursor:number;bootstrapped:0|1;nodes:number;edges:number;snapshots:number;due:number;bootstrap_target_rows:number;available_seed_revision:string;growth_floor:number;growth_floor_met:boolean;architecture_node_cap:number;architecture_evidence_cap:number;network_authorized:false;physical_capacity_verified:false};
export type DatasetTarget={id:string;domain:string;url:string;adapter:string;advertised_rows:number|null;access:string;cadence:string;notes:string;review_seconds:number|null;network_authorized:false;license_verified:false;download_verified:false;training_allowed:false};
export type Lead={id:string;url:string;host:string;title:string;kind:string;family:string;first_seen:number;last_seen:number;next_review:number;observations:number;state:LeadState;verified:false;network_authorized:false};
export type Edge={id:string;parent:string;child:string;relation:string;subject:string;kind:string;title:string;witness:string;snapshot:string|null;snapshot_state:string|null;snapshot_expires_at:number|null;first_seen:number;last_seen:number};
export type DatasetCandidate={id:string;url:string;title:string;kind:string;first_seen:number;last_seen:number;target_id:string|null;projection:Projection|null;enabled:0|1|null;expires_at:number|null;network_authorized:false;source_verified:false};
export type TargetRegistration={target_id:string;lead_id:string;revision:string;enabled:boolean;expires_at:number;network_authorized:false;source_verified:false};
type Unavailable={network_authorized:false};
const bad=():never=>{throw Error('Lead graph or dataset library response invalid.');};
const h=(x:unknown):x is string=>typeof x==='string'&&HASH.test(x);
const t=(x:unknown,max:number):x is string=>typeof x==='string'&&x.length>0&&x.length<=max;
const n=(x:unknown,max=Number.MAX_SAFE_INTEGER):x is number=>typeof x==='number'&&Number.isSafeInteger(x)&&x>=0&&x<=max;
const slug=(x:unknown):x is string=>typeof x==='string'&&SLUG.test(x);
function url(x:unknown){if(!t(x,2048)||!x.startsWith('https://')||/[\s\\?#]/.test(x))return false;try{const u=new URL(x);return u.protocol==='https:'&&!u.port&&!u.username&&!u.password&&u.hostname.includes('.');}catch{return false;}}
function flag(x:Unavailable){return !!x&&x.network_authorized===false;}
function next(value:unknown,ids:string[],prefixed:boolean){
 return value===null||typeof value==='string'&&(prefixed?CURSOR.test(value)&&value.slice(65)===ids[ids.length-1]:value===ids[ids.length-1]&&h(value))&&ids.length===32;
}
async function request<T>(path:string,signal?:AbortSignal,body?:Record<string,unknown>):Promise<T>{
 const token=getAuthToken(),opt={signal,retries:0,timeoutMs:30000,maxResponseChars:512*1024};
 const result=body===undefined?await api.get<T>(ROOT+path,opt):await api.post<T>(ROOT+path,body,opt);
 if(!token||token!==getAuthToken()||signal?.aborted||!result.ok||!result.data)return bad();
 return result.data;
}
function graphStatus(x:GraphStatus){
 if(!flag(x)||x.physical_capacity_verified!==false||![0,1].includes(x.enabled)||![0,1].includes(x.bootstrapped)||
 x.bootstrap_revision!==null&&!h(x.bootstrap_revision)||!h(x.available_seed_revision)||!n(x.bootstrap_cursor)||
 !n(x.bootstrap_target_rows)||!n(x.nodes,20000000)||!n(x.edges,100000000)||!n(x.snapshots,100000)||!n(x.due)||
 !n(x.growth_floor)||x.growth_floor_met!==(x.nodes>=x.growth_floor)||x.architecture_node_cap!==20000000||x.architecture_evidence_cap!==100000000)return bad();
 return x;
}
export async function leadStatus(signal?:AbortSignal){return graphStatus(await request<GraphStatus>(GRAPH,signal));}
export async function configureLeadGraph(enabled:boolean,signal?:AbortSignal){
 return graphStatus(await request<GraphStatus>(GRAPH+'/configure',signal,{enabled,acknowledged:true}));
}
export async function publicDatasetLibrary(q:string,domain:string,after?:string,signal?:AbortSignal){
 if(q.length>256||domain&&!slug(domain)||after!==undefined&&!/^[0-9a-f]{64}:[a-z0-9-]{1,64}$/.test(after))return bad();
 const p=new URLSearchParams({limit:'32'});if(q.trim())p.set('q',q.trim());if(domain)p.set('domain',domain);if(after)p.set('after',after);
 const x=await request<Unavailable&{revision:string;targets:DatasetTarget[];next_cursor:string|null;total_targets:number;license_verified:false;training_allowed:false}>('/dataset-library?'+p,signal);
 if(!flag(x)||!h(x.revision)||x.license_verified!==false||x.training_allowed!==false||!n(x.total_targets,4096)||!Array.isArray(x.targets)||x.targets.length>32||
 x.targets.some(r=>!r||!slug(r.id)||!slug(r.domain)||!url(r.url)||!t(r.adapter,32)||!t(r.access,32)||!t(r.cadence,32)||!t(r.notes,512)||r.advertised_rows!==null&&!n(r.advertised_rows,1e12)||r.review_seconds!==null&&!n(r.review_seconds,2592000)||r.network_authorized!==false||r.license_verified!==false||r.download_verified!==false||r.training_allowed!==false)||
 x.next_cursor!==null&&(!/^[0-9a-f]{64}:[a-z0-9-]{1,64}$/.test(x.next_cursor)||x.targets.length!==32||x.next_cursor.slice(65)!==x.targets[31].id))return bad();
 return x;
}
export async function listLeads(q:string,state:LeadState,dueOnly:boolean,after?:string,signal?:AbortSignal){
 if(q.length>256||!STAGES.includes(state)||after!==undefined&&!CURSOR.test(after))return bad();
 const p=new URLSearchParams({limit:'32',state,due_only:String(dueOnly)});if(q.trim())p.set('q',q.trim());if(after)p.set('after',after);
 const x=await request<Unavailable&{candidate_only:true;leads:Lead[];next_cursor:string|null}>(GRAPH+'/leads?'+p,signal);
 if(!flag(x)||x.candidate_only!==true||!Array.isArray(x.leads)||x.leads.length>32||x.leads.some(r=>!r||!h(r.id)||!url(r.url)||!t(r.host,253)||!t(r.title,256)||!t(r.kind,32)||!t(r.family,32)||!n(r.first_seen)||!n(r.last_seen)||!n(r.next_review)||!n(r.observations)||r.state!==state||r.verified!==false||r.network_authorized!==false)||!next(x.next_cursor,x.leads.map(r=>r.id),true))return bad();
 return x;
}
export async function leadEdges(lead:string,direction:'parents'|'children',after?:string,signal?:AbortSignal){
 if(!h(lead)||after!==undefined&&!h(after))return bad();
 const x=await request<Unavailable&{candidate_only:true;edges:Edge[];next_cursor:string|null}>(GRAPH+'/leads/'+lead+'/edges?direction='+direction+'&limit=32'+(after?'&after='+after:''),signal);
 if(!flag(x)||x.candidate_only!==true||!Array.isArray(x.edges)||x.edges.length>32||x.edges.some(r=>!r||!h(r.id)||!h(r.parent)||!h(r.child)||!h(r.witness)||(direction==='parents'?r.child!==lead:r.parent!==lead)||!t(r.relation,32)||!t(r.subject,256)||!t(r.title,256)||!t(r.kind,32)||!n(r.first_seen)||!n(r.last_seen)||r.snapshot!==null&&!h(r.snapshot)||r.snapshot_state!==null&&!['open','sealed','revoked'].includes(r.snapshot_state)||r.snapshot_expires_at!==null&&!n(r.snapshot_expires_at))||!next(x.next_cursor,x.edges.map(r=>r.id),false))return bad();
 return x;
}
export async function recordLeadReview(lead:string,decision:LeadState,reason:string,operation:string,signal?:AbortSignal){
 if(!h(lead)||!STAGES.includes(decision)||!t(reason,512)||!t(operation,128))return bad();
 const x=await request<Unavailable&{lead_id:string;decision:LeadState;verified:false}>(GRAPH+'/leads/'+lead+'/review',signal,{decision,reason,operation,interval_seconds:604800});
 if(!flag(x)||x.lead_id!==lead||x.decision!==decision||x.verified!==false)return bad();
 return x;
}
export async function listDatasetCandidates(after?:string,signal?:AbortSignal){
 if(after!==undefined&&!h(after))return bad();
 const x=await request<Unavailable&{candidates:DatasetCandidate[];next_cursor:string|null}>(GRAPH+'/dataset-candidates?limit=32'+(after?'&after='+after:''),signal);
 if(!flag(x)||!Array.isArray(x.candidates)||x.candidates.length>32||x.candidates.some(r=>!r||!h(r.id)||!url(r.url)||!t(r.title,256)||!t(r.kind,32)||!n(r.first_seen)||!n(r.last_seen)||r.target_id!==null&&!slug(r.target_id)||r.projection!==null&&!PROJECTIONS.includes(r.projection)||r.enabled!==null&&![0,1].includes(r.enabled)||r.expires_at!==null&&!n(r.expires_at)||r.network_authorized!==false||r.source_verified!==false)||!next(x.next_cursor,x.candidates.map(r=>r.id),false))return bad();
 return x;
}
export async function registerDatasetCandidate(lead:string,projection:Projection,rights:string,enabled:boolean,signal?:AbortSignal){
 if(!h(lead)||!PROJECTIONS.includes(projection)||!t(rights,128)||typeof enabled!=='boolean')return bad();
 const x=await request<TargetRegistration>(GRAPH+'/dataset-candidates/'+lead,signal,{projection,rights_ref:rights,grant_seconds:7*86400,enabled,acknowledged:true});
 if(!flag(x)||x.source_verified!==false||x.lead_id!==lead||!slug(x.target_id)||!h(x.revision)||x.enabled!==enabled||!n(x.expires_at))return bad();return x;
}

export type BundleStatus={bundle_revision:string;source_blob:string;title_identity_candidates:number;store_locator_floor:number;gross_optional_route_candidates:number;shards:number;source_rights_verified:false;source_verified:false;network_authorized:false;source_url:string;snapshot:{id:string;rows:number;expected_rows:number;next_page:number;state:'open'|'sealed'|'revoked';expires_at:number}|null;snapshot_identity_candidates_ingested:number;growth_floor_met:boolean};
function checkBundle(x:BundleStatus){
 if(!flag(x)||!h(x.bundle_revision)||!(/^[a-f0-9]{40}$/.test(x.source_blob))||!n(x.title_identity_candidates,20000000)||!n(x.store_locator_floor)||x.store_locator_floor!==x.title_identity_candidates||x.gross_optional_route_candidates!==17*x.title_identity_candidates||!n(x.shards,4096)||!x.shards||!url(x.source_url)||x.source_rights_verified!==false||x.source_verified!==false||typeof x.growth_floor_met!=='boolean'||!n(x.snapshot_identity_candidates_ingested,x.title_identity_candidates))return bad();
 const s=x.snapshot;
 if(s!==null&&(!s||!h(s.id)||s.expected_rows!==x.title_identity_candidates||!n(s.rows,s.expected_rows)||!n(s.next_page)||!n(s.expires_at)||!['open','sealed','revoked'].includes(s.state)))return bad();
 if(x.snapshot_identity_candidates_ingested!==(s?.rows??0))return bad();
 return x;
}
export async function leadBundleStatus(signal?:AbortSignal){return checkBundle(await request<BundleStatus>(GRAPH+'/bundle',signal));}
export async function enableLeadBundle(rights_ref:string,signal?:AbortSignal){
 if(!t(rights_ref.trim(),128))return bad();
 return checkBundle(await request<BundleStatus>(GRAPH+'/bundle/enable',signal,{rights_ref:rights_ref.trim(),grant_seconds:2592000,acknowledged:true}));
}
