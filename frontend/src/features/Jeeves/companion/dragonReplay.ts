/** Transport-neutral reconnectable event ingestion. Caller supplies authenticated fetch. */
import {EMPTY_COMPANION_JOURNAL,reduceDragonJournal,type CompanionJournal,type WireDragonEvent} from './dragonJournal';
export interface DragonEventPage {events:WireDragonEvent[];nextCursor:string|null;hasMore:boolean}
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
