import React,{useCallback,useEffect,useRef,useState} from 'react';
import {ActivityIndicator,AppState,Switch,Text,TextInput,TouchableOpacity,View} from 'react-native';
import {getAuthToken} from '../../auth/gameforgeAuth';
import {getDragonTreasury,configureDragonArchive,crawlRequestKey,type CrawlSession,type DragonTreasury,type TreasuryMode,type TreasuryRevision} from '../../product/crawlerClient';
import s,{colors} from './CrawlerWorkspace.styles';
import AnimatedDragon from './companion/DragonCompanion';
import {INITIAL_DRAGON_STATE} from './companion/dragonCompanionState';
import {useReducedMotion,useScreenReader} from './companion/useDragonMotion';
import {usePowerAwareness} from '../../hooks/usePowerAwareness';

const MODES: readonly [TreasuryMode,string][]=[['current_only','Current chest'],['historic_only','Historic vault'],['all_revisions','All versions'],['timeline','Timeline'],['compare','Compare']];
const field={backgroundColor:colors.bg,borderWidth:1,borderColor:colors.edge,borderRadius:9,padding:12,color:colors.text,fontSize:14};
const stamp=(n:number)=>new Date(n*1000).toLocaleString();
const short=(s:string)=>s.slice(0,12);
function Button({label,action,disabled=false}:{label:string;action:()=>void;disabled?:boolean}){
 return <TouchableOpacity style={[s.button,disabled&&s.disabled]} accessibilityRole="button" accessibilityState={{disabled}} disabled={disabled} onPress={action}><Text style={s.buttonText}>{label}</Text></TouchableOpacity>;
}
function Revision({row}:{row:TreasuryRevision}){
 return <View style={s.check}>
  <Text selectable style={s.label}>{row.plane==='current'?'Current':'Historic'} · {short(row.revision_id)} · {row.delta.kind.replaceAll('_',' ')}</Text>
  <Text style={s.small}>{stamp(row.first_seen)} → {stamp(row.last_seen)} · {row.reobservations} subsequent observations</Text>
  <Text style={s.small}>{row.indexed?(row.archive_only?'Historical permission only':'Authorized retained text'):'Metadata only · no searchable text'}{row.latest_observed?' · latest observed':''}</Text>
  {row.delta.similarity!==null&&<Text style={s.small}>Lexical similarity {Math.round(row.delta.similarity*100)}% · {row.delta.added_terms} added terms · {row.delta.removed_terms} removed · numeric change {row.delta.numeric_change?'observed':'not observed'}</Text>}
  {row.source_id&&<Text selectable style={s.small}>Source {row.source_id}</Text>}
 </View>;
}
export default function DragonTreasuryPanel({revision,session,canWrite=false,onSession,onRevisit,disabled=false}:{revision:string;session?:CrawlSession|null;canWrite?:boolean;onSession?:(s:CrawlSession)=>void;onRevisit?:(url:string)=>void;disabled?:boolean}){
 const [result,setResult]=useState<DragonTreasury|null>(null);
 const [mode,setMode]=useState<TreasuryMode>('current_only');
 const [query,setQuery]=useState('');
 const [family,setFamily]=useState<string|undefined>();
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [days,setDays]=useState('30');
 const [rights,setRights]=useState(false);
 const [open,setOpen]=useState(false);
 const request=useRef<AbortController|null>(null), timer=useRef<ReturnType<typeof setTimeout>|null>(null);
 const generation=useRef(0), owner=useRef(getAuthToken()), observed=useRef(revision);
 const grantKey=useRef<{identity:string;key:string}|null>(null);
 const reduced=useReducedMotion(),screenReader=useScreenReader(),power=usePowerAwareness();
 const invalidate=useCallback(()=>{
  generation.current++;request.current?.abort();request.current=null;
  if(timer.current!==null)clearTimeout(timer.current);timer.current=null;
 },[]);
 useEffect(()=>{
  if(observed.current!==revision){observed.current=revision;invalidate();setResult(null);setBusy(false);grantKey.current=null;}
  return ()=>invalidate();
 },[revision,invalidate]);
 useEffect(()=>{
  const sub=AppState.addEventListener('change',state=>{if(state!=='active'){invalidate();setResult(null);setBusy(false);}});
  return()=>sub.remove();
 },[invalidate]);
 useEffect(()=>{setRights(false);grantKey.current=null;},[session?.session_id,session?.version]);
 const visible=result&&observed.current===revision&&owner.current===getAuthToken()?result:null;
 async function observe(nextMode=mode,nextFamily=family){
  invalidate();const epoch=generation.current, token=getAuthToken(), started=Date.now(),ctrl=new AbortController();
  owner.current=token;request.current=ctrl;setBusy(true);setResult(null);setError('');
  try{
   const value=await getDragonTreasury(nextMode,query,nextFamily,ctrl.signal);
   if(ctrl.signal.aborted||epoch!==generation.current||token!==getAuthToken())return;
   const ttl=value.earliest_source_expiry===null?120000:Math.min(120000,1000*(value.earliest_source_expiry-value.as_of_unix)-(Date.now()-started));
   if(ttl<=0){setError('A source permission expired. Reparse again.');return;}
   setResult(value);
   timer.current=setTimeout(()=>{if(epoch===generation.current)setResult(null);},ttl);
  }catch(e){if(!ctrl.signal.aborted&&epoch===generation.current&&token===getAuthToken())setError(e instanceof Error?e.message:'Treasury unavailable.');}
  finally{if(epoch===generation.current){request.current=null;setBusy(false);}}
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
 const terminal=session&&['completed','budget_exhausted'].includes(session.status);
 const evolution=visible?.evolution;
 return <View style={s.card}>
  <Text style={s.eyebrow}>HOARDER · TREASURY AND VAULT</Text>
  <Text style={s.heading}>Living knowledge archive</Text>
  <Text style={s.small}>Keep versions separate. Reparse retained text without new network requests. Current means latest observed, not verified live truth.</Text>
  <Button label={open?'Close treasury':'Open treasury'} action={()=>{setOpen(!open);if(open){invalidate();setResult(null);setBusy(false);}}}/>
  {open&&<>
   {terminal&&onSession&&<View style={s.check}>
    <Text style={s.label}>Historical retention for this finished expedition</Text>
    <Text style={s.small}>{session.archive_grant?.active?'Active until '+stamp(session.archive_grant.expires_at!):'No active historical-use grant.'} {session.archive_grant?.usable_sources??0} authorized retained sources.</Text>
    {canWrite&&<><TextInput style={field} value={days} editable={!busy&&!disabled} onChangeText={setDays} keyboardType="number-pad" maxLength={2} accessibilityLabel="Historical retention days"/>
     <View style={s.row}><Switch value={rights} disabled={busy||disabled} onValueChange={setRights} accessibilityLabel="Confirm historical archive rights"/><Text style={[s.small,s.grow]}>I have rights to retain and reparse eligible captured text for the selected period. This does not renew crawl or model-use consent.</Text></View>
     <Button label="Authorize historical use" disabled={!rights||busy||disabled} action={()=>void grant(true)}/></>}
    {session.archive_grant&&<Button label="Revoke historical use" disabled={busy||disabled} action={()=>void grant(false)}/>}
   </View>}
   <TextInput value={query} editable={!busy&&!disabled} onChangeText={v=>{setQuery(v);invalidate();setResult(null);setBusy(false);}} maxLength={256} placeholder="Search retained versions" placeholderTextColor={colors.muted} accessibilityLabel="Search treasury" style={field}/>
   <View style={s.row}>{MODES.map(([id,label])=><TouchableOpacity key={id} style={[s.button,mode===id&&{backgroundColor:'#52382d'}]} accessibilityRole="button" accessibilityState={{selected:mode===id,disabled:busy||disabled}} disabled={busy||disabled} onPress={()=>{setMode(id);invalidate();setResult(null);setBusy(false);}}><Text style={s.buttonText}>{label}</Text></TouchableOpacity>)}</View>
   {family&&<Button label={'Clear family filter '+short(family)} disabled={busy||disabled} action={()=>{setFamily(undefined);invalidate();setResult(null);setBusy(false);}}/>}
   <Button label={busy?'Reparsing…':'Reparse authorized versions'} disabled={busy||disabled} action={()=>void observe()}/>
   {busy&&<ActivityIndicator color={colors.accent}/>}
   {!!error&&<Text style={s.error} accessibilityLiveRegion="polite">{error}</Text>}
   {visible&&evolution&&<>
    <AnimatedDragon state={{...INITIAL_DRAGON_STATE,phase:'sleeping',label:evolution.form==='hoarder'?'Cozy guardian of the hoard':'Growing a little treasure den',detail:'Treasury evolution from retained evidence and verified version custody. Rest is always free.',progress:evolution.stage_progress,wings:evolution.stage>=2,snuggly:true}} evolutionStage={evolution.stage} level={evolution.level} unlocked={evolution.stage>=4?['star_cartographer','apprentice_forge']:[]} researchMode screenReader={screenReader} motion={reduced||screenReader||power.shouldReduceAnimations?'off':'gentle'} reducedMotion={reduced||screenReader||power.shouldReduceAnimations}/>
    <Text style={s.heading}>{evolution.form.toUpperCase()} · Level {evolution.level}</Text>
    <Text style={s.small}>Discovery {evolution.expedition_growth}/1000 · stewardship {evolution.treasury_growth}/500 · effective evolution {evolution.effective_evolution}/1500</Text>
    <Text style={s.small}>Hoarder unlock requires discovery ≥800, sufficient authorized historic transitions and at least two current families. Permission changes may change the collection view, not pet health.</Text>
    <Text style={s.label}>Current indexed {visible.current_indexed} · Historic indexed {visible.historic_indexed} · Metadata only {visible.metadata_only}</Text>
    <Text style={s.small}>{visible.families} families · {visible.revisions} versions · {visible.rollbacks} rollbacks · {visible.blocked_current} current families unavailable · {visible.alias_held_families} alias conflicts</Text>
    {(visible.candidate_limit_reached||visible.excluded_sessions>0)&&<Text style={s.small}>Bounded or unqualified corpus: this observation cannot establish complete archive coverage.</Text>}
    <Text style={s.heading}>Revision families and revisit recommendations</Text>
    <Text style={s.small}>{visible.parsed_unique_payloads} distinct retained payloads reparsed · {visible.revisit_plan.length} prioritized suggestions, interleaved across origins.</Text>
    {visible.family_rows.map(f=><View key={f.family_id} style={s.check}>
     <Text style={s.label}>{short(f.family_id)} · {f.revision_count} versions{f.simultaneous_conflict?' · conflicting observations':''}{f.alias_conflict?' · newer ambiguous alias':''}</Text>
     <Text style={s.small}>{f.current_indexed?'Current indexed':'Current unavailable'} · last seen {stamp(f.last_seen)}</Text>
     <Text style={s.small}>Advisory review {stamp(f.revisit.due_at)} · estimated change risk {Math.round(f.revisit.change_probability_estimate*100)}% · {f.revisit.qualified_intervals} qualified intervals</Text>
     <Button label="Compare versions" disabled={busy||disabled} action={()=>{setFamily(f.family_id);setMode('compare');void observe('compare',f.family_id);}}/>
     {!!f.refresh_url&&!!onRevisit&&canWrite&&f.revisit.ready_for_review&&<Button label="Prepare fresh expedition" disabled={busy||disabled} action={()=>{onRevisit(f.refresh_url!);invalidate();setResult(null);}}/>}
    </View>)}
    {visible.comparison&&<View style={s.check}><Text style={s.heading}>Latest and preceding observation</Text><Revision row={visible.comparison.current}/><Revision row={visible.comparison.previous}/></View>}
    <Text style={s.heading}>{mode==='timeline'?'Revision timeline':'Matching indexed revisions'}</Text>
    {(mode==='timeline'?visible.timeline:visible.hits).map(v=><Revision key={v.revision_id} row={v}/>)}
    <Text selectable style={s.small}>Index receipt {visible.partition_digest}</Text>
   </>}
  </>}
 </View>;
}
