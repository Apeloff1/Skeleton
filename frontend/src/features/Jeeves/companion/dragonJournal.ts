/** Strict, replayable companion event reducer. No UI effect can invent acquisition. */
import {companionFromCrawler,INITIAL_DRAGON_STATE,type DragonCompanionState,type DragonEventKind} from './dragonCompanionState';
export interface WireDragonEvent {schema:'skeleton.ai.dragon_crawl.event.v1';event_id:string;sequence:number;kind:DragonEventKind;url:string;at:number;payload:Record<string,unknown>;previous_digest?:string;digest?:string}
export interface CompanionJournal {lastSequence:number;seenIds:readonly string[];accepted:readonly string[];burning:readonly string[];distilling:readonly string[];state:DragonCompanionState;rejected:number;indexed:number;distilled:number;warnings:readonly string[];chainHead:string;provenance:boolean}
const GENESIS='0'.repeat(64);
export const EMPTY_COMPANION_JOURNAL:CompanionJournal={lastSequence:0,seenIds:[],accepted:[],burning:[],distilling:[],state:INITIAL_DRAGON_STATE,rejected:0,indexed:0,distilled:0,warnings:[],chainHead:GENESIS,provenance:false};
const kinds=new Set<DragonEventKind>(['frontier_discovered','dragon_travel','visual_probe','robots_check','fetch_started','fetch_received','policy_rejected','acquisition_accepted','burn_started','burn_chunk','burn_complete','distill_complete','retry_wait','crawl_complete']);
const HEX=/^[a-f0-9]{64}$/;
export function reduceDragonJournal(j:CompanionJournal,e:WireDragonEvent):CompanionJournal {
 if(e.schema!=='skeleton.ai.dragon_crawl.event.v1'||!kinds.has(e.kind)||!Number.isSafeInteger(e.sequence)||e.sequence<1||!Number.isFinite(e.at)||!/^https?:\/\//.test(e.url)||!e.event_id||typeof e.payload!=='object'||e.payload===null)return j;
 if(j.seenIds.includes(e.event_id)||e.sequence<=j.lastSequence)return j;
 const warning=(reason:string):CompanionJournal=>({...j,warnings:[...j.warnings.slice(-15),reason]});
 if(e.sequence!==j.lastSequence+1)return warning('Event gap: replay required');
 const hasPrev=e.previous_digest!==undefined,hasDigest=e.digest!==undefined;
 if(hasPrev!==hasDigest||(hasDigest&&(!HEX.test(String(e.previous_digest))||!HEX.test(String(e.digest))||e.digest!==e.event_id)))return warning('Event chain rejected: digest is not provenance');
 if(j.provenance&&!hasDigest)return warning('Event chain rejected: provenance disappeared');
 if(hasDigest&&e.previous_digest!==j.chainHead)return warning('Event chain rejected: cursor does not continue');
 const accepted=new Set(j.accepted),burning=new Set(j.burning),distilling=new Set(j.distilling);
 if(e.kind==='acquisition_accepted')accepted.add(e.url);
 if(e.kind==='burn_started'){if(!accepted.has(e.url))return warning('Burn rejected: no accepted acquisition');burning.add(e.url)}
 if(e.kind==='burn_chunk'&&!burning.has(e.url))return warning('Chunk rejected: no active burn');
 if(e.kind==='burn_complete'&&e.payload.persisted!==true)return warning('Completion rejected: durable indexing receipt missing');
 if(e.kind==='burn_complete'){if(!burning.has(e.url))return warning('Completion rejected: no active burn');burning.delete(e.url);accepted.delete(e.url);distilling.add(e.url)}
 if(e.kind==='distill_complete'&&!distilling.has(e.url))return warning('Distillation rejected: burn is not complete');
 if(e.kind==='distill_complete'&&e.payload.distilled!==true)return warning('Distillation rejected: separate distillation receipt missing');
 if(e.kind==='distill_complete')distilling.delete(e.url);
 if(e.kind==='policy_rejected'){accepted.delete(e.url);burning.delete(e.url);distilling.delete(e.url)}
 if(e.kind==='crawl_complete'&&burning.size)return warning('Crawl completion rejected: unfinished burns');
 return {lastSequence:e.sequence,seenIds:[...j.seenIds.slice(-511),e.event_id],accepted:[...accepted],burning:[...burning],distilling:[...distilling],state:companionFromCrawler(e.kind,e.payload),rejected:j.rejected+Number(e.kind==='policy_rejected'),indexed:j.indexed+Number(e.kind==='burn_complete'),distilled:j.distilled+Number(e.kind==='distill_complete'),warnings:j.warnings,chainHead:hasDigest?String(e.digest):j.chainHead,provenance:j.provenance||hasDigest};
}
export function replayDragonJournal(events:readonly WireDragonEvent[]):CompanionJournal{return events.reduce(reduceDragonJournal,EMPTY_COMPANION_JOURNAL)}
