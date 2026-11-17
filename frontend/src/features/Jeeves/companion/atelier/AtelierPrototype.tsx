import React from 'react';
import { Text } from 'react-native';
import type { DragonCompanionState } from '../dragonCompanionState';
export interface AtelierPrototypeProps {
  state: DragonCompanionState;
  reducedMotion: boolean;
  onOpenChange?: (open:boolean)=>void;
}
/** Platform fallback; no claim that the native Unreal runtime is integrated. */
export default function AtelierPrototype(_props: AtelierPrototypeProps) {
  return <Text style={{color:'#94a3b8',fontSize:12}}>Original 3D prototype is available in the web workspace after local asset admission. Native 3D qualification is pending.</Text>;
}
