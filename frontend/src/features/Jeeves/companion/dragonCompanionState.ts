export type CompanionPhase='snuggle'|'listening'|'curious'|'launching'|'crawling'|'acquiring'|'burning'|'distilling'|'celebrating'|'sleeping';
export type DragonEventKind='frontier_discovered'|'dragon_travel'|'visual_probe'|'robots_check'|'fetch_started'|'fetch_received'|'policy_rejected'|'acquisition_accepted'|'burn_started'|'burn_chunk'|'burn_complete'|'distill_complete'|'retry_wait'|'crawl_complete';
export interface DragonCompanionState{phase:CompanionPhase;label:string;detail:string;progress:number;glasses:boolean;bandage:boolean;fire:boolean;embers:boolean;wings:boolean;snuggly:boolean;knowledgePulse:number}
const state=(phase:CompanionPhase,label:string,detail:string,progress:number,extra:Partial<DragonCompanionState>={}):DragonCompanionState=>({phase,label,detail,progress,glasses:false,bandage:false,fire:false,embers:false,wings:false,snuggly:false,knowledgePulse:0,...extra});
export const INITIAL_DRAGON_STATE=state('snuggle','Cozy in his egg','Listening for something interesting…',0,{snuggly:true});
export function companionFromCrawler(kind:DragonEventKind,payload:Record<string,unknown>={}):DragonCompanionState{
 switch(kind){
  case'frontier_discovered':return state('curious','Ooh… something interesting','Following a conversation interest into the knowledge frontier.',.08);
  case'dragon_travel':return state('launching','Adventure time!','Popping out of the egg and flying toward a promising source.',.16,{wings:true});
  case'visual_probe':return state('crawling','Looking closely','Reading the page visually—layout, images, context and structure.',.28,{wings:true});
  case'robots_check':return state('crawling','Checking the rules','Making sure this source may be explored politely.',.34,{wings:true});
  case'fetch_started':return state('acquiring','Nom nom, context','Acquiring the source and preserving its provenance.',.46,{wings:true});
  case'fetch_received':return state('acquiring','Got it!','Inspecting what arrived before anything reaches memory.',.54);
  case'policy_rejected':return state('snuggle','Not for us','That source was left alone. Looking for another path.',1,{snuggly:true});
  case'acquisition_accepted':return state('burning','Fire ready','High-value evidence accepted. Preparing to burn it into structured memory.',.64,{fire:true,embers:true});
  case'burn_started':return state('burning','Burning to memory','Turning acquired material into glowing knowledge embers.',.74,{fire:true,embers:true});
  case'burn_chunk':return state('burning','Making knowledge embers',String(payload.ordinal??'')+' · extracting a structured evidence chunk.',.84,{fire:true,embers:true});
  case'burn_complete':return state('distilling','Nerd mode activated','Distilling facts, entities, relations, timelines and provenance.',.92,{glasses:true,bandage:true,embers:true,knowledgePulse:1});
  case'distill_complete':return state('celebrating','Knowledge sealed','Distillation finished separately from the burn. Promotion still needs review.',1,{snuggly:true,knowledgePulse:1});
  case'retry_wait':return state('snuggle','Tiny smoke break','Waiting politely before trying again.',.24,{snuggly:true});
  case'crawl_complete':return state('celebrating','Crawl finished!','Source gathering finished. Promoting knowledge still needs verification and approval.',1,{snuggly:true,knowledgePulse:1});
 }
}
/** Operational capture events are not knowledge burns. Glasses and fire stay off. */
export function companionFromCapture(kind:string):DragonCompanionState{
 switch(kind){
  case'dispatch_reserved':return state('acquiring','Reserving a request','A request and byte budget are reserved before any network call.',.18,{wings:true});
  case'robots':return state('crawling','Checking the rules','Reading the source rules before another request.',.3,{wings:true});
  case'redirect':return state('crawling','Following a redirect','Staying inside the authorized public scope.',.36,{wings:true});
  case'captured':return state('acquiring','Source captured','The page is stored as unreviewed evidence. It is not burned into memory.',.72);
  case'duplicate':return state('listening','Already captured','This content matches a source already stored in the crawl.',.6,{snuggly:true});
  case'rejected':return state('snuggle','Left alone','That URL was not captured. Looking for another in-scope path.',1,{snuggly:true});
  case'error':return state('snuggle','Request did not finish','The attempt kept its reserved budget. Retry stays inside the grant.',.4,{snuggly:true});
  case'interrupted_dispatch':return state('snuggle','Dispatch interrupted','An uncertain request kept its reserved allowance.',.4,{snuggly:true});
  case'pause':return state('sleeping','Capture paused','The crawl is paused. Nothing new is requested until you resume it.',.2,{snuggly:true});
  case'resume':return state('curious','Ready again','The queue is eligible. A new run still needs an explicit grant.',.12,{snuggly:true});
  case'cancel':return state('snuggle','Capture cancelled','New requests are stopped. Stored sources remain until you erase them.',1,{snuggly:true});
  case'stopped':return state('sleeping','Capture stopped','The crawl stopped. Review of stored sources is a separate step.',1,{snuggly:true});
  case'completed':return state('celebrating','Capture finished','Sources are stored. Review and distillation stay separate.',1,{snuggly:true,knowledgePulse:1});
  default:return state('listening','Watching the crawl','Waiting for the next recorded crawler event.',.02,{snuggly:true});
 }
}
export function companionForConversation(text:string):DragonCompanionState{
 const words=text.trim().split(/\s+/).filter(Boolean);if(words.length<4)return INITIAL_DRAGON_STATE;
 const topic=words.slice(0,8).join(' ');
 return state('listening','Ears perked up',`Interest signal: “${topic}${words.length>8?'…':''}”`,.04,{snuggly:true});
}

/** Real evidence growth and the last confirmed capture event share one actor.
 * Decorative evolution never implies a burn, distillation or model training. */
export function companionFromEvidence(session: import('../../../product/crawlerClient').CrawlSession, eventKind?: string): DragonCompanionState {
 const profile=session.companion;
 if(!profile)return eventKind?companionFromCapture(eventKind):INITIAL_DRAGON_STATE;
 const evolved=profile.stage>=2, terminal=['paused','interrupted','cancelled','failed','completed','budget_exhausted'].includes(session.status);
 if(!session.consent_current||terminal||profile.quest==='rest'){
  return state('sleeping','Resting in the den','The expedition is resting. Evidence growth is retained; no new request or penalty is implied.',profile.growth/1000,{snuggly:true,wings:evolved});
 }
 if(profile.quest==='recover')return state('snuggle','Recovering safely','Waiting for the existing backpressure and recovery controls. No reward is given for failures.',profile.growth/1000,{snuggly:true,wings:evolved});
 if(profile.quest==='conserve')return state('listening','Conserving resources','Remaining request, document and byte budgets constrain the expedition.',profile.growth/1000,{snuggly:true,wings:evolved});
 if(session.worker?.active&&eventKind==='dispatch_reserved'){
  const captured=companionFromCapture(eventKind);
  return {...captured,progress:profile.growth/1000,wings:evolved||captured.wings};
 }
 if(profile.quest==='synthesize')return state('listening','Studying the mosaic','Looking for missing objective terms in admitted work. Captured material is still unreviewed.',profile.growth/1000,{wings:evolved,snuggly:true});
 if(profile.quest==='diversify')return state('curious','Discovering habitats','Prioritizing distinct research origins and formats inside this expedition.',profile.growth/1000,{wings:evolved});
 return state('curious','Following useful novelty','Learning from recorded acquisition yield, not request volume.',profile.growth/1000,{wings:evolved});
}

export function companionEvidenceCosmetics(session: import('../../../product/crawlerClient').CrawlSession): readonly string[] {
 const d=session.companion;
 if(!d)return [];
 const earned=new Set(d.questbook?.quests.filter(q=>q.state==='completed').map(q=>q.code)??[]);
 return [...(d.stage>=2?['winged_builder']:[]),...(earned.has('novel_trail')?['apprentice_forge']:[]),...(earned.has('cartographer')?['star_cartographer']:[])];
}
