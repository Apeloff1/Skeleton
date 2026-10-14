/** Review-only knowledge cards for video evidence. No card silently promotes a claim. */
import React,{useState} from 'react';
import {Pressable,ScrollView,StyleSheet,Text,View} from 'react-native';
import type {WatchCue} from './dragonWatchCues';
export interface ReviewedWatchCue {cueId:string;decision:'keep'|'discard';reviewedAt:number}
export default function DragonVideoEvidence({cues,onReview}:{cues:readonly WatchCue[];onReview?:(decision:ReviewedWatchCue)=>void}){
 const [reviewed,setReviewed]=useState<Record<string,'keep'|'discard'>>({});
 const [expanded,setExpanded]=useState(false);
 const decide=(cue:WatchCue,decision:'keep'|'discard')=>{
  setReviewed(current=>({...current,[cue.id]:decision}));
  onReview?.({cueId:cue.id,decision,reviewedAt:Date.now()});
 };
 return <View style={styles.wrap}>
  <Pressable accessibilityRole="button" accessibilityState={{expanded}} onPress={()=>setExpanded(v=>!v)} style={styles.header}>
   <Text style={styles.heading}>📓 Dragon's video notebook · {cues.length} observations</Text>
   <Text style={styles.meta}>{expanded?'Hide':'Review'}</Text>
  </Pressable>
  {expanded&&<ScrollView style={styles.list} nestedScrollEnabled>
   {cues.length===0&&<Text style={styles.empty}>No authorized, confidence-qualified observations yet.</Text>}
   {cues.map(cue=><View key={cue.id} style={styles.card}>
    <Text style={styles.title}>{cue.title} · {(cue.positionMs/1000).toFixed(1)}s</Text>
    <Text style={styles.description}>{cue.description}</Text>
    <Text style={styles.meta}>Confidence {(cue.confidence*100).toFixed(0)}% · {cue.observationIds.length} evidence item(s) · unverified</Text>
    <View style={styles.actions}>
     <Pressable accessibilityRole="button" disabled={Boolean(reviewed[cue.id])} onPress={()=>decide(cue,'keep')} style={styles.action}><Text style={styles.actionText}>Keep for review</Text></Pressable>
     <Pressable accessibilityRole="button" disabled={Boolean(reviewed[cue.id])} onPress={()=>decide(cue,'discard')} style={styles.action}><Text style={styles.actionText}>Discard</Text></Pressable>
    </View>
    {reviewed[cue.id]&&<Text style={styles.meta}>Marked {reviewed[cue.id]} · not yet persisted</Text>}
   </View>)}
  </ScrollView>}
 </View>;
}
const styles=StyleSheet.create({
 wrap:{borderWidth:1,borderColor:'#334155',borderRadius:14,backgroundColor:'#0f172a',overflow:'hidden'},
 header:{flexDirection:'row',justifyContent:'space-between',padding:12,gap:8},
 heading:{color:'#f8fafc',fontWeight:'700',fontSize:12,flex:1},
 meta:{color:'#94a3b8',fontSize:10},
 list:{maxHeight:340,paddingHorizontal:10},
 card:{borderTopWidth:1,borderColor:'#334155',paddingVertical:12,gap:7},
 title:{color:'#fdba74',fontSize:12,fontWeight:'700'},
 description:{color:'#e2e8f0',fontSize:12,lineHeight:18},
 actions:{flexDirection:'row',gap:8},
 action:{backgroundColor:'#334155',borderRadius:8,padding:9},
 actionText:{color:'#f8fafc',fontSize:11,fontWeight:'600'},
 empty:{color:'#94a3b8',padding:14}
});
