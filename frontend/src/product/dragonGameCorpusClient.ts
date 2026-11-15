import api, { type ApiResult } from '../utils/apiClient';
import { authHeaders, getAuthToken } from '../auth/gameforgeAuth';
import { ChatClientError, chatApiError } from './chatErrors';

const ROOT = '/api/dragon-academy/knowledge/game-corpus';
const SHA = /^[a-f0-9]{64}$/;
const MAX_RESPONSE = 2 * 1024 * 1024;
export type GameIdentity = {game_id:string; namespace:string; external_id:string; first_title:string; first_stage:string; updated_at:number};
export type SourceObservation = { title:string; stage:string; version:string|null; released_on:string|null };
export type GameSource = {family?:string;view_mode?:ViewMode;has_capture_binding?:boolean;source_id:string;url:string;kind:string;language:string;last_observed:number;next_review:number;observation_digest:string;latest_observation:SourceObservation;verified:false};
export type ReleaseEvent = {game_id:string;source_id:string;event_key:string;stage:string;kind:string;language:string;released_on:string|null;observed_at:number;version:string|null;priority:number;first_title:string;observation_digest:string;latest_for_source:boolean;verified:false};
export type ImportReceipt = {batch_id:string;total:number;replayed:boolean;network_executed:false};
export type ImportState = {batch_id:string;total:number;created_at:number;counts:{queued:number;leased:number;done:number;held:number};network_executed:false;wiki_approved:false};
export type CaptureReceipt = {session:{session_id:string;status:string;version:number};game_id:string;source_id:string;observation_digest:string;network_executed:false;canonical_scheduler:boolean;source_is_reviewed:false;wiki_approved:false;archive_rights_extended:false};

function invalid(message:string):never { throw new ChatClientError(message,{kind:'protocol',retryable:false}); }
const text=(v:unknown,max=256):v is string=>typeof v==='string'&&v.length>0&&v.length<=max;
const sha=(v:unknown):v is string=>typeof v==='string'&&SHA.test(v);
const int=(v:unknown,max=Number.MAX_SAFE_INTEGER):v is number=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0&&v<=max;
const nullable=(v:unknown,max:number)=>v===null||text(v,max);
async function request<T>(method:'get'|'post',path:string,signal?:AbortSignal,body?:unknown,key?:string):Promise<T>{
 const token=getAuthToken();
 if(body&&new TextEncoder().encode(JSON.stringify(body)).byteLength>2*1024*1024+8192)invalid('Game corpus request exceeds its bound.');
 const opt={headers:authHeaders(),signal,retries:0,timeoutMs:65000,idempotencyKey:key};
 const p:ApiResult<T>=await(method==='get'?api.get<T>(ROOT+path,opt):api.post<T>(ROOT+path,body,opt));
 if(signal?.aborted||token!==getAuthToken())throw new ChatClientError('The corpus request was detached from this account.',{kind:'authorization',retryable:false});
 if(!p.ok||p.data===null)throw chatApiError(p,'Game corpus operation unavailable.');
 if(new TextEncoder().encode(JSON.stringify(p.data)).byteLength>MAX_RESPONSE)invalid('Game corpus response exceeds its bound.');
 return p.data;
}
export async function searchGames(q:string,signal?:AbortSignal){
 if(!q.trim()||q.length>256)invalid('Use a bounded game title.');
 const p=await request<{games:GameIdentity[];catalogue_only:true;verified:false}>('get','/search?limit=32&q='+encodeURIComponent(q),signal);
 if(!p||p.catalogue_only!==true||p.verified!==false||!Array.isArray(p.games)||p.games.length>32||p.games.some(g=>!sha(g.game_id)||!text(g.namespace,128)||!text(g.external_id,128)||!text(g.first_title)||!text(g.first_stage,32)||!int(g.updated_at)))invalid('Game catalogue response invalid.');
 return p.games;
}
export async function sourcePage(game:string,after?:string,signal?:AbortSignal,filters?:{family?:string;kind?:string;language?:string}){
 if(!sha(game)||after!==undefined&&!sha(after))invalid('Invalid source identity.');
 const params=new URLSearchParams({limit:'32'});if(after)params.set('after',after);
 for(const key of ['family','kind','language'] as const){const val=filters?.[key];if(val){if(!text(val,32))invalid('Invalid source filter.');params.set(key,val);}}
 const p=await request<{sources:GameSource[];next_cursor:string|null;crawl_authorized:false;source_use_authorized:false}>('get','/'+game+'/sources?'+params,signal);
 if(!p||p.crawl_authorized!==false||p.source_use_authorized!==false||!Array.isArray(p.sources)||p.sources.length>32||p.sources.some(s=>!sha(s.source_id)||!sha(s.observation_digest)||!text(s.url,2048)||!s.url.startsWith('https://')||!text(s.kind,32)||!text(s.language,32)||!int(s.last_observed)||!int(s.next_review)||s.verified!==false||s.family!==undefined&&!text(s.family,32)||s.view_mode!==undefined&&!VIEW_MODES.includes(s.view_mode)||s.has_capture_binding!==undefined&&typeof s.has_capture_binding!=='boolean'||!s.latest_observation||!text(s.latest_observation.title)||!text(s.latest_observation.stage,32)||!nullable(s.latest_observation.version,128)||!nullable(s.latest_observation.released_on,10))||p.next_cursor!==null&&(!sha(p.next_cursor)||p.sources.length!==32||p.sources[31].source_id!==p.next_cursor))invalid('Game source page invalid.');
 return p;
}
export type TimelineCursor=[number,string,string,string];
export async function releaseTimeline(stage:string,current:boolean,cursor?:TimelineCursor,signal?:AbortSignal){
 const params=new URLSearchParams({limit:'32',current_only:String(current)});
 if(stage)params.set('stage',stage);
 if(cursor){params.set('stamp',String(cursor[0]));params.set('game',cursor[1]);params.set('source',cursor[2]);params.set('event',cursor[3]);}
 const p=await request<{events:ReleaseEvent[];next_cursor:TimelineCursor|null;catalogue_only:true;verified:false;current_means_latest_observed:true;index_may_be_partial:true}>('get','/timeline?'+params,signal);
 if(!p||p.catalogue_only!==true||p.verified!==false||p.current_means_latest_observed!==true||!Array.isArray(p.events)||p.events.length>32||p.events.some(e=>!sha(e.game_id)||!sha(e.source_id)||!sha(e.observation_digest)||!text(e.event_key,128)||!text(e.first_title)||!text(e.stage,32)||!text(e.kind,32)||!text(e.language,32)||!nullable(e.released_on,10)||!nullable(e.version,128)||!int(e.observed_at)||!int(e.priority,100)||typeof e.latest_for_source!=='boolean'||e.verified!==false))invalid('Release timeline response invalid.');
 if(p.next_cursor!==null&&(!Array.isArray(p.next_cursor)||p.next_cursor.length!==4||!int(p.next_cursor[0])||!sha(p.next_cursor[1])||!sha(p.next_cursor[2])||!text(p.next_cursor[3],128)))invalid('Release timeline cursor invalid.');
 return p;
}
export async function enqueueReleaseImport(payload:string,operation:string,adapter:'manifest'|'steam',signal?:AbortSignal){
 if(!payload.trim()||new TextEncoder().encode(payload).byteLength>256*1024||!text(operation,128))invalid('Paste at most 256 KiB of locally supplied catalogue data.');
 const p=await request<ImportReceipt>('post','/release-imports',signal,{adapter,payload,operation},operation);
 if(!p||!sha(p.batch_id)||!int(p.total,4000)||p.total<1||typeof p.replayed!=='boolean'||p.network_executed!==false)invalid('Import receipt invalid.');
 return p;
}
export async function importStatus(batch:string,signal?:AbortSignal){
 if(!sha(batch))invalid('Invalid release import identity.');
 const p=await request<ImportState>('get','/release-imports/'+batch,signal);
 if(!p||p.batch_id!==batch||!int(p.total,4000)||!int(p.created_at)||!p.counts||!['queued','leased','done','held'].every(k=>int(p.counts[k as keyof ImportState['counts']],p.total))||Object.values(p.counts).reduce((a,b)=>a+b,0)!==p.total||p.network_executed!==false||p.wiki_approved!==false)invalid('Import status invalid.');
 return p;
}
export async function dispatchGameCapture(game:string,source:GameSource,operation:string,autonomous:boolean,signal?:AbortSignal){
 if(!sha(game)||!sha(source.source_id)||!sha(source.observation_digest)||!text(operation,128))invalid('Select an exact source observation.');
 const p=await request<CaptureReceipt>('post','/capture',signal,{game,source:source.source_id,observation_digest:source.observation_digest,operation,capture_rights_acknowledged:true,consent:true,autonomous},operation);
 if(!p||p.game_id!==game||p.source_id!==source.source_id||p.observation_digest!==source.observation_digest||!p.session||!text(p.session.session_id,128)||!text(p.session.status,32)||!int(p.session.version)||p.session.version<1||p.network_executed!==false||p.canonical_scheduler!==autonomous||p.source_is_reviewed!==false||p.archive_rights_extended!==false||p.wiki_approved!==false)invalid('Canonical capture receipt invalid.');
 return p;
}


export type ViewMode='text'|'image'|'video'|'audio'|'document'|'external';
const VIEW_MODES:ViewMode[]=['text','image','video','audio','document','external'];
export type TaxonomyEntry={kind:string;family:string;default_review_seconds:number;priority:number;historical_value:number;view_mode:ViewMode};
export type CaptureBinding={session_id:string;observation_digest:string;recorded_at:number};
export type CaptureCursor=[number,string];
export type CaptureDocument={capture_source_id:string;title:string;url:string;captured_at:number;total_chars:number;session_version:number;snapshot_digest:string;preserved_text_hash:string;valid_until:number;history_only:boolean;legacy_history_only:boolean;representation:'captured_text';view_mode:ViewMode};
export type ViewPin={session:string;capture_source:string;offset:number;length:number;session_version:number;snapshot_digest:string;preserved_text_hash:string;history_only:boolean};
export type DocumentSpan={game_id:string;catalogue_source_id:string;session_id:string;source_id:string;session_version:number;snapshot_digest:string;preserved_text_hash:string;offset:number;end:number;total_chars:number;text:string;span_sha256:string;next_offset:number|null;history_only:boolean;as_of_unix:number;valid_until:number;representation:'captured_text';network_executed:false;model_context_permission:false;training_permission:false;wiki_approved:false};
export type DocumentDiff={game_id:string;catalogue_source_id:string;changes:{operation:'equal'|'replace'|'insert'|'delete';left_offset:number;right_offset:number;left:string;right:string}[];left_digest:string;right_digest:string;left_history:boolean;right_history:boolean;valid_until:number;as_of_unix:number;partial_windows:true;network_executed:false;wiki_approved:false;model_context_permission:false};

const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const uuid=(v:unknown):v is string=>typeof v==='string'&&UUID.test(v);
const finite=(v:unknown):v is number=>typeof v==='number'&&Number.isFinite(v)&&v>=0;
function root(game:string,source:string){if(!sha(game)||!sha(source))invalid('Invalid game source identity.');return '/'+game+'/sources/'+source;}

/** Explicit navigation only, never remote preview or WebView execution. */
export function safeOriginalLink(value:string):string{
 if(!text(value,2048)||/[\s\\]/.test(value))invalid('Invalid external source link.');
 let u:URL;
 try{u=new URL(value);}catch{ return invalid('Invalid external source link.'); }
 if(u.protocol!=='https:'||u.username||u.password||u.port||u.search||u.hash||!/^([a-z0-9-]+\.)+[a-z0-9-]+$/i.test(u.hostname)||/^[0-9.]+$/.test(u.hostname)||/\.(local|localhost|internal|home\.arpa|onion)$/i.test(u.hostname))invalid('Only plain HTTPS source links are supported.');
 return u.href;
}
export async function getSourceTaxonomy(signal?:AbortSignal){
 const p=await request<{source_classes:TaxonomyEntry[];families:string[];network_authority:false;source_use_authority:false;training_allowed:false}>('get','/taxonomy',signal);
 if(!p||p.network_authority!==false||p.source_use_authority!==false||p.training_allowed!==false||!Array.isArray(p.source_classes)||p.source_classes.length>2000||!Array.isArray(p.families)||p.families.length>128||p.families.some(f=>!text(f,32))||new Set(p.source_classes.map(x=>x?.kind)).size!==p.source_classes.length||p.source_classes.some(x=>!x||!text(x.kind,32)||!p.families.includes(x.family)||!int(x.default_review_seconds,604800)||!int(x.priority,100)||!int(x.historical_value,100)||!VIEW_MODES.includes(x.view_mode)))invalid('Source taxonomy response invalid.');
 return p;
}
export async function sourceCaptures(game:string,source:string,before?:CaptureCursor,signal?:AbortSignal){
 const params=new URLSearchParams({limit:'32'});
 if(before){if(!int(before[0])||!uuid(before[1]))invalid('Invalid capture cursor.');params.set('stamp',String(before[0]));params.set('session',before[1]);}
 const p=await request<{captures:CaptureBinding[];next_cursor:CaptureCursor|null;source_use_authorized:false;network_executed:false;wiki_approved:false}>('get',root(game,source)+'/captures?'+params,signal);
 if(!p||p.source_use_authorized!==false||p.network_executed!==false||p.wiki_approved!==false||!Array.isArray(p.captures)||p.captures.length>32||p.captures.some(x=>!x||!uuid(x.session_id)||!sha(x.observation_digest)||!int(x.recorded_at))||p.next_cursor!==null&&(!Array.isArray(p.next_cursor)||p.next_cursor.length!==2||!int(p.next_cursor[0])||!uuid(p.next_cursor[1])))invalid('Capture history invalid.');
 return p;
}
export async function sourceDocuments(game:string,source:string,session:string,after?:string,signal?:AbortSignal){
 if(!uuid(session)||after!==undefined&&!sha(after))invalid('Invalid capture window.');
 const p=await request<{game_id:string;catalogue_source_id:string;session_id:string;documents:CaptureDocument[];held:number;scanned:number;next_cursor:string|null;session_version:number;as_of_unix:number;earliest_expiry:number|null;network_executed:false;wiki_approved:false;model_context_permission:false}>('get',root(game,source)+'/captures/'+session+'/documents?limit=8'+(after?'&after='+after:''),signal);
 if(!p||p.game_id!==game||p.catalogue_source_id!==source||p.session_id!==session||!int(p.session_version)||p.session_version<1||!finite(p.as_of_unix)||!int(p.scanned,8)||!int(p.held,8)||p.network_executed!==false||p.wiki_approved!==false||p.model_context_permission!==false||!Array.isArray(p.documents)||p.documents.length+p.held!==p.scanned||p.next_cursor!==null&&!sha(p.next_cursor)||p.earliest_expiry!==null&&(!finite(p.earliest_expiry)||p.earliest_expiry<=p.as_of_unix)||p.documents.some(d=>!d||!sha(d.capture_source_id)||typeof d.title!=='string'||d.title.length>512||!text(d.url,2048)||!finite(d.captured_at)||!int(d.total_chars,24000)||d.session_version!==p.session_version||!sha(d.snapshot_digest)||!sha(d.preserved_text_hash)||!finite(d.valid_until)||d.valid_until<=p.as_of_unix||typeof d.history_only!=='boolean'||typeof d.legacy_history_only!=='boolean'||d.representation!=='captured_text'||!VIEW_MODES.includes(d.view_mode)))invalid('Capture document listing invalid.');
 return p;
}
export function createViewPin(session:string,d:CaptureDocument,offset=0):ViewPin{
 return {session,capture_source:d.capture_source_id,offset,length:4000,session_version:d.session_version,snapshot_digest:d.snapshot_digest,preserved_text_hash:d.preserved_text_hash,history_only:d.history_only};
}
function validPin(p:ViewPin){
 return !!p&&uuid(p.session)&&sha(p.capture_source)&&int(p.offset,24000)&&int(p.length,4000)&&p.length>0&&int(p.session_version)&&p.session_version>0&&sha(p.snapshot_digest)&&sha(p.preserved_text_hash)&&typeof p.history_only==='boolean';
}
export async function viewSourceDocument(game:string,source:string,pin:ViewPin,signal?:AbortSignal){
 if(!validPin(pin))invalid('Invalid exact view pin.');
 const p=await request<DocumentSpan>('post',root(game,source)+'/view',signal,pin);
 if(!p||p.game_id!==game||p.catalogue_source_id!==source||p.session_id!==pin.session||p.source_id!==pin.capture_source||p.session_version!==pin.session_version||p.snapshot_digest!==pin.snapshot_digest||p.preserved_text_hash!==pin.preserved_text_hash||p.history_only!==pin.history_only||p.offset!==pin.offset||!int(p.end,24000)||p.end<p.offset||!int(p.total_chars,24000)||p.end>p.total_chars||typeof p.text!=='string'||Array.from(p.text).length!==p.end-p.offset||p.end-p.offset>pin.length||!sha(p.span_sha256)||p.next_offset!==(p.end<p.total_chars?p.end:null)||!finite(p.as_of_unix)||!finite(p.valid_until)||p.valid_until<=p.as_of_unix||p.representation!=='captured_text'||p.network_executed!==false||p.model_context_permission!==false||p.training_permission!==false||p.wiki_approved!==false)invalid('Exact captured passage response invalid.');
 return p;
}
export async function compareSourceDocuments(game:string,source:string,left:ViewPin,right:ViewPin,signal?:AbortSignal){
 if(!validPin(left)||!validPin(right))invalid('Invalid comparison pins.');
 const p=await request<DocumentDiff>('post',root(game,source)+'/compare',signal,{left,right});
 if(!p||p.game_id!==game||p.catalogue_source_id!==source||p.partial_windows!==true||p.network_executed!==false||p.model_context_permission!==false||p.wiki_approved!==false||p.left_history!==left.history_only||p.right_history!==right.history_only||!sha(p.left_digest)||!sha(p.right_digest)||!finite(p.as_of_unix)||!finite(p.valid_until)||p.valid_until<=p.as_of_unix||!Array.isArray(p.changes)||p.changes.length>1024||p.changes.some(x=>!x||!['equal','replace','insert','delete'].includes(x.operation)||!int(x.left_offset,512)||!int(x.right_offset,512)||typeof x.left!=='string'||typeof x.right!=='string')||p.changes.reduce((n,x)=>n+Array.from(x.left).length+Array.from(x.right).length,0)>8000)invalid('Source comparison response invalid.');
 return p;
}


export type GlobalSource=GameSource&{game_id:string;game_title:string;namespace:string;external_id:string;first_stage:string;updated_at:number};
export async function searchSourceLibrary(q:string,filters:{kind?:string;family?:string;language?:string},signal?:AbortSignal){
 if(!q.trim()||q.length>256)invalid('Enter a bounded game, source or category query.');
 const params=new URLSearchParams({q,limit:'32'});
 for(const key of ['family','kind','language'] as const){
  const v=filters[key];if(v){if(!text(v,32))invalid('Invalid source search filter.');params.set(key,v);}
 }
 const p=await request<{sources:GlobalSource[];truncated:boolean;index_backfill_complete:boolean;catalogue_only:true;network_executed:false;source_use_authorized:false}>('get','/source-search?'+params,signal);
 if(!p||p.catalogue_only!==true||p.network_executed!==false||p.source_use_authorized!==false||typeof p.truncated!=='boolean'||typeof p.index_backfill_complete!=='boolean'||!Array.isArray(p.sources)||p.sources.length>32||
  p.sources.some(s=>!s||!sha(s.game_id)||!sha(s.source_id)||!sha(s.observation_digest)||!text(s.game_title)||!text(s.url,2048)||!s.url.startsWith('https://')||!text(s.namespace,128)||!text(s.external_id,128)||!text(s.first_stage,32)||!text(s.family,32)||!text(s.kind,32)||!text(s.language,32)||!VIEW_MODES.includes(s.view_mode as ViewMode)||!int(s.updated_at)||!int(s.last_observed)||!int(s.next_review)||typeof s.has_capture_binding!=='boolean'||s.verified!==false||!s.latest_observation||!text(s.latest_observation.title)||!text(s.latest_observation.stage,32)||!nullable(s.latest_observation.version,128)||!nullable(s.latest_observation.released_on,10)))invalid('Indexed source library response invalid.');
 return p;
}
