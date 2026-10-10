/** Strict product projections; these checks validate shape, never grant authority. */
export type DeliveryDesign={
 schema:'skeleton.ai.dragon.game_design.v1';title:string;target:string;genre:string;
 palette:string;stages:number;candidates:number;seed:number;difficulty:number;
 hero:string;quest_theme:string;project_notes:string;
};
export type DeliveryCitation={
 source_id:string;revision_digest:string;note_id:string;source_url:string;title:string;
 mechanic:string;statement:string;stance:string;confidence_ppm:number;dependence_group:string;
 approval:'wiki_hoag_approved'|'source_reviewed_only';review_digest:string|null;expires_at:number|null;
 review_evidence_digest:string|null;approval_evidence_digest:string|null;
};
export type DeliveryBrief={
 schema:'skeleton.dragon.delivery_brief.v1';owner:string;design:DeliveryDesign;
 plan_digest:string;design_digest:string;knowledge_root:string;query:string;
 prepared_at:number;expires_at:number;citations:DeliveryCitation[];independent_groups:number;
 blockers:string[];conflicts:string[];ready_for_source_generation:boolean;
 controls:{effective:string[];metadata_only:string[];cartridge_single_stage:boolean};
 toolchain:string;output_extension:string;compiler_adapter_available:boolean;
 build_state:'not_built';gameplay_state:'not_verified';training_authorized:false;release_authorized:false;
};
export type DeliveryOverview={
 schema:'skeleton.dragon.delivery_overview.v1';owner:string;knowledge_root:string;
 counts:Record<string,number>;acquisition:{stage:string;state:string;count:number}[];
 next_actions:{code:string;label:string}[];resource_runtime_ready:boolean;practice_storage_ready:boolean;
 memory_reconciliation_required:boolean;overall_completion_percent:null;
};
export type DeliveryAlmanac={topic_id:string;headers:string[];discovered_sources:number;machine_learning_records:number};
const HASH=/^[a-f0-9]{64}$/;
const record=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const text=(v:unknown,max=300):v is string=>typeof v==='string'&&v.length<=max&&!/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(v);
const num=(v:unknown,max=4102444800):v is number=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0&&v<=max;
const strings=(v:unknown,max=64):v is string[]=>Array.isArray(v)&&v.length<=max&&v.every(x=>text(x));
const hash=(v:unknown):v is string=>typeof v==='string'&&HASH.test(v);
export const isDesktop=(target:string)=>['pc_linux','pc_windows','pc_macos','steam_deck'].includes(target);
export function starterDeliveryDesign(target='game_boy',genre='arcade_score_attack'):DeliveryDesign{
 return{schema:'skeleton.ai.dragon.game_design.v1',title:'Dragon Original Quest',target,genre,
  palette:target==='game_boy'?'dmg_green':'vga_dusk',stages:isDesktop(target)?4:1,
  candidates:isDesktop(target)?8:1,seed:1,difficulty:4,hero:'hatchling',quest_theme:'ancient_ruins',
  project_notes:'Original homebrew with reviewed design guidance'};
}
export function normalizeDeliveryCitations(v:unknown):DeliveryCitation[]|null{
 if(!Array.isArray(v)||v.length>32)return null;
 const rows:DeliveryCitation[]=[];
 for(const r of v){
  if(!record(r)||!text(r.source_id,128)||!text(r.note_id,128)||!hash(r.revision_digest)||
     !text(r.source_url,2048)||!/^https?:\/\//.test(r.source_url)||!text(r.title,300)||
     !text(r.statement,2000)||!text(r.mechanic,128)||!text(r.dependence_group,128)||
     !['supports','challenges','uncertain'].includes(String(r.stance))||!num(r.confidence_ppm,1000000)||
     !['wiki_hoag_approved','source_reviewed_only'].includes(String(r.approval)))return null;
  if(r.approval==='wiki_hoag_approved'&&(!hash(r.review_digest)||!hash(r.review_evidence_digest)||!hash(r.approval_evidence_digest)||!num(r.expires_at)))return null;
  if(r.approval==='source_reviewed_only'&&(r.review_digest!==null||r.expires_at!==null))return null;
  rows.push(r as DeliveryCitation);
 }
 return rows;
}
export function normalizeDeliveryBrief(v:unknown,now:number):DeliveryBrief|null{
 if(!record(v)||!Number.isFinite(now)||v.schema!=='skeleton.dragon.delivery_brief.v1'||
  !text(v.owner,128)||!hash(v.plan_digest)||!hash(v.design_digest)||!hash(v.knowledge_root)||
  !text(v.query)||!record(v.design)||v.design.schema!=='skeleton.ai.dragon.game_design.v1'||
  !num(v.prepared_at)||!num(v.expires_at)||v.prepared_at>now||v.expires_at<=now||v.expires_at>v.prepared_at+300||
  !strings(v.blockers)||!strings(v.conflicts)||!num(v.independent_groups,32)||
  !record(v.controls)||!strings(v.controls.effective)||!strings(v.controls.metadata_only)||
  typeof v.controls.cartridge_single_stage!=='boolean'||typeof v.ready_for_source_generation!=='boolean'||
  typeof v.compiler_adapter_available!=='boolean'||!text(v.toolchain)||!text(v.output_extension,16)||
  v.build_state!=='not_built'||v.gameplay_state!=='not_verified'||v.training_authorized!==false||v.release_authorized!==false)return null;
 const citations=normalizeDeliveryCitations(v.citations);
 if(!citations||citations.some(c=>c.approval!=='wiki_hoag_approved'||c.stance!=='supports'||(c.expires_at??0)<=now))return null;
 if(v.ready_for_source_generation!==(v.blockers.length===0)||
   (v.ready_for_source_generation&&(v.independent_groups<2||v.conflicts.length>0)))return null;
 return {...v,citations} as DeliveryBrief;
}
export function normalizeDeliveryOverview(v:unknown):DeliveryOverview|null{
 if(!record(v)||v.schema!=='skeleton.dragon.delivery_overview.v1'||!text(v.owner,128)||
  !hash(v.knowledge_root)||v.overall_completion_percent!==null||!record(v.counts)||
  !['discovered_sources','almanacs','reviewed_sources','reviewed_notes','wiki_reviews','approved_mechanics','current_memory_cards','pending_recrawls','source_targets','catalog_targets','compiler_adapters'].every(k=>num((v.counts as Record<string,unknown>)[k],10000000))||
  typeof v.resource_runtime_ready!=='boolean'||typeof v.practice_storage_ready!=='boolean'||
  typeof v.memory_reconciliation_required!=='boolean'||v.training_authorized!==false||v.release_authorized!==false||
  !Array.isArray(v.acquisition)||v.acquisition.length>30||!v.acquisition.every(r=>record(r)&&text(r.stage,32)&&text(r.state,32)&&num(r.count,100000))||
  !Array.isArray(v.next_actions)||v.next_actions.length>12||!v.next_actions.every(r=>record(r)&&text(r.code,64)&&text(r.label,300)))return null;
 return v as DeliveryOverview;
}
export function normalizeDeliveryAlmanacs(v:unknown):DeliveryAlmanac[]|null{
 if(!Array.isArray(v)||v.length>32)return null;
 if(!v.every(r=>record(r)&&text(r.topic_id,128)&&strings(r.headers,16)&&num(r.discovered_sources,100000)&&num(r.machine_learning_records,100000)))return null;
 return v as DeliveryAlmanac[];
}

export type DeliveryLearning={learning_digest:string;kind:string;statement:string;method:string;limitations:string;current_source_lineage:boolean;empirical_truth_established:false;epistemic_state:string};
export function normalizeDeliveryLearning(v:unknown):DeliveryLearning[]|null{
 if(!Array.isArray(v)||v.length>32)return null;
 if(!v.every(r=>record(r)&&hash(r.learning_digest)&&text(r.kind,64)&&text(r.statement,2048)&&text(r.method,2048)&&text(r.limitations,2048)&&typeof r.current_source_lineage==='boolean'&&r.empirical_truth_established===false&&r.epistemic_state==='unreviewed'&&r.memory_promotion_authorized===false&&r.training_authorized===false))return null;
 return v as DeliveryLearning[];
}
