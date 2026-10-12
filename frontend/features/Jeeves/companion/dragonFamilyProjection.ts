/** Dragon Family projection: transport validation only, NEVER a source of XP. */
const HEX = /^[0-9a-f]{64}$/;
export type DragonFamilyRole = 'article'|'video'|'monitor';
export type DragonFamilyStage = 'unborn'|'egg'|'hatchling'|'juvenile'|'dragon';
export interface DragonAlmanakkProjection {
 schema:'skeleton.ai.dragon.almanakk.v1';
 architecture:string;
 counts:{collected:number;wiki_verified:number;shadow_validated:number;weight_handoff:number};
 items:readonly {source_id:string;dragon:string;stage:'collected'|'wiki_verified'|'shadow_validated'|'weight_handoff';
    last_acquired_at:string;topics:readonly string[];measured_gain:number|null}[];
 history:readonly {sequence:number;dragon:string;source_id:string;stage:string;
    at:string;change:string;event_hash:string}[];
 policy:string;
}

export interface DragonIdleFamilyProjection {
 schema:'skeleton.ai.dragon.idle_status.v1';
 configured:boolean;idle_only:true;
 host_state:'not_connected'|'not_observed';
 max_tasks_per_tick:number;
 history:readonly {sequence:number;at:string;dragon:DragonFamilyRole;
   source_id:string;outcome:'changed'|'unchanged'|'failed'|'paused';
   change:string;digest:string}[];
 workers:Partial<Record<DragonFamilyRole,{
   known_sources:number;failed:number;incomplete_leases:number;
   last_changes:number;unchanged:number;earliest_due_at:string|null;
 }>>;
}
export interface DragonGleanProjection {
 schema:'skeleton.ai.dragon.glean.v1';
 insights:number;stale_observations:number;
 total_active_observations:number;lenses_used:number;
 counts:{contested:number;wiki_candidate:number;needs_independent_sources:number};
 read_only:true;
 promotion:string;
 updated_at:string|null;
 cells:readonly {
   lens:string;proposition_digest:string;
   status:'contested'|'wiki_candidate'|'needs_independent_sources';
   source_count:number;support_sources:number;challenge_sources:number;
   support_groups:number;challenge_groups:number;
   modalities:readonly ('article'|'video')[];
   latest_at:string;exemplar:string;
   priority:'investigate_disagreement'|'independent_wiki_review'|'seek_separate_source';
   evidence_fingerprint:string;
 }[];
}
export interface DragonFamilyProjection {
  schema:'skeleton.ai.dragon.family.v1';
  almanakk?:DragonAlmanakkProjection;
  idle_work?:DragonIdleFamilyProjection;
  glean?:DragonGleanProjection;
  parent:{stage:'egg'|'hatchling'|'juvenile'|'adolescent'|'winged'|'adult';
    consumed:number;source_total:number;complete:boolean;laid_at:string|null};
  inventory_sealed:boolean;
  children:readonly {
    id:DragonFamilyRole;name:string;specialty:string;
    stage:DragonFamilyStage;level:number;discoveries:number;
    last_grew_at:string|null;idle_only:true;
  }[];
  history:readonly {
    sequence:number;at:string;dragon:string;action:string;
    source_id:string;change:string;digest:string;
  }[];
  pending_source_count:number;
  knowledge_authority:string;
  update_policy:string;
}
const count=(v:unknown):v is number=>
  typeof v==='number'&&Number.isSafeInteger(v)&&v>=0;
const utc=(v:unknown):v is string=>
  typeof v==='string'&&/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(v)&&
  Number.isFinite(Date.parse(v));
export function validateDragonFamily(input:unknown):DragonFamilyProjection|null {
  if(!input||typeof input!=='object')return null;
  const f=input as Partial<DragonFamilyProjection>;
  const p=f.parent;
  if(f.schema!=='skeleton.ai.dragon.family.v1'||!p||
    !['egg','hatchling','juvenile','adolescent','winged','adult'].includes(p.stage)||
    !count(p.consumed)||!count(p.source_total)||p.consumed>p.source_total||
    typeof p.complete!=='boolean'||p.complete!==(p.stage==='adult')||
    !(p.laid_at===null||utc(p.laid_at))||
    (p.complete&&p.laid_at===null)||(!p.complete&&p.laid_at!==null)||
    typeof f.inventory_sealed!=='boolean'||(p.complete&&!f.inventory_sealed)||
    !count(f.pending_source_count)||
    !Array.isArray(f.children)||f.children.length!==3||
    !Array.isArray(f.history)||f.history.length>100||
    typeof f.knowledge_authority!=='string'||f.knowledge_authority.length>150||
    typeof f.update_policy!=='string'||f.update_policy.length>160)return null;
  const roles:DragonFamilyRole[]=['article','video','monitor'];
  if(!f.children.every((c,i)=>c&&c.id===roles[i]&&
    typeof c.name==='string'&&c.name.length<=50&&
    typeof c.specialty==='string'&&c.specialty.length<=100&&
    ['unborn','egg','hatchling','juvenile','dragon'].includes(c.stage)&&
    count(c.level)&&c.level<=30&&count(c.discoveries)&&
    c.idle_only===true&&(c.last_grew_at===null||utc(c.last_grew_at))&&
    (c.stage==='unborn'?!p.complete:
      p.complete)&&
    (c.discoveries===0?c.level===0&&c.last_grew_at===null&&
      (c.stage==='egg'||c.stage==='unborn'):
      c.level>0&&c.last_grew_at!==null&&
      !['unborn','egg'].includes(c.stage))))return null;
  if(!f.history.every((h,i,all)=>h&&count(h.sequence)&&h.sequence>0&&
    utc(h.at)&&typeof h.dragon==='string'&&h.dragon.length<=25&&
    typeof h.action==='string'&&h.action.length<=50&&
    typeof h.source_id==='string'&&h.source_id.length<=128&&
    typeof h.change==='string'&&h.change.length<=500&&
    typeof h.digest==='string'&&HEX.test(h.digest)&&
    (i===0||h.sequence<all[i-1].sequence)))return null;
  if(f.idle_work!==undefined){
    const w=f.idle_work;
    if(!w||w.schema!=='skeleton.ai.dragon.idle_status.v1'||
      typeof w.configured!=='boolean'||w.idle_only!==true||
      !['not_connected','not_observed'].includes(w.host_state)||
      !count(w.max_tasks_per_tick)||w.max_tasks_per_tick<1||w.max_tasks_per_tick>3||
      !Array.isArray(w.history)||w.history.length>15||
      !w.history.every((e,i)=>e&&count(e.sequence)&&e.sequence>0&&utc(e.at)&&
        ['article','video','monitor'].includes(e.dragon)&&
        typeof e.source_id==='string'&&e.source_id.length<=128&&
        ['changed','unchanged','failed','paused'].includes(e.outcome)&&
        typeof e.change==='string'&&e.change.length<=200&&
        HEX.test(e.digest)&&(i===0||e.sequence<w.history[i-1].sequence))||
      !w.workers||typeof w.workers!=='object'||Array.isArray(w.workers)||
      Object.keys(w.workers).some(k=>!['article','video','monitor'].includes(k)))return null;
    for(const role of ['article','video','monitor'] as const){
      const item=w.workers[role];
      if(item!==undefined&&(!item||!count(item.known_sources)||
         !count(item.failed)||!count(item.incomplete_leases)||
         !count(item.last_changes)||!count(item.unchanged)||
         !(item.earliest_due_at===null||utc(item.earliest_due_at))))return null;
    }
  }
  if(f.glean!==undefined){
    const g=f.glean;
    if(!g||g.schema!=='skeleton.ai.dragon.glean.v1'||g.read_only!==true||
      !count(g.insights)||!count(g.stale_observations)||
      !count(g.total_active_observations)||!count(g.lenses_used)||
      typeof g.promotion!=='string'||g.promotion.length>180||
      !(g.updated_at===null||utc(g.updated_at))||
      !g.counts||!count(g.counts.contested)||!count(g.counts.wiki_candidate)||
      !count(g.counts.needs_independent_sources)||
      g.counts.contested+g.counts.wiki_candidate+g.counts.needs_independent_sources!==g.insights||
      !Array.isArray(g.cells)||g.cells.length>12||
      !g.cells.every((v)=>v&&typeof v.lens==='string'&&v.lens.length<=40&&
       HEX.test(v.proposition_digest)&&HEX.test(v.evidence_fingerprint)&&
       ['contested','wiki_candidate','needs_independent_sources'].includes(v.status)&&
       count(v.source_count)&&v.source_count>0&&count(v.support_sources)&&
       count(v.challenge_sources)&&count(v.support_groups)&&count(v.challenge_groups)&&
       v.support_sources<=v.source_count&&v.challenge_sources<=v.source_count&&
       v.support_groups<=v.support_sources&&v.challenge_groups<=v.challenge_sources&&
       Array.isArray(v.modalities)&&v.modalities.length>0&&v.modalities.length<=2&&
       v.modalities.every((media:unknown)=>media==='article'||media==='video')&&
       utc(v.latest_at)&&typeof v.exemplar==='string'&&v.exemplar.length<=240&&
       ['investigate_disagreement','independent_wiki_review','seek_separate_source'].includes(v.priority)&&
       (v.status!=='contested'||v.challenge_sources>0)&&
       (v.status!=='wiki_candidate'||v.support_sources>=2&&v.support_groups>=2)))return null;
  }
  if(f.almanakk!==undefined){
    const a=f.almanakk;
    if(!a||a.schema!=='skeleton.ai.dragon.almanakk.v1'||
      typeof a.architecture!=='string'||a.architecture.length>240||
      typeof a.policy!=='string'||a.policy.length>240||
      !a.counts||!['collected','wiki_verified','shadow_validated','weight_handoff']
       .every(k=>count(a.counts[k as keyof typeof a.counts]))||
      !Array.isArray(a.items)||a.items.length>20||
      !a.items.every(e=>e&&typeof e.source_id==='string'&&e.source_id.length<=128&&
       typeof e.dragon==='string'&&e.dragon.length<=25&&
       ['collected','wiki_verified','shadow_validated','weight_handoff'].includes(e.stage)&&
       utc(e.last_acquired_at)&&Array.isArray(e.topics)&&e.topics.length<=24&&
       e.topics.every((t:unknown)=>typeof t==='string'&&t.length<=64)&&
       (e.measured_gain===null||(typeof e.measured_gain==='number'&&
       Number.isFinite(e.measured_gain)&&e.measured_gain>=0&&e.measured_gain<=1)))||
      !Array.isArray(a.history)||a.history.length>25||
      !a.history.every((e,i)=>e&&count(e.sequence)&&e.sequence>0&&
       typeof e.dragon==='string'&&e.dragon.length<=25&&
       typeof e.source_id==='string'&&e.source_id.length<=128&&
       typeof e.stage==='string'&&e.stage.length<=32&&
       utc(e.at)&&typeof e.change==='string'&&e.change.length<=250&&
       typeof e.event_hash==='string'&&HEX.test(e.event_hash)&&
       (i===0||e.sequence<a.history[i-1].sequence)))return null;
  }
  return f as DragonFamilyProjection;
}
