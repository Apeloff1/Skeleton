/** Local browser render timing; requestAnimationFrame cadence is not presented GPU FPS. */
export interface PlaybackStats {
  samples:number; meanIntervalMs:number|null; p95IntervalMs:number|null;
  meanRenderSubmissionMs:number|null; slowIntervals:number;
}
export class PlaybackMeter {
  private intervals:number[]=[];
  private submission:number[]=[];
  private previous:number|null=null;
  constructor(private readonly capacity=240){
    if(!Number.isInteger(capacity)||capacity<2||capacity>600)throw new Error('Invalid playback measurement window');
  }
  reset(){this.previous=null;this.intervals=[];this.submission=[];}
  observe(now:number,submissionMs:number){
    if(!Number.isFinite(now)||!Number.isFinite(submissionMs)||submissionMs<0)return;
    const before=this.previous;this.previous=now;
    if(before===null)return;
    const duration=now-before;
    if(duration<=0||duration>1000){this.reset();this.previous=now;return;}
    this.intervals.push(duration);this.submission.push(submissionMs);
    if(this.intervals.length>this.capacity){this.intervals.shift();this.submission.shift();}
  }
  read():PlaybackStats{
    const n=this.intervals.length;
    if(!n)return {samples:0,meanIntervalMs:null,p95IntervalMs:null,meanRenderSubmissionMs:null,slowIntervals:0};
    const sorted=[...this.intervals].sort((a,b)=>a-b);
    return {samples:n,meanIntervalMs:this.intervals.reduce((s,v)=>s+v,0)/n,
      p95IntervalMs:sorted[Math.ceil(.95*n)-1],meanRenderSubmissionMs:this.submission.reduce((s,v)=>s+v,0)/n,
      slowIntervals:this.intervals.filter(v=>v>1000/30).length};
  }
}
export function seekTime(duration:number,fraction:number):number{
  if(!Number.isFinite(duration)||duration<=0||!Number.isFinite(fraction))throw new Error('Invalid clip time');
  // Looping Three actions wrap at their exact endpoint, so inspect just before it.
  return Math.min(duration*(1-1e-7),Math.max(0,Math.min(1,fraction))*duration);
}
