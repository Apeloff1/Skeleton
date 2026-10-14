import React from 'react';
import {StyleSheet,Text,View} from 'react-native';
import type {DragonKnowledgeView} from './dragonKnowledgePyramid';

/** Compact, non-authoritative view of the three knowledge stages. */
export default function DragonKnowledgePyramid({view}:{view:DragonKnowledgeView|null|undefined}){
 if(!view)return null;
 return <View style={s.root} accessibilityLabel="Dragon knowledge pyramid">
  <Text style={s.heading}>Dragon's knowledge pyramid</Text>
  <View style={s.stages}>
   <Text style={s.stage}>Almanac · researched</Text>
   <Text style={s.arrow}>→</Text>
   <Text style={s.stage}>Wiki · adversarial review</Text>
   <Text style={s.arrow}>→</Text>
   <Text style={s.stage}>HOAG · approved view</Text>
  </View>
  <Text style={s.note}>{view.items.length} currently eligible advisory memories
   {view.pending_recrawls>0?' · '+view.pending_recrawls+' source refresh orders':''}</Text>
  {view.items.slice(0,6).map(item=><View style={s.card} key={item.review_digest}>
   <Text style={s.mechanic}>{item.mechanic.replaceAll('_',' ')}</Text>
   <Text style={s.note}>Independently reviewed · {item.independent_groups} evidence groups</Text>
   <Text style={s.proof}>Evidence {item.review_evidence_digest.slice(0,12)}… · expires {new Date(item.expires_at*1000).toLocaleDateString()}</Text>
  </View>)}
  {view.items.length>6&&<Text style={s.note}>Plus {view.items.length-6} more approved topics</Text>}
  {view.items.length===0&&<Text style={s.note}>No currently valid reviewed topics. Research and memory approval remain separate.</Text>}
  <Text style={s.warning}>Advisory only · no automated training, legal clearance, or game release.</Text>
 </View>;
}
const s=StyleSheet.create({
 root:{padding:12,borderRadius:12,backgroundColor:'#111827',gap:7,borderWidth:1,borderColor:'#334155'},
 heading:{fontSize:15,fontWeight:'800',color:'#fef3c7'},
 stages:{flexDirection:'row',flexWrap:'wrap',alignItems:'center',gap:5},
 stage:{color:'#f8fafc',fontSize:10,fontWeight:'700'},
 arrow:{color:'#fbbf24',fontSize:12},
 note:{fontSize:11,color:'#cbd5e1'},
 card:{padding:8,borderRadius:9,backgroundColor:'#1e293b',gap:4},
 mechanic:{fontSize:12,fontWeight:'700',color:'#f8fafc'},
 proof:{fontSize:10,color:'#94a3b8'},
 warning:{fontSize:10,color:'#fbbf24'},
});
