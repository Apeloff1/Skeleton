/** Explicit opt-in video observation policy controls. */
import React,{useState} from 'react';
import {Pressable,StyleSheet,Switch,Text,View} from 'react-native';
import {DEFAULT_VIDEO_PRIVACY,validateVideoPrivacy,type VideoPrivacySettings,type VideoPrivacyMode} from './dragonVideoPrivacy';
export default function DragonVideoConsent({value,onChange}:{value:VideoPrivacySettings;onChange:(value:VideoPrivacySettings)=>void}){
 const [expanded,setExpanded]=useState(false);
 const update=(next:VideoPrivacySettings)=>onChange(validateVideoPrivacy(next));
 const mode=(next:VideoPrivacyMode)=>update(next==='off'?{...DEFAULT_VIDEO_PRIVACY}:next==='ephemeral'?
  {...value,mode:next,retainObservations:false}:{...value,mode:next});
 return <View style={styles.container}>
  <Pressable accessibilityRole="button" accessibilityState={{expanded}} onPress={()=>setExpanded(v=>!v)} style={styles.heading}>
   <Text style={styles.title}>🔒 Video privacy · {value.mode}</Text><Text style={styles.caption}>{expanded?'Hide':'Configure'}</Text>
  </Pressable>
  {expanded&&<View style={styles.options}>
   <View style={styles.modes}>{(['off','ephemeral','review-only'] as const).map(item=><Pressable key={item} accessibilityRole="button" accessibilityState={{selected:value.mode===item}} onPress={()=>mode(item)} style={[styles.mode,value.mode===item&&styles.active]}><Text style={styles.caption}>{item}</Text></Pressable>)}</View>
   {value.mode!=='off'&&<>
    <Toggle label="Read transcripts and captions" value={value.allowTranscript} onChange={allowTranscript=>update({...value,allowTranscript})}/>
    <Toggle label="Inspect video frames and text" value={value.allowVisual} onChange={allowVisual=>update({...value,allowVisual})}/>
    <Toggle label="Inspect audio descriptions" value={value.allowAudio} onChange={allowAudio=>update({...value,allowAudio})}/>
    {value.mode==='review-only'&&<Toggle label="Allow reviewed observation retention" value={value.retainObservations} onChange={retainObservations=>update({...value,retainObservations})}/>}
   </>}
   <Text style={styles.caption}>Watching together does not grant permission to analyze or save video. Permissions are local UI preferences until a trusted media adapter enforces them.</Text>
  </View>}
 </View>;
}
function Toggle({label,value,onChange}:{label:string;value:boolean;onChange:(next:boolean)=>void}){
 return <View style={styles.toggle}><Text style={styles.label}>{label}</Text><Switch accessibilityLabel={label} value={value} onValueChange={onChange}/></View>;
}
const styles=StyleSheet.create({
 container:{borderRadius:12,borderWidth:1,borderColor:'#334155',backgroundColor:'#0f172a'},
 heading:{padding:12,flexDirection:'row',justifyContent:'space-between',gap:8},
 title:{color:'#f8fafc',fontSize:12,fontWeight:'700'},
 caption:{color:'#94a3b8',fontSize:10},
 options:{padding:12,gap:12},
 modes:{flexDirection:'row',flexWrap:'wrap',gap:6},
 mode:{padding:8,borderRadius:8,backgroundColor:'#1e293b'},
 active:{backgroundColor:'#7c3f25'},
 toggle:{flexDirection:'row',alignItems:'center',justifyContent:'space-between',gap:8},
 label:{flex:1,color:'#cbd5e1',fontSize:11}
});
