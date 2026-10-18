/** Read-only projection of the canonical, owner-scoped DragonPracticeLab.
 * No local petting, text input, page count or render tick may grant XP.
 */
export interface DragonPracticeProgress {
 schema:'skeleton.ai.dragon.practice_progress.v1';
 level:number;
 xp:number;
 next_level_xp:number;
 verified_lessons:number;
 demos_built:number;
 demos_reviewed:number;
 demo_attempts:number;
 failed_attempts:number;
 skills:Record<string,number>;
 unlocked:readonly string[];
}
export type DragonAttemptState='built'|'reviewed'|'rejected'|'failed';
export interface DragonPracticeAttempt {
 attempt_id:string;
 lesson_id:string;
 kind:string;
 state:DragonAttemptState;
 artifact_digest:string;
 supported:readonly string[];
 deferred:readonly string[];
}
export interface DragonPracticeSubscription {
 enabled:boolean;
 expires_at:number;
 next_due:number;
 interval_seconds:number;
 remaining_ticks:number;
 demos_per_tick:number;
}
const finite=(n:unknown):n is number=>typeof n==='number'&&Number.isFinite(n);
const integer=(n:unknown):n is number=>finite(n)&&Number.isSafeInteger(n)&&n>=0;
export function validateDragonProgress(input:unknown):DragonPracticeProgress|null {
 if(!input||typeof input!=='object')return null;
 const p=input as Partial<DragonPracticeProgress>;
 if(p.schema!=='skeleton.ai.dragon.practice_progress.v1'
  ||!integer(p.level)||p.level<1||p.level>10000
  ||!integer(p.xp)||!integer(p.next_level_xp)||p.next_level_xp<=p.xp
  ||!integer(p.verified_lessons)||!integer(p.demos_built)
  ||!integer(p.demos_reviewed)||!integer(p.demo_attempts)||!integer(p.failed_attempts)
  ||p.demos_reviewed>p.demos_built||p.demos_built>p.demo_attempts
  ||!p.skills||typeof p.skills!=='object'
  ||!Array.isArray(p.unlocked)||p.unlocked.length>32
  ||p.unlocked.some(s=>typeof s!=='string'||s.length>100))return null;
 const checks=['research','game_design','prototyping','verification'];
 if(!checks.every(k=>integer(p.skills?.[k])&&(p.skills?.[k]??101)<=100))return null;
 const expected=75*p.level*(p.level+1)/2;
 const previous=75*(p.level-1)*p.level/2;
 if(p.next_level_xp!==expected||p.xp<previous)return null;
 return p as DragonPracticeProgress;
}
export function levelFraction(p:DragonPracticeProgress):number{
 const floor=75*(p.level-1)*p.level/2;
 return Math.max(0,Math.min(1,(p.xp-floor)/Math.max(1,p.next_level_xp-floor)));
}
export function dragonRank(level:number):string {
 if(level>=15)return 'Master Game Dragon';
 if(level>=10)return 'Star Cartographer';
 if(level>=7)return 'Winged Builder';
 if(level>=4)return 'Glasses Scholar';
 if(level>=2)return 'Apprentice Forge';
 return 'Little Explorer';
}
export function normalizeDragonAttempts(rows:unknown):DragonPracticeAttempt[]{
 if(!Array.isArray(rows))return [];
 const allowed=new Set(['built','reviewed','rejected','failed']);
 return rows.slice(0,50).filter((x):x is DragonPracticeAttempt=>
  !!x&&typeof x==='object'&&
  typeof x.attempt_id==='string'&&/^[0-9a-f]{64}$/.test(x.attempt_id)&&
  typeof x.lesson_id==='string'&&/^[0-9a-f]{64}$/.test(x.lesson_id)&&
  typeof x.kind==='string'&&x.kind.length<=64&&
  allowed.has(x.state)&&
  typeof x.artifact_digest==='string'&&
  (x.artifact_digest===''||/^[0-9a-f]{64}$/.test(x.artifact_digest))&&
  Array.isArray(x.supported)&&x.supported.length<=16&&
  Array.isArray(x.deferred)&&x.deferred.length<=16&&
  x.supported.every((s:unknown)=>typeof s==='string'&&s.length<=80)&&
  x.deferred.every((s:unknown)=>typeof s==='string'&&s.length<=80)
 );
}
