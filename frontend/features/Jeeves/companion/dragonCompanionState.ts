export type CompanionPhase='snuggle'|'listening'|'curious'|'launching'|'crawling'|'acquiring'|'burning'|'distilling'|'celebrating'|'sleeping';
export type DragonEventKind='frontier_discovered'|'dragon_travel'|'visual_probe'|'robots_check'|'fetch_started'|'fetch_received'|'policy_rejected'|'acquisition_accepted'|'burn_started'|'burn_chunk'|'burn_complete'|'retry_wait'|'crawl_complete';
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
  case'retry_wait':return state('snuggle','Tiny smoke break','Waiting politely before trying again.',.24,{snuggly:true});
  case'crawl_complete':return state('celebrating','Crawl finished!','Source gathering finished. Promoting knowledge still needs verification and approval.',1,{snuggly:true,knowledgePulse:1});
 }
}
export function companionForConversation(text:string):DragonCompanionState{
 const words=text.trim().split(/\s+/).filter(Boolean);if(words.length<4)return INITIAL_DRAGON_STATE;
 const topic=words.slice(0,8).join(' ');
 return state('listening','Ears perked up',`Interest signal: “${topic}${words.length>8?'…':''}”`,.04,{snuggly:true});
}
