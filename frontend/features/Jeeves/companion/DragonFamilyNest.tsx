/** Server-owned Dragon brood: presentation only. No UI action creates evidence or XP. */
import React, {useState} from 'react';
import {Pressable, StyleSheet, Text, View} from 'react-native';

import {validateDragonFamily, type DragonFamilyProjection, type DragonFamilyStage, type DragonFamilyRole} from './dragonFamilyProjection';

const glyph=(stage:DragonFamilyStage)=>stage==='unborn'?'·':stage==='egg'?'🥚':stage==='hatchling'?'🐣':stage==='juvenile'?'🐲':'🐉';
const safeDate=(value:string|null)=>value?value.replace('T',' ').replace('Z',' UTC'):'No new evidence yet';

export default function DragonFamilyNest({family}:{family?:DragonFamilyProjection|null}){
 const [selected,setSelected]=useState<DragonFamilyRole>('article');
 const [showHistory,setShowHistory]=useState(false);
 const f=validateDragonFamily(family);
 if(!f)return <View style={s.root}><Text style={s.heading}>🥚 Dragon Family</Text>
   <Text style={s.muted}>Awaiting a verified source inventory. The nest cannot advance on animations or page views.</Text>
  </View>;
 const child=f.children.find(c=>c.id===selected)??f.children[0];
 const percent=f.parent.source_total?
  Math.round(100*f.parent.consumed/f.parent.source_total):0;
 return <View style={s.root} accessibilityLabel="Dragon Family knowledge game">
  <View style={s.top}><Text style={s.heading}>🐲 Dragon Family · Research Nest</Text>
   <Text style={s.flag}>{f.parent.complete?'3 EGGS LAID':'SOURCE QUEST'}</Text></View>
  <Text style={s.muted}>{f.parent.complete?
   'The parent completed its approved inventory and laid three specialist eggs.':
   'The parent matures by consuming verified sources from its original inventory.'}</Text>
  <View style={s.mother}>
   <Text style={s.motherGlyph}>{f.parent.complete?'🐉':f.parent.consumed===0?'🥚':'🐲'}</Text>
   <View style={s.flex}><Text style={s.title}>Mother dragon · {f.parent.stage}</Text>
    <Text style={s.muted}>{f.parent.consumed} / {f.parent.source_total} sources consumed</Text>
    <View accessibilityRole="progressbar" accessibilityValue={{min:0,max:100,now:percent}}
      style={s.track}><View style={[s.fill,{width:`${percent}%`}]}/></View></View>
  </View>
  <View style={s.brood}>{f.children.map(c=><Pressable key={c.id}
     accessibilityRole="button" accessibilityState={{selected:c.id===selected}}
     accessibilityLabel={`${c.name}, ${c.specialty}, ${c.stage}, level ${c.level}`}
     onPress={()=>setSelected(c.id)} style={[s.creature,c.id===selected&&s.selected]}>
    <Text style={s.creatureGlyph}>{glyph(c.stage)}</Text>
    <Text style={s.name}>{c.name}</Text>
    <Text style={s.role}>{c.specialty}</Text>
    <Text style={s.level}>{c.stage==='unborn'?'Not born':c.stage==='egg'?'Waiting':'Lv '+c.level}</Text>
  </Pressable>)}</View>
  <View style={s.details}><Text style={s.title}>{child.name} · {child.stage}</Text>
   <Text style={s.muted}>{child.id==='article'?'Digests newly approved web articles':
    child.id==='video'?'Digests newly approved video evidence':
    'Detects verified changes in known sources'} · idle only</Text>
   <Text style={s.muted}>New information acquired: {child.discoveries} · Last growth: {safeDate(child.last_grew_at)}</Text>
   <Text style={s.privacy}>Only grows while the host confirms idle time, consent, and resource capacity. Updated or adjacent knowledge must be independently verified.</Text></View>
  {f.idle_host&&<View style={s.details} accessibilityLabel="Consented Dragon idle research host status">
   <Text style={s.title}>🛡️ Idle research permissions</Text>
   <Text style={s.muted}>{f.idle_host.active?
     'Research opt-in is active; the host must still confirm local idle time before every acquisition.':
     f.idle_host.configured?
     'Idle research paused or consent no longer valid. No new work may be admitted.':
     'Research host not configured. The hatchlings will rest.'}</Text>
   <Text style={s.role}>Daily attempted acquisitions: {f.idle_host.daily_attempts}
     {' · '}Ember {f.idle_host.daily_by_specialist.article??0}
     {' · '}Flicker {f.idle_host.daily_by_specialist.video??0}
     {' · '}Scout {f.idle_host.daily_by_specialist.monitor??0}</Text>
   {f.idle_host.active&&<Text style={s.when}>Consent expires: {safeDate(f.idle_host.consent_expires_at)}
      {' · '}Next host tick eligible: {safeDate(f.idle_host.next_tick_at)}</Text>}
   <Text style={s.privacy}>This is a consent and budget snapshot, not live device activity. No browser control can claim the machine is idle or fabricate verified learning.</Text>
  </View>}
  {f.idle_work&&<View style={s.details} accessibilityLabel="Idle-only specialist work status">
   <Text style={s.title}>🌙 Dragon Nest · Idle Research</Text>
   <Text style={s.muted}>{f.idle_work.configured?
    'Host dispatch ledger connected. Current device activity has not been observed in this view.':
    'Idle scheduler has no durable dispatch ledger yet.'}</Text>
   <View style={s.brood}>{f.children.map(child=>{
     const status=f.idle_work?.workers[child.id];
     return <View key={child.id} style={s.creature}>
      <Text style={s.name}>{child.name}</Text>
      <Text style={s.role}>{status?
       `Sources: ${status.known_sources} · New: ${status.last_changes}`:
       'Waiting for idle research'}</Text>
      <Text style={s.role}>{status?
       `Unchanged: ${status.unchanged} · Errors: ${status.failed}`:
       'No dispatch history'}</Text>
      {status?.earliest_due_at&&<Text style={s.when}>Next eligible: {safeDate(status.earliest_due_at)}</Text>}
     </View>;
   })}</View>
   {f.idle_work.history.length>0&&<View style={s.history}>
    <Text style={s.title}>Most recent research activity</Text>
    {f.idle_work.history.slice(0,3).map(h=><View key={h.digest} style={s.event}>
     <Text style={s.when}>{safeDate(h.at)} · {h.dragon}</Text>
     <Text style={s.muted}>{h.outcome} · {h.source_id} {h.change}</Text>
    </View>)}
   </View>}
   <Text style={s.privacy}>Only the trusted host can attest idle time and authorize new research. Pending leases are not proof that anything is running now.</Text>
  </View>}
  {f.glean&&<View style={s.details} accessibilityLabel="Mother Dragon Glean Matrix">
   <Text style={s.title}>🔍 Mother Dragon · Glean Matrix</Text>
   <Text style={s.muted}>Cross-source evidence lenses · {f.glean.lenses_used} active lens families</Text>
   <View style={s.top}>
    <Text style={s.role}>Hypotheses: {f.glean.insights}</Text>
    <Text style={s.role}>For Wiki: {f.glean.counts.wiki_candidate}</Text>
    <Text style={s.role}>Disputed: {f.glean.counts.contested}</Text>
    <Text style={s.role}>Need sources: {f.glean.counts.needs_independent_sources}</Text>
   </View>
   {f.glean.cells.length===0&&<Text style={s.muted}>No independently verified cross-source insights yet. Hatchling discoveries do not automatically become hypotheses.</Text>}
   {f.glean.cells.slice(0,5).map(cell=><View key={cell.lens+cell.proposition_digest} style={s.event}>
    <Text style={s.title}>{cell.status==='contested'?'⚠️':cell.status==='wiki_candidate'?'📚':'🔎'} {cell.lens.replaceAll('_',' ')}</Text>
    <Text style={s.muted}>{cell.exemplar}</Text>
    <Text style={s.role}>Sources: {cell.source_count} · Independent supporters: {cell.support_groups} · Challenges: {cell.challenge_sources}</Text>
    <Text style={s.when}>{safeDate(cell.latest_at)} · {cell.priority.replaceAll('_',' ')}</Text>
   </View>)}
   {f.glean.stale_observations>0&&<Text style={s.muted}>Superseded or revoked observations: {f.glean.stale_observations} (excluded from active insight counts)</Text>}
   <Text style={s.privacy}>Gleaned insights are hypotheses, not verified AI improvement. Disagreements trigger further scrutiny; only separate Wiki and holdout decisions can authorize weight handoff.</Text>
  </View>}
  {f.almanakk&&<View style={s.details} accessibilityLabel="Almanakk verified research pipeline">
   <Text style={s.title}>📚 Almanakk · Wiki knowledge journey</Text>
   <Text style={s.muted}>Dragon → Almanakk → Wiki → HOAG/Jeeves → Game Builder</Text>
   <View style={s.top}>
    <Text style={s.role}>Collected: {f.almanakk.counts.collected}</Text>
    <Text style={s.role}>Wiki: {f.almanakk.counts.wiki_verified}</Text>
    <Text style={s.role}>Shadow tested: {f.almanakk.counts.shadow_validated}</Text>
    <Text style={s.role}>Handoffs: {f.almanakk.counts.weight_handoff}</Text>
   </View>
   {f.almanakk.items.slice(0,3).map(e=><View key={e.source_id} style={s.event}>
    <Text style={s.title}>{e.source_id} · {e.stage.replaceAll('_',' ')}</Text>
    <Text style={s.muted}>Evidence: {e.dragon} · {safeDate(e.last_acquired_at)}</Text>
    {e.measured_gain!==null&&<Text style={s.when}>(improved: +{(e.measured_gain*100).toFixed(1)}% measured held-out quality)</Text>}
   </View>)}
   <Text style={s.privacy}>Shadow-tested knowledge requires independent Wiki and sandbox review. Handoff never implies that model weights were modified.</Text>
  </View>}
  <Pressable accessibilityRole="button" accessibilityState={{expanded:showHistory}}
   onPress={()=>setShowHistory(v=>!v)} style={s.historyButton}>
   <Text style={s.historyTitle}>{showHistory?'Hide':'Show'} timestamped evolution history ({f.history.length} recent)</Text>
  </Pressable>
  {showHistory&&<View style={s.history}>{f.history.length===0?
   <Text style={s.muted}>No source changes recorded.</Text>:
   f.history.slice(0,15).map(h=><View key={h.digest} style={s.event}>
    <Text style={s.when}>{safeDate(h.at)}</Text>
    <Text style={s.title}>{h.dragon} · {h.action.replaceAll('_',' ')}</Text>
    <Text style={s.muted}>{h.change}</Text>
    {!!h.source_id&&<Text numberOfLines={1} style={s.source}>Source: {h.source_id}</Text>}
   </View>)}</View>}
  <Text style={s.privacy}>Gathered evidence does not automatically train the AI, approve game designs, or grant independent crawler permissions.</Text>
 </View>;
}
const s=StyleSheet.create({
 root:{backgroundColor:'#171828',borderWidth:1,borderColor:'#725c3c',borderRadius:18,padding:12,gap:10},
 top:{flexDirection:'row',alignItems:'center',gap:8,flexWrap:'wrap'},
 heading:{fontSize:15,fontWeight:'900',color:'#fef3c7',flexGrow:1},
 flag:{fontSize:9,color:'#fde68a',letterSpacing:1,fontWeight:'800'},
 mother:{backgroundColor:'#282036',borderRadius:14,padding:10,flexDirection:'row',alignItems:'center',gap:12},
 motherGlyph:{fontSize:40},flex:{flex:1,gap:6},title:{fontSize:12,color:'#f8fafc',fontWeight:'800'},
 track:{height:7,backgroundColor:'#544357',borderRadius:8,overflow:'hidden'},
 fill:{height:'100%',backgroundColor:'#fb923c',borderRadius:8},
 brood:{flexDirection:'row',gap:6,flexWrap:'wrap'},
 creature:{flexGrow:1,flexBasis:'30%',minWidth:84,alignItems:'center',justifyContent:'center',
  borderRadius:13,borderWidth:1,borderColor:'#41445c',backgroundColor:'#22283d',padding:7,gap:3},
 selected:{borderColor:'#fbbf24',backgroundColor:'#36304b'},
 creatureGlyph:{fontSize:34},name:{color:'#fff7ed',fontSize:12,fontWeight:'900'},
 role:{color:'#bac8dc',fontSize:9,textAlign:'center'},
 level:{color:'#fcd34d',fontSize:10,fontWeight:'700'},
 details:{padding:10,borderRadius:10,backgroundColor:'#232b3c',gap:5},
 muted:{fontSize:11,color:'#bac8dc',lineHeight:16},
 privacy:{fontSize:10,color:'#94a3b8',lineHeight:16},
 historyButton:{padding:10,backgroundColor:'#3c3244',borderRadius:9},
 historyTitle:{color:'#fef3c7',fontSize:11,fontWeight:'800'},
 history:{gap:6},event:{backgroundColor:'#242737',padding:9,borderRadius:8,gap:3},
 when:{fontSize:9,color:'#fcd34d'},source:{fontSize:9,color:'#94a3b8'},
});