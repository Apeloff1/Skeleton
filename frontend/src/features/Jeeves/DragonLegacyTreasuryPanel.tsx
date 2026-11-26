import React,{useCallback,useEffect,useRef,useState} from 'react';
import {ActivityIndicator,AppState,Switch,Text,TextInput,TouchableOpacity,View} from 'react-native';
import {getAuthToken} from '../../auth/gameforgeAuth';
import {getLegacyTreasuryCatalog,configureLegacyTreasuryArchive,retireDragonSession,crawlRequestKey,type DragonLegacyCandidate,type DragonLegacyCatalog} from '../../product/crawlerClient';
import s,{colors} from './CrawlerWorkspace.styles';

function Button({title,onPress,disabled=false}:{title:string;onPress:()=>void;disabled?:boolean}){
 return <TouchableOpacity accessibilityRole="button" accessibilityState={{disabled}} disabled={disabled} style={[s.button,disabled&&s.disabled]} onPress={onPress}><Text style={s.buttonText}>{title}</Text></TouchableOpacity>;
}

/** Historical checkpoints cannot be resumed. This UI never sends their bytes
 * to the execution API; it only requests explicit archive-only admission. */
export default function DragonLegacyTreasuryPanel({revision,canWrite,disabled,onChanged}:{revision:string;canWrite:boolean;disabled:boolean;onChanged:()=>void}){
 const [catalog,setCatalog]=useState<DragonLegacyCatalog|null>(null);
 const [open,setOpen]=useState(false),[busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [selected,setSelected]=useState<string|null>(null),[days,setDays]=useState('30'),[rights,setRights]=useState(false);
 const [retireId,setRetireId]=useState<string|null>(null),[retention,setRetention]=useState(false);
 const [notice,setNotice]=useState('');
 const pending=useRef<AbortController|null>(null),timer=useRef<ReturnType<typeof setTimeout>|null>(null);
 const epoch=useRef(0),owner=useRef(getAuthToken()),operation=useRef<{identity:string;key:string}|null>(null);
 const invalidate=useCallback(()=>{
  epoch.current++;pending.current?.abort();pending.current=null;
  if(timer.current!==null)clearTimeout(timer.current);timer.current=null;
 },[]);
 const reset=useCallback(()=>{
  invalidate();setCatalog(null);setBusy(false);setSelected(null);setRights(false);setRetireId(null);setRetention(false);operation.current=null;setError('');setNotice('');
 },[invalidate]);
 useEffect(()=>{reset();return invalidate;},[revision,reset,invalidate]);
 useEffect(()=>{
  const sub=AppState.addEventListener('change',state=>{if(state!=='active')reset();});
  const interval=setInterval(()=>{if(owner.current!==getAuthToken()){owner.current=getAuthToken();reset();}},1000);
  return()=>{sub.remove();clearInterval(interval);};
 },[reset]);
 async function load(){
  invalidate();const token=getAuthToken(),attempt=epoch.current,ctrl=new AbortController();
  owner.current=token;pending.current=ctrl;setBusy(true);setCatalog(null);setError('');
  try{
   const value=await getLegacyTreasuryCatalog(ctrl.signal);
   if(ctrl.signal.aborted||epoch.current!==attempt||getAuthToken()!==token)return;
   setCatalog(value);
   timer.current=setTimeout(()=>{if(epoch.current===attempt){setCatalog(null);setRights(false);setSelected(null);}},60000);
  }catch(e){if(!ctrl.signal.aborted&&epoch.current===attempt&&getAuthToken()===token)setError(e instanceof Error?e.message:'Historical catalogue unavailable.');}
  finally{if(epoch.current===attempt){pending.current=null;setBusy(false);}}
 }
 async function grant(row:DragonLegacyCandidate,enabled:boolean){
  if(busy||disabled||owner.current!==getAuthToken()||enabled&&(!canWrite||!row.qualified||row.eligible_sources===0||!rights||selected!==row.session_id))return;
  const n=enabled?Number(days):30;
  if(!Number.isInteger(n)||n<1||n>30){setError('Choose 1–30 retention days.');return;}
  invalidate();const token=getAuthToken(),attempt=epoch.current,ctrl=new AbortController();
  pending.current=ctrl;setBusy(true);setError('');setCatalog(null);
  const identity=[row.session_id,row.version,enabled,n].join(':');
  if(operation.current?.identity!==identity)operation.current={identity,key:crawlRequestKey('legacy-history')};
  try{
   await configureLegacyTreasuryArchive(row.session_id,{expected_version:row.version,idempotency_key:operation.current.key,
       enabled,days:n,archive_rights_acknowledged:enabled&&rights},ctrl.signal);
   if(ctrl.signal.aborted||epoch.current!==attempt||getAuthToken()!==token)return;
   operation.current=null;setRights(false);setSelected(null);onChanged();await load();
  }catch(e){if(!ctrl.signal.aborted&&epoch.current===attempt&&getAuthToken()===token)setError(e instanceof Error?e.message:'Archive permission command unconfirmed. Reload before retrying.');}
  finally{if(epoch.current===attempt){pending.current=null;setBusy(false);}}
 }
 async function retire(row:DragonLegacyCandidate){
  if(busy||disabled||!canWrite||!row.qualified||retireId!==row.session_id||!retention||owner.current!==getAuthToken())return;
  invalidate();const token=getAuthToken(),attempt=epoch.current,ctrl=new AbortController();
  pending.current=ctrl;setBusy(true);setError('');setNotice('');setCatalog(null);
  const identity=['retire',row.session_id,row.version].join(':');
  if(operation.current?.identity!==identity)operation.current={identity,key:crawlRequestKey('legacy-retire')};
  try{
   const receipt=await retireDragonSession(row.session_id,{expected_version:row.version,idempotency_key:operation.current.key,retention_acknowledged:true},ctrl.signal);
   if(ctrl.signal.aborted||epoch.current!==attempt||token!==getAuthToken())return;
   operation.current=null;setRetention(false);setRetireId(null);onChanged();await load();
   setNotice(receipt.vault.active_slot_released?'Historical record retired into cold custody.':'Retirement intent recorded; slot release pending.');
  }catch(e){if(!ctrl.signal.aborted&&epoch.current===attempt&&token===getAuthToken())setError(e instanceof Error?e.message:'Retirement command unconfirmed.');}
  finally{if(epoch.current===attempt){pending.current=null;setBusy(false);}}
 }
 const value=owner.current===getAuthToken()?catalog:null;
 return <View style={s.check}>
  <Text style={s.heading}>Historical relic recovery</Text>
  <Text style={s.small}>Recover previously witnessed terminal checkpoints into the vault without executing old code, renewing crawl permission, or modifying captured bytes.</Text>
  <Button title={open?'Close historical catalogue':'Open historical catalogue'} disabled={busy||disabled} onPress={()=>{if(open)reset();setOpen(!open);}}/>
  {open&&<>
   <Button title={busy?'Inspecting witnessed checkpoints…':'Inspect historical catalogue'} disabled={busy||disabled} onPress={()=>void load()}/>
   {busy&&<ActivityIndicator color={colors.accent}/>}
   {!!notice&&<Text style={s.small} accessibilityLiveRegion="polite">{notice}</Text>}
   {!!error&&<Text style={s.error} accessibilityLiveRegion="polite">{error}</Text>}
   {value&&<>
    <Text style={s.small}>{value.sessions.length} historical candidates{value.capacity_reached?' · bounded scan':''}. Execution remains disabled.</Text>
    {value.sessions.map(row=><View key={row.session_id} style={s.check}>
     <Text selectable style={s.label}>{row.session_id}</Text>
     <Text style={s.small}>{row.qualified?row.eligible_sources+' eligible preserved sources':'Held · exact historical verification failed'}</Text>
     {row.historical_runtime_digest&&<Text selectable style={s.small}>Historical runtime {row.historical_runtime_digest}</Text>}
     {row.snapshot_digest&&<Text selectable style={s.small}>Original checkpoint {row.snapshot_digest}</Text>}
     {row.archive_grant?.active&&<Text style={s.small}>History-only permission through {new Date(row.archive_grant.expires_at!*1000).toLocaleString()} · {row.archive_grant.usable_sources} sources</Text>}
     {canWrite&&row.qualified&&row.eligible_sources>0&&<>
      <Button title={selected===row.session_id?'Cancel historical permission selection':'Select checkpoint for historical use'} disabled={busy||disabled} onPress={()=>{setSelected(selected===row.session_id?null:row.session_id);setRights(false);}}/>
      {selected===row.session_id&&<>
       <TextInput value={days} onChangeText={setDays} keyboardType="number-pad" maxLength={2} editable={!busy&&!disabled} accessibilityLabel="Historical relic retention days"
        style={{backgroundColor:colors.bg,color:colors.text,borderColor:colors.edge,borderWidth:1,borderRadius:8,padding:10}}/>
       <View style={s.row}><Switch value={rights} onValueChange={setRights} disabled={busy||disabled} accessibilityLabel="Authorize historical relic retention rights"/><Text style={[s.small,s.grow]}>I have rights to retain and reparse these exact older captures. No execution, new fetch, or model-context rights are granted.</Text></View>
       <Button title="Authorize archive-only migration" disabled={!rights||busy||disabled} onPress={()=>void grant(row,true)}/>
      </>}
     </>}
     <Button title="Revoke historical use" disabled={busy||disabled} onPress={()=>void grant(row,false)}/>
     {canWrite&&row.qualified&&<>
      <Button title="Move older record into cold custody" disabled={busy||disabled} onPress={()=>{setRetireId(retireId===row.session_id?null:row.session_id);setRetention(false);}}/>
      {retireId===row.session_id&&<>
       <Text style={s.small}>The server requires expired acquisition consent, no live watch or worker, and a witnessed terminal checkpoint.</Text>
       <View style={s.row}><Switch value={retention} onValueChange={setRetention} disabled={busy||disabled} accessibilityLabel="Confirm retained historical record custody"/><Text style={[s.small,s.grow]}>I have rights to retain this original historical record. This does not renew permission to use its text.</Text></View>
       <Button title="Confirm cold-custody retirement" disabled={!retention||busy||disabled} onPress={()=>void retire(row)}/>
      </>}
     </>}
    </View>)}
   </>}
  </>}
 </View>;
}
