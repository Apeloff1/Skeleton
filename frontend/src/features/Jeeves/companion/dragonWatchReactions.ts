/** Build time-coded reaction signals without replaying cues during seeks or pauses. */
import {cuesAtPlayback,type WatchCue} from './dragonWatchCues';
import type {PlayerSnapshot} from './dragonPlayerBridge';
import type {WatchSignal} from './dragonWatch';
export interface ReactionCursor {lastPositionMs:number;seenIds:readonly string[];lastCue?:string}
export const EMPTY_REACTION_CURSOR:ReactionCursor={lastPositionMs:0,seenIds:[]};
export interface ReactionResult {cursor:ReactionCursor;signal?:WatchSignal}
export function advanceWatchReactions(cursor:ReactionCursor,player:PlayerSnapshot,cues:readonly WatchCue[]):ReactionResult{
 const position=Number.isFinite(player.positionMs)?Math.max(0,player.positionMs):0;
 if(player.ended||player.buffering||!player.playing||position<cursor.lastPositionMs)
  return {cursor:{...cursor,lastPositionMs:position}};
 const available=cuesAtPlayback(cues,cursor.lastPositionMs,position);
 const unseen=available.find(c=>!cursor.seenIds.includes(c.id));
 if(!unseen)return {cursor:{...cursor,lastPositionMs:position}};
 const signal:WatchSignal={kind:unseen.kind==='frame'?'frame':'caption',positionMs:position,durationMs:player.durationMs,confidence:unseen.confidence};
 return {cursor:{lastPositionMs:position,seenIds:[...cursor.seenIds.slice(-511),unseen.id],lastCue:unseen.id},signal};
}
