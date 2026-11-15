import React,{useEffect,useState} from 'react';
import {Text,View} from 'react-native';
import {getAuthToken} from '../../auth/gameforgeAuth';
import {verifiedBrowserMedia,type MediaRecord} from '../../product/dragonMediaArchiveClient';

export default function DragonMediaPlayer({record}:{record:MediaRecord}){
 const [uri,setUri]=useState(''),[error,setError]=useState('');
 useEffect(()=>{
  const controller=new AbortController();const token=getAuthToken();let url='',live=true;
  setUri('');setError('');
  function stop(){controller.abort();if(url){URL.revokeObjectURL(url);url='';}if(live)setUri('');}
  void verifiedBrowserMedia(record,controller.signal).then(blob=>{
   if(!live||controller.signal.aborted||token!==getAuthToken())return;
   url=URL.createObjectURL(blob);setUri(url);
  }).catch(e=>{if(live&&!controller.signal.aborted)setError(e instanceof Error?e.message:'Media unavailable.');});
  const timer=setInterval(()=>{if(token!==getAuthToken()||record.expires_at*1000<=Date.now()||document.hidden)stop();},250);
  const timeout=setTimeout(stop,Math.min(30000,Math.max(0,record.expires_at*1000-Date.now())));
  return()=>{live=false;clearInterval(timer);clearTimeout(timeout);stop();};
 },[record]);
 return <View>
  {!!error&&<Text>{error}</Text>}
  {!uri&&!error&&<Text>Verifying local media or playback window expired. Reopen to play.</Text>}
  {!!uri&&(record.mime.startsWith('video/')?React.createElement('video',{src:uri,controls:true,playsInline:true,preload:'metadata',style:{width:'100%',maxHeight:500}}):
   record.mime.startsWith('audio/')?React.createElement('audio',{src:uri,controls:true,preload:'metadata',style:{width:'100%'}}):
   React.createElement('img',{src:uri,alt:'Authorized retained visual reference',style:{width:'100%',objectFit:'contain',maxHeight:500}}))}
 </View>;
}
