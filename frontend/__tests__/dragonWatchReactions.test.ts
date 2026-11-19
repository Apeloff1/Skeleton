import {advanceWatchReactions,EMPTY_REACTION_CURSOR} from '../features/Jeeves/companion/dragonWatchReactions';
import type {WatchCue} from '../features/Jeeves/companion/dragonWatchCues';
describe('video companion reaction timing',()=>{
 const cue:WatchCue={id:'e1',positionMs:2000,kind:'frame',title:'Visual observation',description:'A scene',observationIds:['e1'],confidence:.9,requiresReview:true};
 const player=(positionMs:number,playing=true)=>({positionMs,durationMs:10000,playing,buffering:false,ended:false});
 it('fires when playback crosses the observation timestamp',()=>{
  const result=advanceWatchReactions(EMPTY_REACTION_CURSOR,player(3000),[cue]);
  expect(result.signal?.kind).toBe('frame');
  expect(result.cursor.seenIds).toContain('e1');
 });
 it('never fires the same cue twice',()=>{
  const first=advanceWatchReactions(EMPTY_REACTION_CURSOR,player(3000),[cue]);
  expect(advanceWatchReactions(first.cursor,player(4000),[cue]).signal).toBeUndefined();
 });
 it('does not fire while paused or seeking backward',()=>{
  const paused=advanceWatchReactions(EMPTY_REACTION_CURSOR,player(3000,false),[cue]);
  expect(paused.signal).toBeUndefined();
  expect(advanceWatchReactions({...EMPTY_REACTION_CURSOR,lastPositionMs:9000},player(1000),[cue]).signal).toBeUndefined();
 });
});
