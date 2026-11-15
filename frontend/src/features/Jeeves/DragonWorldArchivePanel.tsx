import React,{useState,useEffect,useRef} from 'react';
import {AppState,Text,TextInput,TouchableOpacity,View} from 'react-native';
import {getAuthToken} from '../../auth/gameforgeAuth';
import {crawlRequestKey} from '../../product/crawlerClient';
import {getDesignProfiles,importDesignProfile,subscribeDiscovery,subscriptions,revokeDiscovery,datasetVersions,datasetRecords,datasetEdges,type DesignProfile,type Subscription,type DatasetVersion,type DatasetRecord,type DatasetEdge,type SubscriptionInput} from '../../product/dragonWorldArchiveClient';
import s,{colors as C} from './CrawlerWorkspace.styles';

const field={color:C.text,backgroundColor:C.bg,borderWidth:1,borderColor:C.edge,borderRadius:9,padding:10};
function Button({label,off,press}:{label:string;off?:boolean;press:()=>void}){
 return <TouchableOpacity accessibilityRole="button" accessibilityState={{disabled:!!off}} disabled={off} onPress={press} style={[s.button,off&&s.disabled]}><Text style={s.buttonText}>{label}</Text></TouchableOpacity>;
}
function Input({value,change,label,off,max=256}:{value:string;change:(v:string)=>void;label:string;off?:boolean;max?:number}){
 return <TextInput accessibilityLabel={label} placeholder={label} placeholderTextColor={C.muted} value={value} onChangeText={change} editable={!off} maxLength={max} style={field}/>;
}
const EVE='https://developers.eveonline.com/static-data/tranquility/latest.jsonl';
const adapters:SubscriptionInput['adapter'][]=['manifest','steam','rss_atom','sitemap','eve_sde'];

export default function DragonWorldArchivePanel({game,visible,canWrite}:{game:string|null;visible:boolean;canWrite:boolean}){
 const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [profiles,setProfiles]=useState<DesignProfile[]>([]),[limits,setLimits]=useState<Record<string,number>>({});
 const [feeds,setFeeds]=useState<Subscription[]>([]),[feedCursor,setFeedCursor]=useState<string|null>(null),[confirm,setConfirm]=useState('');
 const [url,setUrl]=useState(''),[adapter,setAdapter]=useState<SubscriptionInput['adapter']>('manifest'),[provider,setProvider]=useState('developer'),[external,setExternal]=useState(''),[title,setTitle]=useState(''),[rights,setRights]=useState(false);
 const [versions,setVersions]=useState<DatasetVersion[]>([]),[versionCursor,setVersionCursor]=useState<string|null>(null),[version,setVersion]=useState<DatasetVersion|null>(null),[q,setQ]=useState(''),[records,setRecords]=useState<DatasetRecord[]>([]),[recordCursor,setRecordCursor]=useState<string|null>(null),[edges,setEdges]=useState<DatasetEdge[]>([]);
 const active=useRef<AbortController|null>(null),epoch=useRef(0),auth=useRef(getAuthToken());
 function clear(){epoch.current++;active.current?.abort();active.current=null;setBusy(false);setError('');setNotice('');setProfiles([]);setLimits({});setFeeds([]);setFeedCursor(null);setConfirm('');setUrl('');setAdapter('manifest');setProvider('developer');setExternal('');setTitle('');setRights(false);setVersions([]);setVersionCursor(null);setVersion(null);setQ('');setRecords([]);setRecordCursor(null);setEdges([]);}
 useEffect(()=>{
  auth.current=getAuthToken();
  if(!visible){setOpen(false);clear();}
  const a=AppState.addEventListener('change',v=>{if(v!=='active'){clear();setOpen(false);}});
  const t=setInterval(()=>{if(auth.current!==getAuthToken()){auth.current=getAuthToken();clear();setOpen(false);}},500);
  return()=>{a.remove();clearInterval(t);epoch.current++;active.current?.abort();active.current=null;};
 },[visible,game]);
 const enabled=visible&&open&&!busy&&auth.current===getAuthToken();
 function run(work:(signal:AbortSignal,valid:()=>boolean)=>Promise<void>){
  if(!enabled||active.current)return;
  const controller=new AbortController(),e=++epoch.current,token=auth.current;
  active.current=controller;setBusy(true);setError('');setNotice('');
  const valid=()=>e===epoch.current&&!controller.signal.aborted&&token===getAuthToken();
  void work(controller.signal,valid).catch(x=>{if(valid())setError(x instanceof Error?x.message:'Archive operation held.');}).finally(()=>{if(valid()){active.current=null;setBusy(false);}});
 }
 const load=()=>run(async(signal,valid)=>{const p=await getDesignProfiles(signal);if(valid()){setProfiles(p.profiles);setLimits(p.architectural_limits);}});
 const loadFeeds=(after?:string)=>run(async(signal,valid)=>{const p=await subscriptions(after,signal);if(valid()){setFeeds(p.subscriptions);setFeedCursor(p.next_cursor);}});
 const add=()=>run(async(signal,valid)=>{
  if(!canWrite||!rights)return;
  const input:SubscriptionInput={url,adapter,interval_seconds:3600,grant_seconds:7*86400,rights_acknowledged:true};
  if(adapter==='rss_atom'||adapter==='sitemap'){input.provider=provider;input.external_id=external;input.title=title;}
  const p=await subscribeDiscovery(input,signal);if(valid()){setRights(false);setNotice('Feed mandate created; network work depends on operator runtime configuration and robots policy. '+p.subscription_id);}
 });
 const loadVersions=(after?:string)=>{if(!game)return;run(async(signal,valid)=>{const p=await datasetVersions(game,after,signal);if(valid()){setVersions(p.versions);setVersionCursor(p.next_cursor);setVersion(null);setRecords([]);setEdges([]);}});};
 const read=(v:DatasetVersion,after?:string)=>{if(!game||v.state!=='sealed')return;run(async(signal,valid)=>{const p=await datasetRecords(game,v.id,q,after,signal);if(valid()){setVersion(v);setRecords(p.records);setRecordCursor(p.next_cursor);setEdges([]);}});};
 return <View style={s.check}>
  <Text style={s.label}>Hoarder · worldwide ecosystem</Text>
  <Button label={open?'Close worldwide archive tools':'Open worldwide archive tools'} off={!visible||busy} press={()=>{if(open)clear();setOpen(!open);}}/>
  {open&&<>
   <Text style={s.small}>Design profiles describe stress envelopes, not claimed physical capacity or verified game footage.</Text>
   <Button label="Inspect ecosystem design profiles" off={!enabled} press={load}/>
   {Object.entries(limits).map(([k,v])=><Text key={k} style={s.small}>{k.replaceAll('_',' ')}: {v.toLocaleString()}</Text>)}
   {profiles.map(p=><View key={p.id} style={s.check}><Text style={s.label}>{p.example}: {p.title}</Text><Text style={s.small}>{p.candidate_urls} source candidates · no capture authority</Text>
    {Object.entries(p.design_load).map(([k,v])=><Text key={k} style={s.small}>{k.replaceAll('_',' ')}: {v.toLocaleString()}</Text>)}
    {canWrite&&<Button label="Import public source metadata" off={!enabled} press={()=>run(async(signal,valid)=>{const r=await importDesignProfile(p.id,crawlRequestKey('profile'),signal);if(valid())setNotice('Metadata import queued: '+r.batch_id);})}/>}
   </View>)}
   {canWrite&&<View style={s.check}>
    <Text style={s.label}>Unattended public feed subscriptions</Text>
    <Text style={s.small}>Independent seven-day permission; one-hour requested interval. Never gives permission to capture discovered links.</Text>
    <Button label="Prepare official EVE SDE build subscription" off={!enabled} press={()=>{setAdapter('eve_sde');setUrl(EVE);setRights(false);}}/>
    {adapters.map(a=><Button key={a} label={(adapter===a?'Selected: ':'Adapter: ')+a} off={!enabled} press={()=>{setAdapter(a);setRights(false);if(a==='eve_sde')setUrl(EVE);}}/>)}
    <Input label="Public HTTPS feed URL" value={url} change={v=>{setUrl(v);setRights(false);}} max={2048} off={!enabled||adapter==='eve_sde'}/>
    {(adapter==='rss_atom'||adapter==='sitemap')&&<>
     <Input label="Provider namespace" value={provider} change={v=>{setProvider(v);setRights(false);}} max={32} off={!enabled}/>
     <Input label="Existing game external ID" value={external} change={v=>{setExternal(v);setRights(false);}} max={128} off={!enabled}/>
     <Input label="Game title" value={title} change={v=>{setTitle(v);setRights(false);}} off={!enabled}/>
    </>}
    <TouchableOpacity accessibilityRole="checkbox" accessibilityState={{checked:rights,disabled:!enabled}} disabled={!enabled} style={s.button} onPress={()=>setRights(v=>!v)}><Text style={s.buttonText}>{rights?'Acknowledged: ':'Acknowledge: '}I may monitor and retain candidate metadata from this public feed.</Text></TouchableOpacity>
    <Button label="Register finite discovery mandate" off={!enabled||!rights||!url.trim()} press={add}/>
    <Button label="Read subscription status" off={!enabled} press={()=>loadFeeds()}/>
    {feeds.map(f=><View key={f.id} style={s.check}><Text selectable style={s.small}>{f.url}</Text><Text style={s.small}>{f.adapter} · {f.enabled&&f.expires_at*1000>Date.now()?'enabled':'inactive'} · {f.failures} failures · {f.reason||'no hold reported'}</Text><Text style={s.small}>Grant expires {new Date(f.expires_at*1000).toLocaleString()}</Text><Button label={confirm===f.id?'Confirm revoke':'Revoke mandate'} off={!enabled||!f.enabled} press={()=>{if(confirm!==f.id){setConfirm(f.id);return;}run(async(signal,valid)=>{await revokeDiscovery(f.id,signal);if(valid()){setFeeds(x=>x.map(v=>v.id===f.id?{...v,enabled:0}:v));setConfirm('');}});}}/></View>)}
    <Button label="Next subscription page" off={!enabled||!feedCursor} press={()=>{if(feedCursor)loadFeeds(feedCursor);}}/>
   </View>}
   {game&&<View style={s.check}><Text style={s.label}>Game datasets and relation graph</Text>
    <Text style={s.small}>Browse sealed local structured exports. No automatic claim of Wiki approval or permission to train.</Text>
    <Button label="Load dataset versions" off={!enabled} press={()=>loadVersions()}/>
    {versions.map(v=><View key={v.id} style={s.check}><Text style={s.label}>{v.dataset} · {v.label}</Text><Text style={s.small}>{v.rows.toLocaleString()}/{v.expected_rows.toLocaleString()} records · {v.state}</Text><Button label="Inspect dataset" off={!enabled||v.state!=='sealed'} press={()=>read(v)}/></View>)}
    <Button label="Next dataset versions" off={!enabled||!versionCursor} press={()=>{if(versionCursor)loadVersions(versionCursor);}}/>
    {version&&<><Input label="Search retained records" value={q} change={v=>{setQ(v);setRecords([]);setEdges([]);setRecordCursor(null);}} off={!enabled}/>
      <Button label="Search selected dataset" off={!enabled} press={()=>read(version)}/>
      {records.map(r=><View key={r.key} style={s.check}><Text style={s.label}>{r.key}</Text><Text selectable style={s.small}>{JSON.stringify(r.record,null,2).slice(0,8192)}</Text><Button label="Outgoing relations" off={!enabled} press={()=>run(async(signal,valid)=>{const p=await datasetEdges(game,version.id,r.key,false,signal);if(valid())setEdges(p.edges);})}/><Button label="Incoming relations" off={!enabled} press={()=>run(async(signal,valid)=>{const p=await datasetEdges(game,version.id,r.key,true,signal);if(valid())setEdges(p.edges);})}/></View>)}
      <Button label="Next record page" off={!enabled||!recordCursor} press={()=>{if(recordCursor)read(version,recordCursor);}}/>
      {edges.map((e,i)=><Text key={i} selectable style={s.small}>{e.record_key} · {e.relation} → {e.target}</Text>)}
    </>}
   </View>}
   {!!notice&&<Text style={s.small}>{notice}</Text>}{!!error&&<Text style={s.error}>{error}</Text>}
  </>}
 </View>;
}
