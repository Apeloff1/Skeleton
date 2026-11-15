import React,{useEffect,useRef,useState} from 'react';
import {AppState,Switch,Text,TextInput,TouchableOpacity,View} from 'react-native';
import {getAuthToken} from '../../auth/gameforgeAuth';
import {crawlRequestKey} from '../../product/crawlerClient';
import {searchGames,sourcePage,releaseTimeline,enqueueReleaseImport,importStatus,dispatchGameCapture,type GameIdentity,type GameSource,type ReleaseEvent,type TimelineCursor,type ImportReceipt,type ImportState,type CaptureReceipt} from '../../product/dragonGameCorpusClient';
import s,{colors as C} from './CrawlerWorkspace.styles';

const field={color:C.text,backgroundColor:C.bg,borderWidth:1,borderColor:C.edge,borderRadius:9,padding:10};
function Button({label,disabled,press}:{label:string;disabled?:boolean;press:()=>void}){
 return <TouchableOpacity accessibilityRole="button" accessibilityState={{disabled:!!disabled}} disabled={disabled} style={[s.button,disabled&&s.disabled]} onPress={press}><Text style={s.buttonText}>{label}</Text></TouchableOpacity>;
}
const human=(v:string)=>v.replaceAll('_',' ');
const day=(unix:number)=>new Date(unix*1000).toLocaleDateString();
export default function DragonGameCorpusPanel({visible,canWrite}:{visible:boolean;canWrite:boolean}){
 const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [query,setQuery]=useState(''),[games,setGames]=useState<GameIdentity[]>([]);
 const [game,setGame]=useState<GameIdentity|null>(null),[sources,setSources]=useState<GameSource[]>([]),[sourceCursor,setSourceCursor]=useState<string|null>(null);
 const [selected,setSelected]=useState<GameSource|null>(null),[consent,setConsent]=useState(false),[auto,setAuto]=useState(false),[capture,setCapture]=useState<CaptureReceipt|null>(null);
 const [stage,setStage]=useState(''),[latest,setLatest]=useState(true),[events,setEvents]=useState<ReleaseEvent[]>([]),[eventCursor,setEventCursor]=useState<TimelineCursor|null>(null);
 const [payload,setPayload]=useState(''),[adapter,setAdapter]=useState<'manifest'|'steam'>('manifest'),[batch,setBatch]=useState<ImportReceipt|null>(null),[status,setStatus]=useState<ImportState|null>(null);
 const active=useRef<AbortController|null>(null),epoch=useRef(0),token=useRef(getAuthToken());
 const captureOp=useRef<{id:string;key:string}|null>(null),importOp=useRef<{id:string;key:string}|null>(null);
 function clear(){
  epoch.current++;active.current?.abort();active.current=null;
  setBusy(false);setError('');setQuery('');setGames([]);setGame(null);setSources([]);setSourceCursor(null);
  setSelected(null);setConsent(false);setAuto(false);setCapture(null);setEvents([]);setEventCursor(null);
  setPayload('');setBatch(null);setStatus(null);captureOp.current=null;importOp.current=null;
 }
 useEffect(()=>{
  if(!visible){setOpen(false);clear();}
  const sub=AppState.addEventListener('change',v=>{if(v!=='active'){setOpen(false);clear();}});
  const t=setInterval(()=>{const current=getAuthToken();if(token.current!==current){token.current=current;setOpen(false);clear();}},1000);
  return()=>{sub.remove();clearInterval(t);epoch.current++;active.current?.abort();active.current=null;};
 },[visible]);
 const enabled=visible&&open&&!busy&&token.current===getAuthToken();
 function run(work:(signal:AbortSignal,valid:()=>boolean)=>Promise<void>){
  if(!enabled||active.current)return;
  const request=new AbortController(),id=++epoch.current,start=token.current;
  active.current=request;setBusy(true);setError('');
  const valid=()=>id===epoch.current&&!request.signal.aborted&&start===getAuthToken();
  void work(request.signal,valid).catch(e=>{if(valid())setError(e instanceof Error?e.message:'Game corpus operation unavailable.');}).finally(()=>{if(valid()){active.current=null;setBusy(false);}});
 }
 const search=()=>run(async(signal,valid)=>{const rows=await searchGames(query.trim(),signal);if(valid()){setGames(rows);setGame(null);setSources([]);setSourceCursor(null);setSelected(null);setCapture(null);setConsent(false);}});
 const choose=(value:GameIdentity,after?:string)=>run(async(signal,valid)=>{const p=await sourcePage(value.game_id,after,signal);if(valid()){setGame(value);setSources(p.sources);setSourceCursor(p.next_cursor);setSelected(null);setCapture(null);setConsent(false);}});
 const timeline=(cursor?:TimelineCursor)=>run(async(signal,valid)=>{const p=await releaseTimeline(stage,latest,cursor,signal);if(valid()){setEvents(p.events);setEventCursor(p.next_cursor);}});
 const send=()=>{if(!game||!selected||!canWrite||!consent)return;const match=[game.game_id,selected.source_id,selected.observation_digest,auto].join(':');if(captureOp.current?.id!==match)captureOp.current={id:match,key:crawlRequestKey('game-capture')};const key=captureOp.current.key;run(async(signal,valid)=>{const p=await dispatchGameCapture(game.game_id,selected,key,auto,signal);if(valid()){setCapture(p);setConsent(false);}});};
 const upload=()=>{if(!canWrite||!payload.trim())return;const identity=adapter+':'+payload;if(importOp.current?.id!==identity)importOp.current={id:identity,key:crawlRequestKey('release-import')};const key=importOp.current.key;run(async(signal,valid)=>{const p=await enqueueReleaseImport(payload,key,adapter,signal);if(valid()){setBatch(p);setStatus(null);}});};
 const refresh=()=>{if(!batch)return;run(async(signal,valid)=>{const p=await importStatus(batch.batch_id,signal);if(valid())setStatus(p);});};
 return <View style={s.check}>
  <Text style={s.label}>Game corpus · release intelligence</Text>
  <Text style={s.small}>85 source classes. Catalogue observations are not reviewed evidence or automatic network authorization.</Text>
  <Button label={open?'Close game corpus':'Open game corpus'} disabled={!visible||busy} press={()=>{if(open)clear();setOpen(!open);}}/>
  {open&&<>
   <TextInput value={query} onChangeText={v=>{setQuery(v);setGames([]);setGame(null);setSources([]);setSelected(null);setConsent(false);setCapture(null);}} editable={enabled} maxLength={256} accessibilityLabel="Game title search" style={field} placeholder="Game name or alternate title" placeholderTextColor={C.muted}/>
   <Button label="Find game identities" disabled={!enabled||!query.trim()} press={search}/>
   {games.map(g=><View key={g.game_id} style={s.check}><Text style={s.label}>{g.first_title}</Text><Text style={s.small}>{g.namespace} · {g.external_id} · first observation: {human(g.first_stage)}</Text><Text selectable style={s.small}>Game ID: {g.game_id}</Text><Button label="Inspect game sources" disabled={!enabled} press={()=>choose(g)}/></View>)}
   {game&&<Text style={s.label}>Sources for {game.first_title}</Text>}
   {sources.map(x=><View key={x.source_id} style={s.check}><Text selectable style={s.small}>{x.url}</Text><Text style={s.small}>{human(x.kind)} · {x.language} · {human(x.latest_observation.stage)} · {x.latest_observation.version||'version not supplied'}</Text><Text style={s.small}>Observed {day(x.last_observed)} · review due {day(x.next_review)}</Text><Button label="Select exact source observation" disabled={!enabled||!canWrite} press={()=>{setSelected(x);setConsent(false);setCapture(null);}}/></View>)}
   <Button label="Next source page" disabled={!enabled||!game||!sourceCursor} press={()=>{if(game&&sourceCursor)choose(game,sourceCursor)}}/>
   {selected&&canWrite&&<View style={s.check}><Text selectable style={s.small}>{selected.url}</Text>
    <View style={s.row}><Switch disabled={!enabled} value={consent} onValueChange={setConsent} accessibilityLabel="Explicit capture and source rights consent"/><Text style={s.small}>I authorize capture and acknowledge source rights for this exact URL.</Text></View>
    <View style={s.row}><Switch disabled={!enabled} value={auto} onValueChange={setAuto} accessibilityLabel="Finite autonomous grant"/><Text style={s.small}>Allow existing crawler scheduler a finite run, up to 8 slices / 15 minutes.</Text></View>
    <Button label="Create canonical capture" disabled={!enabled||!consent} press={send}/>
    {capture&&<Text selectable style={s.small}>Session {capture.session.session_id} · {capture.session.status} · capture execution not confirmed.</Text>}
   </View>}
   <Text style={s.label}>Release and patch timeline</Text>
   <View style={s.row}><Switch disabled={!enabled} value={latest} onValueChange={v=>{setLatest(v);setEvents([]);setEventCursor(null)}} accessibilityLabel="Latest observation per source"/><Text style={s.small}>{latest?'Latest observed per source':'Include historical observations'}</Text></View>
   {['','announced','early_access','released','updated','delisted','unknown'].map(v=><Button key={v||'all'} label={(stage===v?'Selected: ':'')+(v?human(v):'All stages')} disabled={!enabled} press={()=>{setStage(v);setEvents([]);setEventCursor(null);}}/>)}
   <Button label="Read release timeline" disabled={!enabled} press={()=>timeline()}/>
   {events.map(e=><View key={e.game_id+':'+e.source_id+':'+e.event_key} style={s.check}><Text style={s.label}>{e.first_title}</Text><Text style={s.small}>{human(e.stage)} · {human(e.kind)} · {e.version||'version unknown'} · {e.released_on||'release day unknown'}</Text><Text style={s.small}>{e.latest_for_source?'Latest observed':'Historical'} · observed {day(e.observed_at)} · unverified</Text></View>)}
   <Button label="Next release page" disabled={!enabled||!eventCursor} press={()=>{if(eventCursor)timeline(eventCursor)}}/>
   {canWrite&&<View style={s.check}><Text style={s.label}>Import local game metadata</Text><Text style={s.small}>Paste a normalized manifest or Steam catalogue response. This queues metadata only, not page capture.</Text>
    <Button label={adapter==='manifest'?'Selected: normalized manifest':'Normalized manifest'} disabled={!enabled} press={()=>setAdapter('manifest')}/>
    <Button label={adapter==='steam'?'Selected: Steam app list':'Steam app list'} disabled={!enabled} press={()=>setAdapter('steam')}/>
    <TextInput value={payload} onChangeText={v=>{setPayload(v);setBatch(null);setStatus(null);}} editable={enabled} multiline maxLength={256*1024} style={field} accessibilityLabel="Local game metadata JSON" placeholder="Paste bounded JSON feed…" placeholderTextColor={C.muted}/>
    <Button label="Queue metadata import" disabled={!enabled||!payload.trim()} press={upload}/>
    {batch&&<Text selectable style={s.small}>Batch {batch.batch_id} · {batch.total} observations queued or replayed.</Text>}
    <Button label="Refresh import status" disabled={!enabled||!batch} press={refresh}/>
    {status&&<Text style={s.small}>{status.counts.done} done · {status.counts.queued} queued · {status.counts.leased} leased · {status.counts.held} held</Text>}
   </View>}
   {!!error&&<Text style={s.error}>{error}</Text>}
  </>}
 </View>;
}
