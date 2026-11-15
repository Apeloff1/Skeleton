import React,{useCallback,useEffect,useRef,useState} from 'react';
import {ActivityIndicator,AppState,Switch,Text,TextInput,TouchableOpacity,View} from 'react-native';
import {getAuthToken} from '../../auth/gameforgeAuth';
import {getDragonVault,getDragonVaultQuota,getDragonVaultHealth,discoverDragonVault,searchDragonArchiveIndex,promoteDragonDeep,retireDragonSession,restoreDragonVaultPrimary,repairDragonVaultReplica,configureDragonVaultCare,getDragonVaultCareHistory,getDragonVaultRedundancy,getCrawl,crawlRequestKey,configureDragonArchive,
 configureLegacyTreasuryArchive,eraseCrawl,type DragonVaultCatalog,type DragonVaultQuota,type DragonVaultHealth,type DragonVaultDiscovery,type DragonArchiveIndexSearch,type DragonVaultRedundancy,type DragonVaultCareHistory,type DragonVaultEntry,type CrawlSession} from '../../product/crawlerClient';
import s,{colors} from './CrawlerWorkspace.styles';
import {scanArchiveChambers,bestHistoryWindow,type ChamberScan,SCAN_DEADLINE_MS} from './dragonVaultScan';
import DragonDeepArchivePanel from './DragonDeepArchivePanel';

type Props={revision:string;session?:CrawlSession|null;canWrite:boolean;disabled:boolean;
 onWindow:(ids?:string[],query?:string)=>void;onSession?:(s:CrawlSession)=>void;onChanged:()=>void};
const field={backgroundColor:colors.bg,borderWidth:1,borderColor:colors.edge,borderRadius:9,padding:10,color:colors.text};
function Button({label,action,disabled=false}:{label:string;action:()=>void;disabled?:boolean}){
 return <TouchableOpacity accessibilityRole="button" accessibilityState={{disabled}} disabled={disabled}
   style={[s.button,disabled&&s.disabled]} onPress={action}><Text style={s.buttonText}>{label}</Text></TouchableOpacity>;
}
const stamp=(n:number)=>new Date(n*1000).toLocaleString();

export default function DragonVaultPanel({revision,session,canWrite,disabled,onWindow,onSession,onChanged}:Props){
 const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[catalog,setCatalog]=useState<DragonVaultCatalog|null>(null);
 const [quota,setQuota]=useState<DragonVaultQuota|null>(null);
 const [vaultHealth,setVaultHealth]=useState<DragonVaultHealth|null>(null);
 const [redundancy,setRedundancy]=useState<DragonVaultRedundancy|null>(null);
 const [careHistory,setCareHistory]=useState<DragonVaultCareHistory|null>(null);
 const [discoveryQuery,setDiscoveryQuery]=useState('');
 const [discovery,setDiscovery]=useState<DragonVaultDiscovery|null>(null);
 const [discoveryBusy,setDiscoveryBusy]=useState(false);
 const [archiveScan,setArchiveScan]=useState<ChamberScan|null>(null);
 const [indexed,setIndexed]=useState<DragonArchiveIndexSearch|null>(null);
 const [scanProgress,setScanProgress]=useState<{scanned:number;total:number}|null>(null);
 const scanAbort=useRef<AbortController|null>(null),scanEpoch=useRef(0),scanTimer=useRef<ReturnType<typeof setTimeout>|null>(null);
 const [history,setHistory]=useState<string[]>([]),[cursor,setCursor]=useState<string|undefined>();
 const [selected,setSelected]=useState<string[]>([]),[retention,setRetention]=useState(false);
 const [managed,setManaged]=useState<string|null>(null),[rights,setRights]=useState(false),[days,setDays]=useState('30');
 const [eraseText,setEraseText]=useState(''),[notice,setNotice]=useState(''),[error,setError]=useState('');
 const owner=useRef(getAuthToken()),epoch=useRef(0),pending=useRef<AbortController|null>(null);
 const timer=useRef<ReturnType<typeof setTimeout>|null>(null);
 const operation=useRef<{identity:string;key:string}|null>(null);
 const invalidate=useCallback(()=>{
  epoch.current++;pending.current?.abort();pending.current=null;
  if(timer.current!==null)clearTimeout(timer.current);timer.current=null;
 },[]);
 const clearDiscovery=useCallback(()=>{
  scanEpoch.current++;scanAbort.current?.abort();scanAbort.current=null;
  if(scanTimer.current!==null)clearTimeout(scanTimer.current);scanTimer.current=null;
  setDiscovery(null);setArchiveScan(null);setIndexed(null);setScanProgress(null);setDiscoveryBusy(false);
 },[]);
 const reset=useCallback(()=>{
  invalidate();clearDiscovery();setDiscoveryQuery('');setCatalog(null);setQuota(null);setVaultHealth(null);setRedundancy(null);setCareHistory(null);setSelected([]);setHistory([]);setCursor(undefined);setBusy(false);
  setRetention(false);setManaged(null);setRights(false);setEraseText('');operation.current=null;setNotice('');setError('');
 },[invalidate,clearDiscovery]);
 useEffect(()=>{reset();return()=>{invalidate();clearDiscovery();};},[revision,reset,invalidate,clearDiscovery]);
 useEffect(()=>{
  const sub=AppState.addEventListener('change',state=>{if(state!=='active'){reset();onWindow(undefined);}});
  const tick=setInterval(()=>{if(owner.current!==getAuthToken()){owner.current=getAuthToken();reset();onWindow(undefined);}},1000);
  return()=>{sub.remove();clearInterval(tick);};
 },[reset,onWindow]);
 const valid=(ctrl:AbortController,attempt:number,token:string)=>!ctrl.signal.aborted&&epoch.current===attempt&&getAuthToken()===token;

 async function load(next?:string){
  invalidate();const attempt=epoch.current,token=getAuthToken(),ctrl=new AbortController();
  owner.current=token;pending.current=ctrl;setBusy(true);setCatalog(null);setQuota(null);setVaultHealth(null);setRedundancy(null);setCareHistory(null);setError('');
  try{
   const started=performance.now();
   const [result,health,census]=await Promise.allSettled([getDragonVault(next,ctrl.signal),getDragonVaultQuota(ctrl.signal),getDragonVaultHealth(ctrl.signal)]);
   if(!valid(ctrl,attempt,token))return;
   if(result.status==='rejected')throw result.reason;
   if(health.status==='fulfilled')setQuota(health.value);
   const censusTtl=census.status==='fulfilled'?Math.min(60000,1000*(census.value.valid_until-census.value.as_of_unix)-(performance.now()-started)):0;
   if(census.status==='fulfilled'&&censusTtl>0)setVaultHealth(census.value);
   const page=result.value;
   if(!valid(ctrl,attempt,token))return;
   setCatalog(page);setCursor(next);setManaged(null);setRights(false);setEraseText('');setRetention(false);
   timer.current=setTimeout(()=>{if(epoch.current===attempt){setCatalog(null);setQuota(null);setVaultHealth(null);setRedundancy(null);setCareHistory(null);setSelected([]);setManaged(null);setRights(false);setEraseText('');}},censusTtl>0?censusTtl:60000);
  }catch(e){if(valid(ctrl,attempt,token))setError(e instanceof Error?e.message:'Vault catalogue unavailable.');}
  finally{if(epoch.current===attempt){pending.current=null;setBusy(false);}}
 }

 async function scan(cursor?:string){
  if(discoveryBusy||busy||disabled||!discoveryQuery.trim())return;
  clearDiscovery();const token=getAuthToken(),attempt=scanEpoch.current,ctrl=new AbortController(),started=Date.now();
  scanAbort.current=ctrl;setDiscoveryBusy(true);setError('');
  try{
   const result=await discoverDragonVault(discoveryQuery,cursor,ctrl.signal);
   if(ctrl.signal.aborted||attempt!==scanEpoch.current||token!==getAuthToken())return;
   const ttl=result.earliest_expiry===null?60000:Math.min(60000,1000*(result.earliest_expiry-result.as_of_unix)-(Date.now()-started));
   if(ttl<=0){setError('Historical-use permission expired during chamber discovery.');return;}
   setDiscovery(result);
   scanTimer.current=setTimeout(()=>{if(attempt===scanEpoch.current)setDiscovery(null);},ttl);
  }catch(e){if(!ctrl.signal.aborted&&attempt===scanEpoch.current&&token===getAuthToken())setError(e instanceof Error?e.message:'Chamber discovery unavailable.');}
  finally{if(attempt===scanEpoch.current){scanAbort.current=null;setDiscoveryBusy(false);}}
 }
 async function indexedSearch(){
  if(discoveryBusy||busy||disabled||!discoveryQuery.trim())return;
  clearDiscovery();const token=getAuthToken(),attempt=scanEpoch.current,ctrl=new AbortController(),started=performance.now();
  scanAbort.current=ctrl;setDiscoveryBusy(true);setError('');
  try{
   const result=await searchDragonArchiveIndex(discoveryQuery,ctrl.signal);
   if(ctrl.signal.aborted||attempt!==scanEpoch.current||token!==getAuthToken())return;
   const expiry=Math.min(60_000,...result.results.map(x=>1000*(x.valid_until-result.as_of_unix)))-(performance.now()-started);
   if(expiry<=0){setError('Archive index results expired.');return;}
   setIndexed(result);
   scanTimer.current=setTimeout(()=>{if(attempt===scanEpoch.current)setIndexed(null);},expiry);
  }catch(e){if(!ctrl.signal.aborted&&attempt===scanEpoch.current&&token===getAuthToken())setError(e instanceof Error?e.message:'Archive index unavailable.');}
  finally{if(attempt===scanEpoch.current){scanAbort.current=null;setDiscoveryBusy(false);}}
 }
 async function scanAll(){
  if(discoveryBusy||busy||disabled||!discoveryQuery.trim())return;
  clearDiscovery();const token=getAuthToken(),attempt=scanEpoch.current,ctrl=new AbortController();
  scanAbort.current=ctrl;setDiscoveryBusy(true);setError('');
  const active=()=>attempt===scanEpoch.current&&token===getAuthToken()&&!ctrl.signal.aborted;
  const cutoff=setTimeout(()=>ctrl.abort(),SCAN_DEADLINE_MS);
  try{
   const result=await scanArchiveChambers(discoverDragonVault,discoveryQuery,{
    signal:ctrl.signal,ownerCurrent:active,now:()=>performance.now(),
    onProgress:(scanned,total)=>{if(active())setScanProgress({scanned,total});}
   });
   if(!active())return;
   const ttl=result.expiresMonotonic-performance.now();
   if(ttl<=0){setError('Historical-use permission expired. Restart discovery.');return;}
   setArchiveScan(result);
   scanTimer.current=setTimeout(()=>{if(attempt===scanEpoch.current){setArchiveScan(null);setScanProgress(null);}},ttl);
  }catch(e){
   if(attempt===scanEpoch.current&&token===getAuthToken()){
    setArchiveScan(null);setScanProgress(null);
    setError(ctrl.signal.aborted?'Archive scan reached its time limit. Try a bounded discovery batch.':e instanceof Error?e.message:'Archive-wide discovery unavailable.');
   }
  }finally{clearTimeout(cutoff);if(attempt===scanEpoch.current){scanAbort.current=null;setDiscoveryBusy(false);}}
 }
 function openBest(){
  if(!archiveScan||owner.current!==getAuthToken())return;
  try{const ids=bestHistoryWindow(archiveScan,performance.now());if(ids.length)onWindow(ids,discoveryQuery);}
  catch(e){clearDiscovery();setError(e instanceof Error?e.message:'Archive ranking expired.');}
 }
 async function readCareHistory(row:DragonVaultEntry){
  if(busy||disabled||owner.current!==getAuthToken())return;
  const ctrl=new AbortController(),token=getAuthToken(),attempt=epoch.current;
  pending.current=ctrl;setBusy(true);setCareHistory(null);setError('');
  try{
   const result=await getDragonVaultCareHistory(row.session_id,ctrl.signal);
   if(!valid(ctrl,attempt,token))return;
   if(result.version!==row.version){setError('Custody history changed; refresh the catalogue.');setCatalog(null);return;}
   setCareHistory(result);
  }catch(e){if(valid(ctrl,attempt,token))setError(e instanceof Error?e.message:'Custody history unavailable.');}
  finally{if(epoch.current===attempt){pending.current=null;setBusy(false);}}
 }
 async function verifyCopies(row:DragonVaultEntry){
  if(busy||disabled||owner.current!==getAuthToken())return;
  const ctrl=new AbortController(),token=getAuthToken(),attempt=epoch.current;
  pending.current=ctrl;setBusy(true);setRedundancy(null);setCareHistory(null);setError('');
  try{
   const result=await getDragonVaultRedundancy(row.session_id,ctrl.signal);
   if(!valid(ctrl,attempt,token))return;
   if(result.version!==row.version){setError('Retained record changed; refresh the catalogue.');setCatalog(null);return;}
   setRedundancy(result);
  }catch(e){if(valid(ctrl,attempt,token))setError(e instanceof Error?e.message:'Historical copy verification unavailable.');}
  finally{if(epoch.current===attempt){pending.current=null;setBusy(false);}}
 }
 async function mutate(action:'retire'|'deep'|'restore'|'replica'|'care'|'uncare'|'grant'|'revoke'|'erase',id:string,version:number,legacy=false){
  if(busy||disabled||owner.current!==getAuthToken()||action!=='revoke'&&action!=='uncare'&&!canWrite)return;
  if((action==='retire'||action==='deep'||action==='restore'||action==='replica'||action==='care')&&!retention||action==='grant'&&!rights||action==='erase'&&eraseText!=='ERASE')return;
  const n=action==='grant'?Number(days):30;
  if(!Number.isInteger(n)||n<1||n>30){setError('Historical-use duration must be 1–30 days.');return;}
  clearDiscovery();invalidate();const token=getAuthToken(),attempt=epoch.current,ctrl=new AbortController();pending.current=ctrl;
  setBusy(true);setError('');setNotice('');setCatalog(null);setQuota(null);setVaultHealth(null);setRedundancy(null);setCareHistory(null);
  const identity=[action,id,version,n].join(':');
  if(operation.current?.identity!==identity)operation.current={identity,key:crawlRequestKey('vault-'+action)};
  const command={expected_version:version,idempotency_key:operation.current.key};
  try{
   let message='';
   if(action==='retire'){
    const receipt=await retireDragonSession(id,{...command,retention_acknowledged:true},ctrl.signal);
    message=receipt.vault.active_slot_released?'Retired into cold custody. Active slot released.':
      'Retirement recorded; active slot release is not yet confirmed. Recovery will retry.';
    if(session?.session_id===id&&onSession){
     const updated=await getCrawl(id,ctrl.signal);if(!valid(ctrl,attempt,token))return;onSession(updated);
    }
   }else if(action==='deep'){
    const result=await promoteDragonDeep(id,{...command,retention_acknowledged:true},ctrl.signal);
    message=result.archive.released?'Deep custody committed; the working chamber reservation was released.':'Deep custody recorded; reservation release remains pending.';
   }else if(action==='restore'){
    const receipt=await restoreDragonVaultPrimary(id,{...command,retention_acknowledged:true},ctrl.signal);
    message=receipt.outcome==='restored'?'Exact original primary restored. No permission renewed.':'Original primary is intact. No changes made.';
   }else if(action==='replica'){
    const receipt=await repairDragonVaultReplica(id,{...command,retention_acknowledged:true},ctrl.signal);
    message=receipt.outcome==='repaired'?'Exact retained duplicate repaired; original primary and witness unchanged.':'Retained duplicate already intact.';
   }else if(action==='care'||action==='uncare'){
    const result=await configureDragonVaultCare(id,{...command,enabled:action==='care',days:7,repairs:2,
      retention_acknowledged:action==='care'&&retention},ctrl.signal);
    message=result.care.enabled?'Seven-day care grant recorded; at most two exact-copy repairs.':'Automatic custody repair permission withdrawn.';
   }else if(action==='erase'){
    await eraseCrawl(id,command,ctrl.signal);message='Original retained session erased; exported copies remain outside the app.';
   }else{
    const body={...command,enabled:action==='grant',days:n,archive_rights_acknowledged:action==='grant'&&rights};
    if(legacy)await configureLegacyTreasuryArchive(id,body,ctrl.signal);
    else await configureDragonArchive(id,body,ctrl.signal);
    message=action==='grant'?'Separate historical-use permission confirmed.':'Historical-use permission withdrawn.';
   }
   if(!valid(ctrl,attempt,token))return;
   operation.current=null;setRetention(false);setRights(false);setEraseText('');setSelected(ids=>ids.filter(x=>x!==id));
   onWindow(undefined);onChanged();setHistory([]);await load();
   if(token===getAuthToken())setNotice(message);
  }catch(e){if(valid(ctrl,attempt,token))setError(e instanceof Error?e.message:'Vault command unconfirmed. Reload before retrying.');}
  finally{if(epoch.current===attempt){pending.current=null;setBusy(false);}}
 }
 const active=owner.current===getAuthToken()?catalog:null;
 const eligible=session&&!session.consent_current&&['completed','budget_exhausted'].includes(session.status)
  &&!session.worker?.active&&!session.treasury_watch?.enabled&&session.treasury_vault?.state!=='vaulted';
 function toggle(row:DragonVaultEntry){
  if(row.integrity_held||row.vault?.state!=='vaulted')return;
  setSelected(ids=>ids.includes(row.session_id)?ids.filter(x=>x!==row.session_id):ids.length<32?[...ids,row.session_id]:ids);
 }
 return <View style={s.check}>
  <Text style={s.heading}>Hoarder cold-custody chambers</Text>
  <Text style={s.small}>Retain up to 1,024 retired expedition records separately from the 32 active slots. Retirement moves quota classification, not bytes. Historical use still requires its own finite permission. Retired expeditions cannot start watches or resume capture.</Text>
  <Button label={open?'Close cold-custody catalogue':'Open cold-custody catalogue'} disabled={busy||disabled}
   action={()=>{if(open){reset();onWindow(undefined);}else void load();setOpen(!open);}}/>
  {open&&<>
   <DragonDeepArchivePanel revision={revision} canWrite={canWrite} disabled={disabled||busy} onWindow={onWindow} onChanged={onChanged}/>
   {vaultHealth&&owner.current===getAuthToken()&&<View style={s.check}>
    <Text style={s.heading}>Hoarder den health</Text>
    <Text style={s.small}>{vaultHealth.vaulted} retired · {vaultHealth.pending} retiring · {vaultHealth.marker_held} metadata holds</Text>
    <Text style={s.small}>{vaultHealth.redundant} redundant · {vaultHealth.primary_only} primary-only · {vaultHealth.repairable_primary} repairable primary · {vaultHealth.held} both held</Text>
    <Text style={s.small}>{vaultHealth.uninspected} uninspected · {vaultHealth.stale} stale observations · {vaultHealth.due} due for patrol</Text>
    <Text style={s.small}>{vaultHealth.care_active} active care grants · {vaultHealth.remaining_repairs} authorized repairs remaining · {vaultHealth.care_held} care integrity holds</Text>
    <Text style={s.small}>Version-bound prior observations only; no independent backup or live verification is implied.</Text>
   </View>}
   {quota&&owner.current===getAuthToken()&&<View style={s.check}>
    <Text style={s.label}>Den capacity and recovery</Text>
    <Text style={s.small}>{quota.active_reserved}/{quota.active_capacity} active reservations · {quota.vault_reserved}/{quota.vault_capacity} cold-custody reservations</Text>
    <Text style={s.small}>{quota.in_transit} retirement transitions · {quota.dual_reserved} dual reservations · {quota.tombstoned} erased records awaiting cleanup</Text>
    <Text style={s.small}>{quota.missing} unresolved reservations · {quota.integrity_held} integrity holds. Missing records are never automatically reclaimed.</Text>
   </View>}
   <View style={s.check}>
    <Text style={s.label}>Discover matching historical chambers</Text>
    <Text style={s.small}>Scan eight records at a time, or all bounded chambers sequentially. Archive-wide ranking compares chamber coverage, not document relevance or independent corroboration.</Text>
    <TextInput value={discoveryQuery} onChangeText={value=>{clearDiscovery();setDiscoveryQuery(value);}} maxLength={256}
      editable={!busy&&!disabled} style={field} placeholder="Find retained subject or phrase" placeholderTextColor={colors.muted} accessibilityLabel="Historical chamber discovery query"/>
    <View style={s.row}><Button label={discoveryBusy?'Scanning…':'Scan first chambers'} disabled={busy||disabled||discoveryBusy||!discoveryQuery.trim()} action={()=>void scan()}/>
     <Button label="Next discovery batch" disabled={busy||disabled||discoveryBusy||!discovery?.next_cursor} action={()=>void scan(discovery?.next_cursor??undefined)}/></View>
    <Button label="Search automatic archive index" disabled={busy||disabled||discoveryBusy||!discoveryQuery.trim()} action={()=>void indexedSearch()}/>
    {indexed&&owner.current===getAuthToken()&&<View style={s.check}>
     <Text style={s.label}>Indexed historical references</Text>
     <Text style={s.small}>{indexed.candidate_chambers} routed chambers · {indexed.rechecked_chambers} rechecked · {indexed.held_chambers} held. Index is partial; historical rights and exact passages are checked again when opened.</Text>
     {indexed.results.map(hit=><Text key={hit.citation} selectable style={s.small}>{hit.citation} · {hit.score} matching query terms</Text>)}
     <Button label="Open indexed historical window" disabled={busy||disabled||!indexed.results.length} action={()=>onWindow([...new Set(indexed.results.map(hit=>hit.session_id))].sort(),discoveryQuery)}/>
    </View>}
    <View style={s.row}><Button label="Exhaustive scan (up to 128 chambers)" disabled={busy||disabled||discoveryBusy||!discoveryQuery.trim()} action={()=>void scanAll()}/>
     <Button label="Stop discovery" disabled={!discoveryBusy} action={clearDiscovery}/></View>
    {discoveryBusy&&<><ActivityIndicator color={colors.accent}/>{scanProgress&&<Text style={s.small} accessibilityLiveRegion="polite">{scanProgress.scanned}/{scanProgress.total} chambers checked. No partial ranking published.</Text>}</>}
    {archiveScan&&owner.current===getAuthToken()&&<>
      <Text style={s.label}>Archive-wide coverage ranking</Text>
      <Text style={s.small}>{archiveScan.scanned}/{archiveScan.catalogueSize} catalogue positions · {archiveScan.qualified} qualified · {archiveScan.held} integrity holds · {archiveScan.noGrant} without usable grant</Text>
      <Text style={s.small}>{archiveScan.matches.length} matching chambers across {archiveScan.pages} verified batches. Ranking is a transient advisory; held or ungranted records were not searched.</Text>
      <Button label={'Open best '+Math.min(32,archiveScan.matches.length)+' historical chambers'} disabled={busy||disabled||!archiveScan.matches.length} action={openBest}/>
      {archiveScan.matches.slice(0,32).map(row=><View key={row.session_id} style={s.check}>
        <Text selectable style={s.label}>{row.session_id}</Text>
        <Text style={s.small}>{row.matched_terms}/{archiveScan.queryTerms} terms covered · {row.best_source_terms} in best capture · {row.distinct_matching_payloads} distinct matching payloads</Text>
      </View>)}
      {archiveScan.matches.length>32&&<Text style={s.small}>Showing the best 32 chambers; other matches remain outside this detailed reparse window.</Text>}
    </>}
    {discovery&&owner.current===getAuthToken()&&<>
      <Text style={s.small}>{discovery.page_offset+discovery.scanned_sessions}/{discovery.catalogue_size} catalogue positions · {discovery.qualified} qualified · {discovery.no_grant} without usable permission · {discovery.held} held</Text>
      {!discovery.matches.length&&<Text style={s.small}>No qualified lexical match in this batch.</Text>}
      {discovery.matches.map(row=><View key={row.session_id} style={s.check}>
        <Text selectable style={s.label}>{row.session_id}</Text>
        <Text style={s.small}>{row.matched_terms}/{discovery.query_terms} query terms · {row.matched_sources} matching captures · {row.distinct_matching_payloads} distinct matching payloads</Text>
        <Button label={selected.includes(row.session_id)?'Remove matching chamber':'Add matching chamber to selected history'}
         disabled={busy||disabled||selected.length>=32&&!selected.includes(row.session_id)}
         action={()=>setSelected(ids=>ids.includes(row.session_id)?ids.filter(x=>x!==row.session_id):[...ids,row.session_id])}/>
      </View>)}
      <Button label="Open matching chambers for detailed reparse" disabled={busy||disabled||!discovery.matches.length}
        action={()=>onWindow(discovery.matches.map(row=>row.session_id).sort(),discoveryQuery)}/>
    </>}
   </View>
   {eligible&&canWrite&&<View style={s.check}>
    <Text style={s.label}>Retire selected finished expedition · {session.session_id.slice(0,12)}</Text>
    <View style={s.row}><Switch value={retention} onValueChange={setRetention} disabled={busy||disabled}
      accessibilityLabel="Confirm rights to retain original cold custody"/><Text style={[s.small,s.grow]}>I have rights to retain this original captured record in cold custody. This does not extend archive-use permission.</Text></View>
    <Button label="Retire to cold custody" disabled={busy||disabled||!retention} action={()=>void mutate('retire',session.session_id,session.version)}/>
   </View>}
   <View style={s.row}><Button label="Refresh chambers" disabled={busy||disabled} action={()=>{setHistory([]);void load();}}/>
    <Button label={'Search selected history ('+selected.length+'/32)'} disabled={!selected.length||busy||disabled} action={()=>onWindow([...selected].sort())}/>
    <Button label="Clear selection" disabled={busy||disabled} action={()=>{setSelected([]);onWindow(undefined);}}/></View>
   <Text style={s.small}>Select across catalogue pages; each query is a deliberately incomplete historical window.</Text>
   {busy&&<ActivityIndicator color={colors.accent}/>}
   {!!notice&&<Text style={s.small} accessibilityLiveRegion="polite">{notice}</Text>}
   {!!error&&<Text style={s.error} accessibilityLiveRegion="polite">{error}</Text>}
   {active&&<>
    {!active.sessions.length&&<Text style={s.small}>No cold-custody records on this page.</Text>}
    {active.sessions.map(row=><View key={row.session_id} style={s.check}>
      <Text selectable style={s.label}>{row.session_id}</Text>
      <Text style={s.small}>{row.integrity_held?'Held metadata · repair or explicitly erase':row.vault?.state==='pending'?'Retirement pending':row.vault?.active_slot_released?'Retired · active slot released':'Retired · active slot release pending'}</Text>
      {row.vault&&<Text style={s.small}>Accepted {stamp(row.vault.accepted_at)} · {row.legacy_runtime===null?'primary runtime unknown; verify copies':row.legacy_runtime?'older-runtime witness':'current-runtime witness'}</Text>}
      {row.care&&<Text style={s.small}>Care: {row.care.active?'recorded active':'inactive'} · {row.care.remaining}/{row.care.budget} repairs remaining · expires {stamp(row.care.expires_at)}{row.care.last_repair?' · last '+row.care.last_repair.side+' repair '+stamp(row.care.last_repair.at):''}</Text>}
      {row.last_scrub&&<Text style={s.small}>Last integrity patrol: {row.last_scrub.state.replaceAll('_',' ')} · {stamp(row.last_scrub.checked_at)}. Past observation, not live verification.</Text>}
      {row.archive_expires_at!==null&&<Text style={s.small}>Recorded archive grant expires {stamp(row.archive_expires_at)}. Individual source permission is checked at read time.</Text>}
      <Button label={selected.includes(row.session_id)?'Remove from selected history':'Select for historical window'} disabled={busy||disabled||row.integrity_held||row.vault?.state!=='vaulted'||selected.length>=32&&!selected.includes(row.session_id)} action={()=>toggle(row)}/>
      <Button label="Manage retained record" disabled={busy||disabled} action={()=>{setManaged(managed===row.session_id?null:row.session_id);setRedundancy(null);setCareHistory(null);setRetention(false);setRights(false);setEraseText('');}}/>
      {managed===row.session_id&&<>
       {!row.integrity_held&&row.vault&&!row.vault.active_slot_released&&canWrite&&<>
        <View style={s.row}><Switch value={retention} onValueChange={setRetention} accessibilityLabel="Confirm pending retirement retry"/><Text style={[s.small,s.grow]}>Confirm the same cold-custody intent.</Text></View>
        <Button label="Retry retirement" disabled={busy||disabled||!retention} action={()=>void mutate('retire',row.session_id,row.version)}/>
       </>}
       {!row.integrity_held&&row.vault&&row.legacy_runtime!==null&&<>
        {canWrite&&<><TextInput style={field} value={days} onChangeText={setDays} keyboardType="number-pad" maxLength={2} accessibilityLabel="Vault archive-use days"/>
         <View style={s.row}><Switch value={rights} onValueChange={setRights} accessibilityLabel="Authorize historical source use"/><Text style={[s.small,s.grow]}>I hold rights for this separate historical-use period.</Text></View>
         <Button label="Authorize historical use" disabled={busy||disabled||!rights} action={()=>void mutate('grant',row.session_id,row.version,!!row.legacy_runtime)}/></>}
        <Button label="Revoke historical use" disabled={busy||disabled} action={()=>void mutate('revoke',row.session_id,row.version,!!row.legacy_runtime)}/>
       </>}
       {row.vault?.state==='vaulted'&&<>
        <Button label="Verify both retained copies" disabled={busy||disabled} action={()=>void verifyCopies(row)}/>
        {redundancy?.session_id===row.session_id&&redundancy.version===row.version&&<View style={s.check}>
         <Text style={s.label}>{redundancy.state==='redundant'?'Both copies match the witness':redundancy.state==='primary_only'?'Primary intact; duplicate unavailable or held':redundancy.state==='repairable_primary'?'Exact duplicate can restore original primary':'Both copies held'}</Text>
         <Text style={s.small}>Primary {redundancy.primary} · replica {redundancy.replica}. Same-row redundancy, not an independent backup.</Text>
        </View>}
       </>}
       {canWrite&&row.vault?.state==='vaulted'&&<>
        <Text style={s.small}>Check the original primary and repair only from its exact existing witnessed replica. This cannot restore an older revision or renew permission.</Text>
        <View style={s.row}><Switch value={retention} onValueChange={setRetention} disabled={busy||disabled} accessibilityLabel="Confirm rights to restore original retained custody"/><Text style={[s.small,s.grow]}>I have rights to maintain this retained record.</Text></View>
        {row.vault.active_slot_released&&<Button label="Move into partitioned deep archive" disabled={busy||disabled||!retention} action={()=>void mutate('deep',row.session_id,row.version)}/>}
        <Button label="Verify or repair original primary" disabled={busy||disabled||!retention} action={()=>void mutate('restore',row.session_id,row.version)}/>
        <Button label="Verify or repair retained duplicate" disabled={busy||disabled||!retention} action={()=>void mutate('replica',row.session_id,row.version)}/>
        <Text style={s.small}>Optional care grant: seven days, at most two repairs, only from a surviving exact copy. No crawling, source-use permission or independent backup.</Text>
        <Button label="Authorize seven-day automatic care" disabled={busy||disabled||!retention} action={()=>void mutate('care',row.session_id,row.version)}/>
       </>}
       {row.vault?.state==='vaulted'&&<>
        <Button label="Inspect retained maintenance history" disabled={busy||disabled} action={()=>void readCareHistory(row)}/>
        {careHistory?.session_id===row.session_id&&careHistory.version===row.version&&<View style={s.check}>
         <Text style={s.label}>Care history · {careHistory.state}</Text>
         {careHistory.prefix_unknown&&<Text style={s.small}>Earlier history is unknown; no prior repair is inferred.</Text>}
         {careHistory.omitted>0&&<Text style={s.small}>{careHistory.omitted} older receipts omitted.</Text>}
         {careHistory.events.map(event=><Text key={event.sequence} style={s.small}>{stamp(event.at)} · {event.kind.replaceAll('_',' ')} · version {event.version} · {event.used}/{event.budget} repairs consumed</Text>)}
         <Text style={s.small}>Retained internal receipts only, not independent audit or source-use authority.</Text>
        </View>}
       </>}
       {row.vault?.state==='vaulted'&&<Button label="Withdraw automatic care permission" disabled={busy||disabled} action={()=>void mutate('uncare',row.session_id,row.version)}/>}
       {canWrite&&<><Text style={s.small}>Permanent owner erasure removes the original record, its indexes and both quota IDs. Type ERASE to confirm.</Text>
        <TextInput style={field} value={eraseText} onChangeText={setEraseText} autoCapitalize="characters" maxLength={5} accessibilityLabel="Type ERASE to confirm permanent deletion"/>
        <Button label="Erase this retained expedition" disabled={busy||disabled||eraseText!=='ERASE'} action={()=>void mutate('erase',row.session_id,row.version)}/></>}
      </>}
    </View>)}
    <View style={s.row}><Button label="Previous chamber" disabled={busy||!history.length||disabled} action={()=>{const previous=history[history.length-1];setHistory(v=>v.slice(0,-1));void load(previous||undefined);}}/>
     <Button label="Next chamber" disabled={busy||!active.next_cursor||disabled} action={()=>{setHistory(v=>[...v,cursor||'']);void load(active.next_cursor??undefined);}}/></View>
   </>}
  </>}
 </View>;
}
