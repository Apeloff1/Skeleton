/** Deterministic, consent-aware video observation cue engine.
 * Player playback is never treated as proof of watched or understood content.
 */
export type ObservationModality='transcript'|'caption'|'frame_description'|'audio_description'|'ocr';
export interface TimedObservation {
 id:string;startMs:number;endMs:number;modality:ObservationModality;
 text:string;confidence:number;sourceId:string;
}
export interface WatchCue {
 id:string;positionMs:number;kind:'caption'|'frame'|'insight';
 title:string;description:string;observationIds:readonly string[];
 confidence:number;requiresReview:boolean;
}
export interface CuePolicy {
 minConfidence:number;maxCues:number;mergeWindowMs:number;
 allowTranscript:boolean;allowVisual:boolean;allowAudio:boolean;
}
export const DEFAULT_CUE_POLICY:CuePolicy={
 minConfidence:.65,maxCues:256,mergeWindowMs:4000,
 allowTranscript:true,allowVisual:false,allowAudio:false
};
const modalities=new Set<ObservationModality>(['transcript','caption','frame_description','audio_description','ocr']);
function permitted(o:TimedObservation,p:CuePolicy):boolean{
 if(o.modality==='transcript'||o.modality==='caption')return p.allowTranscript;
 if(o.modality==='frame_description'||o.modality==='ocr')return p.allowVisual;
 return p.allowAudio;
}
function valid(o:TimedObservation):boolean{
 return Boolean(o.id&&o.sourceId&&o.text.trim()&&o.text.length<=10000&&
  modalities.has(o.modality)&&Number.isSafeInteger(o.startMs)&&Number.isSafeInteger(o.endMs)&&
  o.startMs>=0&&o.endMs>o.startMs&&o.endMs<=86400000&&
  Number.isFinite(o.confidence)&&o.confidence>=0&&o.confidence<=1);
}
export function compileWatchCues(observations:readonly TimedObservation[],policy:CuePolicy=DEFAULT_CUE_POLICY):readonly WatchCue[]{
 if(!Number.isFinite(policy.minConfidence)||policy.minConfidence<0||policy.minConfidence>1||
  !Number.isSafeInteger(policy.maxCues)||policy.maxCues<1||policy.maxCues>10000||
  !Number.isSafeInteger(policy.mergeWindowMs)||policy.mergeWindowMs<0||policy.mergeWindowMs>60000)throw new Error('Invalid cue policy');
 const selected=observations.filter(o=>valid(o)&&permitted(o,policy)&&o.confidence>=policy.minConfidence)
  .sort((a,b)=>a.startMs-b.startMs||a.id.localeCompare(b.id));
 const cues:WatchCue[]=[];
 const seen=new Set<string>();
 for(const observation of selected){
  if(seen.has(observation.id))continue;
  seen.add(observation.id);
  const previous=cues[cues.length-1];
  const kind=observation.modality==='frame_description'||observation.modality==='ocr'?'frame':'caption';
  if(previous&&previous.kind===kind&&observation.startMs-previous.positionMs<=policy.mergeWindowMs){
   cues[cues.length-1]={...previous,observationIds:[...previous.observationIds,observation.id],
    confidence:Math.min(previous.confidence,observation.confidence),
    description:previous.description+' · '+observation.text.slice(0,120)};
   continue;
  }
  if(cues.length>=policy.maxCues)break;
  cues.push({id:observation.id,positionMs:observation.startMs,kind,
   title:kind==='frame'?'Visual observation':'Caption observation',
   description:observation.text.slice(0,180),observationIds:[observation.id],
   confidence:observation.confidence,requiresReview:true});
 }
 return cues;
}
export function cuesAtPlayback(cues:readonly WatchCue[],previousMs:number,currentMs:number):readonly WatchCue[]{
 if(!Number.isFinite(previousMs)||!Number.isFinite(currentMs)||currentMs<previousMs)return [];
 return cues.filter(c=>c.positionMs>previousMs&&c.positionMs<=currentMs);
}
