import React,{useEffect,useRef,useState} from 'react';
import {AppState,Text,TextInput,TouchableOpacity,View} from 'react-native';
import {getAuthToken} from '../../auth/gameforgeAuth';
import {datasetVersions,datasetRecords,datasetRecord,datasetGraph,datasetCompare,datasetCompareRecord,type DatasetVersion,type EntityRecord,type EntityGraph,type VersionDiff,type RecordDiff} from '../../product/dragonDatasetExplorerClient';
import s,{colors as C} from './CrawlerWorkspace.styles';

const field={color:C.text,backgroundColor:C.bg,borderWidth:1,borderColor:C.edge,borderRadius:9,padding:10};
const dt=(x:number)=>new Date(x*1000).toLocaleString();
const number=(x:number)=>x.toLocaleString();
type Props={game:string;visible:boolean;disabled:boolean};
export default function DragonDatasetExplorer({game,visible,disabled}:Props){
 const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [versions,setVersions]=useState<DatasetVersion[]>([]),[versionCursor,setVersionCursor]=useState<string|null>(null);
 const [selected,setSelected]=useState<DatasetVersion|null>(null),[baseline,setBaseline]=useState<DatasetVersion|null>(null);
 const [query,setQuery]=useState(''),[records,setRecords]=useState<EntityRecord[]>([]),[recordCursor,setRecordCursor]=useState<string|null>(null),[entity,setEntity]=useState<EntityRecord|null>(null);
 const [direction,setDirection]=useState<'in'|'out'|'both'>('both'),[depth,setDepth]=useState(3),[graph,setGraph]=useState<EntityGraph|null>(null);
 const [diff,setDiff]=useState<VersionDiff|null>(null),[detail,setDetail]=useState<RecordDiff|null>(null);
 const active=useRef<AbortController|null>(null),epoch=useRef(0),timer=useRef<ReturnType<typeof setTimeout>|null>(null);
 function clearMaterial(){if(timer.current)clearTimeout(timer.current);timer.current=null;setRecords([]);setRecordCursor(null);setEntity(null);setGraph(null);setDiff(null);setDetail(null);}
 function reset(){epoch.current++;active.current?.abort();active.current=null;clearMaterial();setOpen(false);setBusy(false);setError('');setVersions([]);setVersionCursor(null);setSelected(null);setBaseline(null);setQuery('');}
 useEffect(()=>{
  const account=getAuthToken();if(!visible)reset();
  const sub=AppState.addEventListener('change',v=>{if(v!=='active')reset();});
  const t=setInterval(()=>{if(account!==getAuthToken())reset();},500);
  return()=>{epoch.current++;active.current?.abort();sub.remove();clearInterval(t);if(timer.current)clearTimeout(timer.current);};
 },[game,visible]);
 const enabled=visible&&open&&!busy&&!disabled&&!!getAuthToken();
 const alive=selected?.state==='sealed'&&selected.expires_at*1000>Date.now();
 function run(work:(signal:AbortSignal,current:()=>boolean)=>Promise<void>){
  if(!enabled||active.current)return;
  const ctrl=new AbortController(),generation=++epoch.current,token=getAuthToken();active.current=ctrl;setBusy(true);setError('');
  const current=()=>!ctrl.signal.aborted&&generation===epoch.current&&token===getAuthToken();
  void work(ctrl.signal,current).catch(e=>{if(current()){clearMaterial();setError(e instanceof Error?e.message:'Dataset operation held.');}}).finally(()=>{if(active.current===ctrl){active.current=null;setBusy(false);}});
 }
 function retention(expires:number){
  const ttl=Math.min(30000,expires*1000-Date.now()-250);
  if(ttl<=0)throw Error('Dataset permission expired.');
  if(timer.current)clearTimeout(timer.current);
  timer.current=setTimeout(clearMaterial,ttl);
 }
 const list=(after?:string)=>run(async(signal,current)=>{const p=await datasetVersions(game,after,signal);if(current()){clearMaterial();setVersions(p.versions);setVersionCursor(p.next_cursor);}});
 const search=(after?:string)=>{if(!selected||!alive)return;const v=selected;run(async(signal,current)=>{
  const p=await datasetRecords(game,v,query,after,signal);if(current()){clearMaterial();retention(v.expires_at);setRecords(p.records);setRecordCursor(p.next_cursor);}
 });};
 const inspect=(key:string)=>{if(!selected||!alive)return;const v=selected;run(async(signal,current)=>{
  const p=await datasetRecord(game,v,key,signal);if(current()){clearMaterial();retention(p.valid_until);setEntity(p);}
 });};
 const explore=(key:string)=>{if(!selected||!alive)return;const v=selected;run(async(signal,current)=>{
  const p=await datasetGraph(game,v,key,direction,depth,signal);if(current()){clearMaterial();retention(p.valid_until);setGraph(p);}
 });};
 const comparable=!!(selected&&baseline&&alive&&baseline.expires_at*1000>Date.now()&&baseline.id!==selected.id&&baseline.dataset===selected.dataset&&baseline.source===selected.source);
 const compare=(after?:string)=>{if(!selected||!baseline||!comparable)return;const a=baseline,b=selected;run(async(signal,current)=>{
  const p=await datasetCompare(game,a,b,after,signal);if(current()){clearMaterial();retention(p.valid_until);setDiff(p);}
 });};
 const compareOne=(key:string)=>{if(!baseline||!selected||!comparable)return;const a=baseline,b=selected;run(async(signal,current)=>{
  const p=await datasetCompareRecord(game,a,b,key,signal);if(current()){clearMaterial();retention(p.valid_until);setDetail(p);}
 });};
 const button=(label:string,onPress:()=>void,off=false)=><TouchableOpacity accessibilityRole="button" disabled={!enabled||off} onPress={onPress} style={[s.button,(!enabled||off)&&s.disabled]}><Text style={s.buttonText}>{label}</Text></TouchableOpacity>;
 if(!visible)return null;
 return <View style={s.check}>
  <Text style={s.label}>World data · MMO entity and patch explorer</Text>
  <Text style={s.small}>Explore immutable public-data imports. No live market orders, private player data or game-client actions.</Text>
  <TouchableOpacity accessibilityRole="button" disabled={disabled||busy} onPress={()=>open?reset():setOpen(true)} style={s.button}><Text style={s.buttonText}>{open?'Close dataset explorer':'Open dataset explorer'}</Text></TouchableOpacity>
  {open&&<>
   {button('Load retained dataset versions',()=>list())}
   {versions.map(v=><View key={v.id} style={s.check}>
    <Text style={s.label}>{v.label} · {v.dataset}</Text><Text style={s.small}>{v.state} · {number(v.rows)} / {number(v.expected_rows)} rows · {dt(v.created_at)}</Text>
    <Text selectable style={s.small}>Chain {v.chain}</Text><Text style={s.small}>Retention expires {dt(v.expires_at)}</Text>
    {button(selected?.id===v.id?'Selected version':'Inspect this version',()=>{clearMaterial();setSelected(v);},v.state!=='sealed')}
    {button(baseline?.id===v.id?'Pinned baseline':'Pin as comparison baseline',()=>{clearMaterial();setBaseline(v);},v.state!=='sealed')}
   </View>)}
   {button('Next version page',()=>{if(versionCursor)list(versionCursor);},!versionCursor)}
   {selected&&<>
    <Text style={s.label}>Selected: {selected.label}</Text>
    <Text style={s.small}>Retained entity records and graph views clear after at most 30 seconds.</Text>
    <TextInput value={query} onChangeText={v=>{setQuery(v);clearMaterial();}} maxLength={256} editable={enabled&&alive} style={field} accessibilityLabel="Search structured game data" placeholder="Ship, item, region, skill, resource…" placeholderTextColor={C.muted}/>
    {button('Search or browse records',()=>search(),!alive)}
    {records.map(r=><View key={r.key} style={s.check}>
     <Text selectable style={s.label}>{r.key}</Text><Text selectable numberOfLines={4} style={s.small}>{JSON.stringify(r.record)}</Text>
     {button('Inspect exact entity',()=>inspect(r.key))}
     {button('Explore entity relations',()=>explore(r.key))}
    </View>)}
    {button('Next record page',()=>{if(recordCursor)search(recordCursor);},!recordCursor)}
    <Text style={s.label}>Graph traversal options</Text>
    {(['in','out','both'] as const).map(d=><React.Fragment key={d}>{button((d===direction?'Selected: ':'')+d,()=>{setDirection(d);setGraph(null);})}</React.Fragment>)}
    <View style={s.row}>{button('Depth −',()=>{setDepth(v=>Math.max(0,v-1));setGraph(null);},depth===0)}<Text style={s.small}>Depth {depth}</Text>{button('Depth +',()=>{setDepth(v=>Math.min(6,v+1));setGraph(null);},depth===6)}</View>
    {entity&&<View style={s.check}><Text style={s.label}>Entity {entity.key}</Text>
     <Text selectable style={s.small}>{JSON.stringify(entity.record,null,2)}</Text><Text selectable style={s.small}>SHA-256 {entity.sha256}</Text>{button('Explore relations',()=>explore(entity.key))}
    </View>}
    {graph&&<View style={s.check}><Text style={s.label}>Entity graph: {graph.root}</Text>
     <Text style={s.small}>{number(graph.nodes.length)} nodes · {number(graph.edges.length)} edges · {graph.unresolved_nodes} missing targets{graph.truncated?' · bounded window':''}</Text>
     {graph.edges.slice(0,64).map((e,i)=><Text selectable key={i} style={s.small}>{e.from} — {e.relation} → {e.to}</Text>)}
     {graph.edges.length>64&&<Text style={s.small}>First 64 edges displayed; explore individual nodes for more.</Text>}
     {graph.nodes.map(n=><View key={n.key} style={s.check}><Text style={s.small}>Depth {n.depth} · {n.key}{n.present?'':' · unresolved'}</Text>
      {button('Read node',()=>inspect(n.key),!n.present)}{button('Recenter graph',()=>explore(n.key),!n.present)}</View>)}
    </View>}
    <Text style={s.label}>Version comparison</Text>
    <Text style={s.small}>{baseline?'Baseline: '+baseline.label:'Pin an older sealed version of the same dataset/source.'}</Text>
    {button('Compare retained versions',()=>compare(),!comparable)}
    {diff&&<View style={s.check}><Text style={s.small}>Window: {diff.scanned} records examined · +{diff.window_counts.added} / −{diff.window_counts.removed} / changed {diff.window_counts.changed} / unchanged {diff.window_counts.unchanged}. Not global totals.</Text>
     {diff.changes.map(c=><View key={c.key} style={s.check}><Text style={s.label}>{c.change} · {c.key}</Text>{button('Inspect exact before and after',()=>compareOne(c.key))}</View>)}
     {button('Next comparison window',()=>{if(diff.next_cursor)compare(diff.next_cursor);},diff.next_cursor===null)}
    </View>}
    {detail&&<View style={s.check}><Text style={s.label}>{detail.change} · {detail.key}</Text>
     {detail.fields.map(f=><Text key={f.field} style={s.small}>{f.change} · {f.field}</Text>)}
     <Text style={s.label}>Before</Text><Text selectable style={s.small}>{detail.before?JSON.stringify(detail.before.record,null,2):'Not present'}</Text>
     <Text style={s.label}>After</Text><Text selectable style={s.small}>{detail.after?JSON.stringify(detail.after.record,null,2):'Not present'}</Text>
    </View>}
   </>}
   {!!error&&<Text style={s.error}>{error}</Text>}
  </>}
 </View>;
}
