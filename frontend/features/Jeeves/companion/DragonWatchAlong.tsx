import React,{useEffect,useRef} from 'react';
import {Animated,StyleSheet,Text,View} from 'react-native';
import DragonCompanion from './DragonCompanion';
import {INITIAL_DRAGON_STATE,type DragonCompanionState} from './dragonCompanion';
import {watchPose,type WatchSignal} from './dragonWatch';
import {useReducedMotion} from './useDragonMotion';

export default function DragonWatchAlong({signal}:{signal:WatchSignal}){
 const reducedMotion=useReducedMotion();
 const pose=watchPose(signal);
 const bounce=useRef(new Animated.Value(0)).current;
 const blink=useRef(new Animated.Value(1)).current;
 const flutter=useRef(new Animated.Value(0)).current;
 useEffect(()=>{
  if(reducedMotion){blink.stopAnimation();flutter.stopAnimation();blink.setValue(1);flutter.setValue(0);return}
  const blinkAnimation=Animated.sequence([Animated.delay(750),Animated.timing(blink,{toValue:.1,duration:85,useNativeDriver:true}),Animated.timing(blink,{toValue:1,duration:110,useNativeDriver:true})]);
  const flutterAnimation=Animated.sequence([Animated.timing(flutter,{toValue:1,duration:140,useNativeDriver:true}),Animated.timing(flutter,{toValue:0,duration:200,useNativeDriver:true})]);
  if(pose.blink)blinkAnimation.start();
  if(pose.wingWave)flutterAnimation.start();
  return()=>{blinkAnimation.stop();flutterAnimation.stop()};
 },[blink,flutter,reducedMotion,pose.blink,pose.wingWave,signal.kind]);
 useEffect(()=>{
  if(reducedMotion){bounce.stopAnimation();bounce.setValue(0);return}
  const animation=Animated.sequence([
   Animated.spring(bounce,{toValue:pose.wingWave?-9:pose.tilt?4:-2,useNativeDriver:true,friction:5}),
   Animated.spring(bounce,{toValue:0,useNativeDriver:true,friction:6})
  ]);
  animation.start();return()=>animation.stop();
 },[bounce,pose.wingWave,pose.tilt,reducedMotion,signal.kind]);
 const state:DragonCompanionState={...INITIAL_DRAGON_STATE,phase:pose.mood==='sleepy'?'sleeping':'listening',
  label:pose.label,detail:pose.detail,progress:pose.progress,snuggly:true};
 return <View style={styles.container} accessibilityLabel={pose.label}>
  <Animated.View style={{transform:[{translateY:bounce},{rotate:reducedMotion?'0deg':pose.tilt+'deg'}]}}>
   <DragonCompanion state={state} reducedMotion={reducedMotion}/>
  </Animated.View>
  <View style={styles.accessories} accessible={false}>
   {pose.blink&&<Animated.Text style={[styles.accessory,{opacity:blink}]}>✨</Animated.Text>}
   {pose.wingWave&&<Animated.Text style={[styles.accessory,{transform:[{translateY:flutter.interpolate({inputRange:[0,1],outputRange:[0,-14]})}]}]}>🪽</Animated.Text>}
   {pose.popcorn&&<Text style={styles.accessory} accessibilityLabel="Tiny popcorn bowl">🍿</Text>}
   {pose.notebook&&<Text style={styles.accessory} accessibilityLabel="Taking notes">📓</Text>}
   {pose.heart&&<Text style={styles.accessory} accessibilityLabel="Delighted">💗</Text>}
   {pose.mood==='sleepy'&&<Text style={styles.accessory} accessibilityLabel="Sleepy">💤</Text>}
  </View>
  <Text style={styles.caption}>{pose.mood==='taking-notes'?'OBSERVATION READY · NOT YET SAVED':'WATCHING TOGETHER · NO AUTOMATIC INGESTION'}</Text>
 </View>;
}
const styles=StyleSheet.create({
 container:{width:'100%',maxWidth:360,alignSelf:'center',gap:5},
 accessories:{flexDirection:'row',justifyContent:'center',gap:12,marginTop:-12},
 accessory:{fontSize:25},
 caption:{color:'#94a3b8',fontSize:10,textAlign:'center',fontWeight:'700',letterSpacing:.5}
});
