import React,{useEffect,useRef,useState} from 'react';
import {AppState,Linking,Text,TouchableOpacity,View} from 'react-native';
import {getAuthToken} from '../../auth/gameforgeAuth';
import {safeOriginalLink,sourceCaptures,sourceDocuments,createViewPin,viewSourceDocument,compareSourceDocuments,type GameSource,type CaptureBinding,type CaptureCursor,type CaptureDocument,type DocumentSpan,type ViewPin,type DocumentDiff} from '../../product/dragonGameCorpusClient';
import s from './CrawlerWorkspace.styles';
import DragonMediaLibrary from './DragonMediaLibrary';

function Button({label,disabled,press}:{label:string;disabled?:boolean;press:()=>void}){
 return <TouchableOpacity accessibilityRole="button" accessibilityState={{disabled:!!disabled}} disabled={disabled} style={[s.button,disabled&&s.disabled]} onPress={press}><Text style={s.buttonText}>{label}</Text></TouchableOpacity>;
}
const date=(n:number)=>new Date(n*1000).toLocaleString();
const human=(v:string)=>v.replaceAll('_',' ');
type Props={game:string;source:GameSource;visible:boolean;disabled:boolean;canWrite:boolean};

export default function DragonSourceViewer({game,source,visible,disabled,canWrite}:Props){
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[confirm,setConfirm]=useState(false);
 const [captures,setCaptures]=useState<CaptureBinding[]>([]),[captureCursor,setCaptureCursor]=useState<CaptureCursor|null>(null);
 const [session,setSession]=useState<string|null>(null),[docs,setDocs]=useState<CaptureDocument[]>([]),[docCursor,setDocCursor]=useState<string|null>(null),[held,setHeld]=useState<number|null>(null);
 const [span,setSpan]=useState<DocumentSpan|null>(null),[pin,setPin]=useState<ViewPin|null>(null),[left,setLeft]=useState<ViewPin|null>(null),[diff,setDiff]=useState<DocumentDiff|null>(null);
 const active=useRef<AbortController|null>(null),epoch=useRef(0),token=useRef(getAuthToken()),timer=useRef<ReturnType<typeof setTimeout>|null>(null),docTimer=useRef<ReturnType<typeof setTimeout>|null>(null);
 function clearText(){if(timer.current){clearTimeout(timer.current);timer.current=null;}setSpan(null);setPin(null);setDiff(null);}
 function reset(){
  epoch.current++;active.current?.abort();active.current=null;setBusy(false);setError('');setConfirm(false);
  clearText();if(docTimer.current){clearTimeout(docTimer.current);docTimer.current=null;}setCaptures([]);setCaptureCursor(null);setDocs([]);setDocCursor(null);setSession(null);setHeld(null);setLeft(null);
 }
 useEffect(()=>{
  token.current=getAuthToken();reset();
  const sub=AppState.addEventListener('change',x=>{if(x!=='active')reset();});
  const t=setInterval(()=>{if(token.current!==getAuthToken()){token.current=getAuthToken();reset();}},500);
  return()=>{sub.remove();clearInterval(t);epoch.current++;active.current?.abort();active.current=null;if(timer.current)clearTimeout(timer.current);if(docTimer.current)clearTimeout(docTimer.current);};
 },[game,source.source_id,visible]);
 const enabled=visible&&!disabled&&!busy&&token.current===getAuthToken();
 function run(work:(signal:AbortSignal,still:()=>boolean)=>Promise<void>){
  if(!enabled||active.current)return;
  const controller=new AbortController(),id=++epoch.current,start=token.current;
  active.current=controller;setBusy(true);setError('');clearText();
  const still=()=>id===epoch.current&&!controller.signal.aborted&&start===getAuthToken();
  void work(controller.signal,still).catch(e=>{if(still())setError(e instanceof Error?e.message:'Source view unavailable.');}).finally(()=>{if(still()){active.current=null;setBusy(false);}});
 }
 function expire(asOf:number,until:number,started:number){
  const ttl=Math.min(30000,(until-asOf)*1000-(Date.now()-started)-250);
  if(ttl<=0)throw Error('Source view expired; reload the exact capture.');
  if(timer.current)clearTimeout(timer.current);
  timer.current=setTimeout(()=>{setSpan(null);setPin(null);setDiff(null);},ttl);
 }
 const history=(before?:CaptureCursor)=>run(async(signal,still)=>{
  const p=await sourceCaptures(game,source.source_id,before,signal);
  if(still()){setCaptures(p.captures);setCaptureCursor(p.next_cursor);setDocs([]);setDocCursor(null);setSession(null);setHeld(null);}
 });
 const browse=(id:string,after?:string)=>run(async(signal,still)=>{
  const started=Date.now(),p=await sourceDocuments(game,source.source_id,id,after,signal);
  if(still()){
   if(docTimer.current){clearTimeout(docTimer.current);docTimer.current=null;}
   if(p.earliest_expiry!==null){
    const ttl=Math.min(30000,(p.earliest_expiry-p.as_of_unix)*1000-(Date.now()-started)-250);
    if(ttl<=0)throw Error('Source listing expired; refresh.');
    docTimer.current=setTimeout(()=>{setDocs([]);setDocCursor(null);},ttl);
   }
   setSession(id);setDocs(p.documents);setDocCursor(p.next_cursor);setHeld(p.held);
  }
 });
 const read=(selected:ViewPin)=>run(async(signal,still)=>{
  const started=Date.now(),p=await viewSourceDocument(game,source.source_id,selected,signal);
  if(still()){expire(p.as_of_unix,p.valid_until,started);setSpan(p);setPin(selected);}
 });
 const compare=(a:ViewPin,b:ViewPin)=>run(async(signal,still)=>{
  const started=Date.now(),p=await compareSourceDocuments(game,source.source_id,a,b,signal);
  if(still()){expire(p.as_of_unix,p.valid_until,started);setDiff(p);}
 });
 function original(){
  if(!enabled||!confirm)return;
  setConfirm(false);
  try{const link=safeOriginalLink(source.url);void Linking.openURL(link).catch(()=>setError('External browser could not open the source.'));}
  catch(e){setError(e instanceof Error?e.message:'External source unavailable.');}
 }
 if(!visible)return null;
 return <View style={s.check}>
  <Text style={s.label}>Source viewer · {human(source.kind)}</Text>
  <Text selectable style={s.small}>{source.url}</Text>
  <Text style={s.small}>{human(source.view_mode||'text')} reference · original site and retained capture are distinct. No automatic remote media, script or download runs.</Text>
  <Button label={confirm?'Cancel external navigation':'Prepare to open original source'} disabled={!enabled} press={()=>setConfirm(v=>!v)}/>
  {confirm&&<View style={s.check}><Text style={s.small}>You are leaving Dragon for this unverified source. The destination can track visits, redirect or offer downloads.</Text><Button label="Open original in external browser" disabled={!enabled} press={original}/></View>}
  <DragonMediaLibrary game={game} source={source} canWrite={canWrite} disabled={!enabled}/>
  <Button label="Load retained capture versions" disabled={!enabled} press={()=>history()}/>
  {captures.map(c=><View key={c.session_id} style={s.check}>
   <Text selectable style={s.small}>{c.session_id}</Text>
   <Text style={s.small}>Capture requested {date(c.recorded_at)} · access is checked when opened.</Text>
   <Button label="Inspect captured documents" disabled={!enabled} press={()=>browse(c.session_id)}/>
  </View>)}
  <Button label="Next capture history page" disabled={!enabled||!captureCursor} press={()=>{if(captureCursor)history(captureCursor);}}/>
  {held!==null&&<Text style={s.small}>{held} held or unavailable documents in this window. Held text is not exposed.</Text>}
  {docs.map(d=><View key={d.capture_source_id} style={s.check}>
   <Text style={s.label}>{d.title||'Untitled captured source'}</Text>
   <Text style={s.small}>{d.history_only?'Historical capture':'Current permitted capture'} · {date(d.captured_at)} · {d.total_chars} code points · unreviewed</Text>
   <Text selectable style={s.small}>{d.url}</Text>
   <Button label="Read retained text" disabled={!enabled||!session} press={()=>{if(session)read(createViewPin(session,d));}}/>
  </View>)}
  <Button label="Next captured documents" disabled={!enabled||!docCursor||!session} press={()=>{if(session&&docCursor)browse(session,docCursor);}}/>
  {span&&pin&&<View style={s.check}>
   <Text style={s.label}>{span.history_only?'Historical':'Current'} source passage</Text>
   <Text style={s.small}>Code points {span.offset}–{span.end} of {span.total_chars} · authority expires {date(span.valid_until)}. Display clears after at most 30 seconds.</Text>
   <Text selectable style={s.small}>{span.text||'(empty retained text)'}</Text>
   <Text selectable style={s.small}>SHA-256 {span.span_sha256}</Text>
   <View style={s.row}><Button label="Previous text page" disabled={!enabled||span.offset===0} press={()=>read({...pin,offset:Math.max(0,span.offset-pin.length)})}/><Button label="Next text page" disabled={!enabled||span.next_offset===null} press={()=>{if(span.next_offset!==null)read({...pin,offset:span.next_offset});}}/></View>
   <Button label="Pin this passage for comparison" disabled={!enabled} press={()=>setLeft(pin)}/>
   <Button label="Compare pinned and current passage" disabled={!enabled||!left||left.session===pin.session&&left.capture_source===pin.capture_source} press={()=>{if(left)compare(left,pin);}}/>
  </View>}
  {left&&<View style={s.row}><Text style={s.small}>Comparison pin retained (identity only; authority will be rechecked).</Text><Button label="Clear comparison pin" disabled={!enabled} press={()=>setLeft(null)}/></View>}
  {diff&&<View style={s.check}><Text style={s.label}>Exact retained passage comparison</Text><Text style={s.small}>Selected windows only, not a complete document revision diff.</Text>
   {diff.changes.filter(x=>x.operation!=='equal').map((x,i)=><View key={i} style={s.check}><Text style={s.label}>{human(x.operation)}</Text>{!!x.left&&<Text selectable style={s.small}>Earlier selection: {x.left}</Text>}{!!x.right&&<Text selectable style={s.small}>Later selection: {x.right}</Text>}</View>)}
   {!diff.changes.some(x=>x.operation!=='equal')&&<Text style={s.small}>No changes in the compared windows.</Text>}
  </View>}
  {!!error&&<Text style={s.error}>{error}</Text>}
 </View>;
}
