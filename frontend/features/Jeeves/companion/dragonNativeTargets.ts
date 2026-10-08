/** Real native-code practice entries, never simulated console ROMs. */
export interface NativeTarget {
 id:string;family:string;generation:string;year:number;cpu:string;
 graphics:string;sound:string;input:string;toolchain:string;
 output:string;status:'native_source'|'toolchain_adapter'|'licensed_sdk';
}
export interface NativeAttempt {
 attempt_id:string;lesson_id:string;owner:string;target_id:string;
 style:string;state:string;source_digest:string;created_at:number;reviewed:boolean;
}
const digest=/^[a-f0-9]{64}$/;
export function normalizeNativeTargets(input:unknown):NativeTarget[]{
 if(!Array.isArray(input))return [];
 return input.filter((t):t is NativeTarget=>!!t&&typeof t==='object'&&
  typeof t.id==='string'&&/^[a-z0-9_]{2,64}$/.test(t.id)&&
  typeof t.family==='string'&&t.family.length<80&&
  typeof t.generation==='string'&&t.generation.length<80&&
  Number.isInteger(t.year)&&t.year>=1970&&t.year<=2100&&
  typeof t.toolchain==='string'&&t.toolchain.length<100&&
  typeof t.output==='string'&&t.output.length<12&&
  typeof t.cpu==='string'&&typeof t.graphics==='string'&&
  typeof t.sound==='string'&&typeof t.input==='string'&&
  ['native_source','toolchain_adapter','licensed_sdk'].includes(t.status)).slice(0,100);
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
  typeof a.reviewed==='boolean').slice(0,50);
}
export function titleCaseId(key:string):string{
 return key.replace(/_/g,' ').replace(/\b\w/g,m=>m.toUpperCase());
}
