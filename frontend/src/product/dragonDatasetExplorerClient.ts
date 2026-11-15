import api from '../utils/apiClient';
import {getAuthToken} from '../auth/gameforgeAuth';

const ROOT='/api/dragon-academy/knowledge/game-corpus/';
const SHA=/^[0-9a-f]{64}$/;
const KEY=/^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$/;
export type DatasetVersion={id:string;game:string;dataset:string;source:string;label:string;expected_rows:number;rows:number;next_page:number;chain:string;state:'building'|'sealed';created_at:number;expires_at:number};
export type EntityRecord={key:string;record:Record<string,unknown>;sha256:string};
export type GraphNode={key:string;depth:number;present:boolean;sha256:string|null};
export type GraphEdge={from:string;relation:string;to:string};
export type EntityGraph={version:string;root:string;nodes:GraphNode[];edges:GraphEdge[];unresolved_nodes:number;truncated:boolean;max_depth:number;valid_until:number;source_verified:false;training_allowed:false};
export type ChangeType='added'|'removed'|'changed'|'unchanged';
export type DataChange={key:string;change:ChangeType;before_sha256:string|null;after_sha256:string|null};
export type VersionDiff={left:string;right:string;changes:DataChange[];window_counts:Record<ChangeType,number>;scanned:number;next_cursor:string|null;complete:boolean;valid_until:number;source_verified:false;training_allowed:false};
export type RecordDiff={left:string;right:string;key:string;change:ChangeType;before:EntityRecord|null;after:EntityRecord|null;fields:{field:string;change:'added'|'removed'|'changed'}[];valid_until:number;source_verified:false;training_allowed:false};
const fail=():never=>{throw Error('Dataset receipt invalid or unavailable.');};
const sha=(v:unknown):v is string=>typeof v==='string'&&SHA.test(v);
const key=(v:unknown):v is string=>typeof v==='string'&&KEY.test(v);
const count=(x:unknown,max:number):x is number=>typeof x==='number'&&Number.isSafeInteger(x)&&x>=0&&x<=max;
const live=(x:unknown):x is number=>typeof x==='number'&&Number.isFinite(x)&&x*1000>Date.now();
const validChange=(x:unknown):x is ChangeType=>typeof x==='string'&&['added','removed','changed','unchanged'].includes(x);
function id(x:string){return sha(x)?x:fail();}
function segment(x:string){if(!key(x)||x.includes('/'))return fail();return encodeURIComponent(x);}
function root(game:string,version?:string){return ROOT+id(game)+'/datasets'+(version?'/'+id(version):'');}
function record(x:unknown):x is EntityRecord{
 if(!x||typeof x!=='object')return false;
 const r=x as EntityRecord;
 return key(r.key)&&sha(r.sha256)&&!!r.record&&typeof r.record==='object'&&!Array.isArray(r.record)&&JSON.stringify(r.record).length<=131072;
}
function validVersion(x:DatasetVersion,game:string){
 return !!x&&sha(x.id)&&x.game===game&&key(x.dataset)&&sha(x.source)&&typeof x.label==='string'&&x.label.length<=128&&count(x.expected_rows,100000000)&&x.expected_rows>0&&count(x.rows,x.expected_rows)&&count(x.next_page,100000000)&&sha(x.chain)&&['building','sealed'].includes(x.state)&&typeof x.created_at==='number'&&Number.isFinite(x.created_at)&&live(x.expires_at)&&x.expires_at>x.created_at&&(x.state!=='sealed'||x.rows===x.expected_rows);
}
async function get<T>(url:string,signal?:AbortSignal):Promise<T>{
 const token=getAuthToken(),p=await api.get<T>(url,{signal,retries:0,timeoutMs:15000,maxResponseChars:2*1024*1024});
 if(!token||token!==getAuthToken()||signal?.aborted||!p.ok||!p.data)return fail();
 return p.data;
}
export async function datasetVersions(game:string,after?:string,signal?:AbortSignal){
 const p=await get<{versions:DatasetVersion[];next_cursor:string|null;source_verified:false;training_allowed:false}>(root(game)+(after?'?after='+id(after):''),signal);
 if(!Array.isArray(p.versions)||p.versions.length>32||p.versions.some(v=>!validVersion(v,game))||p.next_cursor!==null&&(!sha(p.next_cursor)||p.versions.length!==32||p.versions[31].id!==p.next_cursor)||p.source_verified!==false||p.training_allowed!==false)return fail();
 return p;
}
export async function datasetRecords(game:string,version:DatasetVersion,q:string,after?:string,signal?:AbortSignal){
 if(!validVersion(version,game)||version.state!=='sealed'||q.length>256||after!==undefined&&!key(after))return fail();
 const params=new URLSearchParams({limit:'16'});if(q.trim())params.set('q',q.trim());if(after)params.set('after',after);
 const p=await get<{version:string;label:string;records:EntityRecord[];next_cursor:string|null;source_verified:false;training_allowed:false}>(root(game,version.id)+'/records?'+params,signal);
 if(p.version!==version.id||p.label!==version.label||!Array.isArray(p.records)||p.records.length>16||p.records.some(r=>!record(r))||p.next_cursor!==null&&(!key(p.next_cursor)||p.records.length!==16||p.records[15].key!==p.next_cursor)||p.source_verified!==false||p.training_allowed!==false)return fail();
 return p;
}
export async function datasetRecord(game:string,version:DatasetVersion,entity:string,signal?:AbortSignal){
 if(!validVersion(version,game)||version.state!=='sealed')return fail();
 const p=await get<EntityRecord&{version:string;valid_until:number;source_verified:false;training_allowed:false}>(root(game,version.id)+'/record/'+segment(entity),signal);
 if(!record(p)||p.key!==entity||p.version!==version.id||p.valid_until!==version.expires_at||!live(p.valid_until)||p.source_verified!==false||p.training_allowed!==false)return fail();
 return p;
}
export async function datasetGraph(game:string,version:DatasetVersion,entity:string,direction:'in'|'out'|'both',depth:number,signal?:AbortSignal){
 if(!validVersion(version,game)||version.state!=='sealed'||!count(depth,6)||!['in','out','both'].includes(direction))return fail();
 const params=new URLSearchParams({direction,max_depth:String(depth),node_limit:'128',edge_limit:'256'});
 const p=await get<EntityGraph>(root(game,version.id)+'/graph/'+segment(entity)+'?'+params,signal);
 if(p.version!==version.id||p.root!==entity||!Array.isArray(p.nodes)||p.nodes.length<1||p.nodes.length>128||
 p.nodes.some(n=>!n||!key(n.key)||!count(n.depth,depth)||typeof n.present!=='boolean'||n.present&&!sha(n.sha256)||!n.present&&n.sha256!==null)||
 new Set(p.nodes.map(n=>n.key)).size!==p.nodes.length||p.nodes[0].key!==entity||!p.nodes[0].present||
 !Array.isArray(p.edges)||p.edges.length>256||p.edges.some(e=>!e||!key(e.from)||!key(e.to)||!key(e.relation))||
 !count(p.unresolved_nodes,p.nodes.length)||p.unresolved_nodes!==p.nodes.filter(n=>!n.present).length||typeof p.truncated!=='boolean'||p.max_depth!==depth||
 p.valid_until!==version.expires_at||!live(p.valid_until)||p.source_verified!==false||p.training_allowed!==false)return fail();
 const nodes=new Set(p.nodes.map(n=>n.key));if(p.edges.some(e=>!nodes.has(e.from)||!nodes.has(e.to)))return fail();
 return p;
}
function comparison(game:string,a:DatasetVersion,b:DatasetVersion){
 if(!validVersion(a,game)||!validVersion(b,game)||a.state!=='sealed'||b.state!=='sealed'||a.id===b.id||a.dataset!==b.dataset||a.source!==b.source)return fail();
 return root(game,a.id)+'/compare/'+id(b.id);
}
export async function datasetCompare(game:string,a:DatasetVersion,b:DatasetVersion,after?:string,signal?:AbortSignal){
 const base=comparison(game,a,b);if(after!==undefined&&!key(after))return fail();
 const p=await get<VersionDiff>(base+'?limit=32&changes_only=true'+(after?'&after='+encodeURIComponent(after):''),signal);
 if(p.left!==a.id||p.right!==b.id||!count(p.scanned,32)||!Array.isArray(p.changes)||p.changes.length>p.scanned||
 p.changes.some(c=>!c||!key(c.key)||!validChange(c.change)||c.change==='unchanged'||(c.change==='added'?c.before_sha256!==null:!sha(c.before_sha256))||(c.change==='removed'?c.after_sha256!==null:!sha(c.after_sha256)))||
 !p.window_counts||!['added','removed','changed','unchanged'].every(k=>count(p.window_counts[k as ChangeType],32))||Object.values(p.window_counts).reduce((n,x)=>n+x,0)!==p.scanned||
 p.window_counts.added+p.window_counts.removed+p.window_counts.changed!==p.changes.length||typeof p.complete!=='boolean'||p.complete!==(p.next_cursor===null)||p.next_cursor!==null&&!key(p.next_cursor)||
 p.valid_until!==Math.min(a.expires_at,b.expires_at)||!live(p.valid_until)||p.source_verified!==false||p.training_allowed!==false)return fail();
 return p;
}
export async function datasetCompareRecord(game:string,a:DatasetVersion,b:DatasetVersion,entity:string,signal?:AbortSignal){
 const p=await get<RecordDiff>(comparison(game,a,b)+'/record/'+segment(entity),signal);
 if(p.left!==a.id||p.right!==b.id||p.key!==entity||!validChange(p.change)||p.before!==null&&(!record(p.before)||p.before.key!==entity)||p.after!==null&&(!record(p.after)||p.after.key!==entity)||p.before===null&&p.after===null||
 !Array.isArray(p.fields)||p.fields.length>4096||p.fields.some(f=>!f||typeof f.field!=='string'||f.field.length>128||!['added','removed','changed'].includes(f.change))||
 p.valid_until!==Math.min(a.expires_at,b.expires_at)||!live(p.valid_until)||p.source_verified!==false||p.training_allowed!==false)return fail();
 return p;
}
