import React from 'react';
import{Animated,Pressable,StyleSheet,Text,View}from'react-native';
import{Ionicons}from'@expo/vector-icons';
import type{DragonCompanionState}from'./dragonCompanionState';
import type{CompanionMotion}from'./dragonPreferences';
import {useDragonLife} from './useDragonLife';
import DragonAtmosphere from './DragonAtmosphere';
const C={ink:'#f8fafc',muted:'#cbd5e1',shell:'#f6d7a8',shellShade:'#b77945',shellDeep:'#8d5a32',dragon:'#c46a3a',dragonDark:'#6d3528',scale:'#a4532e',belly:'#f3c27a',bellyShade:'#e0a15a',ember:'#fb923c',blue:'#60a5fa',card:'#111827',night:'#141226'};
export default function DragonCompanion({state,reducedMotion=false,motion='gentle',level,unlocked=[],screenReader=false}:{state:DragonCompanionState;reducedMotion?:boolean;motion?:CompanionMotion;level?:number;unlocked?:readonly string[];screenReader?:boolean}){
 const life=useDragonLife(state,motion,reducedMotion);
 const summary=`Dragon companion. ${state.label}. ${state.detail}${screenReader?' Decorative motion is secondary to this description.':''}`;
 return <View style={s.wrap} accessibilityRole="summary" accessibilityLabel={summary}>
  <View style={s.scene}>
   <View style={s.moon}/><Text style={s.stars}>✦    ✧     ✦</Text>
   <View style={s.eggBack}/><View style={s.speckA}/><View style={s.speckB}/><View style={s.speckC}/>
   {unlocked.includes('star_cartographer')&&<Text style={s.starHalo}>✦ ✧ ✦</Text>}<DragonAtmosphere direction={life.direction} life={life}/><View style={s.nest}><Text style={s.nestText}>✦  ·  ✧  ·  ✦</Text></View>
   <Animated.View style={[s.dragon,{transform:[{translateY:life.v.bob.interpolate({inputRange:[0,1],outputRange:[0,-10*life.direction.amplitude]})},{translateY:life.v.lift},{rotate:life.v.tilt.interpolate({inputRange:[-1,1],outputRange:['-3deg','3deg']})}]}]}>
    <Animated.View style={[s.tail,{transform:[{rotate:life.v.tail.interpolate({inputRange:[-1,1],outputRange:['8deg','34deg']})},{translateX:life.v.tailGesture}]}]}><View style={s.tailSpade}/></Animated.View>
    {(state.wings||unlocked.includes('winged_builder'))&&<><Animated.View style={[s.wing,s.wingL,{transform:[{rotate:life.v.wings.interpolate({inputRange:[-1,1],outputRange:['-52deg','-10deg']})},{translateY:life.v.wingGesture}]}]}><View style={s.wingMembrane}/><View style={s.wingClaw}/></Animated.View><Animated.View style={[s.wing,s.wingR,{transform:[{rotate:life.v.wings.interpolate({inputRange:[-1,1],outputRange:['10deg','52deg']})},{translateY:life.v.wingGesture}]}]}><View style={s.wingMembrane}/><View style={s.wingClaw}/></Animated.View></>}
    <View style={s.body}/><View style={s.scaleA}/><View style={s.scaleB}/><View style={s.scaleC}/><View style={s.belly}/>{unlocked.includes('apprentice_forge')&&<View style={s.scarf}/>}
    <Animated.View style={[s.head,{transform:[{rotate:life.v.tilt.interpolate({inputRange:[-1,1],outputRange:['-5deg','6deg']})},{rotate:life.v.headGesture.interpolate({inputRange:[-25,25],outputRange:['-25deg','25deg']})}]}]}>
     <View style={s.hornL}/><View style={s.hornR}/><View style={s.earL}/><View style={s.earR}/>
     <Animated.View style={[s.eyeL,{transform:[{scaleY:life.v.blink}]}]}><Animated.View style={[s.pupil,{transform:[{translateX:life.v.eyeGesture}]}]}><View style={s.catchlight}/></Animated.View></Animated.View>
     <Animated.View style={[s.eyeR,{transform:[{scaleY:life.v.blink}]}]}><Animated.View style={[s.pupil,{transform:[{translateX:life.v.eyeGesture}]}]}><View style={s.catchlight}/></Animated.View></Animated.View>
     <View style={s.snout}/><View style={s.nostrilL}/><View style={s.nostrilR}/><View style={s.smile}/>
     <Animated.View style={[s.shellHat,{transform:[{rotate:life.v.shell.interpolate({inputRange:[-1,1],outputRange:['-11deg','-3deg']})},{translateY:life.v.hatGesture}]}]}><View style={s.shellRidge}/><View style={s.shellCrack}/></Animated.View>
     {state.glasses&&<View style={s.glasses}><View style={s.lens}/><View style={s.bridge}/><View style={s.lens}/><View style={s.bandage}><View style={s.bandagePad}/></View></View>}
    </Animated.View>
    {state.fire&&<Animated.View style={[s.fire,{opacity:life.v.glow}]}><Text style={s.fireText}>🔥</Text></Animated.View>}
    {state.embers&&<View style={s.embers}><Text style={s.emberText}>✦  ▪  ✧  ▫  ✦</Text></View>}
   </Animated.View>
   <View style={s.eggFront}><View style={s.eggCrack}/><View style={s.eggSpeck}/></View>
   {state.snuggly&&<View style={s.blanket}><Text style={s.heart}>♥</Text></View>}
  </View>
  <View style={s.copy}><View style={s.titleRow}>{level!==undefined&&<Text style={s.levelBadge}>LV {level}</Text>}<Ionicons name={state.glasses?'glasses-outline':state.fire?'flame-outline':'sparkles-outline'} size={17} color={state.fire?C.ember:C.blue}/><Text accessibilityLiveRegion="polite" style={s.title}>{state.label}</Text></View><Text style={s.detail}>{state.detail}</Text><Text accessibilityElementsHidden importantForAccessibility="no" style={s.thought}>{life.direction.beat.thought}</Text>
   <View style={s.track}><View style={[s.fill,{width:`${Math.round(state.progress*100)}%`}]}/></View>
   <Text style={s.mode}>{state.glasses?'DISTILLING · GEEKY GLASSES + WHITE BRIDGE BANDAGE':state.snuggly?'SNUGGLE MODE':'LIVE CRAWL MODE'}</Text>
   <View style={s.petRow}><Pressable onPress={life.pet} accessibilityRole="button" accessibilityLabel="Boop the little dragon" style={s.petButton}><Text style={s.petButtonText}>♡ Boop the dragon</Text></Pressable>{!!life.petMessage&&<Text style={s.petReply} accessibilityLiveRegion="polite">{life.petMessage}</Text>}</View>
  </View>
 </View>
}
const s=StyleSheet.create({
 wrap:{backgroundColor:'#121827',borderWidth:1,borderColor:'#344155',borderRadius:22,overflow:'hidden',minWidth:260},
 scene:{height:300,alignItems:'center',justifyContent:'flex-end',backgroundColor:C.night,position:'relative',overflow:'hidden'},
 moon:{position:'absolute',top:18,right:28,width:36,height:36,borderRadius:18,backgroundColor:'#fde68a',opacity:.85},
 stars:{position:'absolute',top:16,left:18,color:'#e2e8f0',opacity:.55,letterSpacing:4,fontSize:12},
 eggBack:{position:'absolute',bottom:28,width:210,height:196,borderRadius:110,backgroundColor:C.shell,borderWidth:7,borderColor:C.shellShade},
 speckA:{position:'absolute',bottom:150,left:78,width:10,height:8,borderRadius:5,backgroundColor:C.shellDeep,opacity:.35},
 speckB:{position:'absolute',bottom:118,right:86,width:14,height:9,borderRadius:6,backgroundColor:C.shellDeep,opacity:.28},
 speckC:{position:'absolute',bottom:86,left:96,width:8,height:8,borderRadius:4,backgroundColor:'#fff7ed',opacity:.35},
 nest:{position:'absolute',bottom:6,width:248,height:52,borderRadius:50,backgroundColor:'#4a2e24',alignItems:'center',justifyContent:'center'},nestText:{color:'#f59e0b',opacity:.5},
 dragon:{width:210,height:214,alignItems:'center',justifyContent:'center',zIndex:3},
 body:{position:'absolute',bottom:34,width:112,height:116,borderRadius:58,backgroundColor:C.dragon,borderWidth:3,borderColor:C.dragonDark},
 scaleA:{position:'absolute',bottom:92,width:18,height:14,borderRadius:9,backgroundColor:C.scale,zIndex:2},
 scaleB:{position:'absolute',bottom:74,left:78,width:16,height:12,borderRadius:8,backgroundColor:C.scale,opacity:.9,zIndex:2},
 scaleC:{position:'absolute',bottom:74,right:78,width:16,height:12,borderRadius:8,backgroundColor:C.scale,opacity:.9,zIndex:2},
 belly:{position:'absolute',bottom:42,width:54,height:84,borderRadius:32,backgroundColor:C.belly,borderBottomWidth:3,borderBottomColor:C.bellyShade},
 head:{position:'absolute',top:8,width:128,height:108,borderRadius:56,backgroundColor:C.dragon,borderWidth:3,borderColor:C.dragonDark},
 hornL:{position:'absolute',left:22,top:-16,width:12,height:28,borderRadius:8,backgroundColor:'#f0d2a0',transform:[{rotate:'-18deg'}]},
 hornR:{position:'absolute',right:22,top:-16,width:12,height:28,borderRadius:8,backgroundColor:'#f0d2a0',transform:[{rotate:'18deg'}]},
 earL:{position:'absolute',left:6,top:-8,width:28,height:36,backgroundColor:C.dragonDark,borderRadius:14,transform:[{rotate:'-24deg'}]},
 earR:{position:'absolute',right:6,top:-8,width:28,height:36,backgroundColor:C.dragonDark,borderRadius:14,transform:[{rotate:'24deg'}]},
 eyeL:{position:'absolute',left:22,top:32,width:32,height:36,borderRadius:18,backgroundColor:'#fff7ed',alignItems:'center',justifyContent:'center'},
 eyeR:{position:'absolute',right:22,top:32,width:32,height:36,borderRadius:18,backgroundColor:'#fff7ed',alignItems:'center',justifyContent:'center'},
 pupil:{width:15,height:19,borderRadius:9,backgroundColor:'#201a2d'},
 catchlight:{position:'absolute',top:2,right:2,width:5,height:5,borderRadius:3,backgroundColor:'#fff'},
 snout:{position:'absolute',left:44,top:64,width:40,height:28,borderRadius:16,backgroundColor:C.belly},
 nostrilL:{position:'absolute',left:52,top:74,width:6,height:5,borderRadius:3,backgroundColor:C.dragonDark},
 nostrilR:{position:'absolute',right:52,top:74,width:6,height:5,borderRadius:3,backgroundColor:C.dragonDark},
 smile:{position:'absolute',left:54,top:84,width:22,height:8,borderBottomWidth:2,borderColor:C.dragonDark,borderRadius:10},
 shellHat:{position:'absolute',top:-24,left:28,width:74,height:40,borderTopLeftRadius:42,borderTopRightRadius:42,backgroundColor:C.shell,borderWidth:3,borderColor:C.shellShade,transform:[{rotate:'-7deg'}]},
 shellRidge:{position:'absolute',top:6,left:18,width:34,height:6,borderRadius:4,backgroundColor:'#fff3d4',opacity:.7},
 shellCrack:{position:'absolute',bottom:-3,left:28,width:16,height:12,borderLeftWidth:3,borderBottomWidth:3,borderColor:C.shellShade,transform:[{rotate:'-35deg'}]},
 eggFront:{position:'absolute',bottom:24,width:214,height:92,borderBottomLeftRadius:100,borderBottomRightRadius:100,borderTopLeftRadius:24,borderTopRightRadius:24,backgroundColor:C.shell,borderWidth:7,borderColor:C.shellShade,zIndex:4},
 eggCrack:{position:'absolute',top:-6,left:86,width:38,height:20,borderTopWidth:5,borderRightWidth:5,borderColor:C.shellShade,transform:[{rotate:'18deg'}]},
 eggSpeck:{position:'absolute',bottom:28,left:36,width:12,height:8,borderRadius:6,backgroundColor:C.shellDeep,opacity:.3},
 wing:{position:'absolute',top:78,width:72,height:84,backgroundColor:'#8b4936',borderWidth:3,borderColor:C.dragonDark,borderRadius:36},
 wingL:{left:-18,transform:[{rotate:'-35deg'}]},wingR:{right:-18,transform:[{rotate:'35deg'}]},
 wingMembrane:{position:'absolute',left:10,top:16,width:46,height:48,borderRadius:24,backgroundColor:'#c47a62',opacity:.55},
 wingClaw:{position:'absolute',top:8,width:8,height:16,borderRadius:4,backgroundColor:C.dragonDark},
 tail:{position:'absolute',right:2,bottom:38,width:74,height:26,borderRadius:20,backgroundColor:C.dragonDark,transform:[{rotate:'22deg'}]},
 tailSpade:{position:'absolute',right:-8,top:-6,width:22,height:22,borderRadius:6,backgroundColor:C.dragon,transform:[{rotate:'45deg'}]},
 glasses:{position:'absolute',left:16,top:26,width:96,height:44,flexDirection:'row',alignItems:'center',zIndex:8},
 lens:{width:36,height:36,borderRadius:12,borderWidth:5,borderColor:'#171717',backgroundColor:'#93c5fd55'},
 bridge:{width:22,height:6,backgroundColor:'#171717'},
 bandage:{position:'absolute',left:38,top:12,width:26,height:14,borderRadius:3,backgroundColor:'#f8fafc',transform:[{rotate:'-4deg'}],alignItems:'center',justifyContent:'center'},
 bandagePad:{width:9,height:8,borderRadius:2,backgroundColor:'#e5e7eb'},
 fire:{position:'absolute',right:-28,top:78,zIndex:8},fireText:{fontSize:58},embers:{position:'absolute',right:-48,top:132},emberText:{color:'#fdba74',fontSize:15},
 blanket:{position:'absolute',bottom:18,width:220,height:58,borderRadius:50,backgroundColor:'#8b3f57',zIndex:6,opacity:.94},heart:{color:'#fecdd3',fontSize:18,textAlign:'center',marginTop:8},
 copy:{padding:15,gap:7,backgroundColor:C.card},
 starHalo:{position:'absolute',top:8,color:'#fcd34d',fontSize:24,fontWeight:'900',letterSpacing:9,zIndex:5},
 scarf:{position:'absolute',bottom:86,width:104,height:14,borderRadius:7,backgroundColor:'#dba552',borderColor:'#facc15',borderWidth:1,zIndex:3},
 levelBadge:{fontWeight:'900',fontSize:10,color:'#422006',backgroundColor:'#fbbf24',borderRadius:7,overflow:'hidden',paddingHorizontal:7,paddingVertical:3},
 thought:{fontSize:11,color:'#fda4af',fontStyle:'italic',minHeight:16},
 petRow:{flexDirection:'row',alignItems:'center',flexWrap:'wrap',gap:8,marginTop:5},
 petButton:{backgroundColor:'#44304b',borderColor:'#825b89',borderWidth:1,paddingVertical:8,paddingHorizontal:13,borderRadius:18},
 petButtonText:{color:'#fce7f3',fontSize:11,fontWeight:'700'},petReply:{color:'#fbcfe8',fontSize:11,flexShrink:1},
 titleRow:{flexDirection:'row',alignItems:'center',gap:7},title:{color:C.ink,fontSize:15,fontWeight:'800'},detail:{color:C.muted,fontSize:12,lineHeight:18},
 track:{height:5,borderRadius:5,backgroundColor:'#263244',overflow:'hidden'},fill:{height:'100%',backgroundColor:C.ember,borderRadius:5},mode:{fontSize:9,fontWeight:'800',letterSpacing:.7,color:'#94a3b8'}
});
