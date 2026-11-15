import React,{useEffect,useRef,useState} from 'react';
import {AppState,Linking,Text,TextInput,TouchableOpacity,View} from 'react-native';
import {getAuthToken} from '../../auth/gameforgeAuth';
import {crawlRequestKey} from '../../product/crawlerClient';
import {directorySummary,directoryLeads,bindDirectoryLeads,type DirectorySummary,type DirectoryGroup,type DirectoryLead,type DirectoryBinding} from '../../product/dragonSourceDirectoryClient';
import {safeOriginalLink,type GameIdentity} from '../../product/dragonGameCorpusClient';
import s,{colors as C} from './CrawlerWorkspace.styles';

const field={color:C.text,backgroundColor:C.bg,borderWidth:1,borderColor:C.edge,borderRadius:9,padding:10};
const human=(x:string)=>x.replaceAll('_',' ').replaceAll('-',' ');
type Props={game:GameIdentity|null;canWrite:boolean;visible:boolean;disabled:boolean};
export default function DragonSourceDirectoryPanel({game,canWrite,visible,disabled}:Props){
 const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [summary,setSummary]=useState<DirectorySummary|null>(null),[group,setGroup]=useState<DirectoryGroup|null>(null);
 const [q,setQ]=useState(''),[family,setFamily]=useState(''),[rows,setRows]=useState<DirectoryLead[]>([]),[cursor,setCursor]=useState<string|null>(null);
 const [selected,setSelected]=useState<DirectoryLead[]>([]),[target,setTarget]=useState<'game'|'preset'|null>(null),[ack,setAck]=useState(false);
 const [receipt,setReceipt]=useState<DirectoryBinding|null>(null),[outbound,setOutbound]=useState<DirectoryLead|null>(null);
 const active=useRef<AbortController|null>(null),epoch=useRef(0),op=useRef<{identity:string;key:string}|null>(null);
 function clearBinding(){setAck(false);setReceipt(null);op.current=null;}
 function reset(){
  epoch.current++;active.current?.abort();active.current=null;
  setOpen(false);setBusy(false);setError('');setSummary(null);setGroup(null);
  setRows([]);setCursor(null);setSelected([]);setFamily('');setQ('');setTarget(null);setOutbound(null);clearBinding();
 }
 useEffect(()=>{
  const account=getAuthToken();if(!visible)reset();
  const sub=AppState.addEventListener('change',v=>{if(v!=='active')reset();});
  const guard=setInterval(()=>{if(account!==getAuthToken())reset();},500);
  return()=>{epoch.current++;active.current?.abort();sub.remove();clearInterval(guard);};
 },[visible]);
 useEffect(()=>{epoch.current++;active.current?.abort();active.current=null;setBusy(false);setTarget(null);clearBinding();},[game?.game_id]);
 const enabled=visible&&open&&!busy&&!disabled&&!!getAuthToken();
 function run(work:(signal:AbortSignal,current:()=>boolean)=>Promise<void>){
  if(!enabled||active.current)return;
  const ctrl=new AbortController(),generation=++epoch.current,token=getAuthToken();
  active.current=ctrl;setBusy(true);setError('');
  const current=()=>!ctrl.signal.aborted&&generation===epoch.current&&token===getAuthToken();
  void work(ctrl.signal,current).catch(e=>{if(current())setError(e instanceof Error?e.message:'Directory unavailable.');}).finally(()=>{if(active.current===ctrl){active.current=null;setBusy(false);}});
 }
 function choose(g:DirectoryGroup){
  setGroup(g);setQ('');setFamily('');setRows([]);setCursor(null);setSelected([]);setTarget(null);setOutbound(null);clearBinding();
 }
 const load=()=>run(async(signal,current)=>{
  const data=await directorySummary(signal);if(current()){setSummary(data);setGroup(null);setRows([]);setCursor(null);setSelected([]);setTarget(null);clearBinding();}
 });
 const browse=(after?:string)=>{if(!summary||!group)return;const a=summary,b=group;
  run(async(signal,current)=>{const data=await directoryLeads(a,b,q,family,after,signal);if(current()){setRows(data.leads);setCursor(data.next_cursor);setOutbound(null);}});
 };
 const filtered=()=>{setRows([]);setCursor(null);setOutbound(null);};
 function toggle(x:DirectoryLead){
  setSelected(v=>v.some(y=>y.lead_id===x.lead_id)?v.filter(y=>y.lead_id!==x.lead_id):v.length<64?[...v,x]:v);clearBinding();
 }
 const bind=()=>{
  if(!summary||!group||!canWrite||!target||!ack||!selected.length||target==='game'&&!game||target==='preset'&&!group.preset_game_id)return;
  const a=summary,b=group,items=[...selected],dest={game:target==='game'?game!.game_id:null,usePreset:target==='preset'};
  const identity=[a.revision,b.id,dest.game||'preset',...items.map(x=>x.lead_id).sort()].join(':');
  if(op.current?.identity!==identity)op.current={identity,key:crawlRequestKey('source-directory')};
  const operation=op.current.key;
  run(async(signal,current)=>{const result=await bindDirectoryLeads(a,b,items,operation,dest,signal);if(current()){setReceipt(result);setAck(false);}});
 };
 const button=(label:string,press:()=>void,off=false)=><TouchableOpacity accessibilityRole="button" disabled={!enabled||off} onPress={press} style={[s.button,(!enabled||off)&&s.disabled]}><Text style={s.buttonText}>{label}</Text></TouchableOpacity>;
 if(!visible)return null;
 return <View style={s.check}>
  <Text style={s.label}>Worldwide game source directory</Text>
  <Text style={s.small}>Browse game, franchise and multi-game discovery leads. A lead is not a verified source, an automatic crawl grant or a training license.</Text>
  <TouchableOpacity accessibilityRole="button" disabled={disabled||busy} onPress={()=>open?reset():setOpen(true)} style={s.button}><Text style={s.buttonText}>{open?'Close directory':'Open source directory'}</Text></TouchableOpacity>
  {open&&<>
   {button('Load directory',load)}
   {summary&&<>
    <Text style={s.small}>{summary.total_leads.toLocaleString()} source leads · {summary.distinct_origins} web hosts · {summary.source_classes} source types · {summary.families} families</Text>
    {summary.groups.map(g=><React.Fragment key={g.id}>{button((group?.id===g.id?'Selected: ':'')+(g.title||human(g.id))+' · '+g.leads,()=>choose(g))}</React.Fragment>)}
   </>}
   {group&&<>
    <Text style={s.label}>{group.title||human(group.id)} · {human(group.scope)}</Text>
    <TextInput value={q} onChangeText={v=>{setQ(v);filtered();}} maxLength={256} editable={enabled} style={field} accessibilityLabel="Search discovery leads" placeholder="Source, category, site, ecosystem…" placeholderTextColor={C.muted}/>
    {button('All source families',()=>{setFamily('');filtered();})}
    {Object.keys(group.families).sort().map(f=><React.Fragment key={f}>{button((family===f?'Selected: ':'')+human(f)+' · '+group.families[f],()=>{setFamily(f);filtered();})}</React.Fragment>)}
    {button('Browse matching public leads',()=>browse())}
    {rows.map(x=><View key={x.lead_id} style={s.check}>
     <Text style={s.label}>{x.label}</Text>
     <Text selectable style={s.small}>{x.url}</Text>
     <Text style={s.small}>{human(x.kind)} · {human(x.family)} · {x.view_mode} · {x.provider} · candidate only</Text>
     {button(selected.some(y=>y.lead_id===x.lead_id)?'Remove from selection':'Select candidate',()=>toggle(x),!canWrite||selected.length>=64&&!selected.some(y=>y.lead_id===x.lead_id))}
     {button(outbound?.lead_id===x.lead_id?'Cancel external navigation':'Prepare external navigation',()=>setOutbound(v=>v?.lead_id===x.lead_id?null:x))}
     {outbound?.lead_id===x.lead_id&&<View style={s.check}><Text style={s.small}>This unverified destination can redirect, offer downloads or track visits.</Text>{button('Open original site',()=>{setOutbound(null);try{void Linking.openURL(safeOriginalLink(x.url)).catch(()=>setError('External browser unavailable.'));}catch(e){setError(e instanceof Error?e.message:'External link held.');}})}</View>}
    </View>)}
    {button('Next discovery page',()=>{if(cursor)browse(cursor);},!cursor)}
    {canWrite&&<View style={s.check}>
     <Text style={s.label}>{selected.length} / 64 selected leads</Text>
     {selected.map(x=><View key={x.lead_id} style={s.row}><Text style={s.small}>{x.label}</Text>{button('Remove',()=>toggle(x))}</View>)}
     {button('Clear selection',()=>{setSelected([]);clearBinding();},!selected.length)}
     <Text style={s.small}>Select an explicit game identity. Multi-game directories cannot create synthetic game records.</Text>
     {button((target==='game'?'Selected: ':'')+'Bind to '+(game?.first_title||'current catalogue game'),()=>{setTarget('game');clearBinding();},!game)}
     {group.preset_game_id&&button((target==='preset'?'Selected: ':'')+'Bind to '+group.title+' preset',()=>{setTarget('preset');clearBinding();})}
     {button(ack?'Binding acknowledged':'Acknowledge catalogue-only binding',()=>setAck(v=>!v),!target||!selected.length)}
     {button('Queue selected source references',bind,!target||!ack||!selected.length)}
     {receipt&&<View><Text style={s.small}>{receipt.total} observations queued or replayed. No network capture authorized.</Text><Text selectable style={s.small}>Batch {receipt.batch_id}</Text><Text selectable style={s.small}>Game {receipt.game_id}</Text></View>}
    </View>}
   </>}
   {!!error&&<Text style={s.error}>{error}</Text>}
  </>}
 </View>;
}
