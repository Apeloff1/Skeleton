/** Authenticated read-and-command adapter for Dragon Academy.
 * The server, not this hook, owns lesson reviews, XP, attempts and consent.
 * No owner ID is sent by the client. Signed-in account is mandatory even on
 * development deployments where some other routes allow anonymous access.
 */
import {AppState,Platform} from 'react-native';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import {API_BASE} from '../../../utils/apiBase';
import {useCallback,useEffect,useRef,useState} from 'react';
import * as Crypto from 'expo-crypto';
import api from '../../../src/utils/apiClient';
import {authHeaders,checkMe,getAuthToken} from '../../../src/auth/gameforgeAuth';
import {
 type DragonPracticeAttempt,type DragonPracticeProgress,type DragonPracticeSubscription,
 normalizeDragonAttempts,validateDragonProgress,
} from './dragonProgression';
import {normalizeDragonWisdomReview,type DragonWisdomReview} from './dragonWisdomReview';
import type {CompanionAcademyInput,CompanionTelemetry} from './DragonCompanionPanel';
import {type NativeAttempt,type NativeTarget,type NativeCurriculum,normalizeNativeAttempts,normalizeNativeTargets,normalizeNativeCurriculum} from './dragonNativeTargets';
import {EMPTY_COMPANION_JOURNAL,reduceDragonJournal,type CompanionJournal,type WireDragonEvent} from './dragonJournal';

type Snapshot={
 ok:boolean;progress:DragonPracticeProgress;attempts:DragonPracticeAttempt[];
 subscription:DragonPracticeSubscription;native_attempts?:NativeAttempt[];
 curriculum?:NativeCurriculum;wisdom_review?:unknown;
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
 const [nativeAttempts,setNativeAttempts]=useState<NativeAttempt[]>([]);
 const [nativeTargets,setNativeTargets]=useState<NativeTarget[]>([]);
 const [nativeStyles,setNativeStyles]=useState<string[]>([]);
 const [wisdomReview,setWisdomReview]=useState<DragonWisdomReview|null>(null);
 const [wisdomExpires,setWisdomExpires]=useState(0);
 const [curriculum,setCurriculum]=useState<NativeCurriculum|null>(null);
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
    setAuthenticated(false);setProgress(null);setWisdomReview(null);setAttempts([]);setNativeAttempts([]);setNativeTargets([]);setCurriculum(null);setSubscription(null);
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
   const wisdom=snapshot.wisdom_review as {review?:unknown;issued_at?:unknown;expires_at?:unknown}|null;
   const currentTime=Date.now()/1000;
   const validWisdom=wisdom&&typeof wisdom.issued_at==='number'&&Number.isSafeInteger(wisdom.issued_at)
    &&typeof wisdom.expires_at==='number'&&Number.isSafeInteger(wisdom.expires_at)
    &&wisdom.issued_at<=currentTime&&currentTime<wisdom.expires_at
    &&wisdom.expires_at-wisdom.issued_at<=86400;
   setWisdomReview(validWisdom?normalizeDragonWisdomReview(wisdom.review):null);
   setWisdomExpires(validWisdom?wisdom.expires_at as number:0);
   setProgress(valid);setAttempts(normalizeDragonAttempts(snapshot.attempts));
   setNativeAttempts(normalizeNativeAttempts(snapshot.native_attempts));
   // Catalog is read-only. If unavailable, remain safely without platform choices.
   const platforms=await api.get<{ok:boolean;targets:NativeTarget[];styles:string[]}>(
    PATH+'/native/targets',{headers:authHeaders(),timeoutMs:12000,retries:0});
   if(alive.current&&platforms.ok&&platforms.data?.ok){
    setNativeTargets(normalizeNativeTargets(platforms.data.targets));
    setNativeStyles(Array.isArray(platforms.data.styles)?platforms.data.styles.filter(
     x=>typeof x==='string'&&/^[a-z_]{2,64}$/.test(x)).slice(0,50):[]);
   }
   const course=await api.get<NativeCurriculum&{ok:boolean}>(
    PATH+'/native/curriculum',{headers:authHeaders(),timeoutMs:12000,retries:0});
   if(alive.current&&course.ok&&course.data?.ok)
    setCurriculum(normalizeNativeCurriculum(course.data));
   setSubscription(snapshot.subscription);setAuthenticated(true);setError('');
  }catch(e){
   if(alive.current){setAuthenticated(false);setProgress(null);setWisdomReview(null);
    setAttempts([]);setNativeAttempts([]);setNativeTargets([]);setCurriculum(null);setSubscription(null);
    setError(e instanceof Error?e.message:'Could not connect to Dragon Academy.');}
  }
 },[]);
 useEffect(()=>{
  if(!wisdomReview)return;
  const expiry=setTimeout(()=>setWisdomReview(null),Math.max(0,wisdomExpires*1000-Date.now()));
  return()=>clearTimeout(expiry);
 },[wisdomReview,wisdomExpires]);
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
    setNativeAttempts(normalizeNativeAttempts(r.data.native_attempts));
    if(r.data.curriculum)
     setCurriculum(normalizeNativeCurriculum(r.data.curriculum));
    setSubscription(r.data.subscription);}
   if(!r.data.curriculum){
    const updated=await api.get<NativeCurriculum&{ok:boolean}>(
      PATH+'/native/curriculum',
      {headers:authHeaders(),timeoutMs:12000,retries:0});
    if(alive.current&&updated.ok&&updated.data?.ok)
     setCurriculum(normalizeNativeCurriculum(updated.data));
   }
  }catch(e){
   if(alive.current)setError(e instanceof Error?e.message:'Practice command failed.');
  }finally{
   inFlight.current=false;if(alive.current)setBusy(false);
  }
 },[authenticated]);
 const generateCurriculum=useCallback(()=>{
  if(!curriculum?.next_recommendation)return;
  void mutate('/native/curriculum/generate',{approved:true});
 },[mutate,curriculum]);
 const generateNative=useCallback((target:string,style:string)=>{
  const valid=nativeTargets.find(t=>t.id===target&&t.status==='native_source');
  if(!valid||!nativeStyles.includes(style))return;
  void mutate('/native/generate',{target_id:target,style});
 },[mutate,nativeTargets,nativeStyles]);
 const downloadNative=useCallback(async(attemptId:string)=>{
  const attempt=nativeAttempts.find(a=>a.attempt_id===attemptId);
  if(!attempt||!authenticated||!getAuthToken()||inFlight.current)return;
  inFlight.current=true;setBusy(true);setError('');
  try{
   const url=API_BASE+PATH+'/native/'+encodeURIComponent(attemptId)+'/archive';
   const filename='dragon-'+attempt.target_id+'-'+attemptId.slice(0,8)+'.zip';
   if(Platform.OS==='web'){
    const response=await fetch(url,{headers:authHeaders()});
    if(!response.ok)throw new Error('Could not retrieve native project archive.');
    const buffer=await response.arrayBuffer();
    if(buffer.byteLength>250000)throw new Error('Native project exceeds download limit.');
    const expected=response.headers.get('X-Content-SHA256');
    const hash=await Crypto.digest(Crypto.CryptoDigestAlgorithm.SHA256,new Uint8Array(buffer));
    const actual=Array.from(new Uint8Array(hash)).map(v=>v.toString(16).padStart(2,'0')).join('');
    if(!expected||expected!==actual)throw new Error('Native project digest mismatch.');
    const location=URL.createObjectURL(new Blob([buffer],{type:'application/zip'}));
    const link=document.createElement('a');link.href=location;link.download=filename;
    document.body.appendChild(link);link.click();link.remove();
    URL.revokeObjectURL(location);
   }else{
    if(!FileSystem.cacheDirectory)throw new Error('Native file cache unavailable.');
    const downloaded=await FileSystem.downloadAsync(url,
     FileSystem.cacheDirectory+filename,{headers:authHeaders()});
    if(downloaded.status!==200)throw new Error('Native source download failed.');
    if(!await Sharing.isAvailableAsync())throw new Error('Device sharing is unavailable.');
    await Sharing.shareAsync(downloaded.uri,{mimeType:'application/zip',dialogTitle:'Save native game source'});
   }
  }catch(e){if(alive.current)setError(e instanceof Error?e.message:'Native download failed.');}
  finally{inFlight.current=false;if(alive.current)setBusy(false);}
 },[nativeAttempts,authenticated]);

 const subscribe=useCallback(()=>{void mutate('/practice/subscribe',{
  hours:24,interval_seconds:3600,max_ticks:24,demos_per_tick:2,approved:true,
  adaptive:true,
 });},[mutate]);
 const stop=useCallback(()=>{void mutate('/practice/stop');},[mutate]);
 const revoke=useCallback(()=>{void mutate('/practice/revoke');},[mutate]);
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
  progress,attempts,subscription,practiceBusy:busy,wisdomReview,
  nativeAttempts,nativeTargets,nativeStyles,nativeCurriculum:curriculum,
  onGenerateCurriculum:authenticated?generateCurriculum:undefined,
  onGenerateNative:authenticated?generateNative:undefined,
  onDownloadNative:authenticated?downloadNative:undefined,
  onRunPractice:undefined, // HTML legacy; native source is the default practice path.
  onStartPractice:authenticated?subscribe:undefined,
  onStopPractice:authenticated?stop:undefined,
  onRevokePractice:authenticated?revoke:undefined,
  onOpenDemo:authenticated?openDemo:undefined,
 };
 return{view,error,demo,telemetry,closeDemo,refresh:load,authenticated};
}
