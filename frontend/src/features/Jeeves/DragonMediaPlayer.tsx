import React,{useEffect,useState} from 'react';
import {AppState,Text,View} from 'react-native';
import {useVideoPlayer,VideoView} from 'expo-video';
import {getAuthToken} from '../../auth/gameforgeAuth';
import {nativeMediaSource,type MediaRecord} from '../../product/dragonMediaArchiveClient';

type Seek={seconds:number;nonce:number}|null;
function Video({record,seek}:{record:MediaRecord;seek?:Seek}){
 const [live,setLive]=useState(true);
 const player=useVideoPlayer(nativeMediaSource(record),p=>{p.loop=false;});
 useEffect(()=>{
  const token=getAuthToken();
  const stop=()=>{player.pause();setLive(false);};
  const sub=AppState.addEventListener('change',x=>{if(x!=='active')stop();});
  const timer=setInterval(()=>{if(getAuthToken()!==token||Date.now()>=record.expires_at*1000)stop();},250);
  const timeout=setTimeout(stop,Math.min(30000,Math.max(0,record.expires_at*1000-Date.now())));
  return()=>{clearInterval(timer);clearTimeout(timeout);sub.remove();player.pause();};
 },[player,record]);
 useEffect(()=>{
  if(!live||!seek||!Number.isFinite(seek.seconds)||seek.seconds<0||seek.seconds>604800)return;
  try{player.currentTime=seek.seconds;}catch{/* unsupported seek held by native player */}
 },[player,seek,live]);
 return live?<VideoView player={player} style={{width:'100%',height:260}} nativeControls/>:<Text>Playback authorization window ended. Reopen the video.</Text>;
}
export default function DragonMediaPlayer({record,seek}:{record:MediaRecord;seek?:Seek}){
 if(!record.mime.startsWith('video/'))return <Text>Inline native playback currently supports video. Audio and images can be viewed through the web workspace.</Text>;
 if(record.state!=='sealed'||record.expires_at*1000<=Date.now()||!getAuthToken())return <Text>Media authorization unavailable.</Text>;
 return <View><Video record={record} seek={seek}/></View>;
}
