/** Authenticated read-and-command adapter for Dragon Academy.
 * The server, not this hook, owns lesson reviews, XP, attempts and consent.
 * No owner ID is sent by the client. Signed-in account is mandatory even on
 * development deployments where some other routes allow anonymous access.
 */
import {AppState} from 'react-native';
import {useCallback,useEffect,useRef,useState} from 'react';
import * as Crypto from 'expo-crypto';
import api from '../../../src/utils/apiClient';
import {authHeaders,checkMe,getAuthToken} from '../../../src/auth/gameforgeAuth';
import {
 type DragonPracticeAttempt,type DragonPracticeProgress,type DragonPracticeSubscription,
 normalizeDragonAttempts,validateDragonProgress,
} from './dragonProgression';
import type {CompanionAcademyInput,CompanionTelemetry} from './DragonCompanionPanel';
import {EMPTY_COMPANION_JOURNAL,reduceDragonJournal,type CompanionJournal,type WireDragonEvent} from './dragonJournal';

type Snapshot={
 ok:boolean;progress:DragonPracticeProgress;attempts:DragonPracticeAttempt[];
 subscription:DragonPracticeSubscription;
};
type HtmlArtifact={ok:boolean;html:string;sha256:string;sandbox_required:boolean;attempt_id:string};
type CrawlFeed={ok:boolean;session_id:string|null;active:boolean;events:WireDragonEvent[];next_cursor:string|null;has_more:boolean};
export interface DemoView{attemptId:string;html:string;digest:string}
const PATH='/api/dragon-academy';
const HEX=/^[a-f0-9]{64}$/;
const subscriptionValid=(v:unknown):v is DragonPracticeSubscription=>{
 if(!v||typeof v!=='object')return false;
 const p=v as DragonPracticeSubscription;
 return typeof p.enabled==='boolean'&&Number.isFinite(p.expires_at)
  &&Number.isFinite(p.next_due)&&Number.isSafeInteger(p.interval_seconds)
  &&Number.isSafeInteger(p.remaining_ticks)&&p.remaining_ticks>=0
  &&Number.isSafeInteger(p.demos_per_tick)&&p.demos_per_tick>=0;
};
export function useDragonAcademy(){
 const [authenticated,setAuthenticated]=useState(false);
 const [progress,setProgress]=useState<DragonPracticeProgress|null>(null);
 const [attempts,setAttempts]=useState<DragonPracticeAttempt[]>([]);
 const [subscription,setSubscription]=useState<DragonPracticeSubscription|null>(null);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [demo,setDemo]=useState<DemoView|null>(null);
 const [telemetry,setTelemetry]=useState<CompanionTelemetry|undefined>();
 const journal=useRef<CompanionJournal>(EMPTY_COMPANION_JOURNAL);
 const sessionRef=useRef<string|null>(null);
 const feedBusy=useRef(false);
 const alive=useRef(true);
 const inFlight=useRef(false);
 const load=useCallback(async()=>{
  try{
   const me=await checkMe();
   if(!alive.current)return;
   if(!me.authenticated||!getAuthToken()){
    setAuthenticated(false);setProgress(null);setAttempts([]);setSubscription(null);
    setTelemetry(undefined);sessionRef.current=null;journal.current=EMPTY_COMPANION_JOURNAL;
    setError('Sign in through Studio to connect Dragon Academy.');
    return;
   }
   const response=await api.get<Snapshot>(PATH+'/status',
    {headers:authHeaders(),timeoutMs:12000,retries:0});
   if(!alive.current)return;
   if(!response.ok||!response.data?.ok)throw new Error(
    response.status===503?'Dragon practice storage is not configured.':
    response.status===401?'Sign in again to load your Dragon Academy.':
    'Dragon Academy is currently unavailable.');
   const snapshot=response.data;
   const valid=validateDragonProgress(snapshot.progress);
   if(!valid||!subscriptionValid(snapshot.subscription))throw new Error(
    'Dragon Academy returned an invalid verified progression snapshot.');
   setProgress(valid);setAttempts(normalizeDragonAttempts(snapshot.attempts));
   setSubscription(snapshot.subscription);setAuthenticated(true);setError('');
  }catch(e){
   if(alive.current){setAuthenticated(false);setProgress(null);
    setAttempts([]);setSubscription(null);
    setError(e instanceof Error?e.message:'Could not connect to Dragon Academy.');}
  }
 },[]);
 const pollCrawler=useCallback(async()=>{
  if(feedBusy.current||!getAuthToken()||!['active','unknown'].includes(AppState.currentState))return;
  feedBusy.current=true;
  try{
   const r=await api.get<CrawlFeed>(
    PATH+'/crawler/feed?after_sequence='+journal.current.lastSequence+'&limit=100',
    {headers:authHeaders(),timeoutMs:8000,retries:0});
   if(!alive.current||!r.ok||!r.data?.ok)return;
   const f=r.data;
   if(!f.active||!f.session_id){
    sessionRef.current=null;journal.current=EMPTY_COMPANION_JOURNAL;
    setTelemetry(undefined);return;
   }
   if(sessionRef.current!==f.session_id){
    sessionRef.current=f.session_id;
    journal.current=EMPTY_COMPANION_JOURNAL;
    // Another session started. Begin at event 1; never splice two sessions.
    return;
   }
   if(!Array.isArray(f.events)||f.events.length>100)return;
   let next=journal.current;
   for(const event of f.events){
    const updated=reduceDragonJournal(next,event);
    if(updated.warnings.length>next.warnings.length)return;
    next=updated;
   }
   journal.current=next;
   const last=f.events.at(-1);
   if(last)setTelemetry({
    kind:last.kind,payload:last.payload,knowledgeItems:next.indexed,
   });
  }catch{
   // The visual feed must never fabricate fallback events on network failure.
  }finally{feedBusy.current=false;}
 },[]);
 useEffect(()=>{
  alive.current=true;
  void load().then(pollCrawler);
  const interval=setInterval(()=>void pollCrawler(),12000);
  const listener=AppState.addEventListener('change',next=>{
   if(next==='active')void load().then(pollCrawler);
  });
  return()=>{alive.current=false;clearInterval(interval);listener.remove();};
 },[load,pollCrawler]);
 const mutate=useCallback(async(endpoint:string,body:object={})=>{
  if(inFlight.current||!authenticated||!getAuthToken())return;
  inFlight.current=true;setBusy(true);setError('');
  try{
   const r=await api.post<Snapshot>(PATH+endpoint,body,
    {headers:authHeaders(),timeoutMs:18000,retries:0});
   if(!r.ok||!r.data?.ok)throw new Error(
    r.status===503?'Practice database unavailable.':
    r.status===403?'Practice needs current approval.':
    'Unable to perform that practice action.');
   const p=validateDragonProgress(r.data.progress);
   if(!p||!subscriptionValid(r.data.subscription))throw new Error('Invalid practice result.');
   if(alive.current){setProgress(p);setAttempts(normalizeDragonAttempts(r.data.attempts));
    setSubscription(r.data.subscription);}
  }catch(e){
   if(alive.current)setError(e instanceof Error?e.message:'Practice command failed.');
  }finally{
   inFlight.current=false;if(alive.current)setBusy(false);
  }
 },[authenticated]);
 const run=useCallback(()=>{void mutate('/practice/run',{max_demos:2});},[mutate]);
 const subscribe=useCallback(()=>{void mutate('/practice/subscribe',{
  hours:24,interval_seconds:3600,max_ticks:24,demos_per_tick:2,approved:true,
 });},[mutate]);
 const stop=useCallback(()=>{void mutate('/practice/stop');},[mutate]);
 const openDemo=useCallback(async(attemptId:string)=>{
  const attempt=attempts.find(a=>a.attempt_id===attemptId&&
   (a.state==='built'||a.state==='reviewed')&&HEX.test(a.artifact_digest));
  if(!attempt||!authenticated||!getAuthToken())return;
  if(inFlight.current)return;
  inFlight.current=true;setBusy(true);setError('');
  try{
   const result=await api.get<HtmlArtifact>(
    PATH+'/practice/'+encodeURIComponent(attemptId)+'/artifact',
    {headers:authHeaders(),timeoutMs:14000,retries:0});
   const item=result.data;
   if(!result.ok||!item?.ok||!item.sandbox_required||
    item.attempt_id!==attemptId||typeof item.html!=='string'||
    item.html.length>160000||!item.html.startsWith('<!doctype html>')||
    item.sha256!==attempt.artifact_digest||!HEX.test(item.sha256)){
    throw new Error('Demo artifact is unavailable or invalid.');
   }
   const computed=await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256,item.html);
   if(computed!==item.sha256)throw new Error('Demo integrity mismatch. Refusing to play.');
   if(alive.current)setDemo({attemptId,html:item.html,digest:computed});
  }catch(e){
   if(alive.current)setError(e instanceof Error?e.message:'Demo failed to open.');
  }finally{
   inFlight.current=false;if(alive.current)setBusy(false);
  }
 },[attempts,authenticated]);
 const closeDemo=useCallback(()=>setDemo(null),[]);
 const view:CompanionAcademyInput={
  progress,attempts,subscription,practiceBusy:busy,
  onRunPractice:authenticated?run:undefined,
  onStartPractice:authenticated?subscribe:undefined,
  onStopPractice:authenticated?stop:undefined,
  onOpenDemo:authenticated?openDemo:undefined,
 };
 return{view,error,demo,telemetry,closeDemo,refresh:load,authenticated};
}
