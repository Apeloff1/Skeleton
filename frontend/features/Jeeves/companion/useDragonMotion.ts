import {useEffect,useState} from 'react';
import {AccessibilityInfo} from 'react-native';
/** Honor the operating system's reduced-motion preference. */
export function useReducedMotion():boolean{
 const [reduced,setReduced]=useState(false);
 useEffect(()=>{
  let mounted=true;
  AccessibilityInfo.isReduceMotionEnabled().then(v=>{if(mounted)setReduced(v)}).catch(()=>{});
  const subscription=AccessibilityInfo.addEventListener('reduceMotionChanged',setReduced);
  return ()=>{mounted=false;subscription.remove()};
 },[]);
 return reduced;
}
