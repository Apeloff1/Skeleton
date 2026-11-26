import React,{useEffect,useRef,useState} from 'react';
import {AppState,Linking,Text,TextInput,TouchableOpacity,View} from 'react-native';
import {getAuthToken} from '../../auth/gameforgeAuth';
import {crawlRequestKey} from '../../product/crawlerClient';
import {safeOriginalLink,type GameIdentity} from '../../product/dragonGameCorpusClient';
import {seedSummary,seedApps,seedLocators,importSeedApps,attachSeedSources,type SeedApp,type SeedFilter,type SeedLane,type SeedLocator,type SeedSummary,type AppReceipt,type AttachReceipt} from '../../product/dragonModSeedsClient';
import s,{colors as C} from './CrawlerWorkspace.styles';

type Props={game:GameIdentity|null;canWrite:boolean;visible:boolean;disabled:boolean};
const field={color:C.text,backgroundColor:C.bg,borderWidth:1,borderColor:C.edge,borderRadius:9,padding:10};
const human=(x:string)=>x.replaceAll('_',' ').replaceAll('-',' ');
const lanes:SeedLane[]=['game_surfaces','mod_platforms','tool_repositories','specialist_sites'];
const label=(n:number)=>n.toLocaleString();

export default function DragonModSeedPanel({game,canWrite,visible,disabled}:Props){
 const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [summary,setSummary]=useState<SeedSummary|null>(null),[mode,setMode]=useState<'apps'|'sources'>('sources');
 const [query,setQuery]=useState(''),[lane,setLane]=useState<SeedLane|''>(''),[provider,setProvider]=useState(''),[modOnly,setModOnly]=useState(true),[appid,setAppid]=useState<string|undefined>();
 const [apps,setApps]=useState<SeedApp[]>([]),[sources,setSources]=useState<SeedLocator[]>([]),[cursor,setCursor]=useState<string|null>(null);
 const [selectedApps,setSelectedApps]=useState<SeedApp[]>([]),[selectedSources,setSelectedSources]=useState<SeedLocator[]>([]);
 const [ack,setAck]=useState(false),[appReceipt,setAppReceipt]=useState<AppReceipt|null>(null),[attachReceipt,setAttachReceipt]=useState<AttachReceipt|null>(null),[outbound,setOutbound]=useState<SeedLocator|null>(null);
 const op=useRef<{identity:string;key:string}|null>(null),active=useRef<AbortController|null>(null),epoch=useRef(0);
 function clearIntent(){setAck(false);setAppReceipt(null);setAttachReceipt(null);op.current=null;}
 function clearRows(){setApps([]);setSources([]);setCursor(null);setOutbound(null);}
 function reset(){
  epoch.current++;active.current?.abort();active.current=null;setOpen(false);setBusy(false);setError('');
  setSummary(null);setMode('sources');setQuery('');setLane('');setProvider('');setModOnly(true);setAppid(undefined);
  clearRows();setSelectedApps([]);setSelectedSources([]);clearIntent();
 }
 useEffect(()=>{
  const initial=getAuthToken();
  if(!visible)reset();
  const app=AppState.addEventListener('change',state=>{if(state!=='active')reset();});
  const guard=setInterval(()=>{if(initial!==getAuthToken())reset();},500);
  return()=>{epoch.current++;active.current?.abort();clearInterval(guard);app.remove();};
 },[visible]);
 useEffect(()=>{
  epoch.current++;active.current?.abort();active.current=null;setBusy(false);
  setSelectedSources([]);clearIntent();
 },[game?.game_id]);
 const enabled=visible&&open&&!busy&&!disabled&&!!getAuthToken();
 function run(work:(signal:AbortSignal,current:()=>boolean)=>Promise<void>){
  if(!enabled||active.current)return;
  const request=new AbortController(),generation=++epoch.current,identity=getAuthToken();
  active.current=request;setBusy(true);setError('');
  const current=()=>!request.signal.aborted&&generation===epoch.current&&identity===getAuthToken();
  void work(request.signal,current).catch(e=>{if(current())setError(e instanceof Error?e.message:'Seed catalogue unavailable.');}).finally(()=>{if(active.current===request){active.current=null;setBusy(false);}});
 }
 function load(){
  run(async(signal,current)=>{const x=await seedSummary(signal);if(current()){
   setSummary(x);clearRows();setSelectedApps([]);setSelectedSources([]);clearIntent();
  }});
 }
 function browse(after?:string){
  if(!summary)return;const census=summary;
  run(async(signal,current)=>{
   if(mode==='apps'){
    const result=await seedApps(census,query,after,signal);
    if(current()){setApps(result.applications);setSources([]);setCursor(result.next_cursor);}
   }else{
    const f:SeedFilter={q:query,lane,provider,appid,modOnly};
    const result=await seedLocators(census,f,after,signal);
    if(current()){setSources(result.seeds);setApps([]);setCursor(result.next_cursor);setOutbound(null);}
   }
  });
 }
 function showApp(a:SeedApp){
  setMode('sources');setAppid(a.appid);setQuery('');setLane('');setProvider('');clearRows();
  if(!summary)return;const census=summary;
  run(async(signal,current)=>{
   const result=await seedLocators(census,{q:'',lane:'',provider:'',appid:a.appid,modOnly},undefined,signal);
   if(current()){setSources(result.seeds);setCursor(result.next_cursor);}
  });
 }
 function selectApp(a:SeedApp){
  setSelectedApps(v=>v.some(x=>x.appid===a.appid)?v.filter(x=>x.appid!==a.appid):v.length<128?[...v,a]:v);clearIntent();
 }
 function selectPage(){
  setSelectedApps(v=>{
   const map=new Map(v.map(x=>[x.appid,x]));
   for(const a of apps){if(map.size>=128)break;map.set(a.appid,a);}
   return [...map.values()];
  });
  clearIntent();
 }
 function selectSource(a:SeedLocator){
  if(!game||a.candidate_game_id!==null&&a.candidate_game_id!==game.game_id)return;
  setSelectedSources(v=>v.some(x=>x.seed_id===a.seed_id)?v.filter(x=>x.seed_id!==a.seed_id):v.length<256?[...v,a]:v);
  clearIntent();
 }
 function importApps(){
  if(!summary||!canWrite||!ack||!selectedApps.length)return;
  const items=[...selectedApps],census=summary,only=modOnly;
  const identity=[census.revision,'applications',String(only),...items.map(a=>a.appid).sort()].join(':');
  if(op.current?.identity!==identity)op.current={identity,key:crawlRequestKey('mod-seed-applications')};
  const operation=op.current.key;
  run(async(signal,current)=>{
   const receipt=await importSeedApps(census,items,only,operation,signal);
   if(current()){setAppReceipt(receipt);setAttachReceipt(null);setAck(false);}
  });
 }
 function attach(){
  if(!summary||!game||!canWrite||!ack||!selectedSources.length)return;
  const items=[...selectedSources],target=game.game_id,census=summary;
  const identity=[census.revision,'attach',target,...items.map(a=>a.seed_id).sort()].join(':');
  if(op.current?.identity!==identity)op.current={identity,key:crawlRequestKey('mod-seed-attach')};
  const operation=op.current.key;
  run(async(signal,current)=>{
   const receipt=await attachSeedSources(census,target,items,operation,signal);
   if(current()){setAttachReceipt(receipt);setAppReceipt(null);setAck(false);}
  });
 }
 const button=(title:string,press:()=>void,off=false)=><TouchableOpacity accessibilityRole="button" disabled={!enabled||off} onPress={press} style={[s.button,(!enabled||off)&&s.disabled]}><Text style={s.buttonText}>{title}</Text></TouchableOpacity>;
 const changeMode=(v:'apps'|'sources')=>{setMode(v);setAppid(undefined);setQuery('');clearRows();clearIntent();};
 const filterChange=()=>{clearRows();clearIntent();};
 if(!visible)return null;
 return <View style={s.check}>
  <Text style={s.label}>Worldwide modding seed federation</Text>
  <Text style={s.small}>Game-specific mod communities, tool repositories, public documentation and historical compatibility. All locators and application IDs remain candidates until verified; no binaries are downloaded, executed or installed.</Text>
  <TouchableOpacity accessibilityRole="button" disabled={disabled||busy} onPress={()=>open?reset():setOpen(true)} style={s.button}><Text style={s.buttonText}>{open?'Close mod discovery':'Explore modding discovery'}</Text></TouchableOpacity>
  {open&&<>
   {button('Load seed census',load)}
   {summary&&<>
    <Text style={s.label}>{label(summary.total_unique_locators)} unique locators across both directories</Text>
    <Text style={s.small}>{label(summary.legacy_unique_locators)} legacy locators · {label(summary.expanded_records)} expansion records · {label(summary.overlap_with_legacy)} overlaps excluded from union</Text>
    <Text style={s.small}>{label(summary.candidate_apps)} title candidates · {label(summary.candidate_repositories)} tool repositories · {label(summary.candidate_community_slugs)} provider communities</Text>
    <Text style={s.small}>{label(summary.mod_related_records)} mod-related expansion routes; {label(summary.generated_route_records)} generated route candidates and {label(summary.curated_locator_records)} curated locator records. No live-source verification claimed.</Text>
    {lanes.map(l=><Text key={l} style={s.small}>{human(l)}: {label(summary.lanes[l]||0)}</Text>)}
    {button((mode==='apps'?'Selected: ':'')+'Game candidates',()=>changeMode('apps'))}
    {button((mode==='sources'?'Selected: ':'')+'Source locators',()=>changeMode('sources'))}
    <TextInput accessibilityLabel="Search mod discovery seeds" value={query} onChangeText={v=>{setQuery(v);filterChange();}} editable={enabled} maxLength={256} style={field} placeholder="Game, tool, mod type, provider…" placeholderTextColor={C.muted}/>
    {button(modOnly?'Mod-related only (selected)':'Include all game surfaces',()=>{setModOnly(v=>!v);filterChange();})}
    {mode==='sources'&&<>
     {appid&&button('Clear candidate app '+appid,()=>{setAppid(undefined);filterChange();})}
     {button((lane===''?'Selected: ':'')+'All source lanes',()=>{setLane('');filterChange();})}
     {lanes.map(l=><React.Fragment key={l}>{button((l===lane?'Selected: ':'')+human(l),()=>{setLane(l);filterChange();})}</React.Fragment>)}
     {button((provider===''?'Selected: ':'')+'All providers',()=>{setProvider('');filterChange();})}
     {Object.keys(summary.providers).sort().map(p=><React.Fragment key={p}>{button((provider===p?'Selected: ':'')+p+' · '+label(summary.providers[p]),()=>{setProvider(p);filterChange();})}</React.Fragment>)}
    </>}
    {button('Browse matching candidates',()=>browse())}
    {mode==='apps'&&<>
     {apps.map(a=><View key={a.appid} style={s.check}>
      <Text style={s.label}>{a.title}</Text><Text style={s.small}>Steam candidate {a.appid} · {label(a.seeds)} routes · {label(a.mod_related_seeds)} mod-related</Text>
      {button('View title source routes',()=>showApp(a))}
      {canWrite&&button(selectedApps.some(x=>x.appid===a.appid)?'Remove candidate':'Select candidate',()=>selectApp(a),selectedApps.length>=128&&!selectedApps.some(x=>x.appid===a.appid))}
     </View>)}
     {canWrite&&button('Select this game page',selectPage,!apps.length||selectedApps.length>=128)}
    </>}
    {mode==='sources'&&sources.map(a=><View key={a.seed_id} style={s.check}>
     <Text style={s.label}>{a.title}: {a.label}</Text><Text style={s.small}>{human(a.kind)} · {a.provider} · {human(a.basis)}</Text>
     <Text selectable style={s.small}>{a.url}</Text>
     {a.appid&&<Text style={s.small}>Candidate Steam identity {a.appid}</Text>}
     {canWrite&&game&&button(selectedSources.some(x=>x.seed_id===a.seed_id)?'Remove source':'Select for '+game.first_title,()=>selectSource(a),!!(a.candidate_game_id&&a.candidate_game_id!==game.game_id)||selectedSources.length>=256&&!selectedSources.some(x=>x.seed_id===a.seed_id))}
     {button(outbound?.seed_id===a.seed_id?'Cancel external navigation':'Prepare original site',()=>setOutbound(v=>v?.seed_id===a.seed_id?null:a))}
     {outbound?.seed_id===a.seed_id&&<View style={s.check}><Text style={s.small}>Unverified external destination. The site may redirect or offer downloads. Dragon will not execute its contents.</Text>{button('Open site in browser',()=>{setOutbound(null);try{void Linking.openURL(safeOriginalLink(a.url)).catch(()=>setError('External browser unavailable.'));}catch(e){setError(e instanceof Error?e.message:'External link held.');}})}</View>}
    </View>)}
    {button('Next candidate page',()=>{if(cursor)browse(cursor);},!cursor)}
    {canWrite&&<View style={s.check}>
     <Text style={s.label}>Bulk catalogue-only admission</Text>
     {mode==='apps'?<>
      <Text style={s.small}>{selectedApps.length} / 128 candidate games · {label(selectedApps.reduce((n,a)=>n+(modOnly?a.mod_related_seeds:a.seeds),0))} selected source references</Text>
      {selectedApps.map(a=><React.Fragment key={a.appid}>{button('Remove '+a.title,()=>selectApp(a))}</React.Fragment>)}
      {button('Clear selected games',()=>{setSelectedApps([]);clearIntent();},!selectedApps.length)}
     </>:<>
      <Text style={s.small}>{selectedSources.length} / 256 sources for {game?.first_title||'no current game selected'}.</Text>
      {selectedSources.map(x=><React.Fragment key={x.seed_id}>{button('Remove '+x.title+' · '+x.label,()=>selectSource(x))}</React.Fragment>)}
      {button('Clear selected sources',()=>{setSelectedSources([]);clearIntent();},!selectedSources.length)}
     </>}
     <Text style={s.small}>Candidate IDs and external tool associations may be incomplete or incorrect. Only catalogue metadata is queued; capture requires separate authority.</Text>
     {button(ack?'Metadata-only binding acknowledged':'Acknowledge candidate metadata only',()=>setAck(v=>!v),mode==='apps'?!selectedApps.length:!selectedSources.length||!game)}
     {mode==='apps'?button('Queue selected games',importApps,!ack||!selectedApps.length):button('Attach selected references to game',attach,!ack||!game||!selectedSources.length)}
     {(appReceipt||attachReceipt)&&<View style={s.check}><Text style={s.small}>{label((appReceipt||attachReceipt)!.total)} metadata observations queued or replayed. No crawl granted.</Text><Text selectable style={s.small}>Batch {(appReceipt||attachReceipt)!.batch_id}</Text></View>}
    </View>}
   </>}
   {!!error&&<Text style={s.error}>{error}</Text>}
  </>}
 </View>;
}
