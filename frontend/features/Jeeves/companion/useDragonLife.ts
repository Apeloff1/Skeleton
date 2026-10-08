import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {Animated,AppState,Easing} from 'react-native';
import type {DragonCompanionState} from './dragonCompanion';
import type {CompanionMotion} from './dragonPreferences';
import {directDragon} from './dragonChoreography';

const PET_REACTIONS=[
 'Mrrp! Tiny nose boop.', 'A happy little squeak!', 'His tail says thank you.',
 'The eggshell hat almost fell off!', 'A sparkle just for you.',
 'A dragon-sized cuddle, in miniature.', 'He gives you a tiny wave.',
 'The world feels extra cozy.', 'A warm, happy rumble.',
] as const;
const timing=(value:Animated.Value,toValue:number,duration:number)=>
 Animated.timing(value,{toValue,duration,easing:Easing.inOut(Easing.sin),useNativeDriver:true});
const oscillate=(value:Animated.Value,low:number,high:number,duration:number)=>
 Animated.loop(Animated.sequence([timing(value,high,duration),timing(value,low,duration)]));
const defaultValues=()=>({
 bob:new Animated.Value(0),tilt:new Animated.Value(0),
 blink:new Animated.Value(1),tail:new Animated.Value(0),
 wings:new Animated.Value(0),shell:new Animated.Value(0),
 glow:new Animated.Value(1),twinkle:new Animated.Value(0),
 heart:new Animated.Value(0),
});
type Values=ReturnType<typeof defaultValues>;

/**
 * One phase-aware animation clock for the existing dragon.
 * Native-driver transforms and opacity only; zero JS per-frame updates.
 * Background, reduced motion and off all stop every repeating animation.
 * Cosmetic boops never modify authoritative crawler state.
 */
export function useDragonLife(
 state:DragonCompanionState, motion:CompanionMotion, reducedMotion:boolean,
){
 const values=useRef<Values>(null);
 if(values.current===null)values.current=defaultValues();
 const v=values.current;
 const [active,setActive]=useState(AppState.currentState==='active');
 const [beatIndex,setBeatIndex]=useState(0);
 const [petCount,setPetCount]=useState(0);
 const [petMessage,setPetMessage]=useState('');
 const mode=reducedMotion?'off':motion;
 const direction=useMemo(()=>directDragon(state,mode,beatIndex,reducedMotion),
  [state.phase,state.fire,state.embers,state.glasses,state.snuggly,mode,beatIndex,reducedMotion]);
 const enabled=active&&direction.animated;
 useEffect(()=>{
  const subscription=AppState.addEventListener('change',next=>setActive(next==='active'));
  return ()=>subscription.remove();
 },[]);
 useEffect(()=>{
  setBeatIndex(0);
 },[state.phase]);
 useEffect(()=>{
  if(!enabled)return;
  const id=setInterval(()=>setBeatIndex(prev=>(prev+1)%12),direction.tempoMs);
  return ()=>clearInterval(id);
 },[direction.tempoMs,enabled,state.phase]);
 useEffect(()=>{
  const all=Object.values(v);
  all.forEach(value=>value.stopAnimation());
  if(!enabled){
   v.bob.setValue(0);v.tilt.setValue(0);v.blink.setValue(1);
   v.tail.setValue(0);v.wings.setValue(0);v.shell.setValue(0);
   v.glow.setValue(1);v.twinkle.setValue(0);v.heart.setValue(0);
   return;
  }
  const duration=mode==='gentle'?2000:1250;
  const loops:Animated.CompositeAnimation[]=[
   oscillate(v.bob,0,1,duration),
   Animated.loop(Animated.sequence([
    Animated.delay(mode==='gentle'?5200:3200),
    timing(v.blink,.08,75),timing(v.blink,1,105),
   ])),
  ];
  if(mode==='full'){
   loops.push(oscillate(v.tilt,-1,1,2600));
   loops.push(oscillate(v.tail,-1,1,state.snuggly?1300:460));
   loops.push(oscillate(v.shell,-1,1,1900));
   if(state.wings)loops.push(oscillate(v.wings,-1,1,340));
   if(direction.particle!=='none')loops.push(oscillate(v.twinkle,0,1,1350));
  }
  if(state.fire||state.embers){
   loops.push(oscillate(v.glow,.45,1,state.fire?380:950));
  }
  loops.forEach(a=>a.start());
  return ()=>loops.forEach(a=>a.stop());
 },[enabled,mode,state.phase,state.wings,state.fire,state.embers,state.snuggly,direction.particle,v]);
 const pet=useCallback(()=>{
  const count=petCount+1;
  setPetCount(count);
  setPetMessage(PET_REACTIONS[(count-1)%PET_REACTIONS.length]);
  v.heart.stopAnimation();
  v.heart.setValue(0);
  if(enabled){
   Animated.sequence([timing(v.heart,1,340),timing(v.heart,0,700)]).start();
  }
 },[enabled,petCount,v]);
 useEffect(()=>{
  if(!petMessage)return;
  const id=setTimeout(()=>setPetMessage(''),3500);
  return ()=>clearTimeout(id);
 },[petMessage,petCount]);
 return {v,direction,enabled,pet,petMessage,mode};
}
