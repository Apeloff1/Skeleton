import type { Catalogue, Family } from './atelierAsset';
import type { DragonCompanionState } from '../dragonCompanionState';
export type Step = Readonly<{family: Family; clip: string; repeat: boolean; serial: number}>;
export type Director = Readonly<{step: Step; airborne: boolean; cursor: number; reduced: boolean}>;
function choose(catalogue: Catalogue, family: Family, cursor: number): Step {
  const choices = catalogue[family];
  const clip = choices[cursor % choices.length];
  if (!clip) throw new Error('Missing real clip in '+family);
  return Object.freeze({family,clip,repeat: family === 'ground' || family === 'flight',serial:cursor});
}
function next(d: Director, catalogue: Catalogue, family: Family): Director {
  const cursor = d.cursor >= Number.MAX_SAFE_INTEGER-1 ? 0 : d.cursor+1;
  return {...d,cursor,step:choose(catalogue,family,cursor)};
}
export function startDirector(catalogue: Catalogue): Director {
  return {step:choose(catalogue,'ground',0),airborne:false,cursor:0,reduced:false};
}
/** Visual intent only. Never starts, completes or changes a capture. */
export function flightIntent(state: DragonCompanionState): boolean {
  return state.wings && (state.phase === 'launching' || state.phase === 'crawling' || state.phase === 'acquiring');
}
export function setIntent(d: Director,catalogue: Catalogue,airborne: boolean,reduced: boolean): Director {
  const value = {...d,airborne:airborne&&!reduced,reduced};
  if (reduced) return d.step.family === 'ground' ? value : next(value,catalogue,'ground');
  if (d.step.family === 'ground' && airborne) return next(value,catalogue,'takeoff');
  if (d.step.family === 'flight' && !airborne) return next(value,catalogue,'landing');
  return value;
}
/** Exact mixer completion only; ignore late callbacks from obsolete actions. */
export function completeStep(d: Director,catalogue: Catalogue,serial: number): Director {
  if (d.reduced || d.step.serial !== serial) return d;
  switch (d.step.family) {
    case 'takeoff': return next(d,catalogue,d.airborne?'flight':'landing');
    case 'landing': return next(d,catalogue,d.airborne?'takeoff':'ground');
    default: return d;
  }
}

/** Explicit visual inspection is separate from the recorded-event director.
 * Keep exact exported names, and allocate a fresh serial even for the same clip.
 */
export function inspectClip(d: Director,catalogue:Catalogue,family:Family,clip:string,reduced:boolean):Director {
  if(!catalogue[family].includes(clip))throw new Error('Clip does not belong to the verified family');
  const cursor=d.cursor>=Number.MAX_SAFE_INTEGER-1?0:d.cursor+1;
  return {cursor,airborne:false,reduced,step:Object.freeze({family,clip,repeat:true,serial:cursor})};
}
export function resetLive(d:Director,catalogue:Catalogue,airborne:boolean,reduced:boolean):Director {
  const ground=next({...d,airborne:false,reduced:false},catalogue,'ground');
  return setIntent(ground,catalogue,airborne,reduced);
}
