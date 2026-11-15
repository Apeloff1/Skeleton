/** Cosmetic-only animation budget. A level never authorizes work or trains a model. */
import type { CompanionPhase } from './dragonCompanionState';

export type DragonLevelProfile = Readonly<{
  level: number; stage: number; scale: number; breathMs: number; blinkMs: number;
  beatMs: number; amplitude: number; snuggleEvery: number; wingScale: number; treasure: number;
}>;
export function dragonLevelProfile(level: number|undefined, stage: number|undefined, phase: CompanionPhase): DragonLevelProfile {
  const l=Number.isFinite(level)?Math.max(1,Math.min(60,Math.floor(level!))):1;
  const s=Number.isFinite(stage)?Math.max(0,Math.min(5,Math.floor(stage!))):0;
  const within=Math.max(0,Math.min(1,(l-(s*10+1))/9));
  const cozy=phase==='sleeping'||phase==='snuggle';
  const maturity=(s+within)/6;
  return {
    level:l,stage:s,scale:.89+.19*maturity,
    breathMs:Math.round((cozy?3000:1900)+850*maturity),
    blinkMs:Math.round((cozy?6200:4300)+1800*maturity),
    beatMs:Math.round((cozy?4900:3200)+950*maturity),
    amplitude:(cozy?.48:.85)*(1-.22*maturity),
    snuggleEvery:cozy?2:s>=4?3:5,
    wingScale:.86+.19*maturity,
    treasure:s>=5?Math.min(6,2+Math.floor(within*5)):s===4?2:s===3?1:0,
  };
}
export function evidenceLevel(growth: number): number {
  const n=Number.isFinite(growth)?Math.max(0,Math.min(1000,growth)):0;
  const starts=[0,120,300,550,800,1150];
  const stage=starts.slice(1).filter(x=>n>=x).length;
  return stage*10+1+Math.floor(10*(n-starts[stage])/(starts[stage+1]-starts[stage]));
}
