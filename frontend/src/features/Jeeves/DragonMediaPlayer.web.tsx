import React,{useEffect,useState} from 'react';
import {Text,View} from 'react-native';
import {getAuthToken} from '../../auth/gameforgeAuth';
import {verifiedBrowserMedia,verifyMediaAuthority,type MediaRecord} from '../../product/dragonMediaArchiveClient';

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
  let deadline=Date.now()+20000,checking=false;
  const heartbeat=setInterval(()=>{
   if(controller.signal.aborted)return;
   if(Date.now()>=deadline){stop();return;}
   if(checking)return;
   checking=true;
   void verifyMediaAuthority(record,controller.signal).then(()=>{if(!controller.signal.aborted)deadline=Date.now()+20000;}).catch(stop).finally(()=>{checking=false;});
  },8000);
  const guard=setInterval(()=>{if(Date.now()>=deadline)stop();},500);
  return()=>{live=false;clearInterval(timer);clearInterval(heartbeat);clearInterval(guard);stop();};
 },[record]);
 return <View>
  {!!error&&<Text>{error}</Text>}
  {!uri&&!error&&<Text>Verifying local media or playback window expired. Reopen to play.</Text>}
  {!!uri&&(record.mime.startsWith('video/')?React.createElement('video',{src:uri,controls:true,playsInline:true,preload:'metadata',style:{width:'100%',maxHeight:500}}):
   record.mime.startsWith('audio/')?React.createElement('audio',{src:uri,controls:true,preload:'metadata',style:{width:'100%'}}):
   React.createElement('img',{src:uri,alt:'Authorized retained visual reference',style:{width:'100%',objectFit:'contain',maxHeight:500}}))}
 </View>;
}
