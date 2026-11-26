import React,{useEffect,useRef,useState} from 'react';
import {AppState,Text,TouchableOpacity,View} from 'react-native';
import {getAuthToken} from '../../auth/gameforgeAuth';
import {listMedia,revokeMedia,type MediaRecord} from '../../product/dragonMediaArchiveClient';
import type {GameSource} from '../../product/dragonGameCorpusClient';
import DragonMediaPlayer from './DragonMediaPlayer';
import DragonMediaImport from './DragonMediaImport';
import s from './CrawlerWorkspace.styles';

export default function DragonMediaLibrary({game,source,canWrite,disabled}:{game:string;source:GameSource;canWrite:boolean;disabled:boolean}){
 const [open,setOpen]=useState(false),[rows,setRows]=useState<MediaRecord[]>([]),[selected,setSelected]=useState<MediaRecord|null>(null);
 const [error,setError]=useState(''),[busy,setBusy]=useState(false),[confirm,setConfirm]=useState('');
 const ctrl=useRef<AbortController|null>(null),epoch=useRef(0);
 function reset(){epoch.current++;ctrl.current?.abort();ctrl.current=null;setSelected(null);setRows([]);setOpen(false);setError('');setConfirm('');setBusy(false);}
 useEffect(()=>{
  const token=getAuthToken();
  const sub=AppState.addEventListener('change',x=>{if(x!=='active')reset();});
  const timer=setInterval(()=>{if(token!==getAuthToken())reset();},500);
  return()=>{epoch.current++;ctrl.current?.abort();clearInterval(timer);sub.remove();};
 },[game,source.source_id]);
 function run(work:(signal:AbortSignal,valid:()=>boolean)=>Promise<void>){
  if(busy||disabled||ctrl.current)return;
  const active=new AbortController(),e=++epoch.current,token=getAuthToken();
  ctrl.current=active;setBusy(true);setError('');setSelected(null);
  const valid=()=>e===epoch.current&&!active.signal.aborted&&token===getAuthToken();
  void work(active.signal,valid).catch(x=>{if(valid())setError(x instanceof Error?x.message:'Media library held.');}).finally(()=>{if(valid()){ctrl.current=null;setBusy(false);}});
 }
 const refresh=()=>run(async(signal,valid)=>{const list=await listMedia(game,source.source_id,signal);if(valid())setRows(list);});
 const remove=(row:MediaRecord)=>run(async(signal,valid)=>{await revokeMedia(row.media_id,signal);if(valid()){setRows(v=>v.filter(x=>x.media_id!==row.media_id));setConfirm('');}});
 const button=(label:string,onPress:()=>void,off=false)=><TouchableOpacity accessibilityRole="button" disabled={disabled||busy||off} onPress={onPress} style={[s.button,(busy||off||disabled)&&s.disabled]}><Text style={s.buttonText}>{label}</Text></TouchableOpacity>;
 return <View style={s.check}>
  <Text style={s.label}>Retained audiovisual library</Text><Text style={s.small}>Local bytes with independent rights and expiry. External links are not media downloads.</Text>
  {button(open?'Close media library':'Open local media library',()=>{if(open)reset();else{setOpen(true);refresh();}})}
  {open&&<>
   {button('Refresh media',refresh)}
   {canWrite&&<DragonMediaImport game={game} source={source} disabled={disabled||busy} onChanged={refresh}/>}
   {rows.map(row=><View key={row.media_id} style={s.check}>
    <Text style={s.small}>{row.mime} · {(row.total_bytes/1048576).toFixed(2)} MiB · {row.state}</Text>
    <Text selectable style={s.small}>{row.sha256}</Text>
    <Text style={s.small}>Retention expires {new Date(row.expires_at*1000).toLocaleString()}</Text>
    {button('Open inline media',()=>setSelected(row),row.state!=='sealed'||row.expires_at*1000<=Date.now())}
    {canWrite&&button(confirm===row.media_id?'Confirm revoke local media':'Revoke retained media',()=>{if(confirm===row.media_id)remove(row);else{setSelected(null);setConfirm(row.media_id);}})}
   </View>)}
   {selected&&<View style={s.check}>{button('Close player',()=>setSelected(null))}<DragonMediaPlayer key={selected.media_id} record={selected}/></View>}
   {!!error&&<Text style={s.error}>{error}</Text>}
  </>}
 </View>;
}
