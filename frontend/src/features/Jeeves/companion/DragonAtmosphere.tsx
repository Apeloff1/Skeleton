import React from 'react';
import {Animated,StyleSheet,Text,View} from 'react-native';
import type {DragonDirection} from './dragonChoreography';
import type {useDragonLife} from './useDragonLife';

const MARKS={hearts:['♥','♡','♥','♡'],stars:['✦','✧','✶','✦'],
 embers:['✦','•','✶','•'],thoughts:['✦','·','✧','·'],
 wind:['⌁','˙','⌁','˙'],none:[]} as const;
const POSITIONS=[
 {left:'13%',top:'22%'},{left:'75%',top:'19%'},
 {left:'6%',top:'58%'},{left:'88%',top:'62%'},
] as const;

/** At most four decorative glyphs. Visual state never implies crawler success. */
export default function DragonAtmosphere({
 direction,life,
}:{direction:DragonDirection;life:ReturnType<typeof useDragonLife>}){
 const marks=MARKS[direction.particle];
 return <View pointerEvents="none" accessibilityElementsHidden importantForAccessibility="no-hide-descendants" style={StyleSheet.absoluteFill}>
  {marks.slice(0,direction.layers).map((mark,i)=>
   <Animated.View key={i} style={[s.particle,POSITIONS[i],{
    opacity:life.v.twinkle.interpolate({inputRange:[0,1],outputRange:[.13,.8-(i%2)*.15]}),
    transform:[{translateY:life.v.twinkle.interpolate({inputRange:[0,1],outputRange:[i%2?8:-8,i%2?-8:8]})},
     {scale:life.v.twinkle.interpolate({inputRange:[0,1],outputRange:[.72,1.12]})},{translateX:life.v.fxGesture}],
   }]}>
    <Text style={[s.glyph,{color:direction.tint,fontSize:i%2?22:17}]}>{mark}</Text>
   </Animated.View>)}
  <Animated.View style={[s.petHeart,{
   opacity:life.v.heart,
   transform:[{translateY:life.v.heart.interpolate({inputRange:[0,1],outputRange:[0,-24]})},
    {scale:life.v.heart.interpolate({inputRange:[0,1],outputRange:[.65,1.32]})}],
  }]}>
   <Text style={s.petGlyph}>♥</Text>
  </Animated.View>
 </View>;
}
const s=StyleSheet.create({
 particle:{position:'absolute',alignItems:'center',justifyContent:'center'},
 glyph:{fontWeight:'800',textShadowColor:'#fbbf2466',textShadowRadius:12},
 petHeart:{position:'absolute',left:'59%',top:24},
 petGlyph:{fontSize:34,color:'#fda4af'},
});
