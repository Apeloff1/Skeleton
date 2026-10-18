/** Deterministic watch-along animation choreography from real player signals. */
export type WatchMood='nesting'|'watching'|'curious'|'delighted'|'concerned'|'sleepy'|'taking-notes'|'paused'|'buffering';
export interface WatchSignal {kind:'play'|'pause'|'buffer'|'seek'|'frame'|'caption'|'insight'|'surprise'|'end';positionMs:number;durationMs?:number;caption?:string;confidence?:number}
export interface WatchPose {mood:WatchMood;label:string;detail:string;blink:boolean;tilt:number;wingWave:boolean;heart:boolean;popcorn:boolean;notebook:boolean;snuggle:boolean;progress:number}
const bounded=(n:number)=>Number.isFinite(n)?Math.max(0,Math.min(1,n)):0;
export function watchPose(signal:WatchSignal):WatchPose {
 const progress=signal.durationMs&&signal.durationMs>0?bounded(signal.positionMs/signal.durationMs):0;
 const base={blink:false,tilt:0,wingWave:false,heart:false,popcorn:true,notebook:false,snuggle:true,progress};
 switch(signal.kind){
 case 'play':return {...base,mood:'watching',label:'Watching with you',detail:'Curled up in his egg, eyes on the screen.'};
 case 'pause':return {...base,mood:'paused',label:'Waiting for you',detail:'Tiny paws tucked in. We can resume whenever you like.',blink:true,popcorn:false};
 case 'buffer':return {...base,mood:'buffering',label:'Loading snacks…',detail:'A patient little dragon waits for the video.',tilt:8};
 case 'seek':return {...base,mood:'curious',label:'Where did we go?',detail:'His shell hat wobbles as he finds the new scene.',tilt:-12};
 case 'frame':return {...base,mood:'curious',label:'Big curious eyes',detail:'Watching the visuals and following the story.',tilt:5};
 case 'caption':return {...base,mood:'watching',label:'Listening closely',detail:'Following the captions with you.',blink:true};
 case 'insight':return {...base,mood:'taking-notes',label:'Tiny notebook time',detail:'A time-coded observation is ready for review.',notebook:true,popcorn:false};
 case 'surprise':return {...base,mood:'delighted',label:'Ooh! Did you see that?',detail:'A delighted wing flutter!',wingWave:true,heart:true,tilt:-9};
 case 'end':return {...base,mood:'sleepy',label:'Cozy credits',detail:'Snuggling back into his eggshell after the video.',blink:true,popcorn:false};
 }
}
