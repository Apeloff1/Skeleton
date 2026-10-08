import React,{useMemo,useState} from 'react';
import{Pressable,ScrollView,StyleSheet,Text,TextInput,View}from'react-native';
import{Ionicons}from'@expo/vector-icons';
import{type NativeAttempt,type NativeTarget,type NativeCurriculum,titleCaseId}from'./dragonNativeTargets';

export interface DragonNativeWorkshopProps{
 targets?:readonly NativeTarget[];
 attempts?:readonly NativeAttempt[];
 styles?:readonly string[];
 curriculum?:NativeCurriculum|null;
 onGenerateCurriculum?:()=>void;
 onGenerate?:(target:string,style:string)=>void;
 onDownload?:(attemptId:string)=>void;
 busy?:boolean;
}
const C={fg:'#f8fafc',muted:'#9ca3af',gold:'#fbbf24',mint:'#86efac'};
export default function DragonNativeWorkshop({
 targets=[],attempts=[],styles=[],curriculum,onGenerateCurriculum,onGenerate,onDownload,busy=false,
}:DragonNativeWorkshopProps){
 const [selected,setSelected]=useState('game_boy');
 const [style,setStyle]=useState('arcade_score_attack');
 const [all,setAll]=useState(false);
 const [search,setSearch]=useState('');
 const visible=useMemo(()=>targets.filter(t=>{
  if(!all&&t.status!=='native_source')return false;
  const query=search.trim().toLowerCase();
  return !query||[t.id,t.family,t.generation,t.cpu].some(v=>v.toLowerCase().includes(query));
 }),[targets,all,search]);
 const current=targets.find(t=>t.id===selected);
 const choices=styles.filter(s=>current?.supported_styles?.includes(s));
 const selectedStyle=choices.includes(style)?style:choices[0];
 const enabled=!!current&&current.status==='native_source'&&!!selectedStyle&&!!onGenerate;
 return <View style={s.root}>
  <Text style={s.title}>Native game forge · every era</Text>
  <Text style={s.copy}>Original Game Boy, NES, DOS and desktop source projects. Real ROMs or executables require their actual compilers, emulators and playtests. Console names alone never count as implemented engines.</Text>
  {curriculum&&<View style={s.selectedInfo}>
    <Ionicons name="school-outline" color={C.gold} size={20}/>
    <View style={{flex:1,gap:5}}>
     <Text style={s.infoTitle}>Adaptive native acquisition · evidence tier {curriculum.curriculum_level}</Text>
     <Text style={s.note}>Structurally evidenced ROM targets: {curriculum.structural_build_targets.length} · Pending unlocked lessons: {curriculum.unlocked.length} · Evidence tier is not a gameplay mastery level</Text>
     {curriculum.next_recommendation?<View style={{gap:3}}>
       <Text style={s.platformTitle}>Next: {titleCaseId(curriculum.next_recommendation.target)} · {titleCaseId(curriculum.next_recommendation.genre)}</Text>
       <Text style={s.note}>{curriculum.next_recommendation.reason} · {curriculum.next_recommendation.previous_attempts} source attempts</Text>
     </View>:<Text style={s.note}>No further unlocked exercises. Verified compiler receipts or new approved lessons are needed.</Text>}
     {onGenerateCurriculum&&curriculum.next_recommendation&&
      <Pressable accessibilityRole="button" accessibilityLabel="Generate suggested native practice project"
        accessibilityState={{disabled:busy}} disabled={busy} onPress={onGenerateCurriculum}
        style={[s.build,busy&&s.disabled]}>
        <Ionicons name="sparkles-outline" size={16} color="#052e16"/>
        <Text style={s.buildText}>Generate suggested practice game</Text>
      </Pressable>}
    </View>
   </View>}
  <View style={s.chips}>
   <Pressable accessibilityRole="button" onPress={()=>setAll(false)}
    accessibilityState={{selected:!all}} style={[s.pill,!all&&s.chosen]}>
    <Text style={s.pillText}>Source emitters</Text>
   </Pressable>
   <Pressable accessibilityRole="button" onPress={()=>setAll(true)}
    accessibilityState={{selected:all}} style={[s.pill,all&&s.chosen]}>
    <Text style={s.pillText}>All {targets.length} platforms</Text>
   </Pressable>
  </View>
  <TextInput value={search} onChangeText={setSearch}
   style={s.search} placeholder="Find Game Boy, PlayStation, Xbox, Sega, PC…"
   placeholderTextColor="#94a3b8" accessibilityLabel="Search native platform catalog"/>
  <ScrollView nestedScrollEnabled style={s.platformList} keyboardShouldPersistTaps="handled">
   {visible.map(t=><Pressable key={t.id} onPress={()=>setSelected(t.id)}
    accessibilityRole="button" accessibilityState={{selected:t.id===selected}}
    style={[s.platform,t.id===selected&&s.active]}>
    <View style={{flex:1,gap:2}}>
     <Text style={s.platformTitle}>{titleCaseId(t.id)} · {t.year}</Text>
     <Text style={s.note}>{t.generation} · {t.toolchain}</Text>
    </View>
    <Text style={[s.state,t.status!=='native_source'&&s.unavailable]}>
     {t.status==='native_source'?'Source ready':t.status==='licensed_sdk'?'Licensed SDK':'Adapter needed'}
    </Text>
   </Pressable>)}
  </ScrollView>
  <Text style={s.label}>Original gameplay style</Text>
  <ScrollView horizontal showsHorizontalScrollIndicator={false}
   style={s.styleScroll} contentContainerStyle={s.styleRow}>
   {choices.map(sid=><Pressable key={sid}
    accessibilityRole="button" accessibilityState={{selected:selectedStyle===sid}}
    onPress={()=>setStyle(sid)} style={[s.styleChoice,selectedStyle===sid&&s.styleActive]}>
    <Text style={s.styleText}>{titleCaseId(sid)}</Text>
   </Pressable>)}
  </ScrollView>
  {choices.length===0&&<Text style={s.note}>No supported gameplay engine for this hardware yet.</Text>}
  {current&&<View style={s.selectedInfo}>
    <Ionicons name="hardware-chip-outline" color={C.gold} size={18}/>
    <View style={{flex:1}}>
     <Text style={s.infoTitle}>{current.family} · {current.output.toUpperCase()} target</Text>
     <Text style={s.note}>{current.cpu} · {current.graphics}</Text>
     <Text style={s.note}>{current.status==='native_source'?'Source project implemented; native compilation and gameplay require verification':current.status==='licensed_sdk'?'Licensed console SDK access required':'Platform-specific emitter is not built yet'}</Text>
    </View>
   </View>}
  {onGenerate&&<Pressable accessibilityRole="button"
   accessibilityState={{disabled:!enabled||busy}} disabled={!enabled||busy}
   onPress={()=>onGenerate(selected,selectedStyle)}
   style={[s.build,(!enabled||busy)&&s.disabled]}>
   <Ionicons name="construct-outline" size={17} color="#052e16"/>
   <Text style={s.buildText}>{busy?'Generating project…':'Generate native game source ZIP'}</Text>
  </Pressable>}
  {!onGenerate&&<Text style={s.note}>Sign in and connect the authoritative practice host before generating source.</Text>}
  <Text style={s.subhead}>Generated native projects · {attempts.length}</Text>
  {attempts.length===0?<Text style={s.note}>No native project attempts yet. A reviewed crawler lesson is required for progression-linked generation. The offline CLI can generate a separate practice source project without XP.</Text>:
   attempts.slice(0,12).map(a=><View key={a.attempt_id} style={s.attempt}>
    <Ionicons name="file-tray-full-outline" color={C.gold} size={19}/>
    <View style={{flex:1}}>
     <Text style={s.infoTitle}>{titleCaseId(a.target_id)} · {titleCaseId(a.style)}</Text>
     <Text style={s.note}>Source only · compilation unverified · {a.attempt_id.slice(0,10)}</Text>
    </View>
    {onDownload&&<Pressable accessibilityRole="button" accessibilityLabel="Download native game source ZIP"
     disabled={busy} onPress={()=>onDownload(a.attempt_id)} style={s.download}>
     <Text style={s.downloadText}>Save ZIP</Text>
    </Pressable>}
   </View>)}
  <Text style={s.disclaimer}>No unlicensed console SDKs, system ROMs, decryption keys or copyrighted commercial game files are included. A source project is not a compiled or device-verified game.</Text>
 </View>;
}
const s=StyleSheet.create({
 root:{backgroundColor:'#141923',borderRadius:15,padding:12,gap:10,borderWidth:1,borderColor:'#374151'},
 title:{fontSize:14,fontWeight:'900',color:C.fg},copy:{fontSize:11,lineHeight:17,color:C.muted},
 chips:{flexDirection:'row',gap:7,flexWrap:'wrap'},pill:{paddingVertical:8,paddingHorizontal:12,borderRadius:10,backgroundColor:'#253247'},
 chosen:{borderWidth:1,borderColor:C.gold},pillText:{fontWeight:'800',fontSize:11,color:C.fg},
 search:{backgroundColor:'#0b1220',padding:10,borderRadius:9,borderWidth:1,borderColor:'#334155',fontSize:12,color:C.fg},
 platformList:{maxHeight:190},platform:{flexDirection:'row',alignItems:'center',padding:9,borderRadius:9,gap:8,borderBottomWidth:1,borderBottomColor:'#334155'},
 active:{backgroundColor:'#344150'},platformTitle:{color:C.fg,fontWeight:'800',fontSize:11},
 note:{color:C.muted,fontSize:10,lineHeight:14},state:{fontSize:9,color:C.mint,fontWeight:'800'},
 unavailable:{color:C.gold},label:{color:C.fg,fontSize:11,fontWeight:'800'},
 styleScroll:{maxHeight:46},styleRow:{flexDirection:'row',gap:7,alignItems:'center'},
 styleChoice:{padding:9,backgroundColor:'#263548',borderRadius:10},
 styleActive:{borderWidth:1,borderColor:C.gold,backgroundColor:'#574529'},
 styleText:{fontSize:10,fontWeight:'700',color:C.fg},
 selectedInfo:{flexDirection:'row',alignItems:'center',gap:9,padding:10,borderRadius:9,backgroundColor:'#27303f'},
 infoTitle:{fontSize:11,fontWeight:'800',color:C.fg},
 build:{backgroundColor:C.mint,padding:12,borderRadius:12,gap:7,flexDirection:'row',justifyContent:'center',alignItems:'center'},
 disabled:{opacity:.40},buildText:{fontSize:12,fontWeight:'900',color:'#052e16'},
 subhead:{color:C.fg,fontSize:12,fontWeight:'800'},
 attempt:{flexDirection:'row',alignItems:'center',gap:9,borderRadius:8,padding:9,backgroundColor:'#1e293b'},
 download:{backgroundColor:'#345a46',padding:9,borderRadius:9},
 downloadText:{color:C.mint,fontSize:10,fontWeight:'800'},
 disclaimer:{fontSize:10,lineHeight:16,color:'#94a3b8'},
});
