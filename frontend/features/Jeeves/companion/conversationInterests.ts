/** Bounded, privacy-aware interest selection; requires an explicit research action. */
export interface ResearchInterest {id:string;topic:string;weight:number;source:'conversation';evidence:string}
const STOP=new Set('about after again also because could would should there their these those where which while with from into this that have your what when then than been were will just some more very much want need make build please'.split(' '));
export function extractConversationInterests(messages:readonly {role:string;text:string}[],limit=8):ResearchInterest[]{
 const bounded=Math.max(0,Math.min(16,Math.floor(Number.isFinite(limit)?limit:8)));
 const counts=new Map<string,{count:number;snippet:string}>();
 for(const m of messages.slice(-30)){if(m.role!=='user')continue;const raw=m.text.slice(0,3000).toLowerCase();const tokens=(raw.match(/[a-z][a-z0-9-]{3,}/g)||[]).filter(w=>!STOP.has(w)&&!/^\d/.test(w));
  for(const t of new Set(tokens)){const prior=counts.get(t);counts.set(t,{count:(prior?.count||0)+1,snippet:t})}
 }
 return [...counts].sort((a,b)=>b[1].count-a[1].count||a[0].localeCompare(b[0])).slice(0,bounded).map(([topic,v])=>({id:'interest:'+topic,topic,weight:Math.min(1,v.count/5),source:'conversation',evidence:'Repeated user-authored topic; no automatic crawl authorization'}));
}
export interface ResearchMission {query:string;interestIds:string[];maxPages:number;maxSources:number;requiresConsent:true}
export function proposeResearchMission(interests:readonly ResearchInterest[],maxPages=20):ResearchMission|null {
 const selected=interests.slice(0,4).filter(x=>/^[a-z][a-z0-9-]{3,}$/.test(x.topic));if(!selected.length)return null;
 return {query:selected.map(x=>x.topic).join(' '),interestIds:selected.map(x=>x.id),maxPages:Math.max(1,Math.min(100,Math.floor(Number.isFinite(maxPages)?maxPages:20))),maxSources:10,requiresConsent:true};
}
