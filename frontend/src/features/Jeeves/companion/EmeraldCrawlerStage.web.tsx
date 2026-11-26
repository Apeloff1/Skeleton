import React,{useEffect,useRef,useState} from 'react';
import {View,Text,StyleSheet} from 'react-native';
import type { EmeraldStageProps } from './emeraldStageTypes';
import { mountEmerald, type MountedEmerald } from './emeraldWebRenderer';

export default function EmeraldCrawlerStage({projection,reducedMotion,fallback}:EmeraldStageProps){
  const canvas=useRef<HTMLCanvasElement|null>(null);
  const handle=useRef<MountedEmerald|null>(null);
  const latest=useRef({projection,reducedMotion});
  const [ready,setReady]=useState(false);
  const [unavailable,setUnavailable]=useState(false);
  useEffect(()=>{latest.current={projection,reducedMotion};handle.current?.setProjection(projection);handle.current?.setReduced(reducedMotion);},[projection,reducedMotion]);
  useEffect(()=>{
    const element=canvas.current;if(!element)return;
    const controller=new AbortController();let mounted=true;
    setReady(false);setUnavailable(false);
    const fail=()=>{if(mounted){setUnavailable(true);setReady(false);}};
    void mountEmerald(element,controller.signal,fail).then(runtime=>{
      if(!mounted){runtime.dispose();return;}
      handle.current=runtime;runtime.setProjection(latest.current.projection);runtime.setReduced(latest.current.reducedMotion);setReady(true);
    }).catch(fail);
    return ()=>{mounted=false;controller.abort();handle.current?.dispose();handle.current=null;};
  },[projection.sessionId]);
  const target=projection.target;
  return <View>
    <View style={[styles.surface,!ready&&styles.hidden]}>
      {React.createElement('canvas',{ref:canvas,'aria-hidden':true,style:{width:'100%',height:'100%',display:'block',pointerEvents:'none'}})}
    </View>
    {!ready&&fallback}
    {unavailable&&<Text style={styles.note}>Emerald art pack unavailable or unverified. Using the existing companion.</Text>}
    {ready&&<View accessibilityLiveRegion="polite" style={styles.status}>
      <Text style={styles.title}>Emerald · {projection.availability==='live'?'recorded crawler activity':projection.availability==='stale'?'connection unavailable':'resting'}</Text>
      {target&&projection.availability!=='stale'&&<Text selectable style={styles.note}>{target.captured?'Capture recorded (not reviewed or learned): ':'Observed target: '}{target.url??'source'}</Text>}
      <Text style={styles.note}>Decorative motion only. No new network requests, review or XP authority.</Text>
    </View>}
  </View>;
}
const styles=StyleSheet.create({surface:{height:300,overflow:'hidden',backgroundColor:'#081b1b',borderRadius:16},hidden:{height:0,opacity:0},status:{paddingVertical:8,gap:4},title:{color:'#e6c773',fontWeight:'600'},note:{color:'#a3bdb8',fontSize:12}});
