import React,{useState} from 'react';
import{Pressable,StyleSheet,Text,View}from'react-native';
import{Ionicons}from'@expo/vector-icons';
import{
 type DragonPracticeProgress,type DragonPracticeAttempt,
 type DragonPracticeSubscription,
 dragonRank,levelFraction,normalizeDragonAttempts,validateDragonProgress,
}from'./dragonProgression';

const C={fg:'#f8fafc',muted:'#aab7ca',mint:'#86efac',gold:'#fbbf24',rose:'#f9a8d4',bg:'#111827'};
type Icon=keyof typeof Ionicons.glyphMap;
const skills:ReadonlyArray<{key:string;label:string;icon:Icon;color:string;detail:string}>=[
 {key:'research',label:'Research',icon:'telescope-outline',color:'#60a5fa',detail:'Reviewed knowledge'},
 {key:'game_design',label:'Design',icon:'shapes-outline',color:'#fda4af',detail:'Playtested designs'},
 {key:'prototyping',label:'Forge',icon:'hammer-outline',color:'#fbbf24',detail:'Original demo attempts'},
 {key:'verification',label:'Validation',icon:'shield-checkmark-outline',color:'#86efac',detail:'Reviewed gameplay'},
];
const quests=[
 {id:'first_source',label:'First spark',description:'Promote a reviewed evidence-backed lesson',get:(p:DragonPracticeProgress)=>p.verified_lessons>=1,reward:'30 knowledge XP'},
 {id:'first_demo',label:'Tiny game forge',description:'Generate your first original offline game demo',get:(p:DragonPracticeProgress)=>p.demos_built>=1,reward:'A playable prototype'},
 {id:'first_playtest',label:'QA hatchling',description:'Finish a documented human playtest',get:(p:DragonPracticeProgress)=>p.demos_reviewed>=1,reward:'55 mastery XP'},
 {id:'trilogy',label:'Three little worlds',description:'Review three separate game attempts',get:(p:DragonPracticeProgress)=>p.demos_reviewed>=3,reward:'Progress toward a new rank'},
 {id:'dragon_master',label:'Game Dragon',description:'Reach level 10 through verified practice',get:(p:DragonPracticeProgress)=>p.level>=10,reward:'Star Cartographer title'},
];
const trophies=[
 ['little_explorer','🥚','Little explorer'],['apprentice_forge','🛠️','Forge apprentice'],
 ['glasses_scholar','👓','Glasses scholar'],['winged_builder','🪽','Winged builder'],
 ['star_cartographer','🌟','Star cartographer'],['master_game_dragon','🐉','Master game dragon'],
] as const;

export interface DragonQuestBoardProps{
 progress?:DragonPracticeProgress|null;
 attempts?:readonly DragonPracticeAttempt[];
 subscription?:DragonPracticeSubscription|null;
 onRunPractice?:()=>void;
 onStartPractice?:()=>void;
 onOpenDemo?:(attemptId:string)=>void;
 onStopPractice?:()=>void;
 onRevokePractice?:()=>void;
 busy?:boolean;
}
export default function DragonQuestBoard({
 progress,attempts=[],subscription,onRunPractice,onStartPractice,onOpenDemo,onStopPractice,onRevokePractice,busy=false
}:DragonQuestBoardProps){
 const [tab,setTab]=useState<'quests'|'workshop'>('quests');
 const [confirmRevoke,setConfirmRevoke]=useState(false);
 // No pseudo-XP when the trusted host has not supplied an accepted projection.
 const verified=validateDragonProgress(progress);
 const history=normalizeDragonAttempts(attempts);
 const cleared=verified?quests.filter(q=>q.get(verified)).length:0;
 const fraction=verified?levelFraction(verified):0;
 return <View style={s.root} accessibilityLabel="Dragon academy and game practice">
  <View style={s.head}>
   <View style={s.rankBadge}><Text style={s.rankEmoji}>🐲</Text><View style={{flex:1}}>
    <Text style={s.overline}>DRAGON ACADEMY</Text>
    <Text style={s.rank}>{verified?dragonRank(verified.level):'Awaiting first adventure'}</Text>
    <Text style={s.caption}>{verified?'Proof-backed progress · no free XP':'Connect verified crawler and practice receipts to level up'}</Text>
   </View></View>
   <View style={s.levelTile}>
    <Text style={s.levelLabel}>LEVEL</Text>
    <Text style={s.level}>{verified?verified.level:'—'}</Text>
   </View>
  </View>
  <View accessibilityRole="progressbar" accessibilityLabel="Progress to next dragon level"
   accessibilityValue={{min:0,max:100,now:Math.round(fraction*100)}} style={s.xpTrack}>
   <View style={[s.xpFill,{width:`${Math.round(fraction*100)}%`}]}/>
  </View>
  <View style={s.xpRow}><Text style={s.caption}>{verified?`${verified.xp} earned XP`:'Verified XP not connected'}</Text>
   <Text style={s.caption}>{verified?`${verified.next_level_xp} XP for next level`:'No XP from chat or petting'}</Text>
  </View>
  <View style={s.metrics}>
   <Stat icon="book-outline" label="Learned" value={verified?.verified_lessons}/>
   <Stat icon="game-controller-outline" label="Built" value={verified?.demos_built}/>
   <Stat icon="checkmark-done-outline" label="Playtested" value={verified?.demos_reviewed}/>
   <Stat icon="sparkles-outline" label="Quest seals" value={verified?cleared:undefined}/>
  </View>
  <Text style={s.groupHeading}>Capability tree</Text>
  <View style={s.skills}>
   {skills.map(skill=>{
    const n=verified?.skills[skill.key]??0;
    return <View key={skill.key} style={s.skill}>
     <View style={s.skillHead}><Ionicons name={skill.icon} size={16} color={skill.color}/>
      <Text style={s.skillName}>{skill.label}</Text><Text style={s.skillN}>{verified?`${n}/100`:'—'}</Text>
     </View>
     <View style={s.miniTrack}><View style={[s.miniFill,{width:`${n}%`,backgroundColor:skill.color}]}/></View>
     <Text style={s.small}>{skill.detail}</Text>
    </View>;
   })}
  </View>
  <Text style={s.groupHeading}>Evolution collection</Text>
  <View style={s.trophies}>
   {trophies.map(([name,emoji,label])=>{
    const unlocked=verified?.unlocked.includes(name)??false;
    return <View key={name} style={[s.trophy,unlocked&&s.trophyWon]}>
     <Text style={[s.trophyEmoji,!unlocked&&s.lockedEmoji]}>{emoji}</Text>
     <Text style={[s.trophyTitle,!unlocked&&s.muted]}>{label}</Text>
     <Text style={s.unlockState}>{unlocked?'UNLOCKED':'LOCKED'}</Text>
    </View>
   })}
  </View>
  <View style={s.tabs}>
   <Pressable accessibilityRole="button" accessibilityState={{selected:tab==='quests'}}
    onPress={()=>setTab('quests')} style={[s.tab,tab==='quests'&&s.activeTab]}><Text style={s.tabText}>Quests</Text></Pressable>
   <Pressable accessibilityRole="button" accessibilityState={{selected:tab==='workshop'}}
    onPress={()=>setTab('workshop')} style={[s.tab,tab==='workshop'&&s.activeTab]}><Text style={s.tabText}>Game workshop</Text></Pressable>
  </View>
  {tab==='quests'?<View style={s.questList}>
    {quests.map((quest,index)=>{
     const done=verified?quest.get(verified):false;
     return <View key={quest.id} style={s.quest}>
      <View style={[s.questMark,done&&s.questDone]}>
       <Ionicons name={done?'checkmark':'lock-closed-outline'} color={done?'#052e16':'#94a3b8'} size={17}/>
      </View>
      <View style={{flex:1}}><Text style={s.questTitle}>{index+1}. {quest.label}</Text>
       <Text style={s.caption}>{quest.description}</Text>
       <Text style={s.questReward}>{quest.reward}</Text>
      </View>
     </View>;
    })}
   </View>:<View style={s.workshop}>
    <Text style={s.workshopTitle}>The little game foundry</Text>
    <Text style={s.caption}>After reviewed knowledge is promoted, make original offline microgames as experiments. Each build needs a separate playtest before mastery XP is awarded.</Text>
    <View style={s.workshopRow}><View style={{flex:1}}>
     <Text style={s.statusTitle}>{subscription?.enabled?'Practice subscription active':'Practice is opt-in'}</Text>
     <Text style={s.caption}>{subscription?.enabled?`${subscription.remaining_ticks} bounded cycles remaining`:'No autonomous work without approval and a connected scheduler.'}</Text>
    </View>
    {subscription?.enabled&&onStopPractice&&<Pressable accessibilityRole="button" accessibilityLabel="Stop scheduled practice" onPress={onStopPractice} style={s.stop}><Text style={s.stopText}>Stop</Text></Pressable>}
    </View>
    {!subscription?.enabled&&onStartPractice&&<Pressable disabled={busy} accessibilityRole="button"
      accessibilityLabel="Enable Dragon practice for one day" onPress={onStartPractice}
      accessibilityState={{disabled:busy}} style={s.practiceStart}>
      <Ionicons name="time-outline" size={17} color="#fef3c7"/>
      <Text style={s.practiceStartText}>Enable 24h hourly practice · up to 2 demos / run</Text>
    </Pressable>}
    {onRunPractice&&<Pressable disabled={busy} accessibilityRole="button" onPress={onRunPractice}
     accessibilityState={{disabled:busy}} style={[s.run,busy&&{opacity:.5}]}>
     <Ionicons name="hammer-outline" size={17} color="#15271c"/><Text style={s.runText}>{busy?'Preparing attempt…':'Generate a practice demo'}</Text>
    </Pressable>}
    {!onRunPractice&&<Text style={s.notConnected}>Demo creation requires the authenticated practice host. No demo has been started from this screen.</Text>}
    {onRevokePractice&&<Pressable accessibilityRole="button"
      accessibilityLabel={confirmRevoke?'Confirm revocation of lesson practice consent':'Revoke lesson practice consent'}
      onPress={()=>{
       if(confirmRevoke){onRevokePractice();setConfirmRevoke(false);}
       else setConfirmRevoke(true);
      }} style={s.revoke}>
      <Text style={s.revokeText}>{confirmRevoke?'Confirm: revoke all approved practice grants':'Revoke practice consent for lessons'}</Text>
    </Pressable>}
    {history.length===0?<Text style={s.empty}>No workshop attempts recorded yet. Your first documented attempt will appear here.</Text>:
     history.slice(0,8).map(a=><View key={a.attempt_id} style={s.attempt}>
      <Ionicons name={a.state==='reviewed'?'trophy-outline':a.state==='failed'?'alert-circle-outline':'game-controller-outline'}
       color={a.state==='reviewed'?C.gold:C.muted} size={20}/>
      <View style={{flex:1}}><Text style={s.questTitle}>{a.kind.replaceAll('_',' ')}</Text>
       <Text style={s.caption}>{a.state} · {a.supported.join(', ')||'Scaffold only'}</Text>
       {!!a.deferred.length&&<Text style={s.small}>Deferred: {a.deferred.join(', ')}</Text>}
      </View>
      {!!a.artifact_digest&&onOpenDemo&&<Pressable accessibilityRole="button"
       accessibilityLabel="Open offline game demo" onPress={()=>onOpenDemo(a.attempt_id)} style={s.open}>
       <Text style={s.openText}>Play</Text>
      </Pressable>}
     </View>)}
   </View>}
  <Text style={s.disclaimer}>Levels unlock companion presentation only. Knowledge and engine capability are promoted by independent evidence checks, not by an XP threshold.</Text>
 </View>;
}
function Stat({icon,label,value}:{icon:Icon;label:string;value?:number}){
 return <View style={s.stat}><Ionicons name={icon} size={17} color={C.gold}/>
  <Text style={s.statNumber}>{value===undefined?'—':value}</Text><Text style={s.small}>{label}</Text></View>;
}
const s=StyleSheet.create({
 root:{backgroundColor:'#0f172a',borderRadius:19,borderWidth:1,borderColor:'#334155',padding:14,gap:11},
 head:{flexDirection:'row',alignItems:'center',gap:10},rankBadge:{flex:1,flexDirection:'row',gap:10,alignItems:'center'},
 rankEmoji:{fontSize:35},overline:{fontSize:9,color:C.gold,letterSpacing:1.7,fontWeight:'900'},rank:{color:C.fg,fontSize:17,fontWeight:'900'},
 caption:{color:C.muted,fontSize:11,lineHeight:16},levelTile:{padding:9,borderWidth:1,borderColor:'#ca8a04',borderRadius:14,minWidth:58,alignItems:'center'},
 levelLabel:{fontSize:9,color:C.gold,fontWeight:'900'},level:{fontSize:23,fontWeight:'900',color:C.fg},
 xpTrack:{height:11,borderRadius:10,backgroundColor:'#334155',overflow:'hidden'},xpFill:{height:'100%',backgroundColor:C.gold,borderRadius:10},
 xpRow:{flexDirection:'row',justifyContent:'space-between',flexWrap:'wrap'},
 metrics:{flexDirection:'row',gap:7,flexWrap:'wrap'},stat:{flexGrow:1,minWidth:65,backgroundColor:'#1e293b',borderRadius:12,alignItems:'center',padding:8,gap:3},
 statNumber:{color:C.fg,fontSize:17,fontWeight:'800'},small:{fontSize:9,color:'#94a3b8'},
 groupHeading:{fontSize:13,fontWeight:'900',color:C.fg,marginTop:6},skills:{flexDirection:'row',gap:8,flexWrap:'wrap'},
 skill:{width:'48%',minWidth:120,flexGrow:1,padding:10,borderRadius:11,backgroundColor:'#1e293b',gap:6},
 skillHead:{flexDirection:'row',alignItems:'center',gap:4},skillName:{fontSize:11,color:C.fg,fontWeight:'700',flex:1},
 skillN:{fontSize:10,color:C.muted},miniTrack:{height:5,backgroundColor:'#475569',borderRadius:5,overflow:'hidden'},
 miniFill:{height:'100%',borderRadius:5},trophies:{flexDirection:'row',flexWrap:'wrap',gap:7},
 trophy:{flexBasis:'30%',flexGrow:1,borderWidth:1,borderColor:'#334155',borderRadius:12,paddingVertical:12,paddingHorizontal:6,alignItems:'center',gap:3},
 trophyWon:{backgroundColor:'#2e2919',borderColor:'#a16207'},trophyEmoji:{fontSize:23},lockedEmoji:{opacity:.22},
 trophyTitle:{fontSize:9,color:C.fg,textAlign:'center',fontWeight:'700'},muted:{color:'#64748b'},unlockState:{fontSize:8,color:C.muted,fontWeight:'800'},
 tabs:{flexDirection:'row',gap:8,marginTop:4},tab:{flex:1,padding:10,alignItems:'center',backgroundColor:'#1e293b',borderRadius:11},
 activeTab:{backgroundColor:'#374151',borderWidth:1,borderColor:'#fbbf24'},tabText:{fontSize:11,color:C.fg,fontWeight:'800'},
 questList:{gap:7},quest:{flexDirection:'row',gap:11,alignItems:'center',padding:9,backgroundColor:'#1e293b',borderRadius:12},
 questMark:{height:30,width:30,borderRadius:15,backgroundColor:'#334155',alignItems:'center',justifyContent:'center'},
 questDone:{backgroundColor:C.mint},questTitle:{color:C.fg,fontSize:12,fontWeight:'800'},
 questReward:{color:C.gold,fontSize:10,fontWeight:'700',marginTop:3},
 workshop:{gap:9},workshopTitle:{fontSize:14,color:C.fg,fontWeight:'900'},
 workshopRow:{backgroundColor:'#1e293b',borderRadius:11,padding:10,flexDirection:'row',gap:8,alignItems:'center'},
 statusTitle:{fontSize:11,color:C.fg,fontWeight:'800'},stop:{padding:8,borderWidth:1,borderColor:'#fca5a5',borderRadius:9},
 stopText:{color:'#fca5a5',fontSize:11},run:{backgroundColor:C.mint,padding:12,borderRadius:12,
  flexDirection:'row',alignItems:'center',justifyContent:'center',gap:8},runText:{color:'#15271c',fontWeight:'900'},
 practiceStart:{flexDirection:'row',gap:7,alignItems:'center',padding:11,backgroundColor:'#4b3c21',borderRadius:11},
 practiceStartText:{color:'#fef3c7',fontSize:11,fontWeight:'700',flex:1},
 revoke:{padding:10,borderRadius:10,borderWidth:1,borderColor:'#9f5353',alignItems:'center'},
 revokeText:{color:'#fca5a5',fontSize:10,fontWeight:'700'},
 notConnected:{color:'#93c5fd',fontSize:10,lineHeight:16},
 empty:{color:C.muted,fontSize:11,textAlign:'center',paddingVertical:13},
 attempt:{flexDirection:'row',alignItems:'center',gap:10,padding:10,borderRadius:10,backgroundColor:'#1e293b'},
 open:{backgroundColor:'#365a4a',paddingHorizontal:12,paddingVertical:8,borderRadius:9},
 openText:{color:C.mint,fontSize:11,fontWeight:'800'},disclaimer:{fontSize:10,lineHeight:15,color:'#94a3b8',marginTop:4},
});
