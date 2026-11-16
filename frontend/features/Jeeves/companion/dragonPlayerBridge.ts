/** Player-to-companion signal bridge with deterministic seek and jitter handling. */
import type {WatchSignal} from './dragonWatch';
export interface PlayerSnapshot {positionMs:number;durationMs?:number;playing:boolean;buffering:boolean;ended:boolean}
const finiteNonnegative=(value:number):number=>Number.isFinite(value)?Math.max(0,value):0;
export function signalFromPlayer(snapshot:PlayerSnapshot,previous?:PlayerSnapshot):WatchSignal {
 const positionMs=finiteNonnegative(snapshot.positionMs);
 const durationMs=snapshot.durationMs!==undefined&&Number.isFinite(snapshot.durationMs)&&snapshot.durationMs>0?snapshot.durationMs:undefined;
 const base={positionMs,durationMs};
 if(snapshot.ended)return {...base,kind:'end'};
 if(snapshot.buffering)return {...base,kind:'buffer'};
 if(previous){
  const oldPosition=finiteNonnegative(previous.positionMs);
  const jump=positionMs-oldPosition;
  // A backwards jump is always a seek; forward jumps must exceed plausible playback.
  if(jump < -1200 || jump > 15000)return {...base,kind:'seek'};
 }
 if(!snapshot.playing)return {...base,kind:'pause'};
 return {...base,kind:'play'};
}
