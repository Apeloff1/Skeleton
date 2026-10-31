/** Bounded, deterministic watch-along event processor. Never infers observations from playback alone. */
import {signalFromPlayer,type PlayerSnapshot} from './dragonPlayerBridge';
import type {WatchSignal} from './dragonWatch';

export interface WatchAlongEvent {id:string;signal:WatchSignal;receivedAt:number}
export interface WatchAlongTimeline {lastSnapshot?:PlayerSnapshot;events:readonly WatchAlongEvent[];lastId:number;sessionEnded:boolean}
export const EMPTY_WATCH_TIMELINE:WatchAlongTimeline={events:[],lastId:0,sessionEnded:false};
export function ingestPlayerSnapshot(timeline:WatchAlongTimeline,snapshot:PlayerSnapshot,at:number):WatchAlongTimeline {
 if(!Number.isFinite(at)||at<0||timeline.sessionEnded)return timeline;
 const signal=signalFromPlayer(snapshot,timeline.lastSnapshot);
 const previous=timeline.events[timeline.events.length-1];
 const sameKind=previous?.signal.kind===signal.kind;
 const sameBucket=previous&&Math.floor(previous.signal.positionMs/1000)===Math.floor(signal.positionMs/1000);
 if(sameKind&&sameBucket)return {...timeline,lastSnapshot:snapshot};
 const lastId=timeline.lastId+1;
 const event={id:String(lastId),signal,receivedAt:at};
 return {lastSnapshot:snapshot,events:[...timeline.events.slice(-127),event],lastId,sessionEnded:signal.kind==='end'};
}
export function ingestExplicitWatchSignal(timeline:WatchAlongTimeline,signal:WatchSignal,at:number):WatchAlongTimeline {
 if(timeline.sessionEnded||!Number.isFinite(at)||at<0||!Number.isFinite(signal.positionMs)||signal.positionMs<0)return timeline;
 const lastId=timeline.lastId+1;
 return {...timeline,lastId,events:[...timeline.events.slice(-127),{id:String(lastId),signal,receivedAt:at}]};
}
