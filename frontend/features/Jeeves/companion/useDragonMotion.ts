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
/** Honor the operating system's screen reader so decorative motion can yield to text. */
export function useScreenReader():boolean{
 const [enabled,setEnabled]=useState(false);
 useEffect(()=>{
  let mounted=true;
  AccessibilityInfo.isScreenReaderEnabled().then(value=>{if(mounted)setEnabled(value)}).catch(()=>{});
  const subscription=AccessibilityInfo.addEventListener('screenReaderChanged',setEnabled);
  return()=>{mounted=false;subscription.remove()};
 },[]);
 return enabled;
}
