import {compileWatchCues,cuesAtPlayback,type TimedObservation} from '../features/Jeeves/companion/dragonWatchCues';
import {DEFAULT_VIDEO_PRIVACY,validateVideoPrivacy,mayProcessVideoModality} from '../features/Jeeves/companion/dragonVideoPrivacy';
describe('dragon video knowledge safety',()=>{
 const observation=(id:string,startMs:number,modality:TimedObservation['modality']='caption'):TimedObservation=>({
  id,startMs,endMs:startMs+1000,modality,text:'A useful, timestamped observation',
  confidence:.95,sourceId:'stream-1'
 });
 it('does not admit visual observations without consent',()=>{
  const cues=compileWatchCues([observation('a',1000,'frame_description'),observation('b',2000)]);
  expect(cues).toHaveLength(1);
  expect(cues[0].observationIds).toEqual(['b']);
 });
 it('deduplicates and merges nearby observations deterministically',()=>{
  const input=[observation('a',1000),observation('a',1000),observation('b',2000)];
  const cues=compileWatchCues(input);
  expect(cues).toHaveLength(1);
  expect(cues[0].observationIds).toEqual(['a','b']);
  expect(cues[0].requiresReview).toBe(true);
 });
 it('does not replay cue animations during backward seeking',()=>{
  const cues=compileWatchCues([observation('a',1000),observation('b',9000)]);
  expect(cuesAtPlayback(cues,8000,2000)).toEqual([]);
  expect(cuesAtPlayback(cues,0,2000)).toHaveLength(1);
 });
 it('defaults to video observation disabled',()=>{
  expect(mayProcessVideoModality(DEFAULT_VIDEO_PRIVACY,'transcript')).toBe(false);
  expect(()=>validateVideoPrivacy({...DEFAULT_VIDEO_PRIVACY,allowVisual:true})).toThrow();
 });
 it('rejects retention in ephemeral mode',()=>{
  expect(()=>validateVideoPrivacy({...DEFAULT_VIDEO_PRIVACY,mode:'ephemeral',retainObservations:true})).toThrow();
 });
});
