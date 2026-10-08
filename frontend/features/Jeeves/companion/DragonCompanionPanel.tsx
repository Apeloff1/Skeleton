import React, { useEffect, useMemo, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useReducedMotion } from './useDragonMotion';
import { DEFAULT_COMPANION_PREFERENCES, type CompanionMotion } from './dragonPreferences';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { extractConversationInterests, proposeResearchMission } from './conversationInterests';
import { Ionicons } from '@expo/vector-icons';
import DragonCompanion from './DragonCompanion';
import DragonQuestBoard from './DragonQuestBoard';
import {type DragonPracticeProgress,type DragonPracticeAttempt,type DragonPracticeSubscription,validateDragonProgress} from './dragonProgression';
import { companionForConversation, companionFromCrawler, type DragonEventKind } from './dragonCompanion';

export interface CompanionTelemetry {
  kind: DragonEventKind;
  payload?: Record<string, unknown>;
  pages?: number;
  knowledgeItems?: number;
  quality?: number;
}

export interface CompanionAcademyInput {
  progress?:DragonPracticeProgress|null;
  attempts?:readonly DragonPracticeAttempt[];
  subscription?:DragonPracticeSubscription|null;
  onRunPractice?:()=>void;
  onOpenDemo?:(attemptId:string)=>void;
  onStopPractice?:()=>void;
  practiceBusy?:boolean;
}

export default function DragonCompanionPanel({ draft, lastUserText, telemetry, academy }: {
  draft: string;
  lastUserText?: string;
  telemetry?: CompanionTelemetry;
  academy?: CompanionAcademyInput;
}) {
  const [showResearch, setShowResearch] = useState(false);
  const [showAcademy,setShowAcademy]=useState(true);
  const verifiedProgress=validateDragonProgress(academy?.progress);
  const [motion, setMotion] = useState<CompanionMotion>(DEFAULT_COMPANION_PREFERENCES.motion);
  const systemReducedMotion = useReducedMotion();
  const [motionLoaded, setMotionLoaded] = useState(false);
  useEffect(() => {
    let mounted = true;
    AsyncStorage.getItem('skeleton.dragon.motion.v1').then(value => {
      if (mounted && (value === 'full' || value === 'gentle' || value === 'off')) setMotion(value);
    }).catch(() => {}).finally(() => { if (mounted) setMotionLoaded(true); });
    return () => { mounted = false; };
  }, []);
  useEffect(() => {
    if (motionLoaded) void AsyncStorage.setItem('skeleton.dragon.motion.v1', motion).catch(() => {});
  }, [motion, motionLoaded]);
  const interest = draft.trim() || lastUserText || '';
  const interests = useMemo(() => extractConversationInterests([{ role: 'user', text: interest }]), [interest]);
  const proposal = useMemo(() => proposeResearchMission(interests), [interests]);
  const state = telemetry
    ? companionFromCrawler(telemetry.kind, telemetry.payload)
    : companionForConversation(interest);
  return <View style={s.panel}>
    <DragonCompanion state={state} motion={motion} reducedMotion={systemReducedMotion}
      level={verifiedProgress?.level} unlocked={verifiedProgress?.unlocked} />
    <View style={s.motionRow}><Text style={s.label}>Animation · 120 tiny moments</Text>{(['full','gentle','off'] as const).map(choice => <Pressable key={choice} accessibilityRole="button" accessibilityState={{selected:motion===choice}} onPress={() => setMotion(choice)} style={[s.motionButton,motion===choice && s.motionSelected]}><Text style={s.value}>{choice}</Text></Pressable>)}</View>
    <View style={s.stats}>
      <Metric icon="chatbubble-ellipses-outline" label="Interest" value={interest ? interest.split(/\s+/).slice(0, 5).join(' ') : 'Listening'} />
      <Metric icon="globe-outline" label="Pages" value={String(telemetry?.pages ?? 0)} />
      <Metric icon="library-outline" label="Knowledge" value={String(telemetry?.knowledgeItems ?? 0)} />
      <Metric icon="diamond-outline" label="Quality" value={telemetry?.quality == null ? '—' : Math.round(telemetry.quality * 100) + '%'} />
    </View>
    <Pressable accessibilityRole="button" accessibilityLabel="Inspect suggested research interests" onPress={() => setShowResearch(v => !v)} style={s.metric}><Ionicons name="bulb-outline" size={16} color="#fb923c" /><Text style={s.value}>{showResearch ? 'Hide research interests' : 'Inspect research interests'}</Text></Pressable>
    {showResearch && <View style={s.metric}><Text style={s.value}>{proposal ? proposal.query : 'No research interest yet'}</Text><Text style={s.note}>Suggestion only · no web crawl starts without a separate explicit command.</Text></View>}
    <Pressable accessibilityRole="button" accessibilityLabel="Toggle Dragon Academy" onPress={()=>setShowAcademy(x=>!x)} style={s.academyButton}><Ionicons name="trophy-outline" color="#fbbf24" size={16}/><Text style={s.academyText}>{showAcademy?"Hide":"Show"} Dragon Academy · capability levels & game practice</Text></Pressable>
    {showAcademy&&<DragonQuestBoard progress={academy?.progress} attempts={academy?.attempts}
      subscription={academy?.subscription} onRunPractice={academy?.onRunPractice}
      onOpenDemo={academy?.onOpenDemo} onStopPractice={academy?.onStopPractice}
      busy={academy?.practiceBusy} />}
    <Text style={s.note}>Petting and animation are just for fun. System reduced-motion settings take priority. These reactions never start research or change memory.</Text>
    <Text style={s.note}>Conversation creates interest signals. Only policy-compliant, provenance-preserved acquisitions may become distilled memory.</Text>
  </View>;
}
function Metric({ icon, label, value }: { icon: keyof typeof Ionicons.glyphMap; label: string; value: string }) {
  return <View style={s.metric}><Ionicons name={icon} size={14} color="#fb923c" /><View style={s.copy}><Text style={s.label}>{label}</Text><Text numberOfLines={1} style={s.value}>{value}</Text></View></View>;
}
const s = StyleSheet.create({
  panel: { gap: 10, width: '100%' },
  academyButton:{flexDirection:'row',alignItems:'center',gap:7,padding:11,borderRadius:11,backgroundColor:'#2b2537',borderColor:'#a16207',borderWidth:1},
  academyText:{fontSize:12,fontWeight:'800',color:'#fef3c7',flex:1},
  motionRow:{flexDirection:'row',alignItems:'center',gap:5,flexWrap:'wrap'},motionButton:{paddingHorizontal:9,paddingVertical:5,borderRadius:10,backgroundColor:'#1e293b'},motionSelected:{backgroundColor:'#7c3f25'},
  stats: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  metric: { flexGrow: 1, minWidth: 112, flexDirection: 'row', alignItems: 'center', gap: 7, padding: 9, borderRadius: 11, borderWidth: 1, borderColor: '#334155', backgroundColor: '#111827' },
  copy: { flex: 1 }, label: { color: '#94a3b8', fontSize: 9, fontWeight: '700', textTransform: 'uppercase' },
  value: { color: '#f8fafc', fontSize: 11, fontWeight: '700' },
  note: { color: '#64748b', fontSize: 9, lineHeight: 14, paddingHorizontal: 2 },
});
