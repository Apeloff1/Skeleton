import {describe, it} from 'node:test';
import assert from 'node:assert/strict';
import {EMPTY_WATCH_TIMELINE,ingestExplicitWatchSignal,ingestPlayerSnapshot} from '../features/Jeeves/companion/dragonWatchTimeline';
import {signalFromPlayer} from '../features/Jeeves/companion/dragonPlayerBridge';
describe('dragon video session integrity',()=>{
 const playing=(positionMs:number)=>({positionMs,durationMs:100000,playing:true,buffering:false,ended:false});
 it('deduplicates noisy playback updates in a one-second bucket',()=>{
  const first=ingestPlayerSnapshot(EMPTY_WATCH_TIMELINE,playing(1000),1);
  const second=ingestPlayerSnapshot(first,playing(1500),2);
  assert.equal(second.events.length,1);
  assert.equal(second.lastSnapshot?.positionMs,1500);
 });
 it('recognizes backward seek and prioritizes buffering',()=>{
  assert.equal(signalFromPlayer(playing(1000),playing(20000)).kind,'seek');
  assert.equal(signalFromPlayer({...playing(1000),buffering:true},playing(20000)).kind,'buffer');
 });
 it('never accepts player events after session end',()=>{
  const ended=ingestPlayerSnapshot(EMPTY_WATCH_TIMELINE,{...playing(100000),ended:true},1);
  assert.equal(ingestPlayerSnapshot(ended,playing(0),2),ended);
 });
 it('bounds retained history and rejects invalid explicit signals',()=>{
  let t=EMPTY_WATCH_TIMELINE;
  for(let i=0;i<150;i++)t=ingestExplicitWatchSignal(t,{kind:'insight',positionMs:i*1000},i);
  assert.equal(t.events.length,128);
  assert.equal(t.lastId,150);
  assert.equal(ingestExplicitWatchSignal(t,{kind:'insight',positionMs:NaN},151),t);
 });
});
