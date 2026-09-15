/**
 * useReduceMotion — single source of truth for the system reduce-motion
 * preference. Use this in every animated component instead of querying
 * AccessibilityInfo ad-hoc (Cat-4.5 + Cat-5).
 */
import React from 'react';
import { AccessibilityInfo } from 'react-native';

export function useReduceMotion(): boolean {
  const [rm, setRm] = React.useState(false);
  React.useEffect(() => {
    AccessibilityInfo.isReduceMotionEnabled().then(setRm).catch(() => {});
    const sub = AccessibilityInfo.addEventListener('reduceMotionChanged', setRm);
    return () => { try { (sub as any)?.remove?.(); } catch {} };
  }, []);
  return rm;
}

export default useReduceMotion;
