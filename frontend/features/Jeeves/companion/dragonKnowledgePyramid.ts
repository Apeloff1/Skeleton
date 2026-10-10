/** Strict display projection of server-verified Almanac/Wiki/HOAG custody.
 * Parsing is defensive UI validation, not evidence authentication.
 */
export type DragonKnowledgeCard = {
 mechanic:string;
 grade:'independently_reviewed_not_universal_truth';
 independent_groups:number;
 review_digest:string;
 review_evidence_digest:string;
 source_revisions:string[];
 expires_at:number;
 training_authorized:false;
 release_authorized:false;
};
export type DragonKnowledgeView = {
 schema:'skeleton.dragon.hoag_wisdom_view.v1';
 owner:string;
 knowledge_root:string;
 head_digest:string|null;
 items:DragonKnowledgeCard[];
 pending_recrawls:number;
 permanent_memory_eligible:number;
 authority:'advisory_only';
};
const HASH=/^[a-f0-9]{64}$/;
const ID=/^[A-Za-z0-9][A-Za-z0-9.:-]{0,127}$/;
const record=(v:unknown):v is Record<string,unknown>=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const bounded=(x:unknown,max:number)=>typeof x==='number'&&Number.isSafeInteger(x)&&x>=0&&x<=max;

export function normalizeDragonKnowledgeView(value:unknown,nowSeconds:number):DragonKnowledgeView|null{
 if(!record(value)||!Number.isFinite(nowSeconds)||
    value.schema!=='skeleton.dragon.hoag_wisdom_view.v1'||
    value.authority!=='advisory_only'||typeof value.owner!=='string'||!ID.test(value.owner)||
    typeof value.knowledge_root!=='string'||!HASH.test(value.knowledge_root)||
    (value.head_digest!==null&&(typeof value.head_digest!=='string'||!HASH.test(value.head_digest)))||
    !bounded(value.pending_recrawls,10000)||
    !Array.isArray(value.items)||value.items.length>64||
    value.permanent_memory_eligible!==value.items.length||
    (value.items.length>0&&value.head_digest===null))return null;
 const cards:DragonKnowledgeCard[]=[];
 const seen=new Set<string>();
 for(const entry of value.items){
  if(!record(entry)||typeof entry.mechanic!=='string'||!ID.test(entry.mechanic)||
     entry.grade!=='independently_reviewed_not_universal_truth'||
     !bounded(entry.independent_groups,256)||Number(entry.independent_groups)<2||
     typeof entry.review_digest!=='string'||!HASH.test(entry.review_digest)||
     typeof entry.review_evidence_digest!=='string'||!HASH.test(entry.review_evidence_digest)||
     !bounded(entry.expires_at,4102444800)||Number(entry.expires_at)<=nowSeconds||
     entry.training_authorized!==false||entry.release_authorized!==false||
     !Array.isArray(entry.source_revisions)||entry.source_revisions.length<2||
     entry.source_revisions.length>256||
     entry.source_revisions.some(x=>typeof x!=='string'||!HASH.test(x))||
     seen.has(entry.review_digest as string))return null;
  seen.add(entry.review_digest as string);
  cards.push(entry as DragonKnowledgeCard);
 }
 return {...value,items:cards} as DragonKnowledgeView;
}
