/** Transport-neutral reconnectable event ingestion. Caller supplies authenticated fetch. */
import {EMPTY_COMPANION_JOURNAL,reduceDragonJournal,type CompanionJournal,type WireDragonEvent} from './dragonJournal';
export interface DragonEventPage {events:WireDragonEvent[];nextCursor:string|null;hasMore:boolean}
export interface DragonFeedPage {events:WireDragonEvent[];history_truncated?:boolean}
/** Apply one companion page. A truncated crawler tail seeds the local cursor only as a reducer precondition. */
export function acceptDragonFeed(journal:CompanionJournal,page:DragonFeedPage):CompanionJournal{
 if(!page||!Array.isArray(page.events))return journal;
 const first=page.events[0];
 const truncated=journal.lastSequence===0&&page.history_truncated===true&&!!first
  &&Number.isSafeInteger(first.sequence)&&first.sequence>1&&typeof first.previous_digest==='string';
 let cursor:CompanionJournal=truncated?{...journal,lastSequence:first.sequence-1,chainHead:first.previous_digest,provenance:false}:journal;
 let applied=journal;
 let started=false;
 for(const event of page.events){
  const next=reduceDragonJournal(cursor,event);
  // A warning keeps the prior sequence. The truncation seed is not kept unless a later event lands.
  if(next===cursor||next.lastSequence===cursor.lastSequence)return started?applied:journal;
  cursor=next;applied=next;started=true;
 }
 return applied;
}
export type FetchDragonPage=(cursor:string|null,signal?:AbortSignal)=>Promise<DragonEventPage>;
export interface ReplayResult {journal:CompanionJournal;cursor:string|null;complete:boolean;pages:number}
export async function replayDragonPages(fetchPage:FetchDragonPage,options:{cursor?:string|null;maxPages?:number;signal?:AbortSignal}={}):Promise<ReplayResult>{
 let journal=EMPTY_COMPANION_JOURNAL;let cursor=options.cursor??null;let pages=0;const maxPages=Math.max(1,Math.min(100,options.maxPages??20));const cursors=new Set<string>();
 while(pages<maxPages){
  if(options.signal?.aborted)throw new Error('Dragon replay cancelled');
  const page=await fetchPage(cursor,options.signal);pages++;
  if(!Array.isArray(page.events)||page.events.length>1000)throw new Error('Invalid dragon event page');
  for(const event of page.events){const next=reduceDragonJournal(journal,event);if(next.warnings.length>journal.warnings.length)throw new Error(next.warnings.at(-1));journal=next}
  if(!page.hasMore)return {journal,cursor:page.nextCursor,complete:true,pages};
  if(!page.nextCursor||cursors.has(page.nextCursor)||page.nextCursor===cursor)throw new Error('Dragon replay cursor loop');
  cursors.add(page.nextCursor);cursor=page.nextCursor;
 }
 return {journal,cursor,complete:false,pages};
}
