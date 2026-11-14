import {useCallback,useEffect,useRef,useState} from 'react';
import {AppState} from 'react-native';
import * as Crypto from 'expo-crypto';
import api from '../../../src/utils/apiClient';
import {authHeaders,getAuthToken} from '../../../src/auth/gameforgeAuth';
import {type DeliveryDesign,type DeliveryBrief,type DeliveryCitation,type DeliveryOverview,type DeliveryAlmanac,type DeliveryLearning,
 normalizeDeliveryBrief,normalizeDeliveryCitations,normalizeDeliveryOverview,normalizeDeliveryAlmanacs,normalizeDeliveryLearning} from './dragonDelivery';
const PATH='/api/dragon-academy/delivery';
export function useDragonDelivery(onGenerated?:()=>void){
 const [overview,setOverview]=useState<DeliveryOverview|null>(null);
 const [citations,setCitations]=useState<DeliveryCitation[]>([]);
 const [almanacs,setAlmanacs]=useState<DeliveryAlmanac[]>([]);
 const [findings,setFindings]=useState<DeliveryLearning[]>([]);
 const [recoveryAttempt,setRecoveryAttempt]=useState<string|null>(null);
 const [offset,setOffset]=useState(0);const [total,setTotal]=useState(0);
 const [brief,setBrief]=useState<DeliveryBrief|null>(null);
 const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [notice,setNotice]=useState('');
 const live=useRef(true);const pending=useRef(false);const epoch=useRef(0);
 const requestKey=useRef('');const session=useRef(getAuthToken());
 const invalidate=useCallback(()=>{epoch.current++;setBrief(null);requestKey.current='';setNotice('');},[]);
 const clear=useCallback(()=>{invalidate();setOverview(null);setCitations([]);setAlmanacs([]);setFindings([]);setRecoveryAttempt(null);setOffset(0);setTotal(0);},[invalidate]);
 const perform=useCallback(async<T,>(work:(token:string,version:number)=>Promise<T>)=>{
  const token=getAuthToken();
  if(!token){clear();setError('Sign in to use the knowledge workbench.');return;}
  if(pending.current)return;
  if(session.current!==token){clear();session.current=token;}
  pending.current=true;setBusy(true);setError('');const version=epoch.current;
  try{return await work(token,version);}catch(e){if(live.current&&getAuthToken()===token)setError(e instanceof Error?e.message:'Workbench unavailable.');}
  finally{pending.current=false;if(live.current)setBusy(false);}
 },[clear]);
 const valid=(token:string,version:number)=>live.current&&getAuthToken()===token&&epoch.current===version;
 const read=async(path:string)=>{
  const result=await api.get<Record<string,unknown>>(PATH+path,{headers:authHeaders(),timeoutMs:12000,retries:0});
  if(!result.ok||result.data?.ok!==true)throw new Error(result.status===503?'Knowledge storage or runtime is not configured.':'Current knowledge could not be verified.');
  return result.data;
 };
 const refresh=useCallback(()=>perform(async(token,version)=>{
  const data=await read('/overview');const projection=normalizeDeliveryOverview(data);
  if(!projection)throw new Error('Invalid delivery overview.');
  if(valid(token,version))setOverview(projection);
 }),[perform]);
 const search=useCallback((query:string)=>perform(async(token,version)=>{
  const data=await read('/knowledge?query='+encodeURIComponent(query));const rows=normalizeDeliveryCitations(data.items);
  if(!rows||data.training_authorized!==false||data.release_authorized!==false)throw new Error('Invalid cited knowledge result.');
  if(valid(token,version))setCitations(rows);
 }),[perform]);
 const browse=useCallback((page:number)=>perform(async(token,version)=>{
  const data=await read('/almanacs?offset='+page);const rows=normalizeDeliveryAlmanacs(data.almanacs);
  if(!rows||typeof data.total_almanacs!=='number'||!Number.isSafeInteger(data.total_almanacs)||data.total_almanacs<0)throw new Error('Invalid Almanakk index.');
  if(valid(token,version)){setAlmanacs(rows);setOffset(page);setTotal(data.total_almanacs);}
 }),[perform]);
 const inspectLearning=useCallback((topic:string)=>perform(async(token,version)=>{
  const data=await read('/almanacs/'+encodeURIComponent(topic)+'/learning');
  const rows=normalizeDeliveryLearning(data.findings);
  if(!rows)throw new Error('Invalid project learning lineage.');
  if(valid(token,version))setFindings(rows);
 }),[perform]);
 const recoverLearning=useCallback(()=>{
  if(!recoveryAttempt)return;
  return perform(async(token,version)=>{
   const result=await api.post<Record<string,unknown>>(PATH+'/'+recoveryAttempt+'/learning',{},
    {headers:authHeaders(),timeoutMs:12000,retries:0});
   if(!result.ok||result.data?.ok!==true||result.data.new_source_generated!==false)throw new Error('Learning could not be reconciled. The native artifact remains available.');
   if(valid(token,version)){setRecoveryAttempt(null);setNotice('Project synthesis restored to its Almanakk without regenerating the game.');}
  });
 },[perform,recoveryAttempt]);
 const prepare=useCallback((design:DeliveryDesign,query:string)=>{
  invalidate();return perform(async(token,version)=>{
   const result=await api.post<Record<string,unknown>>(PATH+'/brief',{design,query},{headers:authHeaders(),timeoutMs:15000,retries:0});
   if(!result.ok||result.data?.ok!==true)throw new Error(result.status===422?'These design controls are not supported by the target.':'Could not prepare a current knowledge brief.');
   const next=normalizeDeliveryBrief(result.data,Date.now()/1000);
   if(!next)throw new Error('Knowledge brief is malformed or expired.');
   if(valid(token,version)){setBrief(next);requestKey.current=Crypto.randomUUID();}
  });
 },[perform,invalidate]);
 const generate=useCallback(()=>{
  if(!brief?.ready_for_source_generation||brief.expires_at<=Date.now()/1000)return;
  const captured=brief;
  return perform(async(token,version)=>{
   const result=await api.post<Record<string,unknown>>(PATH+'/generate',{
    design:captured.design,query:captured.query,plan_digest:captured.plan_digest,
    prepared_at:captured.prepared_at,request_id:requestKey.current,approved:true,
   },{headers:authHeaders(),timeoutMs:25000,retries:0});
   if(!result.ok||result.data?.ok!==true){
    if(result.status===409&&valid(token,version))invalidate();
    throw new Error(result.status===503?'Generation needs the shared resource runtime.':result.status===403?'A current approved practice lesson is required.':result.status===409?'The brief or practice budget changed. Prepare it again.':'Generation did not confirm a result. Retry the same request safely.');
   }
   if(!valid(token,version))return;
   if(result.data.delivery_state==='deferred'){
    setNotice('Resources are busy. Nothing was generated; retry this same brief.');return;
   }
   const attempt=result.data.created_native;
   if(result.data.delivery_state!=='source_generated'||result.data.plan_digest!==captured.plan_digest||
      result.data.compiled!==false||result.data.gameplay_verified!==false||!attempt||typeof attempt!=='object'||
      !('attempt_id'in attempt)||typeof attempt.attempt_id!=='string'||!/^[a-f0-9]{64}$/.test(attempt.attempt_id))throw new Error('Invalid project delivery receipt.');
   setRecoveryAttempt(result.data.learning_recovery_required===true?attempt.attempt_id:null);
   setNotice(result.data.learning_recovery_required===true?'Native source was saved. Its Almanakk projection needs recovery; use the recovery action below.':'Native source and project synthesis recorded. Download from Generated native projects below, then compile and playtest.');
   setBrief(null);requestKey.current='';onGenerated?.();
  });
 },[brief,perform,invalidate,onGenerated]);
 useEffect(()=>{
  live.current=true;void refresh();
  const listener=AppState.addEventListener('change',state=>{
   if(state==='active'&&session.current!==getAuthToken()){clear();session.current=getAuthToken();void refresh();}
  });
  const timer=setInterval(()=>{if(session.current!==getAuthToken()){clear();session.current=getAuthToken();}},1000);
  return()=>{live.current=false;listener.remove();clearInterval(timer);};
 },[clear,refresh]);
 useEffect(()=>{
  if(!brief)return;
  const timer=setTimeout(()=>{invalidate();setNotice('The brief expired. Prepare it again to use current evidence.');},Math.max(0,brief.expires_at*1000-Date.now()));
  return()=>clearTimeout(timer);
 },[brief,invalidate]);
 return{overview,citations,almanacs,findings,recoveryAttempt,offset,total,brief,busy,error,notice,refresh,search,browse,inspectLearning,recoverLearning,prepare,generate,invalidate};
}
