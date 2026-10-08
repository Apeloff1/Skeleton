/** Pure watch-along player integration; caller owns the actual video player. */
import React,{useMemo,useState} from 'react';
import {Pressable,StyleSheet,Text,View} from 'react-native';
import DragonWatchAlong from './DragonWatchAlong';
import {EMPTY_WATCH_TIMELINE,ingestPlayerSnapshot,type WatchAlongTimeline} from './dragonWatchTimeline';
import type {PlayerSnapshot} from './dragonPlayerBridge';
import type {WatchSignal} from './dragonWatch';

export function useDragonWatchSession(){
 const [timeline,setTimeline]=useState<WatchAlongTimeline>(EMPTY_WATCH_TIMELINE);
 const onPlayback=React.useCallback((snapshot:PlayerSnapshot)=>{
  setTimeline(current=>ingestPlayerSnapshot(current,snapshot,Date.now()));
 },[]);
 const latest=timeline.events[timeline.events.length-1]?.signal;
 return {onPlayback,latest,timeline,reset:()=>setTimeline(EMPTY_WATCH_TIMELINE)};
}
export default function DragonWatchDock({signal,compact=false}:{signal:WatchSignal;compact?:boolean}){
 const [visible,setVisible]=useState(true);
 const progress=useMemo(()=>signal.durationMs&&signal.durationMs>0?Math.max(0,Math.min(100,Math.round(signal.positionMs/signal.durationMs*100))):null,[signal.positionMs,signal.durationMs]);
 return <View style={styles.dock}>
  <Pressable accessibilityRole="button" accessibilityState={{expanded:visible}} accessibilityLabel={visible?'Hide dragon watch companion':'Show dragon watch companion'} onPress={()=>setVisible(v=>!v)} style={styles.toggle}>
   <Text style={styles.toggleText}>{visible?'▾':'▸'} 🐉 Watch with me {progress===null?'':`· ${progress}%`}</Text>
  </Pressable>
  {visible&&<View style={compact?styles.compact:styles.expanded}><DragonWatchAlong signal={signal}/></View>}
 </View>;
}
const styles=StyleSheet.create({
 dock:{width:'100%',maxWidth:380,alignSelf:'center',borderRadius:18,overflow:'hidden',backgroundColor:'#0f172a'},
 toggle:{paddingHorizontal:14,paddingVertical:12,backgroundColor:'#1e293b'},
 toggleText:{fontSize:12,color:'#f8fafc',fontWeight:'700'},
 expanded:{padding:8},compact:{padding:3,transform:[{scale:.86}],marginVertical:-18}
});
