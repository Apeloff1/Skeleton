import React,{useCallback,useEffect,useRef,useState} from 'react';
import {ActivityIndicator,AppState,Switch,Text,TextInput,TouchableOpacity,View} from 'react-native';
import {getAuthToken} from '../../auth/gameforgeAuth';
import {getDragonTreasury,getTreasuryPassage,configureDragonArchive,configureTreasuryWatch,getCrawl,crawlRequestKey,type CrawlSession,type DragonTreasury,type TreasuryMode,type TreasuryRevision,type TreasuryPassage,type TreasurySearchOptions} from '../../product/crawlerClient';
import s,{colors} from './CrawlerWorkspace.styles';
import AnimatedDragon from './companion/DragonCompanion';
import DragonLegacyTreasuryPanel from './DragonLegacyTreasuryPanel';
import DragonVaultPanel from './DragonVaultPanel';
import {INITIAL_DRAGON_STATE} from './companion/dragonCompanionState';
import {useReducedMotion,useScreenReader} from './companion/useDragonMotion';
import {usePowerAwareness} from '../../hooks/usePowerAwareness';

const MODES: readonly [TreasuryMode,string][]=[['current_only','Current chest'],['historic_only','Historic vault'],['all_revisions','All versions'],['timeline','Timeline'],['compare','Compare'],['at_time','At observation date']];
const field={backgroundColor:colors.bg,borderWidth:1,borderColor:colors.edge,borderRadius:9,padding:12,color:colors.text,fontSize:14};
const stamp=(n:number)=>new Date(n*1000).toLocaleString();
const short=(s:string)=>s.slice(0,12);
function Button({label,action,disabled=false}:{label:string;action:()=>void;disabled?:boolean}){
 return <TouchableOpacity style={[s.button,disabled&&s.disabled]} accessibilityRole="button" accessibilityState={{disabled}} disabled={disabled} onPress={action}><Text style={s.buttonText}>{label}</Text></TouchableOpacity>;
}
function Revision({row,inspect,select,watch,disabled=false}:{row:TreasuryRevision;inspect?:(row:TreasuryRevision)=>void;select?:(row:TreasuryRevision)=>void;watch?:(row:TreasuryRevision)=>void;disabled?:boolean}){
 return <View style={s.check}>
  <Text selectable style={s.label}>{row.plane==='current'?'Current':'Historic'} · {short(row.revision_id)} · {row.delta.kind.replaceAll('_',' ')}</Text>
  <Text style={s.small}>{stamp(row.first_seen)} → {stamp(row.last_seen)} · {row.reobservations} subsequent observations</Text>
  <Text style={s.small}>{row.indexed?(row.archive_only?'Historical permission only':'Authorized retained text'):'Metadata only · no searchable text'}{row.latest_observed?' · latest observed':''}</Text>
  {row.delta.similarity!==null&&<Text style={s.small}>Lexical similarity {Math.round(row.delta.similarity*100)}% · {row.delta.added_terms} added terms · {row.delta.removed_terms} removed · numeric change {row.delta.numeric_change?'observed':'not observed'}</Text>}
  {row.source_id&&<Text selectable style={s.small}>Source {row.source_id}{row.indexed_capture_at!==null?' · indexed observation '+stamp(row.indexed_capture_at):''}</Text>}
  {row.indexed&&inspect&&<Button label="Inspect exact retained text" disabled={disabled} action={()=>inspect(row)}/>}
  {row.indexed&&select&&<Button label="Select this revision for comparison" disabled={disabled} action={()=>select(row)}/>}
  {row.indexed&&watch&&<Button label="Choose source for finite automatic watch" disabled={disabled} action={()=>watch(row)}/>}
 </View>;
}
export default function DragonTreasuryPanel({revision,session,canWrite=false,onSession,onRevisit,disabled=false}:{revision:string;session?:CrawlSession|null;canWrite?:boolean;onSession?:(s:CrawlSession)=>void;onRevisit?:(url:string)=>void;disabled?:boolean}){
 const [result,setResult]=useState<DragonTreasury|null>(null);
 const [mode,setMode]=useState<TreasuryMode>('current_only');
 const [vaultWindow,setVaultWindow]=useState<string[]|undefined>();
 const [query,setQuery]=useState('');
 const [cutoff,setCutoff]=useState('');
 const [selectedChange,setSelectedChange]=useState<TreasuryRevision|null>(null);
 const [pair,setPair]=useState<{left:string;right:string}|null>(null);
 const [family,setFamily]=useState<string|undefined>();
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [days,setDays]=useState('30');
 const [rights,setRights]=useState(false);
 const [watchSource,setWatchSource]=useState<string|null>(null);
 const [watchDays,setWatchDays]=useState('7');
 const [watchCycles,setWatchCycles]=useState('3');
 const [watchHours,setWatchHours]=useState('24');
 const [watchCapture,setWatchCapture]=useState(false),[watchArchive,setWatchArchive]=useState(false);
 const watchKey=useRef<{identity:string;key:string}|null>(null);
 const [open,setOpen]=useState(false);
 const [passage,setPassage]=useState<TreasuryPassage|null>(null);
 const [passageBusy,setPassageBusy]=useState(false);
 const passageRequest=useRef<AbortController|null>(null),passageTimer=useRef<ReturnType<typeof setTimeout>|null>(null);
 const request=useRef<AbortController|null>(null), timer=useRef<ReturnType<typeof setTimeout>|null>(null);
 const generation=useRef(0), owner=useRef(getAuthToken()), observed=useRef(revision);
 const grantKey=useRef<{identity:string;key:string}|null>(null);
 const reduced=useReducedMotion(),screenReader=useScreenReader(),power=usePowerAwareness();
 const invalidate=useCallback(()=>{
  generation.current++;request.current?.abort();request.current=null;
  passageRequest.current?.abort();passageRequest.current=null;
  if(passageTimer.current!==null)clearTimeout(passageTimer.current);passageTimer.current=null;
  setPassage(null);setPassageBusy(false);
  if(timer.current!==null)clearTimeout(timer.current);timer.current=null;
 },[]);
 const chooseVaultWindow=useCallback((ids?:string[],discoveryQuery?:string)=>{
  invalidate();setResult(null);setBusy(false);setSelectedChange(null);setPair(null);setFamily(undefined);
  if(discoveryQuery!==undefined)setQuery(discoveryQuery);
  setVaultWindow(ids);setMode(ids?'historic_only':'current_only');
 },[invalidate]);
 useEffect(()=>{
  if(observed.current!==revision){observed.current=revision;invalidate();setResult(null);setBusy(false);grantKey.current=null;setSelectedChange(null);setPair(null);}
  return ()=>invalidate();
 },[revision,invalidate]);
 useEffect(()=>{
  const sub=AppState.addEventListener('change',state=>{if(state!=='active'){invalidate();setResult(null);setBusy(false);setVaultWindow(undefined);setMode('current_only');}});
  const tick=setInterval(()=>{if(owner.current!==getAuthToken()){
   owner.current=getAuthToken();invalidate();setResult(null);setBusy(false);setVaultWindow(undefined);setMode('current_only');
   setFamily(undefined);setSelectedChange(null);setPair(null);setQuery('');setError('');
  }},1000);
  return()=>{sub.remove();clearInterval(tick);};
 },[invalidate]);
 useEffect(()=>{setRights(false);grantKey.current=null;setWatchSource(null);setWatchCapture(false);setWatchArchive(false);watchKey.current=null;},[session?.session_id,session?.version]);
 const visible=result&&observed.current===revision&&owner.current===getAuthToken()?result:null;
 async function observe(nextMode=mode,nextFamily=family,page?:string,comparison?:{left:string;right:string}){
  const search:TreasurySearchOptions={cursor:page,...comparison,vaultSessions:vaultWindow};
  if(nextMode==='at_time'){
   if(!/^\d{4}-\d{2}-\d{2}$/.test(cutoff)){setError('Enter an observation date as YYYY-MM-DD (UTC).');return;}
   const date=Date.parse(cutoff+'T23:59:59Z');
   if(!Number.isFinite(date)||new Date(date).toISOString().slice(0,10)!==cutoff||date>Date.now()){setError('Choose a valid past UTC observation date.');return;}
   search.observedBefore=date/1000;
  }
  invalidate();const epoch=generation.current, token=getAuthToken(), started=Date.now(),ctrl=new AbortController();
  owner.current=token;request.current=ctrl;setBusy(true);setResult(null);setError('');
  try{
   const value=await getDragonTreasury(nextMode,query,nextFamily,ctrl.signal,search);
   if(ctrl.signal.aborted||epoch!==generation.current||token!==getAuthToken())return;
   const ttl=value.earliest_source_expiry===null?120000:Math.min(120000,1000*(value.earliest_source_expiry-value.as_of_unix)-(Date.now()-started));
   if(ttl<=0){setError('A source permission expired. Reparse again.');return;}
   setResult(value);
   timer.current=setTimeout(()=>{if(epoch===generation.current)setResult(null);},ttl);
  }catch(e){if(!ctrl.signal.aborted&&epoch===generation.current&&token===getAuthToken())setError(e instanceof Error?e.message:'Treasury unavailable.');}
  finally{if(epoch===generation.current){request.current=null;setBusy(false);}}
 }
 function selectRevision(row:TreasuryRevision){
  if(!visible||!row.indexed)return;
  if(!selectedChange||selectedChange.family_id!==row.family_id){setSelectedChange(row);setPair(null);return;}
  if(selectedChange.revision_id===row.revision_id){setSelectedChange(null);return;}
  const sorted=[selectedChange,row].sort((a,b)=>a.first_seen-b.first_seen||a.revision_id.localeCompare(b.revision_id));
  const selection={left:sorted[0].revision_id,right:sorted[1].revision_id};
  setPair(selection);setSelectedChange(null);setFamily(row.family_id);setMode('compare');
  void observe('compare',row.family_id,undefined,selection);
 }
 async function inspect(row:{session_id:string|null;source_id:string|null},offset=0){
  if(!visible||!row.session_id||!row.source_id||passageBusy)return;
  const sid=row.session_id,source=row.source_id,token=getAuthToken(),epoch=generation.current,started=Date.now();
  passageRequest.current?.abort();if(passageTimer.current!==null)clearTimeout(passageTimer.current);
  const ctrl=new AbortController();passageRequest.current=ctrl;setPassageBusy(true);setPassage(null);setError('');
  try{
   const p=await getTreasuryPassage(sid,source,offset,ctrl.signal);
   if(ctrl.signal.aborted||generation.current!==epoch||getAuthToken()!==token)return;
   const ttl=Math.min(120000,1000*(p.valid_until-p.as_of_unix)-(Date.now()-started));
   if(ttl<=0){setError('Source permission expired during inspection.');return;}
   setPassage(p);
   passageTimer.current=setTimeout(()=>{if(generation.current===epoch)setPassage(null);},ttl);
  }catch(e){if(!ctrl.signal.aborted&&generation.current===epoch&&getAuthToken()===token)setError(e instanceof Error?e.message:'Historical inspection unavailable.');}
  finally{if(passageRequest.current===ctrl){passageRequest.current=null;setPassageBusy(false);}}
 }
 async function grant(enabled:boolean){
  if(!session||!onSession||busy||disabled||enabled&&(!canWrite||!rights))return;
  const n=enabled?Number(days):30;if(!Number.isInteger(n)||n<1||n>30){setError('Choose a retention period of 1–30 days.');return;}
  invalidate();const ctrl=new AbortController(),epoch=generation.current,token=getAuthToken();
  owner.current=token;request.current=ctrl;setBusy(true);setError('');setResult(null);
  const identity=[session.session_id,session.version,enabled,n,enabled&&rights].join(':');
  if(grantKey.current?.identity!==identity)grantKey.current={identity,key:crawlRequestKey('archive')};
  try{
   const updated=await configureDragonArchive(session.session_id,{expected_version:session.version,idempotency_key:grantKey.current.key,enabled,days:n,archive_rights_acknowledged:enabled&&rights},ctrl.signal);
   if(ctrl.signal.aborted||epoch!==generation.current||token!==getAuthToken())return;
   grantKey.current=null;setRights(false);onSession(updated);
  }catch(e){if(!ctrl.signal.aborted&&epoch===generation.current&&token===getAuthToken())setError(e instanceof Error?e.message:'Archive command was not confirmed.');}
  finally{if(epoch===generation.current){request.current=null;setBusy(false);}}
 }
 async function configureWatch(enabled:boolean){
  if(!session||!onSession||busy||disabled||enabled&&(!canWrite||!watchSource||!watchCapture||!watchArchive))return;
  const sourceId=enabled?watchSource:session.treasury_watch?.source_id;
  if(!sourceId)return;
  const d=enabled?Number(watchDays):7,n=enabled?Number(watchCycles):3,h=enabled?Number(watchHours):24;
  const retention=enabled?Number(days):30;
  if(![d,n,h,retention].every(Number.isInteger)||d<1||d>7||n<1||n>6||h<6||h>168||retention<1||retention>30||enabled&&h>=24*d){
   setError('Choose 1–7 watch days, 1–6 cycles, a 6–168 hour minimum interval shorter than the grant, and 1–30 retention days.');return;
  }
  invalidate();const ctrl=new AbortController(),epoch=generation.current,token=getAuthToken();
  owner.current=token;request.current=ctrl;setBusy(true);setError('');setResult(null);
  const identity=[session.session_id,session.version,enabled,sourceId,d,n,h,retention].join(':');
  if(watchKey.current?.identity!==identity)watchKey.current={identity,key:crawlRequestKey('watch')};
  try{
   await configureTreasuryWatch(session.session_id,{expected_version:session.version,idempotency_key:watchKey.current.key,
    enabled,source_id:sourceId,days:d,cycles:n,minimum_interval:h*3600,retention_days:retention,
    capture_rights_acknowledged:enabled&&watchCapture,archive_rights_acknowledged:enabled&&watchArchive},ctrl.signal);
   const updated=await getCrawl(session.session_id,ctrl.signal);
   if(ctrl.signal.aborted||generation.current!==epoch||getAuthToken()!==token)return;
   watchKey.current=null;setWatchCapture(false);setWatchArchive(false);onSession(updated);
  }catch(e){if(!ctrl.signal.aborted&&generation.current===epoch&&getAuthToken()===token)setError(e instanceof Error?e.message:'Watch command unconfirmed. Refresh before retrying.');}
  finally{if(generation.current===epoch){request.current=null;setBusy(false);}}
 }
 const terminal=session&&['completed','budget_exhausted'].includes(session.status);
 const activeWatch=session?.treasury_watch;
 const pickWatch=(row:TreasuryRevision)=>{if(row.session_id===session?.session_id&&row.source_id){setWatchSource(row.source_id);setWatchCapture(false);setWatchArchive(false);}};
 const evolution=visible?.evolution;
 return <View style={s.card}>
  <Text style={s.eyebrow}>HOARDER · TREASURY AND VAULT</Text>
  <Text style={s.heading}>Living knowledge archive</Text>
  <Text style={s.small}>Keep versions separate. Reparse retained text without new network requests. Current means latest observed, not verified live truth.</Text>
  <Button label={open?'Close treasury':'Open treasury'} action={()=>{setOpen(!open);if(open){invalidate();setResult(null);setBusy(false);}}}/>
  {open&&<>
   <DragonLegacyTreasuryPanel revision={revision} canWrite={canWrite} disabled={busy||disabled} onChanged={()=>{invalidate();setResult(null);setBusy(false);}}/>
   <DragonVaultPanel revision={revision} session={session} canWrite={canWrite} disabled={busy||disabled}
     onWindow={chooseVaultWindow} onSession={onSession} onChanged={()=>{invalidate();setResult(null);setBusy(false);}}/>
   {vaultWindow&&<View style={s.check}><Text style={s.label}>Selected cold-custody window · {vaultWindow.length} expeditions</Text>
    <Text style={s.small}>Only separately authorized historical text. This window cannot establish global current coverage or earn current discovery credit.</Text>
    <Button label="Return to owner-wide treasury" disabled={busy||disabled} action={()=>chooseVaultWindow(undefined)}/>
   </View>}
   {terminal&&onSession&&<View style={s.check}>
    <Text style={s.label}>Historical retention for this finished expedition</Text>
    <Text style={s.small}>{session.archive_grant?.active?'Active until '+stamp(session.archive_grant.expires_at!):'No active historical-use grant.'} {session.archive_grant?.usable_sources??0} authorized retained sources.</Text>
    {canWrite&&<><TextInput style={field} value={days} editable={!busy&&!disabled} onChangeText={setDays} keyboardType="number-pad" maxLength={2} accessibilityLabel="Historical retention days"/>
     <View style={s.row}><Switch value={rights} disabled={busy||disabled} onValueChange={setRights} accessibilityLabel="Confirm historical archive rights"/><Text style={[s.small,s.grow]}>I have rights to retain and reparse eligible captured text for the selected period. This does not renew crawl or model-use consent.</Text></View>
     <Button label="Authorize historical use" disabled={!rights||busy||disabled} action={()=>void grant(true)}/></>}
    {session.archive_grant&&<Button label="Revoke historical use" disabled={busy||disabled} action={()=>void grant(false)}/>}
   </View>}
   {terminal&&onSession&&!session.watch_managed&&<View style={s.check}>
    <Text style={s.heading}>Automatic source maintenance</Text>
    <Text style={s.small}>Finite exact-source watch. Each cycle uses the existing crawler and a new bounded expedition; explicit robots refusals and quarantined instructions stop the watch. A revoke stops new requests but cannot undo a request already sent.</Text>
    {activeWatch&&<><Text style={s.label}>{activeWatch.enabled?'Authorized':'Stopped'} · {activeWatch.state} · {activeWatch.cycles_completed}/{activeWatch.max_cycles} reserved cycles settled</Text>
     <Text style={s.small}>Next review {stamp(activeWatch.next_due)} · grant ends {stamp(activeWatch.expires_at)}{activeWatch.stop_reason?' · '+activeWatch.stop_reason:''}</Text>
     {activeWatch.last_child_id&&<Text selectable style={s.small}>Latest child expedition: {activeWatch.last_child_id}</Text>}
     {activeWatch.enabled&&<Button label="Revoke automatic maintenance" disabled={busy||disabled} action={()=>void configureWatch(false)}/>}</>}
    {canWrite&&!activeWatch?.enabled&&<>
      <Text style={s.small}>{watchSource?'Selected exact source '+short(watchSource):'Reparse the treasury and choose an indexed source from this selected expedition below.'}</Text>
      {[[watchDays,setWatchDays,'Watch duration (days)'],[watchCycles,setWatchCycles,'Maximum cycles'],[watchHours,setWatchHours,'Minimum interval (hours)']].map(([value,set,label])=><View key={String(label)}><Text style={s.label}>{String(label)}</Text><TextInput value={String(value)} onChangeText={set as (v:string)=>void} keyboardType="number-pad" maxLength={3} style={field} accessibilityLabel={String(label)} editable={!busy&&!disabled}/></View>)}
      <Text style={s.small}>Each successful eligible child receives the historical retention period selected above ({days} days).</Text>
      <View style={s.row}><Switch value={watchCapture} onValueChange={setWatchCapture} disabled={busy||disabled} accessibilityLabel="Authorize repeated public source capture"/><Text style={[s.small,s.grow]}>I authorize the specified recurring public capture, including the required robots request, within these limits.</Text></View>
      <View style={s.row}><Switch value={watchArchive} onValueChange={setWatchArchive} disabled={busy||disabled} accessibilityLabel="Authorize retained history for watched captures"/><Text style={[s.small,s.grow]}>I have rights to retain and reparse eligible snapshots for the chosen period.</Text></View>
      <Button label="Authorize finite automatic watch" disabled={!watchSource||!watchCapture||!watchArchive||busy||disabled} action={()=>void configureWatch(true)}/>
    </>}
   </View>}
   <TextInput value={query} editable={!busy&&!disabled} onChangeText={v=>{setQuery(v);invalidate();setResult(null);setBusy(false);setSelectedChange(null);setPair(null);}} maxLength={256} placeholder="Search retained versions" placeholderTextColor={colors.muted} accessibilityLabel="Search treasury" style={field}/>
   <View style={s.row}>{MODES.filter(([id])=>!vaultWindow||id!=='current_only').map(([id,label])=><TouchableOpacity key={id} style={[s.button,mode===id&&{backgroundColor:'#52382d'}]} accessibilityRole="button" accessibilityState={{selected:mode===id,disabled:busy||disabled}} disabled={busy||disabled} onPress={()=>{setMode(id);invalidate();setResult(null);setBusy(false);setSelectedChange(null);setPair(null);}}><Text style={s.buttonText}>{label}</Text></TouchableOpacity>)}</View>
   {mode==='at_time'&&<TextInput value={cutoff} onChangeText={value=>{setCutoff(value);invalidate();setResult(null);setBusy(false);}} maxLength={10} placeholder="YYYY-MM-DD (UTC)" placeholderTextColor={colors.muted} accessibilityLabel="Historical observation date UTC" style={field}/>}
   {family&&<Button label={'Clear family filter '+short(family)} disabled={busy||disabled} action={()=>{setFamily(undefined);invalidate();setResult(null);setBusy(false);setSelectedChange(null);setPair(null);}}/>}
   {selectedChange&&<Text style={s.small}>Selected {short(selectedChange.revision_id)}. Choose another indexed version from the same family to compare.</Text>}
   <Button label={busy?'Reparsing…':'Reparse authorized versions'} disabled={busy||disabled} action={()=>void observe(mode,family,undefined,pair??undefined)}/>
   {busy&&<ActivityIndicator color={colors.accent}/>}
   {!!error&&<Text style={s.error} accessibilityLiveRegion="polite">{error}</Text>}
   {visible&&evolution&&<>
    <AnimatedDragon state={{...INITIAL_DRAGON_STATE,phase:'sleeping',label:evolution.form==='hoarder'?'Cozy guardian of the hoard':'Growing a little treasure den',detail:'Treasury evolution from retained evidence and verified version custody. Rest is always free.',progress:evolution.stage_progress,wings:evolution.stage>=2,snuggly:true}} evolutionStage={evolution.stage} level={evolution.level} unlocked={evolution.stage>=4?['star_cartographer','apprentice_forge']:[]} researchMode screenReader={screenReader} motion={reduced||screenReader||power.shouldReduceAnimations?'off':'gentle'} reducedMotion={reduced||screenReader||power.shouldReduceAnimations}/>
    <Text style={s.heading}>{evolution.form.toUpperCase()} · Level {evolution.level}</Text>
    <Text style={s.small}>Discovery {evolution.expedition_growth}/1000 · stewardship {evolution.treasury_growth}/500 · effective evolution {evolution.effective_evolution}/1500</Text>
    <Text style={s.small}>Hoarder unlock requires discovery ≥800, sufficient authorized historic transitions and at least two current families. Permission changes may change the collection view, not pet health.</Text>
    <Text style={s.label}>Current indexed {visible.current_indexed} · Historic indexed {visible.historic_indexed} · Metadata only {visible.metadata_only}</Text>
    <Text style={s.small}>{visible.families} families · {visible.revisions} versions · {visible.rollbacks} rollbacks · {visible.blocked_current} current families unavailable · {visible.alias_held_families} alias conflicts</Text>
    <Text style={s.small}>{visible.indexed_observations}/{visible.eligible_observations} permitted observations selected · {visible.legacy_history_sessions} older runtime sessions. Selected-family and historical-date queries reserve capacity for their requested evidence.</Text>
    {visible.query_admission&&<Text style={s.small}>Query-aware selection: {visible.query_admission.scanned_representatives} permitted versions scanned · {visible.query_admission.matching_representatives} lexical matches · {visible.query_admission.prioritized_representatives} prioritized for structural reparse. Not an exhaustive structural index.</Text>}
    {visible.index_health&&<View style={s.check}>
      <Text style={s.label}>Hoarder den · archival index health</Text>
      <Text style={s.small}>{visible.index_health.qualified_segments}/{visible.index_health.active_grants} active grant segments qualified · {visible.index_health.materialized_archive_members}/{visible.index_health.eligible_archive_members} permitted archive members materialized.</Text>
      <Text style={s.small}>{visible.index_health.missing_segments} missing · {visible.index_health.stale_segments} stale · {visible.index_health.invalid_segments} damaged. The crawler can repair derived postings; older versions remain history-only.</Text>
    </View>}
    {visible.invalid_materialized_segments>0&&<Text style={s.small}>An invalid or stale derived index was ignored. Scheduled maintenance can repair stored postings without renewing permission.</Text>}
    {(visible.candidate_limit_reached||visible.excluded_sessions>0)&&<Text style={s.small}>Bounded or unqualified corpus: this observation cannot establish complete archive coverage.</Text>}
    <Text style={s.heading}>Revision families and revisit recommendations</Text>
    <Text style={s.small}>{visible.parsed_unique_payloads} distinct retained payload projections · {visible.materialized_payload_hits} reused from durable index · {visible.verified_historic_transitions} distinct verified version transitions · {visible.revisit_plan.length} prioritized suggestions, interleaved across origins.</Text>
    {visible.family_rows.map(f=><View key={f.family_id} style={s.check}>
     <Text style={s.label}>{short(f.family_id)} · {f.revision_count} versions{f.simultaneous_conflict?' · conflicting observations':''}{f.alias_conflict?' · newer ambiguous alias':''}</Text>
     <Text style={s.small}>{f.current_indexed?'Current indexed':'Current unavailable'} · last seen {stamp(f.last_seen)}</Text>
     <Text style={s.small}>Advisory review {stamp(f.revisit.due_at)} · estimated change risk {Math.round(f.revisit.change_probability_estimate*100)}% · {f.revisit.qualified_intervals} qualified intervals</Text>
     <Button label="Compare versions" disabled={busy||disabled} action={()=>{setFamily(f.family_id);setMode('compare');setPair(null);setSelectedChange(null);void observe('compare',f.family_id);}}/>
     {!!f.refresh_url&&!!onRevisit&&canWrite&&f.revisit.ready_for_review&&<Button label="Prepare fresh expedition" disabled={busy||disabled} action={()=>{onRevisit(f.refresh_url!);invalidate();setResult(null);}}/>}
    </View>)}
    {visible.comparison&&<View style={s.check}><Text style={s.heading}>{visible.comparison_selection?'Selected historical observations':'Latest and preceding observation'}</Text><Revision row={visible.comparison.current} inspect={inspect} disabled={passageBusy}/><Revision row={visible.comparison.previous} inspect={inspect} disabled={passageBusy}/></View>}
    <Text style={s.heading}>{mode==='timeline'?'Revision timeline':'Matching indexed revisions'}</Text>
    {(mode==='timeline'?visible.timeline:visible.hits).map(v=><Revision key={v.revision_id} row={v} inspect={inspect} select={selectRevision} watch={!vaultWindow&&terminal&&canWrite&&!session?.treasury_vault&&!session?.watch_managed&&!activeWatch?.enabled&&v.session_id===session?.session_id?pickWatch:undefined} disabled={passageBusy}/>)}
    {passageBusy&&<ActivityIndicator color={colors.accent}/>}
    {passage&&<View style={s.check}>
      <Text style={s.heading}>Exact retained source · {passage.history_only?'history only':'current use permitted'}</Text>
      <Text style={s.small}>Captured {stamp(passage.captured_at)} · characters {passage.offset}–{passage.end} of {passage.total_chars}. Unreviewed; not authorized for model context by this reader.</Text>
      <Text selectable style={s.message}>{passage.text}</Text>
      <Text selectable style={s.small}>Span SHA-256: {passage.span_sha256}</Text>
      <Text selectable style={s.small}>Retained text SHA-256: {passage.preserved_text_hash}</Text>
      <View style={s.row}>
        <Button label="Previous passage" disabled={passageBusy||passage.offset===0} action={()=>void inspect(passage,Math.max(0,passage.offset-1600))}/>
        <Button label="Next passage" disabled={passageBusy||passage.next_offset===null} action={()=>void inspect(passage,passage.next_offset??0)}/>
        <Button label="Close passage" action={()=>setPassage(null)}/>
      </View>
    </View>}
    <View style={s.row}><Button label="Previous page" disabled={busy||visible.page_offset===0} action={()=>void observe(mode,family,visible.page_offset>24?visible.query_scope_digest+':'+(visible.page_offset-24):undefined,pair??undefined)}/><Button label="Next page" disabled={busy||!visible.next_cursor} action={()=>void observe(mode,family,visible.next_cursor??undefined,pair??undefined)}/></View>
    <Text style={s.small}>Page {visible.page_offset/24+1}{visible.next_cursor?' · more results available':''}. Changing evidence invalidates old page cursors.</Text>
    <Text selectable style={s.small}>Index receipt {visible.partition_digest}</Text>
   </>}
  </>}
 </View>;
}
