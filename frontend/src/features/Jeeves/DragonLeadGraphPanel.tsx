import React,{useEffect,useRef,useState} from 'react';
import {AppState,Linking,Text,TextInput,TouchableOpacity,View} from 'react-native';
import {getAuthToken} from '../../auth/gameforgeAuth';
import {crawlRequestKey} from '../../product/crawlerClient';
import {safeOriginalLink} from '../../product/dragonGameCorpusClient';
import {leadBundleStatus,enableLeadBundle,type BundleStatus,leadStatus,configureLeadGraph,publicDatasetLibrary,listLeads,leadEdges,recordLeadReview,listDatasetCandidates,registerDatasetCandidate,type GraphStatus,type DatasetTarget,type Lead,type Edge,type DatasetCandidate,type LeadState,type Projection,type TargetRegistration} from '../../product/dragonLeadGraphClient';
import s,{colors as C} from './CrawlerWorkspace.styles';

const field={color:C.text,backgroundColor:C.bg,borderWidth:1,borderColor:C.edge,borderRadius:9,padding:10};
const domains=['games','preservation','mods','game-data','competitive','media','research','development'];
const pretty=(x:string)=>x.replaceAll('_',' ').replaceAll('-',' ');
const number=(x:number)=>x.toLocaleString();
type Tab='library'|'leads'|'datasets';
type Props={visible:boolean;disabled:boolean;canWrite:boolean};
export default function DragonLeadGraphPanel({visible,disabled,canWrite}:Props){
 const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[status,setStatus]=useState<GraphStatus|null>(null);
 const [bundle,setBundle]=useState<BundleStatus|null>(null),[bundleRights,setBundleRights]=useState(''),[bundleAck,setBundleAck]=useState(false);
 const [tab,setTab]=useState<Tab>('library'),[q,setQ]=useState(''),[domain,setDomain]=useState(''),[state,setState]=useState<LeadState>('candidate'),[due,setDue]=useState(false);
 const [targets,setTargets]=useState<DatasetTarget[]>([]),[leads,setLeads]=useState<Lead[]>([]),[datasets,setDatasets]=useState<DatasetCandidate[]>([]),[cursor,setCursor]=useState<string|null>(null),[total,setTotal]=useState(0);
 const [selected,setSelected]=useState<Lead|null>(null),[edges,setEdges]=useState<Edge[]>([]),[edgeCursor,setEdgeCursor]=useState<string|null>(null),[direction,setDirection]=useState<'parents'|'children'>('children');
 const [candidate,setCandidate]=useState<DatasetCandidate|null>(null),[projection,setProjection]=useState<Projection>('locator'),[rights,setRights]=useState(''),[reason,setReason]=useState(''),[ack,setAck]=useState(false),[configAck,setConfigAck]=useState(false),[registration,setRegistration]=useState<TargetRegistration|null>(null),[outbound,setOutbound]=useState<string|null>(null);
 const active=useRef<AbortController|null>(null),epoch=useRef(0),reviewOp=useRef<{identity:string;key:string}|null>(null);
 function clearResults(){setTargets([]);setLeads([]);setDatasets([]);setCursor(null);setSelected(null);setEdges([]);setEdgeCursor(null);setCandidate(null);setRegistration(null);setOutbound(null);setAck(false);setRights('');setReason('');reviewOp.current=null;}
 function reset(){
  epoch.current++;active.current?.abort();active.current=null;setOpen(false);setBusy(false);setError('');setStatus(null);setBundle(null);setBundleRights('');setBundleAck(false);setTab('library');setQ('');setDomain('');setState('candidate');setDue(false);setTotal(0);setConfigAck(false);clearResults();
 }
 useEffect(()=>{
  const token=getAuthToken();if(!visible)reset();
  const app=AppState.addEventListener('change',v=>{if(v!=='active')reset();});
  const guard=setInterval(()=>{if(token!==getAuthToken())reset();},500);
  return()=>{epoch.current++;active.current?.abort();app.remove();clearInterval(guard);};
 },[visible]);
 const enabled=visible&&open&&!disabled&&!busy&&!!getAuthToken();
 function run(work:(signal:AbortSignal,current:()=>boolean)=>Promise<void>){
  if(!enabled||active.current)return;
  const ctrl=new AbortController(),token=getAuthToken(),id=++epoch.current;active.current=ctrl;setBusy(true);setError('');
  const current=()=>!ctrl.signal.aborted&&token===getAuthToken()&&epoch.current===id;
  void work(ctrl.signal,current).catch(e=>{if(current())setError(e instanceof Error?e.message:'Lead graph unavailable.');}).finally(()=>{if(active.current===ctrl){active.current=null;setBusy(false);}});
 }
 function loadStatus(){run(async(signal,current)=>{const x=await leadStatus(signal);if(current())setStatus(x);});}
 function loadBundle(){run(async(signal,current)=>{const x=await leadBundleStatus(signal);if(current())setBundle(x);});}
 function authorizeBundle(){
  if(!canWrite||!status?.enabled||!bundleAck||!bundleRights.trim())return;
  run(async(signal,current)=>{const x=await enableLeadBundle(bundleRights,signal);if(current()){setBundle(x);setBundleAck(false);setBundleRights('');}});
 }
 function configure(value:boolean){
  if(!canWrite||!configAck)return;
  run(async(signal,current)=>{const x=await configureLeadGraph(value,signal);if(current()){setStatus(x);setConfigAck(false);}});
 }
 function browse(after?:string){
  run(async(signal,current)=>{
   if(tab==='library'){
    const x=await publicDatasetLibrary(q,domain,after,signal);
    if(current()){setTargets(x.targets);setTotal(x.total_targets);setCursor(x.next_cursor);}
   }else if(tab==='leads'){
    const x=await listLeads(q,state,due,after,signal);
    if(current()){setLeads(x.leads);setCursor(x.next_cursor);setSelected(null);setEdges([]);setEdgeCursor(null);}
   }else{
    const x=await listDatasetCandidates(after,signal);
    if(current()){setDatasets(x.candidates);setCursor(x.next_cursor);setCandidate(null);setRegistration(null);setRights('');setAck(false);}
   }
  });
 }
 function showEdges(lead:Lead,dir:'parents'|'children',after?:string){
  run(async(signal,current)=>{const x=await leadEdges(lead.id,dir,after,signal);if(current()){setSelected(lead);setDirection(dir);setEdges(x.edges);setEdgeCursor(x.next_cursor);setAck(false);setReason('');}});
 }
 function review(decision:LeadState){
  if(!selected||!canWrite||!reason.trim()||!ack)return;
  const id=selected.id,why=reason.trim(),identity=[id,decision,why].join(':');
  if(reviewOp.current?.identity!==identity)reviewOp.current={identity,key:crawlRequestKey('lead-review')};
  const operation=reviewOp.current.key;
  run(async(signal,current)=>{await recordLeadReview(id,decision,why,operation,signal);if(current()){setAck(false);setReason('');setSelected(null);setEdges([]);setLeads([]);setCursor(null);}});
 }
 function register(value:boolean){
  if(!candidate||!canWrite||!rights.trim()||!ack)return;
  const lead=candidate.id,ref=rights.trim(),kind=projection;
  run(async(signal,current)=>{const x=await registerDatasetCandidate(lead,kind,ref,value,signal);if(current()){setRegistration(x);setAck(false);setRights('');}});
 }
 const button=(label:string,press:()=>void,off=false)=><TouchableOpacity accessibilityRole="button" disabled={!enabled||off} onPress={press} style={[s.button,(!enabled||off)&&s.disabled]}><Text style={s.buttonText}>{label}</Text></TouchableOpacity>;
 const external=(url:string)=><>{button(outbound===url?'Cancel external navigation':'Prepare external source',()=>setOutbound(v=>v===url?null:url))}{outbound===url&&<View style={s.check}><Text style={s.small}>Unverified external location. Review terms and per-file rights before acquiring data.</Text>{button('Open original source',()=>{setOutbound(null);try{void Linking.openURL(safeOriginalLink(url)).catch(()=>setError('External browser unavailable.'));}catch(e){setError(e instanceof Error?e.message:'External location held.');}})}</View>}</>;
 function changeTab(value:Tab){setTab(value);setQ('');setDomain('');clearResults();}
 if(!visible)return null;
 return <View style={s.check}>
  <Text style={s.label}>Ever-growing lead graph and public datasets</Text>
  <Text style={s.small}>Discover, retain and review candidate paths independently of authorization to capture or ingest content. The graph grows from dataset projections and already-authorized feeds.</Text>
  <TouchableOpacity accessibilityRole="button" disabled={disabled||busy} onPress={()=>open?reset():setOpen(true)} style={s.button}><Text style={s.buttonText}>{open?'Close lead graph':'Explore lead graph'}</Text></TouchableOpacity>
  {open&&<>
   {button('Refresh measured graph status',loadStatus)}
   {button('Inspect bundled identity snapshot',loadBundle)}
   {bundle&&<View style={s.check}>
    <Text style={s.label}>{number(bundle.title_identity_candidates)} bundled candidate AppIDs</Text>
    <Text style={s.small}>{number(bundle.store_locator_floor)} distinct candidate storefront locators · {bundle.shards} pinned shards · {number(bundle.gross_optional_route_candidates)} gross optional routes (not verified).</Text>
    <Text style={s.small}>{number(bundle.snapshot_identity_candidates_ingested)} / {number(bundle.title_identity_candidates)} identity rows admitted · {bundle.snapshot?.state||'not started'} · source rights not independently verified.</Text>
    <Text selectable style={s.small}>Source: {bundle.source_url} · revision {bundle.bundle_revision}</Text>
    {external(bundle.source_url)}
    {canWrite&&<>
     <TextInput style={field} accessibilityLabel="Bundled source rights reference" placeholder="Reviewed metadata rights reference" placeholderTextColor={C.muted} value={bundleRights} maxLength={128} editable={enabled} onChangeText={v=>{setBundleRights(v);setBundleAck(false);}}/>
     {button(bundleAck?'Metadata rights acknowledged':'Acknowledge reviewed metadata rights',()=>setBundleAck(v=>!v),!bundleRights.trim())}
     {button('Enable or renew 30-day bundle admission',authorizeBundle,!status?.enabled||!bundleRights.trim()||!bundleAck)}
    </>}
   </View>}
   {status&&<View style={s.check}>
    <Text style={s.label}>{number(status.nodes)} unique owned lead nodes · {number(status.edges)} provenance edges</Text>
    <Text style={s.small}>{number(status.bootstrap_cursor)} / {number(status.bootstrap_target_rows)} bootstrap input records processed · {status.bootstrapped?'complete':'in progress or disabled'}</Text>
    <Text style={s.small}>Growth floor: {number(status.growth_floor)} · {status.growth_floor_met?'met':'not yet met'} · {number(status.snapshots)} dataset snapshots</Text>
    <Text style={s.small}>Logical cap: {number(status.architecture_node_cap)} nodes, {number(status.architecture_evidence_cap)} evidence edges. Not physically qualified.</Text>
   </View>}
   {canWrite&&<View style={s.check}>
    {button(configAck?'Metadata-only expansion acknowledged':'Acknowledge metadata-only expansion',()=>setConfigAck(v=>!v))}
    {button(status?.enabled?'Suspend lead growth':'Enable recurring lead growth',()=>configure(!status?.enabled),!configAck)}
   </View>}
   {(['library','leads','datasets'] as Tab[]).map(value=><React.Fragment key={value}>{button((tab===value?'Selected: ':'')+(value==='library'?'Public dataset library':value==='leads'?'Lead index':'Discovered dataset candidates'),()=>changeTab(value))}</React.Fragment>)}
   {tab!=='datasets'&&<TextInput style={field} accessibilityLabel="Search lead graph" placeholder="Game, dataset, source…" placeholderTextColor={C.muted} value={q} maxLength={256} editable={enabled} onChangeText={v=>{setQ(v);clearResults();}}/>}
   {tab==='library'&&<>{button('All dataset domains',()=>{setDomain('');clearResults();})}{domains.map(d=><React.Fragment key={d}>{button((domain===d?'Selected: ':'')+pretty(d),()=>{setDomain(d);clearResults();})}</React.Fragment>)}</>}
   {tab==='leads'&&<>{(['candidate','held','retired'] as LeadState[]).map(v=><React.Fragment key={v}>{button((state===v?'Selected: ':'')+v,()=>{setState(v);clearResults();})}</React.Fragment>)}{button(due?'Due review only':'All review dates',()=>{setDue(v=>!v);clearResults();})}</>}
   {button('Browse',()=>browse())}
   {tab==='library'&&<>
    {!!total&&<Text style={s.small}>{total} registry targets · not all sites are direct data exports.</Text>}
    {targets.map(x=><View key={x.id} style={s.check}>
     <Text style={s.label}>{pretty(x.id)}</Text><Text style={s.small}>{pretty(x.domain)} · {pretty(x.access)} · {x.cadence}</Text>
     <Text style={s.small}>{x.notes}</Text>{x.advertised_rows!==null&&<Text style={s.small}>Advertised rows: {number(x.advertised_rows)} (overlapping, not ingested)</Text>}
     <Text selectable style={s.small}>{x.url}</Text><Text selectable style={s.small}>Target ID: {x.id} · adapter: {x.adapter}</Text>{external(x.url)}
    </View>)}
    <Text style={s.small}>For large authorized local exports, use core.dragon_lead_ingest with an explicit target, dataset checksum and owner-reviewed metadata rights. The streaming importer supports Steam CSV, optional Parquet/JSON readers, and normalized NDJSON.</Text>
   </>}
   {tab==='leads'&&<>
    {leads.map(x=><View key={x.id} style={s.check}>
     <Text style={s.label}>{x.title}</Text><Text selectable style={s.small}>{x.url}</Text>
     <Text style={s.small}>{pretty(x.kind)} · {number(x.observations)} observations · {x.state}</Text>
     {button('Inspect discovery parents',()=>showEdges(x,'parents'))}{button('Inspect discovered children',()=>showEdges(x,'children'))}{external(x.url)}
    </View>)}
    {selected&&<View style={s.check}>
     <Text style={s.label}>{selected.title}: {direction}</Text>
     {edges.map(e=><View key={e.id} style={s.check}><Text style={s.label}>{e.title}</Text><Text style={s.small}>{pretty(e.relation)} · {e.subject} · {e.snapshot_state||'no dataset snapshot'}</Text><Text selectable style={s.small}>{direction==='parents'?e.parent:e.child}</Text><Text selectable style={s.small}>Witness {e.witness}</Text></View>)}
     {button('Next edge page',()=>{if(edgeCursor)showEdges(selected,direction,edgeCursor);},!edgeCursor)}
     {canWrite&&<>
      <TextInput style={field} accessibilityLabel="Lead disposition reason" placeholder="Review reason" placeholderTextColor={C.muted} value={reason} maxLength={512} editable={enabled} onChangeText={v=>{setReason(v);setAck(false);}}/>
      {button(ack?'Review acknowledged':'Acknowledge metadata-only disposition',()=>setAck(v=>!v),!reason.trim())}
      {(['candidate','held','retired'] as LeadState[]).map(v=><React.Fragment key={v}>{button('Mark '+v,()=>review(v),!ack||!reason.trim())}</React.Fragment>)}
     </>}
    </View>}
   </>}
   {tab==='datasets'&&<>
    {datasets.map(x=><View key={x.id} style={s.check}><Text style={s.label}>{x.title}</Text><Text selectable style={s.small}>{x.url}</Text>
     <Text style={s.small}>{x.target_id?'Registered target: '+x.target_id:'Unregistered dataset lead'}</Text>{external(x.url)}
     {canWrite&&button('Review dataset target',()=>{setCandidate(x);setProjection(x.projection||'locator');setRights('');setRegistration(null);setAck(false);})}</View>)}
    {candidate&&<View style={s.check}>
     <Text style={s.label}>Review target: {candidate.title}</Text>
     {(['locator','steam','modrinth'] as Projection[]).map(v=><React.Fragment key={v}>{button((projection===v?'Selected: ':'')+v,()=>{setProjection(v);setAck(false);})}</React.Fragment>)}
     <TextInput style={field} accessibilityLabel="Source rights reference" placeholder="Metadata rights reference (no credentials)" placeholderTextColor={C.muted} value={rights} maxLength={128} editable={enabled} onChangeText={v=>{setRights(v);setAck(false);}}/>
     {button(ack?'Finite import rights acknowledged':'Acknowledge seven-day metadata import rights',()=>setAck(v=>!v),!rights.trim())}
     {button('Register or renew dataset target',()=>register(true),!ack||!rights.trim())}{button('Withdraw dataset target',()=>register(false),!ack||!rights.trim()||!candidate.target_id)}
     {registration&&<Text selectable style={s.small}>{registration.enabled?'Registered':'Withdrawn'} target {registration.target_id} · no network grant.</Text>}
    </View>}
   </>}
   {button('Next page',()=>{if(cursor)browse(cursor);},!cursor)}
   {!!error&&<Text style={s.error}>{error}</Text>}
  </>}
 </View>;
}
