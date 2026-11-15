import React,{useEffect,useRef,useState} from 'react';
import {AppState,Text,TextInput,TouchableOpacity,View} from 'react-native';
import {getAuthToken} from '../../auth/gameforgeAuth';
import {captionTracks,captionCues,importCaptionTrack,revokeCaptionTrack,type CaptionTrack,type CaptionCue,type MediaRecord} from '../../product/dragonMediaArchiveClient';
import s,{colors as C} from './CrawlerWorkspace.styles';

const field={color:C.text,backgroundColor:C.bg,borderWidth:1,borderColor:C.edge,borderRadius:9,padding:10};
function clock(ms:number){const secs=Math.floor(ms/1000);return [Math.floor(secs/3600),Math.floor(secs/60)%60,secs%60].map(n=>String(n).padStart(2,'0')).join(':');}
type Props={record:MediaRecord;canWrite:boolean;disabled:boolean;onSeek:(seconds:number)=>void};
export default function DragonCaptionPanel({record,canWrite,disabled,onSeek}:Props){
 const [tracks,setTracks]=useState<CaptionTrack[]>([]),[track,setTrack]=useState<CaptionTrack|null>(null),[cues,setCues]=useState<CaptionCue[]>([]);
 const [cursor,setCursor]=useState<number|null>(null),[query,setQuery]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 const [lang,setLang]=useState('en'),[format,setFormat]=useState<'vtt'|'srt'>('vtt'),[payload,setPayload]=useState(''),[rights,setRights]=useState(false),[confirm,setConfirm]=useState(false);
 const active=useRef<AbortController|null>(null),epoch=useRef(0),timer=useRef<ReturnType<typeof setTimeout>|null>(null);
 function clearCues(){if(timer.current)clearTimeout(timer.current);timer.current=null;setCues([]);setCursor(null);}
 function reset(){epoch.current++;active.current?.abort();active.current=null;clearCues();setTracks([]);setTrack(null);setQuery('');setPayload('');setRights(false);setConfirm(false);setBusy(false);setNotice('');}
 useEffect(()=>{
  const token=getAuthToken(),sub=AppState.addEventListener('change',v=>{if(v!=='active')reset();});
  const guard=setInterval(()=>{if(token!==getAuthToken()||Date.now()>=record.expires_at*1000)reset();},500);
  return()=>{epoch.current++;active.current?.abort();if(timer.current)clearTimeout(timer.current);sub.remove();clearInterval(guard);};
 },[record.media_id,record.sha256,record.expires_at]);
 const enabled=!disabled&&!busy&&Date.now()<record.expires_at*1000&&!!getAuthToken();
 const run=(work:(signal:AbortSignal,current:()=>boolean)=>Promise<void>)=>{
  if(!enabled||active.current)return;
  const ctrl=new AbortController(),generation=++epoch.current,token=getAuthToken();
  active.current=ctrl;setBusy(true);setNotice('');clearCues();
  const current=()=>!ctrl.signal.aborted&&generation===epoch.current&&token===getAuthToken()&&Date.now()<record.expires_at*1000;
  void work(ctrl.signal,current).catch(e=>{if(current())setNotice(e instanceof Error?e.message:'Caption operation held.');}).finally(()=>{if(active.current===ctrl){active.current=null;setBusy(false);}});
 };
 const refresh=()=>run(async(signal,current)=>{const p=await captionTracks(record,signal);if(current()){setTracks(p.tracks);setTrack(null);setConfirm(false);}});
 const search=(selected:CaptionTrack,after?:number)=>run(async(signal,current)=>{
  const started=Date.now(),p=await captionCues(record,selected,query,after,signal);
  if(current()){
   const ttl=Math.min(30000,Math.floor((p.valid_until-p.as_of_unix)*1000)-(Date.now()-started)-250);
   if(ttl<=0)throw Error('Caption view expired.');
   setTrack(selected);setCues(p.cues);setCursor(p.next_cursor);setNotice(p.cues.length?'':'No matching captions.');
   timer.current=setTimeout(()=>{setCues([]);setCursor(null);},ttl);
  }
 });
 const upload=()=>run(async(signal,current)=>{
  if(!rights||!canWrite)return;
  const receipt=await importCaptionTrack(record,lang.trim().toLowerCase(),format,payload,signal);
  const result=await captionTracks(record,signal);
  if(current()){setTracks(result.tracks);setTrack(null);setPayload('');setRights(false);setNotice('Indexed '+receipt.cues+' user-supplied captions.');}
 });
 const withdraw=()=>{if(!track||!confirm||!canWrite)return;const selected=track;run(async(signal,current)=>{
  await revokeCaptionTrack(record,selected,signal);
  if(current()){setTrack(null);setTracks(v=>v.filter(x=>x.track_id!==selected.track_id));setConfirm(false);setNotice('Caption track logically removed.');}
 });};
 const button=(label:string,press:()=>void,off=false)=><TouchableOpacity accessibilityRole="button" disabled={!enabled||off} onPress={press} style={[s.button,(!enabled||off)&&s.disabled]}><Text style={s.buttonText}>{label}</Text></TouchableOpacity>;
 if(!record.mime.startsWith('audio/')&&!record.mime.startsWith('video/'))return null;
 return <View style={s.check}>
  <Text style={s.label}>Timestamped transcript library</Text>
  <Text style={s.small}>User-supplied captions are indexed as plaintext, not verified facts or model training data.</Text>
  {button('Load caption tracks',refresh)}
  {tracks.map(x=><View key={x.track_id} style={s.check}>
   <Text style={s.small}>{x.language} · {x.format.toUpperCase()} · {x.cues} cues</Text>
   {button(track?.track_id===x.track_id?'Selected track: reload cues':'Select transcript',()=>{setConfirm(false);search(x);})}
  </View>)}
  {track&&<>
   <TextInput accessibilityLabel="Search transcript" value={query} onChangeText={v=>{setQuery(v);clearCues();}} style={field} editable={enabled} maxLength={256} placeholder="Find a word, mechanic or location" placeholderTextColor={C.muted}/>
   {button('Search exact caption text',()=>search(track))}
   {cues.map(c=><View style={s.check} key={c.ordinal}>
    <Text style={s.label}>{clock(c.start_ms)} – {clock(c.end_ms)}</Text>
    <Text selectable style={s.small}>{c.text}</Text>
    {button('Seek playback to '+clock(c.start_ms),()=>onSeek(c.start_ms/1000))}
   </View>)}
   {button('Next caption page',()=>{if(cursor!==null)search(track,cursor);},cursor===null)}
   {canWrite&&button(confirm?'Confirm remove this caption track':'Remove selected caption track',()=>confirm?withdraw():setConfirm(true))}
  </>}
  {canWrite&&<View style={s.check}>
   <Text style={s.label}>Import a local caption track</Text>
   <TextInput value={lang} onChangeText={setLang} maxLength={32} autoCapitalize="none" editable={enabled} style={field} accessibilityLabel="Caption language" placeholder="en" placeholderTextColor={C.muted}/>
   {button(format==='vtt'?'Selected: WebVTT':'WebVTT',()=>setFormat('vtt'))}
   {button(format==='srt'?'Selected: SubRip':'SubRip',()=>setFormat('srt'))}
   <TextInput multiline value={payload} onChangeText={setPayload} maxLength={1024*1024} editable={enabled} style={field} accessibilityLabel="Caption text" placeholder="Paste timestamped captions…" placeholderTextColor={C.muted}/>
   {button(rights?'Caption retention rights acknowledged':'Acknowledge caption retention rights',()=>setRights(v=>!v))}
   {button('Index transcript',upload,!rights||!payload.trim())}
  </View>}
  {!!notice&&<Text style={s.small}>{notice}</Text>}
 </View>;
}
