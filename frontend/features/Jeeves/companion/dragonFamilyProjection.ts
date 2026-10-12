/** Dragon Family projection: transport validation only, NEVER a source of XP. */
const HEX = /^[0-9a-f]{64}$/;
export type DragonFamilyRole = 'article'|'video'|'monitor';
export type DragonFamilyStage = 'unborn'|'egg'|'hatchling'|'juvenile'|'dragon';
export interface DragonFamilyProjection {
  schema:'skeleton.ai.dragon.family.v1';
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
  return f as DragonFamilyProjection;
}
