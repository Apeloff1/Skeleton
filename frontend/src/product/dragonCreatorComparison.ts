/** Read-only differences between two exact, owned, committed creator revisions. */
import {CREATOR_MAX_BYTES,CREATOR_PROJECT_ID,canonicalCreatorJSON,creatorBytes} from './dragonCreatorProject.ts';

export const CREATOR_COMPARISON_SCHEMA = 'skeleton.dragon.creator-comparison.v1' as const;
type Value = string | number | boolean | string[];
export type CreatorFieldChange = {path:string;before:Value;after:Value;before_truncated:boolean;after_truncated:boolean;before_sha256:string;after_sha256:string};
export type CreatorReferenceChange = {reference_sha256:string;source_id:string;revision_digest:string;title:string;url:string;title_truncated:boolean;url_truncated:boolean;count:number};
export type CreatorCellChange = [number,number,string|null,string|null];
export interface CreatorComparison {
  ok:true;schema:typeof CREATOR_COMPARISON_SCHEMA;project_id:string;
  from:{version:number;document_sha256:string};to:{version:number;document_sha256:string};observed_head_version:number;
  changes:{fields:CreatorFieldChange[];
    brief:{changed:boolean;before_preview:string;after_preview:string;before_characters:number;after_characters:number;before_sha256:string;after_sha256:string};
    citations:{before_count:number;after_count:number;order_changed:boolean;added:CreatorReferenceChange[];removed:CreatorReferenceChange[]};
    boards:{before_count:number;after_count:number;items:{stage:number;kind:'added'|'removed'|'modified';changed_cells:number;cells:CreatorCellChange[]}[]}};
  source_only:true;approval_restored:false;
}
const HASH=/^[a-f0-9]{64}$/;
const PATHS=new Set(['title','style','targets','seed',...['palette','hero','quest_theme','difficulty','stages','candidates','project_notes','procedural_levels','campaign_pathing','challenge_profile'].map(key=>'portable_design.'+key)]);
const record=(value:unknown):value is Record<string,unknown>=>value!==null&&typeof value==='object'&&!Array.isArray(value)&&(Object.getPrototypeOf(value)===Object.prototype||Object.getPrototypeOf(value)===null);
const closed=(value:unknown,keys:string[]):value is Record<string,unknown>=>record(value)&&Object.keys(value).length===keys.length&&keys.every(key=>Object.hasOwn(value,key));
const integer=(value:unknown,min:number,max:number):value is number=>typeof value==='number'&&Number.isSafeInteger(value)&&value>=min&&value<=max;
const hash=(value:unknown):value is string=>typeof value==='string'&&HASH.test(value);
const text=(value:unknown,max:number):value is string=>typeof value==='string'&&[...value].length<=max&&!/[\u0000-\u0008\u000b-\u001f\ud800-\udfff]/u.test(value);
const identity=(value:unknown,version:number,digest:string):boolean=>closed(value,['version','document_sha256'])&&value.version===version&&value.document_sha256===digest;
function fieldValue(path:string,value:unknown):boolean {
  if(path==='seed')return integer(value,0,0xffffffff);
  if(path==='targets')return Array.isArray(value)&&value.length>=1&&value.length<=3&&new Set(value).size===value.length&&value.every(v=>typeof v==='string'&&/^[a-z0-9_]{2,64}$/.test(v));
  if(path==='portable_design.procedural_levels')return typeof value==='boolean';
  const ranges:Record<string,[number,number]>={'portable_design.difficulty':[1,10],'portable_design.stages':[1,8],'portable_design.candidates':[1,24]};
  return path in ranges?integer(value,...ranges[path]):text(value,240);
}
function reference(value:unknown):value is CreatorReferenceChange {
  return closed(value,['reference_sha256','source_id','revision_digest','title','url','title_truncated','url_truncated','count'])
    &&hash(value.reference_sha256)&&hash(value.revision_digest)&&text(value.source_id,128)&&value.source_id.length>0
    &&text(value.title,96)&&text(value.url,256)&&/^https?:\/\/[^\s]+$/.test(value.url)
    &&typeof value.title_truncated==='boolean'&&typeof value.url_truncated==='boolean'&&integer(value.count,1,32);
}
/** Bind the response to the precise pair selected before the request; a newer
 * observed head cannot silently substitute a different saved revision. */
export function normalizeCreatorComparison(raw:unknown,id:string,fromVersion:number,toVersion:number,fromDigest:string,toDigest:string):CreatorComparison|null {
  try{
    if(!CREATOR_PROJECT_ID.test(id)||!integer(fromVersion,1,512)||!integer(toVersion,1,512)||!hash(fromDigest)||!hash(toDigest)
      ||!closed(raw,['ok','schema','project_id','from','to','observed_head_version','changes','source_only','approval_restored'])
      ||raw.ok!==true||raw.schema!==CREATOR_COMPARISON_SCHEMA||raw.project_id!==id||raw.source_only!==true||raw.approval_restored!==false
      ||!identity(raw.from,fromVersion,fromDigest)||!identity(raw.to,toVersion,toDigest)||!integer(raw.observed_head_version,Math.max(fromVersion,toVersion),512)
      ||!closed(raw.changes,['fields','brief','citations','boards']))return null;
    const changes=raw.changes;
    if(!Array.isArray(changes.fields)||changes.fields.length>14)return null;
    const paths=new Set<string>();
    for(const field of changes.fields){
      if(!closed(field,['path','before','after','before_truncated','after_truncated','before_sha256','after_sha256'])
        ||typeof field.path!=='string'||!PATHS.has(field.path)||paths.has(field.path)||!fieldValue(field.path,field.before)||!fieldValue(field.path,field.after)
        ||typeof field.before_truncated!=='boolean'||typeof field.after_truncated!=='boolean'||!hash(field.before_sha256)||!hash(field.after_sha256)||field.before_sha256===field.after_sha256
        ||field.before_truncated&&(!text(field.before,240)||[...field.before].length!==240)||field.after_truncated&&(!text(field.after,240)||[...field.after].length!==240))return null;
      paths.add(field.path);
    }
    const brief=changes.brief;
    if(!closed(brief,['changed','before_preview','after_preview','before_characters','after_characters','before_sha256','after_sha256'])
      ||typeof brief.changed!=='boolean'||!hash(brief.before_sha256)||!hash(brief.after_sha256)||brief.changed!==(brief.before_sha256!==brief.after_sha256)
      ||!text(brief.before_preview,240)||!text(brief.after_preview,240)||!integer(brief.before_characters,0,12000)||!integer(brief.after_characters,0,12000)
      ||[...brief.before_preview].length!==Math.min(240,brief.before_characters)||[...brief.after_preview].length!==Math.min(240,brief.after_characters)
      ||!brief.changed&&(brief.before_preview!==brief.after_preview||brief.before_characters!==brief.after_characters))return null;
    const citations=changes.citations;
    if(!closed(citations,['before_count','after_count','order_changed','added','removed'])||!integer(citations.before_count,0,32)||!integer(citations.after_count,0,32)
      ||typeof citations.order_changed!=='boolean'||!Array.isArray(citations.added)||!Array.isArray(citations.removed)||citations.added.length>32||citations.removed.length>32
      ||!citations.added.every(reference)||!citations.removed.every(reference))return null;
    const added=citations.added as CreatorReferenceChange[],removed=citations.removed as CreatorReferenceChange[];
    const addedCount=added.reduce((sum,r)=>sum+r.count,0),removedCount=removed.reduce((sum,r)=>sum+r.count,0);
    if(new Set(added.map(r=>r.reference_sha256)).size!==added.length||new Set(removed.map(r=>r.reference_sha256)).size!==removed.length
      ||added.some(r=>removed.some(other=>r.reference_sha256===other.reference_sha256))
      ||addedCount>citations.after_count||removedCount>citations.before_count||addedCount-removedCount!==citations.after_count-citations.before_count
      ||!citations.order_changed&&(added.length>0||removed.length>0||citations.before_count!==citations.after_count))return null;
    const boards=changes.boards;
    if(!closed(boards,['before_count','after_count','items'])||!integer(boards.before_count,0,8)||!integer(boards.after_count,0,8)||!Array.isArray(boards.items)||boards.items.length>8)return null;
    let previousStage=0;
    for(const board of boards.items){
      if(!closed(board,['stage','kind','changed_cells','cells'])||!integer(board.stage,previousStage+1,Math.max(boards.before_count,boards.after_count))
        ||!integer(board.changed_cells,1,120)||!Array.isArray(board.cells)||board.cells.length!==board.changed_cells)return null;
      const kind=board.stage>boards.before_count?'added':board.stage>boards.after_count?'removed':'modified';
      if(board.kind!==kind||kind!=='modified'&&board.changed_cells!==120)return null;
      const coordinates=new Set<string>();
      for(const cell of board.cells){
        if(!Array.isArray(cell)||cell.length!==4||!integer(cell[0],0,9)||!integer(cell[1],0,11)||cell[2]===cell[3]
          ||![cell[2],cell[3]].every(tile=>tile===null||typeof tile==='string'&&/^[#.@$o]$/.test(tile))
          ||kind==='added'&&(cell[2]!==null||cell[3]===null)||kind==='removed'&&(cell[3]!==null||cell[2]===null)
          ||kind==='modified'&&(cell[2]===null||cell[3]===null))return null;
        const coordinate=cell[0]+':'+cell[1];if(coordinates.has(coordinate))return null;coordinates.add(coordinate);
      }
      previousStage=board.stage;
    }
    const unchanged=!changes.fields.length&&!brief.changed&&!citations.order_changed&&!boards.items.length;
    if(unchanged!==(fromDigest===toDigest))return null;
    if(creatorBytes(canonicalCreatorJSON(raw))>CREATOR_MAX_BYTES)return null;
    return JSON.parse(JSON.stringify(raw)) as CreatorComparison;
  }catch{return null;}
}
