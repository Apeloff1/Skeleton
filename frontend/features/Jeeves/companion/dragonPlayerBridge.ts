/** Safe player integration contract for the companion watch-along. */
import type {WatchSignal} from './dragonWatch';
export interface PlayerSnapshot {positionMs:number;durationMs?:number;playing:boolean;buffering:boolean;ended:boolean}
export function signalFromPlayer(snapshot:PlayerSnapshot,previous?:PlayerSnapshot):WatchSignal {
 const positionMs=Number.isFinite(snapshot.positionMs)?Math.max(0,snapshot.positionMs):0;
 const durationMs=snapshot.durationMs&&Number.isFinite(snapshot.durationMs)?Math.max(0,snapshot.durationMs):undefined;
 const base={positionMs,durationMs};
 if(snapshot.ended)return {...base,kind:'end'};
 if(snapshot.buffering)return {...base,kind:'buffer'};
 if(previous&&Math.abs(positionMs-previous.positionMs)>15000)return {...base,kind:'seek'};
 if(!snapshot.playing)return {...base,kind:'pause'};
 return {...base,kind:'play'};
}
