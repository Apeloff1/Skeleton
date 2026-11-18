/**
 * Bounded, owner-detachable archive-wide chamber candidate ranking.
 * This is aggregate coverage ranking, not global document BM25 or independent
 * corroboration. Only validated server metadata enters this accumulator.
 * No raw source text, persisted query state, or network/model authority.
 */
import type {DragonVaultDiscovery,DragonVaultDiscoveryMatch} from '../../product/crawlerClient';

export const MAX_CHAMBERS=128;
export const PAGE_SIZE=8;
export const WINDOW_LIMIT=32;
export const SCAN_DEADLINE_MS=60_000;
export const DISPLAY_TTL_MS=60_000;
export type ChamberScan={
  scopeDigest:string; catalogueSize:number; scanned:number; pages:number;
  queryTerms:number; qualified:number; noGrant:number; held:number;
  eligibleSources:number; scannedBytes:number; matches:DragonVaultDiscoveryMatch[];
  expiresMonotonic:number; nextCursor:string|null; complete:boolean;
};
type ReadPage=(query:string,cursor?:string,signal?:AbortSignal)=>Promise<DragonVaultDiscovery>;
type ScanOptions={
  signal:AbortSignal; ownerCurrent:()=>boolean; now:()=>number;
  onProgress?:(scanned:number,total:number)=>void;
};

function fail(reason:string):never {throw new Error(reason);}
const finite=(n:number)=>Number.isFinite(n)&&n>=0;
const rank=(a:DragonVaultDiscoveryMatch,b:DragonVaultDiscoveryMatch)=>
  b.matched_terms-a.matched_terms||b.best_source_terms-a.best_source_terms
  ||b.distinct_matching_payloads-a.distinct_matching_payloads
  ||(a.session_id<b.session_id?-1:a.session_id>b.session_id?1:0);

export function appendChamberPage(prior:ChamberScan|null,page:DragonVaultDiscovery,
  started:number,finished:number,absoluteDeadline:number):ChamberScan {
  if(!finite(started)||!finite(finished)||finished<started||finished>=absoluteDeadline)
    fail('Archive-wide scan exceeded its bounded time window.');
  if(page.catalogue_size>MAX_CHAMBERS)fail('Catalogue exceeds the exhaustive scan bound; use the indexed archive search.');
  if(page.scanned_sessions>PAGE_SIZE||
      page.page_offset!==(prior?.scanned??0)||prior?.complete||
      (prior!==null&&(page.scope_digest!==prior.scopeDigest||page.catalogue_size!==prior.catalogueSize||
       page.query_terms!==prior.queryTerms||prior.nextCursor!==page.scope_digest+':'+page.page_offset)))
    fail('Historical catalogue changed. Restart archive discovery.');
  // Use the elapsed transport time as a conservative deduction. No client
  // wall-clock alignment with the server is required.
  const localExpiry=page.earliest_expiry===null?Infinity:
    started+1000*(page.earliest_expiry-page.as_of_unix);
  const expires=Math.min(prior?.expiresMonotonic??Infinity,localExpiry,absoluteDeadline);
  if(expires<=finished)fail('Historical-use permission expired during archive discovery.');
  const matches=[...(prior?.matches??[]),...page.matches];
  if(matches.length>MAX_CHAMBERS||new Set(matches.map(x=>x.session_id)).size!==matches.length)
    fail('Archive discovery repeated a chamber identity.');
  const scanned=page.page_offset+page.scanned_sessions;
  const complete=page.next_cursor===null;
  if(scanned>page.catalogue_size||complete!==(scanned===page.catalogue_size)
      ||(!complete&&page.scanned_sessions!==PAGE_SIZE))
    fail('Archive discovery did not conserve catalogue coverage.');
  return {scopeDigest:page.scope_digest,catalogueSize:page.catalogue_size,scanned,pages:(prior?.pages??0)+1,
    queryTerms:page.query_terms,qualified:(prior?.qualified??0)+page.qualified,
    noGrant:(prior?.noGrant??0)+page.no_grant,held:(prior?.held??0)+page.held,
    eligibleSources:(prior?.eligibleSources??0)+page.eligible_sources,
    scannedBytes:(prior?.scannedBytes??0)+page.scanned_bytes,
    matches:matches.sort(rank),expiresMonotonic:expires,nextCursor:page.next_cursor,complete};
}

function sameFirstPage(a:DragonVaultDiscovery,b:DragonVaultDiscovery):boolean{
  // Do not compare the server read clock itself; compare all evidence counts,
  // IDs, witnessed versions and permission deadlines in the canonical page.
  return a.scope_digest===b.scope_digest&&a.catalogue_size===b.catalogue_size&&
    a.page_offset===b.page_offset&&a.scanned_sessions===b.scanned_sessions&&
    a.query_terms===b.query_terms&&a.earliest_expiry===b.earliest_expiry&&
    a.qualified===b.qualified&&a.no_grant===b.no_grant&&a.held===b.held&&
    a.eligible_sources===b.eligible_sources&&a.scanned_bytes===b.scanned_bytes&&
    a.next_cursor===b.next_cursor&&a.matches.length===b.matches.length&&
    a.matches.every((x,i)=>{const y=b.matches[i];return x.session_id===y.session_id&&
      x.version===y.version&&x.valid_until===y.valid_until&&x.eligible_sources===y.eligible_sources&&
      x.matched_sources===y.matched_sources&&x.distinct_matching_payloads===y.distinct_matching_payloads&&
      x.matched_terms===y.matched_terms&&x.best_source_terms===y.best_source_terms&&x.scanned_bytes===y.scanned_bytes;});
}

export async function scanArchiveChambers(read:ReadPage,query:string,options:ScanOptions):Promise<ChamberScan>{
  const {signal,ownerCurrent,now,onProgress}=options;
  const begin=now(),deadline=begin+SCAN_DEADLINE_MS;
  const guard=()=>{if(signal.aborted||!ownerCurrent())fail('Archive discovery detached.');
    if(now()>=deadline)fail('Archive-wide scan exceeded its bounded time window.');};
  let state:ChamberScan|null=null,first:DragonVaultDiscovery|null=null;
  // Exactly sixteen possible data pages, sequential; no unconstrained
  // fan-out, retries, or background persistence.
  for(let i=0;i<MAX_CHAMBERS/PAGE_SIZE;i++){
    guard();const started=now();
    const page=await read(query,state?.nextCursor??undefined,signal);
    guard();const finished=now();
    first??=page;
    state=appendChamberPage(state,page,started,finished,deadline);
    onProgress?.(state.scanned,state.catalogueSize);
    if(state.complete)break;
  }
  if(!state?.complete||!first)fail('Archive discovery did not finish within the catalogue bound.');
  // Final independent metadata fence using the existing authority-checking
  // endpoint. Neither first-page matches nor earlier grants may silently
  // survive a changed catalogue.
  guard();const started=now();
  const check=await read(query,undefined,signal);
  guard();const end=now();
  if(!sameFirstPage(first,check))fail('Historical catalogue changed before publication. Restart discovery.');
  const expiry=check.earliest_expiry===null?Infinity:started+1000*(check.earliest_expiry-check.as_of_unix);
  const expires=Math.min(state.expiresMonotonic,expiry,end+DISPLAY_TTL_MS);
  if(expires<=end)fail('Historical-use permission expired before ranking publication.');
  if(state.qualified+state.noGrant+state.held!==state.scanned||state.matches.length>state.qualified||
      state.eligibleSources>64*state.qualified||state.scannedBytes>24000*state.eligibleSources)
    fail('Archive discovery did not conserve source coverage.');
  return {...state,expiresMonotonic:expires};
}

export function bestHistoryWindow(scan:ChamberScan,now:number):string[]{
  if(!scan.complete||!finite(now)||now>=scan.expiresMonotonic)
    fail('Archive discovery is incomplete or expired.');
  // Ranking is lexicographic chamber-level coverage, not independent
  // corroboration or global source rank. The canonical history-only
  // reparse still independently checks every selected grant/source.
  return scan.matches.slice(0,WINDOW_LIMIT).map(row=>row.session_id).sort();
}
