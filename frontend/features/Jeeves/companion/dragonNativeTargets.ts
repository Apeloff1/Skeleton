/** Real native-code practice entries, never simulated console ROMs. */
export interface NativeTarget {
 id:string;family:string;generation:string;year:number;cpu:string;
 graphics:string;sound:string;input:string;toolchain:string;
 output:string;status:'native_source'|'toolchain_adapter'|'licensed_sdk';
 supported_styles?:string[];
}
export interface NativeAttempt {
 attempt_id:string;lesson_id:string;owner:string;target_id:string;
 style:string;state:string;source_digest:string;created_at:number;reviewed:boolean;
 variant?:number;
}
const digest=/^[a-f0-9]{64}$/;
export function normalizeNativeTargets(input:unknown):NativeTarget[]{
 if(!Array.isArray(input))return [];
 return input.filter((t: unknown):t is NativeTarget=>!!t&&typeof t==='object'&&
  typeof t.id==='string'&&/^[a-z0-9_]{2,64}$/.test(t.id)&&
  typeof t.family==='string'&&t.family.length<80&&
  typeof t.generation==='string'&&t.generation.length<80&&
  Number.isInteger(t.year)&&t.year>=1970&&t.year<=2100&&
  typeof t.toolchain==='string'&&t.toolchain.length<100&&
  typeof t.output==='string'&&t.output.length<12&&
  typeof t.cpu==='string'&&typeof t.graphics==='string'&&
  typeof t.sound==='string'&&typeof t.input==='string'&&
  ['native_source','toolchain_adapter','licensed_sdk'].includes(t.status)&&
  (!t.supported_styles||(Array.isArray(t.supported_styles)&&
   t.supported_styles.every((s: unknown)=>typeof s==='string'&&/^[a-z_]{2,64}$/.test(s))))
 ).slice(0,100);
}
export function normalizeNativeAttempts(input:unknown):NativeAttempt[]{
 if(!Array.isArray(input))return [];
 return input.filter((a):a is NativeAttempt=>!!a&&typeof a==='object'&&
  typeof a.attempt_id==='string'&&digest.test(a.attempt_id)&&
  typeof a.lesson_id==='string'&&digest.test(a.lesson_id)&&
  typeof a.source_digest==='string'&&digest.test(a.source_digest)&&
  typeof a.target_id==='string'&&/^[a-z0-9_]{2,64}$/.test(a.target_id)&&
  typeof a.style==='string'&&a.style.length<80&&
  a.state==='source_generated'&&Number.isFinite(a.created_at)&&
  typeof a.reviewed==='boolean'&&
  (a.variant===undefined||(Number.isSafeInteger(a.variant)&&a.variant>=0&&a.variant<=7))).slice(0,50);
}
export function titleCaseId(key:string):string{
 return key.replace(/_/g,' ').replace(/\b\w/g,m=>m.toUpperCase());
}

export interface NativeCurriculumRecommendation {
 target:string;genre:string;milestone_id:string;reason:string;
 priority:number;previous_attempts:number;build_evidence_count:number;
 proof_level:string;
}
export interface NativeCurriculum {
 owner:string;curriculum_level:number;
 structural_build_targets:string[];native_source_attempts:number;
 unlocked:NativeCurriculumRecommendation[];
 blocked:{id:string;target:string;requires:string[];missing:string[];reason:string}[];
 next_recommendation:NativeCurriculumRecommendation|null;
 proof_scope:string;schema:string;
}
export function normalizeNativeCurriculum(value:unknown):NativeCurriculum|null {
 if(!value||typeof value!=='object')return null;
 const r=value as NativeCurriculum;
 if(typeof r.owner!=='string'||!digest.test(r.owner)||
    !Number.isInteger(r.curriculum_level)||r.curriculum_level<1||r.curriculum_level>8||
    !Number.isInteger(r.native_source_attempts)||r.native_source_attempts<0||
    !Array.isArray(r.unlocked)||r.unlocked.length>60||
    !Array.isArray(r.blocked)||r.blocked.length>60||
    !Array.isArray(r.structural_build_targets)||r.structural_build_targets.length>50||
    r.schema!=='skeleton.ai.dragon.native_curriculum.v1')return null;
 const valid=(c:unknown):c is NativeCurriculumRecommendation=>{
  if(!c||typeof c!=='object')return false;
  const x=c as NativeCurriculumRecommendation;
  return typeof x.milestone_id==='string'&&/^[a-z0-9_]{2,64}$/.test(x.milestone_id)&&
   typeof x.target==='string'&&/^[a-z0-9_]{2,64}$/.test(x.target)&&
   typeof x.genre==='string'&&/^[a-z_]{3,64}$/.test(x.genre)&&
   typeof x.reason==='string'&&x.reason.length<180&&
   Number.isFinite(x.priority)&&
   Number.isInteger(x.previous_attempts)&&x.previous_attempts>=0&&
   Number.isInteger(x.build_evidence_count)&&x.build_evidence_count>=0&&
   typeof x.proof_level==='string'&&x.proof_level.length<80;
 };
 if(!r.unlocked.every(valid)||(r.next_recommendation!==null&&!valid(r.next_recommendation)))return null;
 if(!r.structural_build_targets.every(x=>typeof x==='string'&&/^[a-z0-9_]{2,64}$/.test(x)))return null;
 return r;
}
