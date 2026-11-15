import React,{useCallback,useEffect,useRef,useState} from 'react';
import {ActivityIndicator,AppState,Switch,Text,TextInput,TouchableOpacity,View} from 'react-native';
import {getAuthToken} from '../../auth/gameforgeAuth';
import {getDragonVault,retireDragonSession,getCrawl,crawlRequestKey,configureDragonArchive,
 configureLegacyTreasuryArchive,eraseCrawl,type DragonVaultCatalog,type DragonVaultEntry,type CrawlSession} from '../../product/crawlerClient';
import s,{colors} from './CrawlerWorkspace.styles';

type Props={revision:string;session?:CrawlSession|null;canWrite:boolean;disabled:boolean;
 onWindow:(ids?:string[])=>void;onSession?:(s:CrawlSession)=>void;onChanged:()=>void};
const field={backgroundColor:colors.bg,borderWidth:1,borderColor:colors.edge,borderRadius:9,padding:10,color:colors.text};
function Button({label,action,disabled=false}:{label:string;action:()=>void;disabled?:boolean}){
 return <TouchableOpacity accessibilityRole="button" accessibilityState={{disabled}} disabled={disabled}
   style={[s.button,disabled&&s.disabled]} onPress={action}><Text style={s.buttonText}>{label}</Text></TouchableOpacity>;
}
const stamp=(n:number)=>new Date(n*1000).toLocaleString();

export default function DragonVaultPanel({revision,session,canWrite,disabled,onWindow,onSession,onChanged}:Props){
 const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[catalog,setCatalog]=useState<DragonVaultCatalog|null>(null);
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
 const reset=useCallback(()=>{
  invalidate();setCatalog(null);setSelected([]);setHistory([]);setCursor(undefined);setBusy(false);
  setRetention(false);setManaged(null);setRights(false);setEraseText('');operation.current=null;setNotice('');setError('');
 },[invalidate]);
 useEffect(()=>{reset();return invalidate;},[revision,reset,invalidate]);
 useEffect(()=>{
  const sub=AppState.addEventListener('change',state=>{if(state!=='active'){reset();onWindow(undefined);}});
  const tick=setInterval(()=>{if(owner.current!==getAuthToken()){owner.current=getAuthToken();reset();onWindow(undefined);}},1000);
  return()=>{sub.remove();clearInterval(tick);};
 },[reset,onWindow]);
 const valid=(ctrl:AbortController,attempt:number,token:string)=>!ctrl.signal.aborted&&epoch.current===attempt&&getAuthToken()===token;

 async function load(next?:string){
  invalidate();const attempt=epoch.current,token=getAuthToken(),ctrl=new AbortController();
  owner.current=token;pending.current=ctrl;setBusy(true);setCatalog(null);setError('');
  try{
   const result=await getDragonVault(next,ctrl.signal);
   if(!valid(ctrl,attempt,token))return;
   setCatalog(result);setCursor(next);setManaged(null);setRights(false);setEraseText('');setRetention(false);
   timer.current=setTimeout(()=>{if(epoch.current===attempt){setCatalog(null);setSelected([]);setManaged(null);setRights(false);setEraseText('');}},60000);
  }catch(e){if(valid(ctrl,attempt,token))setError(e instanceof Error?e.message:'Vault catalogue unavailable.');}
  finally{if(epoch.current===attempt){pending.current=null;setBusy(false);}}
 }

 async function mutate(action:'retire'|'grant'|'revoke'|'erase',id:string,version:number,legacy=false){
  if(busy||disabled||owner.current!==getAuthToken()||action!=='revoke'&&!canWrite)return;
  if(action==='retire'&&!retention||action==='grant'&&!rights||action==='erase'&&eraseText!=='ERASE')return;
  const n=action==='grant'?Number(days):30;
  if(!Number.isInteger(n)||n<1||n>30){setError('Historical-use duration must be 1–30 days.');return;}
  invalidate();const token=getAuthToken(),attempt=epoch.current,ctrl=new AbortController();pending.current=ctrl;
  setBusy(true);setError('');setNotice('');setCatalog(null);
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
  <Text style={s.small}>Retain up to 128 retired expedition records separately from the 32 active slots. Retirement moves quota classification, not bytes. Historical use still requires its own finite permission. Retired expeditions cannot start watches or resume capture.</Text>
  <Button label={open?'Close cold-custody catalogue':'Open cold-custody catalogue'} disabled={busy||disabled}
   action={()=>{if(open){reset();onWindow(undefined);}else void load();setOpen(!open);}}/>
  {open&&<>
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
      {row.vault&&<Text style={s.small}>Accepted {stamp(row.vault.accepted_at)} · {row.legacy_runtime?'older-runtime witness':'current-runtime witness'}</Text>}
      {row.archive_expires_at!==null&&<Text style={s.small}>Recorded archive grant expires {stamp(row.archive_expires_at)}. Individual source permission is checked at read time.</Text>}
      <Button label={selected.includes(row.session_id)?'Remove from selected history':'Select for historical window'} disabled={busy||disabled||row.integrity_held||row.vault?.state!=='vaulted'||selected.length>=32&&!selected.includes(row.session_id)} action={()=>toggle(row)}/>
      <Button label="Manage retained record" disabled={busy||disabled} action={()=>{setManaged(managed===row.session_id?null:row.session_id);setRetention(false);setRights(false);setEraseText('');}}/>
      {managed===row.session_id&&<>
       {!row.integrity_held&&row.vault&&!row.vault.active_slot_released&&canWrite&&<>
        <View style={s.row}><Switch value={retention} onValueChange={setRetention} accessibilityLabel="Confirm pending retirement retry"/><Text style={[s.small,s.grow]}>Confirm the same cold-custody intent.</Text></View>
        <Button label="Retry retirement" disabled={busy||disabled||!retention} action={()=>void mutate('retire',row.session_id,row.version)}/>
       </>}
       {!row.integrity_held&&row.vault&&<>
        {canWrite&&<><TextInput style={field} value={days} onChangeText={setDays} keyboardType="number-pad" maxLength={2} accessibilityLabel="Vault archive-use days"/>
         <View style={s.row}><Switch value={rights} onValueChange={setRights} accessibilityLabel="Authorize historical source use"/><Text style={[s.small,s.grow]}>I hold rights for this separate historical-use period.</Text></View>
         <Button label="Authorize historical use" disabled={busy||disabled||!rights} action={()=>void mutate('grant',row.session_id,row.version,!!row.legacy_runtime)}/></>}
        <Button label="Revoke historical use" disabled={busy||disabled} action={()=>void mutate('revoke',row.session_id,row.version,!!row.legacy_runtime)}/>
       </>}
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
