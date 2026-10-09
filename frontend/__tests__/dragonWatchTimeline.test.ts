import {EMPTY_WATCH_TIMELINE,ingestExplicitWatchSignal,ingestPlayerSnapshot} from '../features/Jeeves/companion/dragonWatchTimeline';
import {signalFromPlayer} from '../features/Jeeves/companion/dragonPlayerBridge';
describe('dragon video session integrity',()=>{
 const playing=(positionMs:number)=>({positionMs,durationMs:100000,playing:true,buffering:false,ended:false});
 it('deduplicates noisy playback updates in a one-second bucket',()=>{
  const first=ingestPlayerSnapshot(EMPTY_WATCH_TIMELINE,playing(1000),1);
  const second=ingestPlayerSnapshot(first,playing(1500),2);
  expect(second.events).toHaveLength(1);
  expect(second.lastSnapshot?.positionMs).toBe(1500);
 });
 it('recognizes backward seek and prioritizes buffering',()=>{
  expect(signalFromPlayer(playing(1000),playing(20000)).kind).toBe('seek');
  expect(signalFromPlayer({...playing(1000),buffering:true},playing(20000)).kind).toBe('buffer');
 });
 it('never accepts player events after session end',()=>{
  const ended=ingestPlayerSnapshot(EMPTY_WATCH_TIMELINE,{...playing(100000),ended:true},1);
  expect(ingestPlayerSnapshot(ended,playing(0),2)).toBe(ended);
 });
 it('bounds retained history and rejects invalid explicit signals',()=>{
  let t=EMPTY_WATCH_TIMELINE;
  for(let i=0;i<150;i++)t=ingestExplicitWatchSignal(t,{kind:'insight',positionMs:i*1000},i);
  expect(t.events).toHaveLength(128);
  expect(t.lastId).toBe(150);
  expect(ingestExplicitWatchSignal(t,{kind:'insight',positionMs:NaN},151)).toBe(t);
 });
});
