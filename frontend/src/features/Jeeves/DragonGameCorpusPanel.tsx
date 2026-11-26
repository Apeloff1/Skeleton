import React,{useEffect,useRef,useState} from 'react';
import {AppState,Switch,Text,TextInput,TouchableOpacity,View} from 'react-native';
import {getAuthToken} from '../../auth/gameforgeAuth';
import {crawlRequestKey} from '../../product/crawlerClient';
import {getSourceTaxonomy,searchSourceLibrary,searchGames,sourcePage,releaseTimeline,enqueueReleaseImport,importStatus,dispatchGameCapture,type GameIdentity,type GameSource,type ReleaseEvent,type TimelineCursor,type ImportReceipt,type ImportState,type CaptureReceipt,type TaxonomyEntry,type GlobalSource} from '../../product/dragonGameCorpusClient';
import s,{colors as C} from './CrawlerWorkspace.styles';
import DragonSourceViewer from './DragonSourceViewer';
import DragonSourceDirectoryPanel from './DragonSourceDirectoryPanel';
import DragonModSeedPanel from './DragonModSeedPanel';
import DragonWorldArchivePanel from './DragonWorldArchivePanel';

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
 const [globalQuery,setGlobalQuery]=useState(''),[globalResults,setGlobalResults]=useState<GlobalSource[]>([]),[globalNotice,setGlobalNotice]=useState('');
 const [viewer,setViewer]=useState<GameSource|null>(null);
 const [taxonomy,setTaxonomy]=useState<{source_classes:TaxonomyEntry[];families:string[]}|null>(null),[family,setFamily]=useState(''),[kind,setKind]=useState(''),[language,setLanguage]=useState(''),[categoryQuery,setCategoryQuery]=useState(''),[categoryPage,setCategoryPage]=useState(0);
 const [selected,setSelected]=useState<GameSource|null>(null),[consent,setConsent]=useState(false),[auto,setAuto]=useState(false),[capture,setCapture]=useState<CaptureReceipt|null>(null);
 const [stage,setStage]=useState(''),[latest,setLatest]=useState(true),[events,setEvents]=useState<ReleaseEvent[]>([]),[eventCursor,setEventCursor]=useState<TimelineCursor|null>(null);
 const [payload,setPayload]=useState(''),[adapter,setAdapter]=useState<'manifest'|'steam'>('manifest'),[batch,setBatch]=useState<ImportReceipt|null>(null),[status,setStatus]=useState<ImportState|null>(null);
 const active=useRef<AbortController|null>(null),epoch=useRef(0),token=useRef(getAuthToken());
 const captureOp=useRef<{id:string;key:string}|null>(null),importOp=useRef<{id:string;key:string}|null>(null);
 function clear(){
  epoch.current++;active.current?.abort();active.current=null;
  setBusy(false);setError('');setQuery('');setGames([]);setGame(null);setSources([]);setSourceCursor(null);
  setGlobalQuery('');setGlobalResults([]);setGlobalNotice('');setViewer(null);setTaxonomy(null);setFamily('');setKind('');setLanguage('');setCategoryQuery('');setCategoryPage(0);
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
 const search=()=>run(async(signal,valid)=>{const rows=await searchGames(query.trim(),signal);if(valid()){setGames(rows);setGame(null);setViewer(null);setSources([]);setSourceCursor(null);setSelected(null);setCapture(null);setConsent(false);}});
 const choose=(value:GameIdentity,after?:string)=>run(async(signal,valid)=>{const p=await sourcePage(value.game_id,after,signal,{family:family||undefined,kind:kind||undefined,language:language.trim()||undefined});if(valid()){setGame(value);setViewer(null);setSources(p.sources);setSourceCursor(p.next_cursor);setSelected(null);setCapture(null);setConsent(false);}});
 const loadTaxonomy=()=>run(async(signal,valid)=>{const p=await getSourceTaxonomy(signal);if(valid())setTaxonomy(p);});
 const clearFilters=()=>{setGlobalResults([]);setGlobalNotice('');setSources([]);setSourceCursor(null);setSelected(null);setViewer(null);setCapture(null);setConsent(false);};
 const globalSearch=()=>run(async(signal,valid)=>{const p=await searchSourceLibrary(globalQuery.trim(),{family:family||undefined,kind:kind||undefined,language:language.trim()||undefined},signal);if(valid()){setGlobalResults(p.sources);setGlobalNotice((p.truncated?'Top matching source references; narrow the query.':'Matched catalogue source references.')+(p.index_backfill_complete?'':' Historical indexing is still incomplete.'));}});
 const classes=(taxonomy?.source_classes||[]).filter(x=>(!family||x.family===family)&&(!categoryQuery.trim()||human(x.kind).includes(categoryQuery.trim().toLowerCase().replaceAll('_',' '))||human(x.family).includes(categoryQuery.trim().toLowerCase())));
 const timeline=(cursor?:TimelineCursor)=>run(async(signal,valid)=>{const p=await releaseTimeline(stage,latest,cursor,signal);if(valid()){setEvents(p.events);setEventCursor(p.next_cursor);}});
 const send=()=>{if(!game||!selected||!canWrite||!consent)return;const match=[game.game_id,selected.source_id,selected.observation_digest,auto].join(':');if(captureOp.current?.id!==match)captureOp.current={id:match,key:crawlRequestKey('game-capture')};const key=captureOp.current.key;run(async(signal,valid)=>{const p=await dispatchGameCapture(game.game_id,selected,key,auto,signal);if(valid()){setCapture(p);setConsent(false);}});};
 const upload=()=>{if(!canWrite||!payload.trim())return;const identity=adapter+':'+payload;if(importOp.current?.id!==identity)importOp.current={id:identity,key:crawlRequestKey('release-import')};const key=importOp.current.key;run(async(signal,valid)=>{const p=await enqueueReleaseImport(payload,key,adapter,signal);if(valid()){setBatch(p);setStatus(null);}});};
 const refresh=()=>{if(!batch)return;run(async(signal,valid)=>{const p=await importStatus(batch.batch_id,signal);if(valid())setStatus(p);});};
 return <View style={s.check}>
  <Text style={s.label}>Game corpus · release intelligence</Text>
  <Text style={s.small}>Expanded source classes spanning text, artwork, maps, video, audio, documents and development. Catalogue observations are not reviewed evidence or automatic network authorization.</Text>
  <Button label={open?'Close game corpus':'Open game corpus'} disabled={!visible||busy} press={()=>{if(open)clear();setOpen(!open);}}/>
  {open&&<>
   <TextInput value={query} onChangeText={v=>{setQuery(v);setGames([]);setGame(null);setViewer(null);setSources([]);setSelected(null);setConsent(false);setCapture(null);}} editable={enabled} maxLength={256} accessibilityLabel="Game title search" style={field} placeholder="Game name or alternate title" placeholderTextColor={C.muted}/>
   <Button label="Find game identities" disabled={!enabled||!query.trim()} press={search}/>
   {games.map(g=><View key={g.game_id} style={s.check}><Text style={s.label}>{g.first_title}</Text><Text style={s.small}>{g.namespace} · {g.external_id} · first observation: {human(g.first_stage)}</Text><Text selectable style={s.small}>Game ID: {g.game_id}</Text><Button label="Inspect game sources" disabled={!enabled} press={()=>choose(g)}/></View>)}
   <DragonSourceDirectoryPanel game={game} canWrite={canWrite} visible={visible&&open} disabled={busy}/>
   <DragonModSeedPanel game={game} canWrite={canWrite} visible={visible&&open} disabled={busy}/>
   <Button label="Load source category explorer" disabled={!enabled} press={loadTaxonomy}/>
   {taxonomy&&<View style={s.check}>
    <Text style={s.label}>{taxonomy.source_classes.length} source categories · {taxonomy.families.length} families</Text>
    <Text style={s.small}>Choose a family, category or language and refresh the selected game's sources.</Text>
    <Button label={!family?'Selected: all families':'All families'} disabled={!enabled} press={()=>{setFamily('');setKind('');setCategoryPage(0);clearFilters();}}/>
    {taxonomy.families.map(f=><Button key={f} label={(family===f?'Selected: ':'')+human(f)} disabled={!enabled} press={()=>{setFamily(f);setKind('');setCategoryPage(0);clearFilters();}}/>)}
    <TextInput accessibilityLabel="Search source categories" value={categoryQuery} onChangeText={v=>{setCategoryQuery(v);setCategoryPage(0);}} editable={enabled} maxLength={64} style={field} placeholder="Filter categories…" placeholderTextColor={C.muted}/>
    <Button label={!kind?'Selected: all categories':'All categories in family'} disabled={!enabled} press={()=>{setKind('');clearFilters();}}/>
    {classes.slice(categoryPage*16,categoryPage*16+16).map(k=><Button key={k.kind} label={(kind===k.kind?'Selected: ':'')+human(k.kind)+' · '+k.view_mode} disabled={!enabled} press={()=>{setKind(k.kind);clearFilters();}}/>)}
    <Text style={s.small}>{classes.length} matching categories</Text>
    <View style={s.row}><Button label="Previous categories" disabled={!enabled||categoryPage===0} press={()=>setCategoryPage(v=>v-1)}/><Button label="Next categories" disabled={!enabled||(categoryPage+1)*16>=classes.length} press={()=>setCategoryPage(v=>v+1)}/></View>
    <TextInput accessibilityLabel="Source language filter" value={language} onChangeText={v=>{setLanguage(v);clearFilters();}} editable={enabled} maxLength={32} style={field} placeholder="Optional language (en, ja, nb)" placeholderTextColor={C.muted}/>
   </View>}
   <View style={s.check}>
    <Text style={s.label}>Search sources across all games</Text>
    <TextInput accessibilityLabel="Global source search" value={globalQuery} onChangeText={v=>{setGlobalQuery(v);setGlobalResults([]);setGlobalNotice('');}} editable={enabled} maxLength={256} style={field} placeholder="Wiki, mechanics, trailer, map, guide, hostname…" placeholderTextColor={C.muted}/>
    <Button label="Search indexed source directory" disabled={!enabled||!globalQuery.trim()} press={globalSearch}/>
    {!!globalNotice&&<Text style={s.small}>{globalNotice}</Text>}
    {globalResults.map(x=><View key={x.game_id+':'+x.source_id} style={s.check}>
     <Text style={s.label}>{x.game_title}</Text>
     <Text style={s.small}>{human(x.kind)} · {x.view_mode} · {x.language}</Text>
     <Text selectable style={s.small}>{x.url}</Text>
     <Button label="View this source" disabled={!enabled} press={()=>{setGame({game_id:x.game_id,first_title:x.game_title,namespace:x.namespace,external_id:x.external_id,first_stage:x.first_stage,updated_at:x.updated_at});setViewer(x);setSources([]);setSourceCursor(null);setSelected(null);setConsent(false);setCapture(null);}}/>
    </View>)}
   </View>
   {game&&<><Text style={s.label}>Sources for {game.first_title}</Text><Button label="Refresh filtered sources" disabled={!enabled} press={()=>choose(game)}/></>}
   {sources.map(x=><View key={x.source_id} style={s.check}><Text selectable style={s.small}>{x.url}</Text><Text style={s.small}>{human(x.family||"source")} · {human(x.kind)} · {x.view_mode||"text"} · {x.language} · {human(x.latest_observation.stage)} · {x.latest_observation.version||'version not supplied'}</Text><Text style={s.small}>Observed {day(x.last_observed)} · review due {day(x.next_review)}</Text><Button label="Open source viewer" disabled={!enabled} press={()=>setViewer(x)}/><Button label="Select exact source observation" disabled={!enabled||!canWrite} press={()=>{setSelected(x);setConsent(false);setCapture(null);}}/></View>)}
   <Button label="Next source page" disabled={!enabled||!game||!sourceCursor} press={()=>{if(game&&sourceCursor)choose(game,sourceCursor)}}/>
   {game&&viewer&&<View style={s.check}><Button label="Close source viewer" disabled={busy} press={()=>setViewer(null)}/><DragonSourceViewer key={game.game_id+":"+viewer.source_id} game={game.game_id} source={viewer} visible={visible&&open} disabled={busy} canWrite={canWrite}/></View>}
   {selected&&canWrite&&<View style={s.check}><Text selectable style={s.small}>{selected.url}</Text>
    <View style={s.row}><Switch disabled={!enabled} value={consent} onValueChange={setConsent} accessibilityLabel="Explicit capture and source rights consent"/><Text style={s.small}>I authorize capture and acknowledge source rights for this exact URL.</Text></View>
    <View style={s.row}><Switch disabled={!enabled} value={auto} onValueChange={setAuto} accessibilityLabel="Finite autonomous grant"/><Text style={s.small}>Allow existing crawler scheduler a finite run, up to 8 slices / 15 minutes.</Text></View>
    <Button label="Create canonical capture" disabled={!enabled||!consent} press={send}/>
    {capture&&<Text selectable style={s.small}>Session {capture.session.session_id} · {capture.session.status} · capture execution not confirmed.</Text>}
   </View>}
   <DragonWorldArchivePanel key={game?.game_id||'world'} game={game?.game_id||null} visible={visible&&open} canWrite={canWrite}/>
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
