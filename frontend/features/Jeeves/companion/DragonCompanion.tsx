import React,{useEffect,useRef}from'react';
import{Animated,Easing,StyleSheet,Text,View}from'react-native';
import{Ionicons}from'@expo/vector-icons';
import type{DragonCompanionState}from'./dragonCompanion';
const C={ink:'#f8fafc',muted:'#cbd5e1',shell:'#f5d9a7',shellShade:'#c99a63',dragon:'#b86538',dragonDark:'#6d3528',belly:'#f0bd77',ember:'#fb923c',blue:'#60a5fa',card:'#111827'};
export default function DragonCompanion({state,reducedMotion=false}:{state:DragonCompanionState;reducedMotion?:boolean}){
 const bob=useRef(new Animated.Value(0)).current;const glow=useRef(new Animated.Value(.35)).current;
 useEffect(()=>{if(reducedMotion){bob.setValue(0);return}const a=Animated.loop(Animated.sequence([Animated.timing(bob,{toValue:-5,duration:900,easing:Easing.inOut(Easing.sin),useNativeDriver:true}),Animated.timing(bob,{toValue:2,duration:900,easing:Easing.inOut(Easing.sin),useNativeDriver:true})]));a.start();return()=>a.stop()},[bob,reducedMotion,state.phase]);
 useEffect(()=>{const a=Animated.loop(Animated.sequence([Animated.timing(glow,{toValue:.9,duration:state.fire?260:900,useNativeDriver:true}),Animated.timing(glow,{toValue:.3,duration:state.fire?260:900,useNativeDriver:true})]));a.start();return()=>a.stop()},[glow,state.fire]);
 return <View style={s.wrap} accessibilityRole="summary" accessibilityLabel={`Dragon companion. ${state.label}. ${state.detail}`}>
  <View style={s.scene}>
   <View style={s.eggBack}/><View style={s.nest}><Text style={s.nestText}>✦  ·  ✧  ·  ✦</Text></View>
   <Animated.View style={[s.dragon,{transform:[{translateY:bob}]}]}>
    <View style={s.tail}/>{state.wings&&<><View style={[s.wing,s.wingL]}/><View style={[s.wing,s.wingR]}/></>}
    <View style={s.body}/><View style={s.belly}/>
    <View style={s.head}>
     <View style={s.earL}/><View style={s.earR}/><View style={s.eyeL}><View style={s.pupil}/></View><View style={s.eyeR}><View style={s.pupil}/></View>
     <View style={s.snout}/><View style={s.smile}/>
     <View style={s.shellHat}><View style={s.shellCrack}/></View>
     {state.glasses&&<View style={s.glasses}><View style={s.lens}/><View style={s.bridge}/><View style={s.lens}/><View style={s.bandage}><View style={s.bandagePad}/></View></View>}
    </View>
    {state.fire&&<Animated.View style={[s.fire,{opacity:glow}]}><Text style={s.fireText}>🔥</Text></Animated.View>}
    {state.embers&&<View style={s.embers}><Text style={s.emberText}>✦  ▪  ✧  ▫  ✦</Text></View>}
   </Animated.View>
   <View style={s.eggFront}><View style={s.eggCrack}/></View>
   {state.snuggly&&<View style={s.blanket}><Text style={s.heart}>♥</Text></View>}
  </View>
  <View style={s.copy}><View style={s.titleRow}><Ionicons name={state.glasses?'glasses-outline':state.fire?'flame-outline':'sparkles-outline'} size={17} color={state.fire?C.ember:C.blue}/><Text style={s.title}>{state.label}</Text></View><Text style={s.detail}>{state.detail}</Text>
   <View style={s.track}><View style={[s.fill,{width:`${Math.round(state.progress*100)}%`}]}/></View>
   <Text style={s.mode}>{state.glasses?'DISTILLING · GEEKY GLASSES + WHITE BRIDGE BANDAGE':state.snuggly?'SNUGGLE MODE':'LIVE CRAWL MODE'}</Text>
  </View>
 </View>
}
const s=StyleSheet.create({
 wrap:{backgroundColor:'#121827',borderWidth:1,borderColor:'#344155',borderRadius:22,overflow:'hidden',minWidth:260},
 scene:{height:214,alignItems:'center',justifyContent:'flex-end',backgroundColor:'#171629',position:'relative',overflow:'hidden'},
 eggBack:{position:'absolute',bottom:22,width:176,height:158,borderRadius:90,backgroundColor:C.shell,borderWidth:6,borderColor:C.shellShade},
 nest:{position:'absolute',bottom:4,width:220,height:44,borderRadius:50,backgroundColor:'#4a2e24',alignItems:'center',justifyContent:'center'},nestText:{color:'#f59e0b',opacity:.5},
 dragon:{width:170,height:170,alignItems:'center',justifyContent:'center',zIndex:3},body:{position:'absolute',bottom:26,width:96,height:98,borderRadius:50,backgroundColor:C.dragon,borderWidth:3,borderColor:C.dragonDark},
 belly:{position:'absolute',bottom:32,width:48,height:72,borderRadius:30,backgroundColor:C.belly},head:{position:'absolute',top:12,width:112,height:94,borderRadius:48,backgroundColor:C.dragon,borderWidth:3,borderColor:C.dragonDark},
 earL:{position:'absolute',left:8,top:-11,width:25,height:32,backgroundColor:C.dragonDark,borderRadius:12,transform:[{rotate:'-24deg'}]},earR:{position:'absolute',right:8,top:-11,width:25,height:32,backgroundColor:C.dragonDark,borderRadius:12,transform:[{rotate:'24deg'}]},
 eyeL:{position:'absolute',left:19,top:28,width:28,height:32,borderRadius:18,backgroundColor:'#fff7ed',alignItems:'center',justifyContent:'center'},eyeR:{position:'absolute',right:19,top:28,width:28,height:32,borderRadius:18,backgroundColor:'#fff7ed',alignItems:'center',justifyContent:'center'},pupil:{width:13,height:17,borderRadius:9,backgroundColor:'#201a2d'},
 snout:{position:'absolute',left:39,top:56,width:34,height:24,borderRadius:15,backgroundColor:C.belly},smile:{position:'absolute',left:48,top:72,width:20,height:8,borderBottomWidth:2,borderColor:C.dragonDark,borderRadius:10},
 shellHat:{position:'absolute',top:-22,left:25,width:64,height:34,borderTopLeftRadius:38,borderTopRightRadius:38,backgroundColor:C.shell,borderWidth:3,borderColor:C.shellShade,transform:[{rotate:'-7deg'}]},shellCrack:{position:'absolute',bottom:-3,left:24,width:16,height:12,borderLeftWidth:3,borderBottomWidth:3,borderColor:C.shellShade,transform:[{rotate:'-35deg'}]},
 eggFront:{position:'absolute',bottom:20,width:182,height:78,borderBottomLeftRadius:90,borderBottomRightRadius:90,borderTopLeftRadius:22,borderTopRightRadius:22,backgroundColor:C.shell,borderWidth:6,borderColor:C.shellShade,zIndex:4},eggCrack:{position:'absolute',top:-5,left:72,width:34,height:18,borderTopWidth:5,borderRightWidth:5,borderColor:C.shellShade,transform:[{rotate:'18deg'}]},
 wing:{position:'absolute',top:66,width:58,height:70,backgroundColor:'#8b4936',borderWidth:3,borderColor:C.dragonDark,borderRadius:32},wingL:{left:-7,transform:[{rotate:'-35deg'}]},wingR:{right:-7,transform:[{rotate:'35deg'}]},tail:{position:'absolute',right:6,bottom:30,width:60,height:24,borderRadius:20,backgroundColor:C.dragonDark,transform:[{rotate:'22deg'}]},
 glasses:{position:'absolute',left:12,top:23,width:88,height:40,flexDirection:'row',alignItems:'center',zIndex:8},lens:{width:34,height:34,borderRadius:11,borderWidth:5,borderColor:'#171717',backgroundColor:'#93c5fd55'},bridge:{width:20,height:6,backgroundColor:'#171717'},bandage:{position:'absolute',left:36,top:11,width:25,height:14,borderRadius:3,backgroundColor:'#f8fafc',transform:[{rotate:'-4deg'}],alignItems:'center',justifyContent:'center'},bandagePad:{width:9,height:8,borderRadius:2,backgroundColor:'#e5e7eb'},
 fire:{position:'absolute',right:-26,top:66,zIndex:8},fireText:{fontSize:54},embers:{position:'absolute',right:-44,top:113},emberText:{color:'#fdba74',fontSize:15},blanket:{position:'absolute',bottom:15,width:188,height:50,borderRadius:50,backgroundColor:'#8b3f57',zIndex:6,opacity:.94},heart:{color:'#fecdd3',fontSize:18,textAlign:'center',marginTop:7},
 copy:{padding:15,gap:7,backgroundColor:C.card},titleRow:{flexDirection:'row',alignItems:'center',gap:7},title:{color:C.ink,fontSize:15,fontWeight:'800'},detail:{color:C.muted,fontSize:12,lineHeight:18},track:{height:5,borderRadius:5,backgroundColor:'#263244',overflow:'hidden'},fill:{height:'100%',backgroundColor:C.ember,borderRadius:5},mode:{fontSize:9,fontWeight:'800',letterSpacing:.7,color:'#94a3b8'}
});
