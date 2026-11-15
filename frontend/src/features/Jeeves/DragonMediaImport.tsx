import React,{useEffect,useRef,useState} from 'react';
import {AppState,Text,TouchableOpacity,View} from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import {File,Paths} from 'expo-file-system';
import * as Crypto from 'expo-crypto';
import {getAuthToken} from '../../auth/gameforgeAuth';
import {crawlRequestKey} from '../../product/crawlerClient';
import {allowedMediaMime,beginMedia,appendNativeMedia,sealMedia,BLOCK,type MediaMime} from '../../product/dragonMediaArchiveClient';
import type {GameSource} from '../../product/dragonGameCorpusClient';
import s from './CrawlerWorkspace.styles';

const MAX_NATIVE_BYTES=32*1024*1024;
type Selection={uri:string;name:string;size:number;mime:MediaMime};
async function sha(bytes:Uint8Array){return Array.from(new Uint8Array(await Crypto.digest(Crypto.CryptoDigestAlgorithm.SHA256,new Uint8Array(bytes)))).map(x=>x.toString(16).padStart(2,'0')).join('');}
function deleteCacheCopy(uri:string){
 try{const f=new File(uri),root=Paths.cache.uri.replace(/\/$/,'')+'/';if(f.uri.startsWith(root)&&!f.uri.slice(root.length).split('/').some(p=>p==='..'||p==='.'||p.includes('%')))f.delete();}catch{/* never remove an unqualified path */}
}
function mimeFor(name:string,provided?:string):MediaMime|null{
 if(provided&&allowedMediaMime(provided))return provided;
 const ext=name.toLowerCase().split('.').pop();
 const formats:Record<string,MediaMime>={mp4:'video/mp4',webm:'video/webm',mp3:'audio/mpeg',ogg:'audio/ogg',wav:'audio/wav',png:'image/png',jpg:'image/jpeg',jpeg:'image/jpeg',webp:'image/webp'};
 return ext&&Object.hasOwn(formats,ext)?formats[ext]:null;
}

export default function DragonMediaImport({game,source,onChanged,disabled}:{game:string;source:GameSource;onChanged:()=>void;disabled:boolean}){
 const [file,setFile]=useState<Selection|null>(null),[consent,setConsent]=useState(false),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
 const active=useRef<AbortController|null>(null),epoch=useRef(0),fileRef=useRef<Selection|null>(null),operation=useRef<{sha:string;key:string}|null>(null);
 function discard(){
  // The selected URI is a picker-owned cache copy, not a user original.
  const old=fileRef.current;fileRef.current=null;
  if(old)deleteCacheCopy(old.uri);
 }
 function reset(){epoch.current++;active.current?.abort();active.current=null;discard();operation.current=null;setBusy(false);setFile(null);setConsent(false);setNotice('');}
 useEffect(()=>{
  const account=getAuthToken();const sub=AppState.addEventListener('change',v=>{if(v!=='active'&&active.current)reset();});
  const timer=setInterval(()=>{if(account!==getAuthToken())reset();},500);
  return()=>{epoch.current++;active.current?.abort();discard();clearInterval(timer);sub.remove();};
 },[game,source.source_id,source.observation_digest]);
 const choose=async()=>{
  if(disabled||busy||active.current)return;
  const generation=++epoch.current,account=getAuthToken();
  setBusy(true);setNotice('');
  try{
   const result=await DocumentPicker.getDocumentAsync({type:['video/*','audio/*','image/*'],multiple:false,copyToCacheDirectory:true});
   if(result.canceled)return;
   const asset=result.assets[0],kind=mimeFor(asset.name,asset.mimeType);
   // Ignore stale picker responses; they cannot change the source or account.
   if(generation!==epoch.current||account!==getAuthToken()){deleteCacheCopy(asset.uri);return;}
   if(!kind||!asset.size||asset.size>MAX_NATIVE_BYTES||!asset.uri.startsWith('file://')){
    deleteCacheCopy(asset.uri);
    throw Error('Select a supported file no larger than 32 MiB.');
   }
   discard();const item={uri:asset.uri,name:asset.name,size:asset.size,mime:kind};
   fileRef.current=item;setFile(item);setConsent(false);operation.current=null;
  }catch(e){if(generation===epoch.current)setNotice(e instanceof Error?e.message:'File selection unavailable.');}
  finally{if(generation===epoch.current)setBusy(false);}
 };
 const ingest=async()=>{
  if(!file||!consent||disabled||busy||active.current)return;
  const ctrl=new AbortController(),generation=++epoch.current,account=getAuthToken(),selected=file;
  active.current=ctrl;setBusy(true);setNotice('Verifying selected bytes…');
  const current=()=>!ctrl.signal.aborted&&generation===epoch.current&&account===getAuthToken();
  try{
   const disk=new File(selected.uri);
   if(disk.size!==selected.size||selected.size>MAX_NATIVE_BYTES)throw Error('Selected file changed.');
   const bytes=await disk.bytes();
   if(bytes.length!==selected.size||!current())throw Error('Media selection detached or changed.');
   const digest=await sha(bytes);if(!current())throw Error('Media selection detached.');
   if(operation.current?.sha!==digest)operation.current={sha:digest,key:crawlRequestKey('native-media')};
   const receipt=await beginMedia({game,source:source.source_id,observation_digest:source.observation_digest,operation:operation.current.key,
       mime:selected.mime,total_bytes:selected.size,sha256:digest,rights_acknowledged:true,grant_seconds:86400},ctrl.signal);
   if(receipt.state!=='sealed'){
    const total=Math.ceil(bytes.length/BLOCK);
    for(let ordinal=0;ordinal<total;ordinal++){
     if(!current())throw Error('Media import detached.');
     const block=bytes.subarray(ordinal*BLOCK,(ordinal+1)*BLOCK),witness=await sha(block);
     await appendNativeMedia(receipt.media_id,ordinal,block,witness,ctrl.signal);
     if(current())setNotice('Verified '+(ordinal+1)+' / '+total+' blocks');
    }
    const sealed=await sealMedia(receipt.media_id,ctrl.signal);
    if(sealed.sha256!==digest||sealed.total_bytes!==selected.size)throw Error('Sealed media differs.');
   }
   if(current()){discard();setFile(null);setConsent(false);operation.current=null;setNotice('Exact local media sealed. Retention grant: 24 hours.');onChanged();}
  }catch(e){if(current())setNotice(e instanceof Error?e.message:'Media import held; retry the exact file.');}
  finally{if(active.current===ctrl){active.current=null;setBusy(false);}}
 };
 const button=(name:string,press:()=>void,off=false)=><TouchableOpacity accessibilityRole="button" disabled={disabled||busy||off} onPress={press} style={[s.button,(disabled||busy||off)&&s.disabled]}><Text style={s.buttonText}>{name}</Text></TouchableOpacity>;
 return <View style={s.check}>
  <Text style={s.label}>Import local audiovisual source</Text>
  <Text style={s.small}>Native intake supports files up to 32 MiB; verifies all bytes and uploads bounded blocks. Only import files you may retain.</Text>
  {button('Choose local media',()=>void choose())}
  {file&&<Text selectable style={s.small}>{file.name} · {file.mime} · {(file.size/1048576).toFixed(2)} MiB</Text>}
  {button(consent?'Retention rights acknowledged':'Acknowledge retention rights',()=>setConsent(x=>!x),!file)}
  {button(busy?'Working…':'Archive exact local media',()=>void ingest(),!file||!consent)}
  {file&&button('Discard selected copy',reset)}
  {!!notice&&<Text style={s.small}>{notice}</Text>}
 </View>;
}
