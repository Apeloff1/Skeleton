import React,{useEffect,useState} from 'react';
import {AppState,Image,Text,TouchableOpacity,View} from 'react-native';
import {useVideoPlayer,VideoView} from 'expo-video';
import {useAudioPlayer,useAudioPlayerStatus} from 'expo-audio';
import {getAuthToken} from '../../auth/gameforgeAuth';
import {nativeMediaSource,verifyMediaAuthority,type MediaRecord} from '../../product/dragonMediaArchiveClient';

function useAuthority(record:MediaRecord){
 const [live,setLive]=useState(false);
 useEffect(()=>{
  const ctrl=new AbortController(),token=getAuthToken();let valid=true,deadline=0,checking=false;
  const stop=()=>{if(!valid)return;valid=false;ctrl.abort();setLive(false);};
  const renew=()=>{
   if(!valid||checking)return;
   checking=true;
   void verifyMediaAuthority(record,ctrl.signal).then(()=>{
    if(!valid||token!==getAuthToken()||Date.now()>=record.expires_at*1000){stop();return;}
    deadline=Date.now()+20000;setLive(true);
   }).catch(stop).finally(()=>{checking=false;});
  };
  renew();
  const app=AppState.addEventListener('change',x=>{if(x!=='active')stop();});
  const timer=setInterval(()=>{if(token!==getAuthToken()||Date.now()>=record.expires_at*1000||deadline>0&&Date.now()>=deadline)stop();},250);
  const heartbeat=setInterval(renew,8000);
  return()=>{valid=false;ctrl.abort();app.remove();clearInterval(timer);clearInterval(heartbeat);};
 },[record]);
 return live;
}

function Video({record}:{record:MediaRecord}){
 const player=useVideoPlayer(nativeMediaSource(record),p=>{p.loop=false;});
 useEffect(()=>()=>{player.pause();},[player]);
 return <VideoView player={player} style={{width:'100%',height:260}} nativeControls/>;
}
function Audio({record}:{record:MediaRecord}){
 const source=nativeMediaSource(record);
 const player=useAudioPlayer({uri:source.uri,headers:source.headers});
 const status=useAudioPlayerStatus(player);
 useEffect(()=>()=>{player.pause();},[player]);
 return <View><Text>Position: {Math.floor(status.currentTime||0)} s / {Math.floor(status.duration||0)} s</Text>
  <TouchableOpacity accessibilityRole="button" onPress={()=>{if(status.playing)player.pause();else player.play();}}><Text>{status.playing?'Pause audio':'Play audio'}</Text></TouchableOpacity>
  <TouchableOpacity accessibilityRole="button" onPress={()=>{void player.seekTo(0);}}><Text>Restart audio</Text></TouchableOpacity>
 </View>;
}
function Visual({record}:{record:MediaRecord}){
 const source=nativeMediaSource(record);
 return <Image accessibilityLabel="Retained visual reference" source={{uri:source.uri,headers:source.headers,cache:'reload'}} style={{width:'100%',height:260}} resizeMode="contain"/>;
}
export default function DragonMediaPlayer({record}:{record:MediaRecord}){
 const live=useAuthority(record);
 if(!live)return <Text>Verifying local media or playback authorization expired. Reopen to play.</Text>;
 if(record.state!=='sealed'||record.expires_at*1000<=Date.now()||!getAuthToken())return <Text>Media authorization unavailable.</Text>;
 return <View>{record.mime.startsWith('video/')?<Video record={record}/>:record.mime.startsWith('audio/')?<Audio record={record}/>:<Visual record={record}/>}</View>;
}
