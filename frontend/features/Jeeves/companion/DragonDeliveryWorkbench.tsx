import React,{useState} from 'react';
import {Pressable,ScrollView,StyleSheet,Text,TextInput,View} from 'react-native';
import {type NativeTarget,titleCaseId} from './dragonNativeTargets';
import {type DeliveryDesign,isDesktop,starterDeliveryDesign} from './dragonDelivery';
import {useDragonDelivery} from './useDragonDelivery';

type Props={targets?:readonly NativeTarget[];onGenerated?:()=>void};
export default function DragonDeliveryWorkbench({targets=[],onGenerated}:Props){
 const delivery=useDragonDelivery(onGenerated);
 const [query,setQuery]=useState('movement');
 const [design,setDesign]=useState<DeliveryDesign>(starterDeliveryDesign());
 const [tab,setTab]=useState<'knowledge'|'design'>('knowledge');
 const [showTargets,setShowTargets]=useState(false);
 const [targetQuery,setTargetQuery]=useState('');
 const target=targets.find(t=>t.id===design.target);
 const choices=target?.supported_styles??[];
 const desktop=isDesktop(design.target);
 const update=(patch:Partial<DeliveryDesign>)=>{delivery.invalidate();setDesign(d=>({...d,...patch}));};
 const changeTarget=(id:string)=>{
  const next=targets.find(t=>t.id===id);if(!next)return;
  const genre=next.supported_styles?.includes(design.genre)?design.genre:next.supported_styles?.[0]??'arcade_score_attack';
  delivery.invalidate();setDesign({...starterDeliveryDesign(id,genre),title:design.title,seed:design.seed});setShowTargets(false);
 };
 const counts=delivery.overview?.counts;
 return <View style={s.root}>
  <View style={s.heading}>
   <Text style={s.title}>Knowledge → original native game</Text>
   <Button label="Refresh" onPress={()=>void delivery.refresh()} disabled={delivery.busy}/>
  </View>
  <Text style={s.copy}>Follow the evidence from discovered sources to reviewed mechanics, then make an original game with a reproducible design.</Text>
  {counts&&<View style={s.metrics}>
   {[
    ['Sources discovered',counts.discovered_sources],['Reviewed sources',counts.reviewed_sources],
    ['Almanakks',counts.almanacs],['Approved mechanics',counts.approved_mechanics],
    ['Current memory cards',counts.current_memory_cards],['Recrawls due',counts.pending_recrawls],
   ].map(([label,value])=><View key={label} style={s.metric}><Text style={s.number}>{value}</Text><Text style={s.muted}>{label}</Text></View>)}
  </View>}
  {delivery.overview&&<>
   <Text style={s.muted}>Source emitters: {counts?.source_targets}/{counts?.catalog_targets} catalog targets · local compiler adapters: {counts?.compiler_adapters}. These counts do not certify complete game engines.</Text>
   {delivery.overview.acquisition.length>0&&<View style={s.card}>
    <Text style={s.subtitle}>Acquisition pipeline</Text>
    {delivery.overview.acquisition.map(r=><Text key={r.stage+':'+r.state} style={s.copy}>{titleCaseId(r.stage)} · {r.state} · {r.count}</Text>)}
   </View>}
   {(!delivery.overview.resource_runtime_ready||!delivery.overview.practice_storage_ready)&&<Text style={s.warning}>
    Generation setup: {!delivery.overview.resource_runtime_ready?'shared resource runtime required. ':''}{!delivery.overview.practice_storage_ready?'practice storage required.':''} You can still inspect available knowledge and prepare a brief.
   </Text>}
   <View style={s.card}><Text style={s.subtitle}>Next steps for this knowledgebase</Text>{delivery.overview.next_actions.map(a=><Text key={a.code} style={s.copy}>• {a.label}</Text>)}</View>
  </>}
  <View style={s.row}>
   <Button label="1 · Explore knowledge" selected={tab==='knowledge'} onPress={()=>setTab('knowledge')}/>
   <Button label="2 · Design & deliver" selected={tab==='design'} onPress={()=>setTab('design')}/>
  </View>
  <Text style={s.label}>Mechanic or research question</Text>
  <TextInput value={query} onChangeText={v=>{setQuery(v);delivery.invalidate();}} maxLength={300}
   accessibilityLabel="Knowledge search and design brief query" placeholder="Movement, collision, camera, combat…" placeholderTextColor="#94a3b8" style={s.input}/>
  {tab==='knowledge'?<>
   <View style={s.row}>
    <Button label="Find cited knowledge" disabled={delivery.busy||!query.trim()} onPress={()=>void delivery.search(query)}/>
    <Button label="Browse Almanakks" disabled={delivery.busy} onPress={()=>void delivery.browse(0)}/>
   </View>
   {delivery.citations.map(c=><View key={c.source_id+':'+c.note_id} style={s.card}>
    <Text style={s.subtitle}>{titleCaseId(c.mechanic)} · {c.stance}</Text>
    <Text style={s.copy}>{c.statement}</Text>
    <Text style={c.approval==='wiki_hoag_approved'?s.approved:s.warning}>{c.approval==='wiki_hoag_approved'?'Wiki reviewed + Hoag approved':'Source reviewed · further approval required'}</Text>
    <Text style={s.muted}>Confidence {Math.round(c.confidence_ppm/10000)}% · source group {c.dependence_group}</Text>
    <Text selectable style={s.citation}>{c.title}{'\n'}{c.source_url}</Text>
    <Text style={s.muted}>Revision {c.revision_digest.slice(0,16)}{c.expires_at?' · valid until '+new Date(c.expires_at*1000).toLocaleString():''}</Text>
    <Button label="Use this mechanic as design query" onPress={()=>{setQuery(c.mechanic);delivery.invalidate();setTab('design');}}/>
   </View>)}
   {delivery.almanacs.length>0&&<View style={s.card}>
    <Text style={s.subtitle}>Almanakk index · {delivery.offset+1}–{delivery.offset+delivery.almanacs.length} of {delivery.total}</Text>
    {delivery.almanacs.map(a=><View key={a.topic_id} style={s.almanac}>
     <Text style={s.copy}>{a.headers.join(' / ')}</Text>
     <Text style={s.muted}>{a.discovered_sources} discovered sources · {a.machine_learning_records} recorded findings</Text>
     {a.machine_learning_records>0&&<Button label="Inspect project findings" disabled={delivery.busy} onPress={()=>void delivery.inspectLearning(a.topic_id)}/>}
    </View>)}
    <View style={s.row}>
     <Button label="Previous" disabled={delivery.busy||delivery.offset===0} onPress={()=>void delivery.browse(Math.max(0,delivery.offset-32))}/>
     <Button label="Next" disabled={delivery.busy||delivery.offset+32>=delivery.total} onPress={()=>void delivery.browse(delivery.offset+32)}/>
    </View>
   </View>}
   {delivery.findings.map(f=><View key={f.learning_digest} style={s.card}><Text style={s.subtitle}>{titleCaseId(f.kind)} · {f.current_source_lineage?'current lineage':'stale source dependencies'}</Text><Text style={s.copy}>{f.statement}</Text><Text style={s.copy}>{f.method}</Text><Text style={s.warning}>{f.limitations}</Text><Text style={s.muted}>Unreviewed project finding · not promoted to memory</Text></View>)}
  </>:<>
   <Text style={s.label}>Original project title</Text>
   <TextInput value={design.title} onChangeText={title=>update({title})} maxLength={80} accessibilityLabel="Original game title" style={s.input}/>
   <Button label={'Target · '+titleCaseId(design.target)} onPress={()=>setShowTargets(v=>!v)}/>
   {showTargets&&<View style={s.card}>
    <TextInput value={targetQuery} onChangeText={setTargetQuery} accessibilityLabel="Filter target hardware" placeholder="Console, computer or family" placeholderTextColor="#94a3b8" style={s.input}/>
    <ScrollView style={{maxHeight:200}} nestedScrollEnabled>
     {targets.filter(t=>(t.id+' '+t.family).toLowerCase().includes(targetQuery.toLowerCase())).map(t=><Button key={t.id}
      label={titleCaseId(t.id)+(t.status==='native_source'?' · source emitter':' · adapter unavailable')}
      disabled={t.status!=='native_source'} selected={t.id===design.target} onPress={()=>changeTarget(t.id)}/>)}
    </ScrollView>
   </View>}
   <Text style={s.label}>Supported gameplay style</Text>
   <ScrollView horizontal showsHorizontalScrollIndicator={false}><View style={s.row}>{choices.map(genre=><Button key={genre} label={titleCaseId(genre)} selected={design.genre===genre} onPress={()=>update({genre})}/>)}</View></ScrollView>
   <Text style={s.muted}>{target?.toolchain??'Load the platform catalog to see the required toolchain'} · {desktop?'Desktop generation supports multi-stage design.':'This cartridge emitter produces one seeded stage. Other art settings remain metadata.'}</Text>
   <NumberControl label="Seed" value={design.seed} min={0} max={4294967295} onChange={seed=>update({seed})}/>
   {desktop&&<>
    <NumberControl label="Stages" value={design.stages} min={1} max={8} onChange={stages=>update({stages})}/>
    <NumberControl label="Difficulty" value={design.difficulty} min={1} max={10} onChange={difficulty=>update({difficulty})}/>
    {!['fixed_screen_puzzle','rhythm_game'].includes(design.genre)&&<>
     <NumberControl label="Generated candidates" value={design.candidates} min={1} max={24} onChange={candidates=>update({candidates})}/>
     <Choice label="Palette" values={['dmg_green','cga','vga_dusk','crt_arcade','handheld','modern_neon']} value={design.palette} onChange={palette=>update({palette})}/>
     {design.genre!=='turn_based_rpg'&&<Choice label="Theme" values={['crystals','ancient_ruins','forest','ice','space','volcano','clockwork']} value={design.quest_theme} onChange={quest_theme=>update({quest_theme})}/>}
     {!['first_person_shooter','immersive_sim','turn_based_rpg'].includes(design.genre)&&<Choice label="Hero" values={['hatchling','knight','explorer','pilot','astronaut','robot']} value={design.hero} onChange={hero=>update({hero})}/>}
    </>}
   </>}
   <Button label={delivery.busy?'Working…':'3 · Prepare cited design brief'} disabled={delivery.busy||!query.trim()||!target||!choices.includes(design.genre)} onPress={()=>void delivery.prepare(design,query)}/>
   {delivery.brief&&<View style={s.brief}>
    <Text style={s.subtitle}>{delivery.brief.ready_for_source_generation?'Brief ready for your confirmation':'Brief needs more evidence'}</Text>
    <Text style={s.copy}>{delivery.brief.independent_groups} independent source groups · {delivery.brief.citations.length} approved citations</Text>
    {delivery.brief.blockers.map(b=><Text key={b} style={s.warning}>• {titleCaseId(b)}</Text>)}
    {delivery.brief.citations.map(c=><Text key={c.source_id+':'+c.note_id} style={s.copy}>• {c.statement} ({c.title})</Text>)}
    <Text style={s.muted}>Applied controls: {delivery.brief.controls.effective.map(titleCaseId).join(', ')}</Text>
    <Text style={s.muted}>Design guidance is cited; this generator does not turn arbitrary research claims into new engine code.</Text>
    <Text style={s.muted}>Build with {delivery.brief.toolchain}. {delivery.brief.compiler_adapter_available?'The offline CLI supports this compiler.':'A separate installed SDK build is still required.'}</Text>
    <Button label="4 · Confirm brief & generate native source" disabled={delivery.busy||!delivery.brief.ready_for_source_generation||!delivery.overview?.resource_runtime_ready||!delivery.overview?.practice_storage_ready} onPress={()=>void delivery.generate()}/>
   </View>}
  </>}
  {!!delivery.recoveryAttempt&&<Button label="Recover project Almanakk entry" disabled={delivery.busy} onPress={()=>void delivery.recoverLearning()}/>}
  {!!delivery.error&&<Text accessibilityRole="alert" style={s.warning}>{delivery.error}</Text>}
  {!!delivery.notice&&<Text accessibilityLiveRegion="polite" style={s.approved}>{delivery.notice}</Text>}
  <Text style={s.muted}>Source projects retain the design and evidence lineage. Compilation, target gameplay and release approval are separate milestones. No training or permanent-memory approval is granted here.</Text>
 </View>;
}
function Button({label,onPress,disabled=false,selected=false}:{label:string;onPress:()=>void;disabled?:boolean;selected?:boolean}){
 return <Pressable accessibilityRole="button" accessibilityState={{disabled,selected}} disabled={disabled} onPress={onPress} style={[s.button,selected&&s.selected,disabled&&s.disabled]}><Text style={s.buttonText}>{label}</Text></Pressable>;
}
function NumberControl({label,value,min,max,onChange}:{label:string;value:number;min:number;max:number;onChange:(n:number)=>void}){
 return <View style={s.row}><Text style={s.label}>{label} · {value}</Text><Button label="−" disabled={value<=min} onPress={()=>onChange(value-1)}/><Button label="+" disabled={value>=max} onPress={()=>onChange(value+1)}/></View>;
}
function Choice({label,values,value,onChange}:{label:string;values:string[];value:string;onChange:(v:string)=>void}){
 return <View style={{gap:6}}><Text style={s.label}>{label}</Text><View style={s.row}>{values.map(v=><Button key={v} label={titleCaseId(v)} selected={v===value} onPress={()=>onChange(v)}/>)}</View></View>;
}
const s=StyleSheet.create({
 root:{padding:14,gap:12,borderRadius:14,borderWidth:1,borderColor:'#376052',backgroundColor:'#0c1918'},
 heading:{flexDirection:'row',alignItems:'center',justifyContent:'space-between',gap:10,flexWrap:'wrap'},
 title:{fontSize:17,fontWeight:'800',color:'#e9fff3',flexShrink:1},subtitle:{fontSize:13,fontWeight:'700',color:'#d2f5df'},
 copy:{fontSize:12,lineHeight:19,color:'#d1dce1'},muted:{fontSize:11,lineHeight:17,color:'#96adb0'},
 citation:{fontSize:11,lineHeight:17,color:'#adcff2'},approved:{fontSize:12,lineHeight:19,color:'#8ee3b2'},warning:{fontSize:12,lineHeight:19,color:'#f6c789'},
 label:{fontSize:12,fontWeight:'700',color:'#d2e8e1'},row:{flexDirection:'row',gap:8,alignItems:'center',flexWrap:'wrap'},
 metrics:{flexDirection:'row',flexWrap:'wrap',gap:8},metric:{minWidth:115,flexGrow:1,padding:10,backgroundColor:'#172a28',borderRadius:9},
 number:{fontSize:21,fontWeight:'800',color:'#b4f1cf'},card:{gap:7,padding:11,borderRadius:10,backgroundColor:'#142625'},
 brief:{gap:9,padding:12,borderRadius:10,borderWidth:1,borderColor:'#5c8d69',backgroundColor:'#162d26'},
 input:{color:'#f4faf8',borderColor:'#47645f',borderWidth:1,borderRadius:8,padding:10,fontSize:13,backgroundColor:'#101f20'},
 button:{paddingHorizontal:11,paddingVertical:9,borderRadius:8,backgroundColor:'#254740',marginVertical:2},
 selected:{backgroundColor:'#426c53'},disabled:{opacity:.4},buttonText:{fontSize:11,fontWeight:'700',color:'#e2f8ec'},
 almanac:{paddingVertical:7,borderBottomWidth:1,borderBottomColor:'#28403c'},
});
