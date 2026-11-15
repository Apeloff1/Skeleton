import React,{useEffect,useRef,useState} from 'react';
import {Text,TouchableOpacity,View} from 'react-native';
import {getAuthToken} from '../../auth/gameforgeAuth';
import {crawlRequestKey} from '../../product/crawlerClient';
import {allowedMediaMime,beginMedia,appendMedia,sealMedia,BLOCK,MAX_BROWSER_BYTES} from '../../product/dragonMediaArchiveClient';
import type {GameSource} from '../../product/dragonGameCorpusClient';
import s from './CrawlerWorkspace.styles';

export default function DragonMediaImport({game,source,onChanged,disabled}:{game:string;source:GameSource;onChanged:()=>void;disabled:boolean}){
 const [file,setFile]=useState<File|null>(null),[consent,setConsent]=useState(false),[progress,setProgress]=useState(''),[busy,setBusy]=useState(false);
 const active=useRef<AbortController|null>(null),operation=useRef<string|null>(null);
 useEffect(()=>()=>{active.current?.abort();},[game,source.source_id]);
 const ingest=async()=>{
  if(!file||!consent||disabled||busy||!allowedMediaMime(file.type)||file.size<1||file.size>MAX_BROWSER_BYTES)return;
  const ctrl=new AbortController(),account=getAuthToken();active.current=ctrl;setBusy(true);
  try{
   const mime=file.type;
   const bytes=await file.arrayBuffer();
   const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(x=>x.toString(16).padStart(2,'0')).join('');
   if(ctrl.signal.aborted||account!==getAuthToken())throw Error('Media import detached.');
   const key=operation.current||crawlRequestKey('media');operation.current=key;
   const receipt=await beginMedia({game,source:source.source_id,observation_digest:source.observation_digest,operation:key,mime,total_bytes:file.size,sha256:hash,rights_acknowledged:true,grant_seconds:86400},ctrl.signal);
   if(receipt.state!=='sealed'){
    for(let i=0;i<Math.ceil(file.size/BLOCK);i++){
     if(ctrl.signal.aborted||account!==getAuthToken())throw Error('Media import detached.');
     await appendMedia(receipt.media_id,i,file.slice(i*BLOCK,(i+1)*BLOCK),ctrl.signal);
     setProgress('Stored '+(i+1)+' / '+Math.ceil(file.size/BLOCK)+' blocks');
    }
    await sealMedia(receipt.media_id,ctrl.signal);
   }
   if(!ctrl.signal.aborted&&account===getAuthToken()){setProgress('Sealed exact local media. Retention grant: 24 hours.');setConsent(false);setFile(null);operation.current=null;onChanged();}
  }catch(e){if(!ctrl.signal.aborted)setProgress(e instanceof Error?e.message:'Import held. Retry the exact same file.');}
  finally{if(active.current===ctrl){active.current=null;setBusy(false);}}
 };
 return <View style={s.check}>
  <Text style={s.label}>Import local audiovisual source</Text>
  <Text style={s.small}>Choose a media file you have permission to retain. Browser import: up to 64 MiB. No remote video download or training authorization.</Text>
  {React.createElement('input',{type:'file',accept:'video/mp4,video/webm,audio/mpeg,audio/ogg,audio/wav,image/png,image/jpeg,image/webp',disabled:disabled||busy,onChange:(event:React.ChangeEvent<HTMLInputElement>)=>{operation.current=null;setConsent(false);setProgress('');setFile(event.target.files?.[0]||null);}})}
  <TouchableOpacity accessibilityRole="checkbox" accessibilityState={{checked:consent,disabled:disabled||busy}} disabled={disabled||busy} onPress={()=>setConsent(v=>!v)} style={s.button}><Text style={s.buttonText}>{consent?'Acknowledged: ':'Acknowledge: '}I hold rights to retain this local file.</Text></TouchableOpacity>
  <TouchableOpacity accessibilityRole="button" disabled={disabled||busy||!consent||!file||file.size>MAX_BROWSER_BYTES||!allowedMediaMime(file.type)} onPress={()=>void ingest()} style={s.button}><Text style={s.buttonText}>{busy?'Importing…':'Archive exact local media'}</Text></TouchableOpacity>
  {!!progress&&<Text style={s.small}>{progress}</Text>}
 </View>;
}
