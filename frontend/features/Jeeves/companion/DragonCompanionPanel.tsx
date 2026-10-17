import { useRouter } from 'expo-router';
import React, { useEffect, useMemo, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useReducedMotion, useScreenReader } from './useDragonMotion';
import { usePowerAwareness } from '../../../hooks/usePowerAwareness';
import { DEFAULT_COMPANION_PREFERENCES, effectiveMotion, type CompanionMotion } from './dragonPreferences';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { approveResearchMission, extractConversationInterests, proposeResearchMission, type ApprovedResearchMission } from './conversationInterests';
import { Ionicons } from '@expo/vector-icons';
import DragonCompanion from './DragonCompanion';
import DragonFamilyNest from './DragonFamilyNest';
import type {DragonFamilyProjection} from './dragonFamilyProjection';
import DragonQuestBoard from './DragonQuestBoard';
import type{NativeAttempt,NativeTarget,NativeCurriculum}from './dragonNativeTargets';
import {type DragonPracticeProgress,type DragonPracticeAttempt,type DragonPracticeSubscription,validateDragonProgress} from './dragonProgression';
import { companionForConversation, companionFromCrawler, type DragonEventKind } from './dragonCompanionState';

export interface CompanionTelemetry {
  kind: DragonEventKind;
  payload?: Record<string, unknown>;
  pages?: number;
  knowledgeItems?: number;
  quality?: number;
}

export interface CompanionAcademyInput {
  family?: DragonFamilyProjection|null;
  progress?:DragonPracticeProgress|null;
  attempts?:readonly DragonPracticeAttempt[];
  nativeAttempts?:readonly NativeAttempt[];
  nativeTargets?:readonly NativeTarget[];
  nativeStyles?:readonly string[];
  nativeCurriculum?:NativeCurriculum|null;
  onGenerateCurriculum?:()=>void;
  onGenerateNative?:(target:string,style:string)=>void;
  onDownloadNative?:(attemptId:string)=>void;
  subscription?:DragonPracticeSubscription|null;
  onRunPractice?:()=>void;
  onStartPractice?:()=>void;
  onOpenDemo?:(attemptId:string)=>void;
  onStopPractice?:()=>void;
  onRevokePractice?:()=>void;
  practiceBusy?:boolean;
}

export default function DragonCompanionPanel({ draft, lastUserText, telemetry, academy }: {
  draft: string;
  lastUserText?: string;
  telemetry?: CompanionTelemetry;
  academy?: CompanionAcademyInput;
}) {
  const router = useRouter();
  const [showResearch, setShowResearch] = useState(false);
  const [showAcademy,setShowAcademy]=useState(false);
  const verifiedProgress=validateDragonProgress(academy?.progress);
  const [motion, setMotion] = useState<CompanionMotion>(DEFAULT_COMPANION_PREFERENCES.motion);
  const [lowPower, setLowPower] = useState(DEFAULT_COMPANION_PREFERENCES.lowPower);
  const [privacy, setPrivacy] = useState(DEFAULT_COMPANION_PREFERENCES.privacy);
  const [hosts, setHosts] = useState('');
  const [approval, setApproval] = useState<ApprovedResearchMission | null>(null);
  const systemReducedMotion = useReducedMotion();
  const screenReader = useScreenReader();
  const power = usePowerAwareness();
  const shownMotion = effectiveMotion({ ...DEFAULT_COMPANION_PREFERENCES, motion, lowPower, privacy }, systemReducedMotion, power.shouldReduceAnimations);
  const [motionLoaded, setMotionLoaded] = useState(false);
  useEffect(() => {
    let mounted = true;
    Promise.all([
      AsyncStorage.getItem('skeleton.dragon.motion.v1'),
      AsyncStorage.getItem('skeleton.dragon.comfort.v1'),
    ]).then(([motionValue, comfortRaw]) => {
      if (!mounted) return;
      if (motionValue === 'full' || motionValue === 'gentle' || motionValue === 'off') setMotion(motionValue);
      if (comfortRaw) {
        const saved = JSON.parse(comfortRaw) as { lowPower?: boolean; privacy?: string };
        if (saved.lowPower === true) setLowPower(true);
        if (saved.privacy === 'local-only' || saved.privacy === 'approved-research') setPrivacy(saved.privacy);
      }
    }).catch(() => {}).finally(() => { if (mounted) setMotionLoaded(true); });
    return () => { mounted = false; };
  }, []);
  useEffect(() => {
    if (motionLoaded) {
      void AsyncStorage.setItem('skeleton.dragon.motion.v1', motion).catch(() => {});
      void AsyncStorage.setItem('skeleton.dragon.comfort.v1', JSON.stringify({ lowPower, privacy })).catch(() => {});
    }
  }, [motion, motionLoaded, lowPower, privacy]);
  const interest = draft.trim() || lastUserText || '';
  const interests = useMemo(() => extractConversationInterests([{ role: 'user', text: interest }]), [interest]);
  const proposal = useMemo(() => proposeResearchMission(interests), [interests]);
  const state = telemetry
    ? companionFromCrawler(telemetry.kind, telemetry.payload)
    : companionForConversation(interest);
  const approve = () => {
    const next = approveResearchMission(proposal, {
      approved: true, privacy, sourceHosts: hosts.split(/[\s,]+/), maxPages: proposal?.maxPages, maxSources: proposal?.maxSources,
    });
    setApproval(next);
  };
  return <View style={s.panel}>
    <DragonCompanion state={state} motion={shownMotion} reducedMotion={shownMotion === 'off'} screenReader={screenReader}
      level={verifiedProgress?.level} unlocked={verifiedProgress?.unlocked} />
    <DragonFamilyNest family={academy?.family} />
    <View style={s.motionRow}><Text style={s.label}>Animation · 120 tiny moments</Text>{(['full','gentle','off'] as const).map(choice => <Pressable key={choice} accessibilityRole="button" accessibilityState={{selected:motion===choice}} onPress={() => setMotion(choice)} style={[s.motionButton,motion===choice && s.motionSelected]}><Text style={s.value}>{choice}</Text></Pressable>)}<Pressable accessibilityRole="button" accessibilityState={{selected:lowPower}} onPress={() => setLowPower(value => !value)} style={[s.motionButton, lowPower && s.motionSelected]}><Text style={s.value}>low power</Text></Pressable></View>
    {(screenReader || power.shouldReduceAnimations || systemReducedMotion || lowPower) && <Text style={s.note}>{screenReader ? 'Screen reader is active. ' : ''}{power.shouldReduceAnimations ? 'Battery saver is slowing the dragon. ' : ''}{systemReducedMotion ? 'System reduced motion is on. ' : ''}{lowPower ? 'Low-power mode is on.' : ''}</Text>}
    <View style={s.stats}>
      <Metric icon="chatbubble-ellipses-outline" label="Interest" value={interest ? interest.split(/\s+/).slice(0, 5).join(' ') : 'Listening'} />
      <Metric icon="globe-outline" label="Pages" value={String(telemetry?.pages ?? 0)} />
      <Metric icon="library-outline" label="Knowledge" value={String(telemetry?.knowledgeItems ?? 0)} />
      <Metric icon="diamond-outline" label="Quality" value={telemetry?.quality == null ? '—' : Math.round(telemetry.quality * 100) + '%'} />
    </View>
    <Pressable accessibilityRole="button" accessibilityLabel="Inspect suggested research interests" onPress={() => setShowResearch(v => !v)} style={s.metric}><Ionicons name="bulb-outline" size={16} color="#fb923c" /><Text style={s.value}>{showResearch ? 'Hide research interests' : 'Inspect research interests'}</Text></Pressable>
    {showResearch && <View style={s.research}><Text style={s.value}>{proposal ? proposal.query : 'No research interest yet'}</Text><Text style={s.note}>Suggestion only · no web crawl starts without a separate explicit command.</Text>
      <Pressable accessibilityRole="button" accessibilityState={{selected:privacy==='approved-research'}} onPress={() => setPrivacy(value => value === 'approved-research' ? 'local-only' : 'approved-research')} style={s.motionButton}><Text style={s.value}>{privacy === 'approved-research' ? 'Research privacy on' : 'Keep topics local'}</Text></Pressable>
      <TextInput accessibilityLabel="Allowed research hosts" value={hosts} onChangeText={setHosts} autoCapitalize="none" autoCorrect={false} placeholder="example.org, docs.example.org" placeholderTextColor="#64748b" style={s.hostInput} />
      <Pressable accessibilityRole="button" accessibilityLabel="Approve bounded research scope" onPress={approve} style={s.motionButton}><Text style={s.value}>Approve topic and host scope</Text></Pressable>
      <Text style={s.note}>{approval ? `Approved topics “${approval.query}” on ${approval.sourceHosts.join(', ')}. Conversation history stays here.` : 'Approval records a bounded topic and host scope. It does not send conversation history and does not start a crawl.'}</Text>
      {approval && <Pressable accessibilityRole="button" accessibilityLabel="Open capture with approved topics and hosts. This does not start the crawl." onPress={() => router.push(`/crawler?topics=${encodeURIComponent(approval.query)}&seeds=${encodeURIComponent(approval.sourceHosts.map(host => `https://${host}/`).join('\n'))}` as never)} style={s.motionButton}><Text style={s.value}>Open capture with these topics and hosts</Text></Pressable>}
    </View>}
    <Pressable accessibilityRole="button" accessibilityLabel="Toggle Dragon Academy" onPress={()=>setShowAcademy(x=>!x)} style={s.academyButton}><Ionicons name="trophy-outline" color="#fbbf24" size={16}/><Text style={s.academyText}>{showAcademy?"Hide":"Show"} Dragon Academy · capability levels & game practice</Text></Pressable>
    {showAcademy&&<DragonQuestBoard progress={academy?.progress} attempts={academy?.attempts}
      nativeAttempts={academy?.nativeAttempts} nativeTargets={academy?.nativeTargets}
      nativeStyles={academy?.nativeStyles}
      nativeCurriculum={academy?.nativeCurriculum}
      onGenerateCurriculum={academy?.onGenerateCurriculum}
      onGenerateNative={academy?.onGenerateNative}
      onDownloadNative={academy?.onDownloadNative}
      subscription={academy?.subscription} onRunPractice={academy?.onRunPractice}
      onStartPractice={academy?.onStartPractice}
      onOpenDemo={academy?.onOpenDemo} onStopPractice={academy?.onStopPractice}
      onRevokePractice={academy?.onRevokePractice}
      busy={academy?.practiceBusy} />}
    <Pressable accessibilityRole="button" accessibilityLabel="Open source review and measured reference practice" onPress={() => router.push('/crawler?pane=review' as never)} style={s.academyButton}><Ionicons name="library-outline" color="#fbbf24" size={16} /><Text style={s.academyText}>Source review & measured reference practice</Text></Pressable><Text style={s.note}>Captured passages need a separate human decision. Practice reports only actual reference-environment observations; reviewing a source does not award XP or grant model-training rights.</Text><Text style={s.note}>Petting and animation are just for fun. System reduced-motion settings take priority. These reactions never start research or change memory.</Text>
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
  hostInput: { minWidth: 180, flexGrow: 1, borderWidth: 1, borderColor: '#334155', borderRadius: 8, color: '#f8fafc', paddingHorizontal: 8, paddingVertical: 6, fontSize: 12 },
  research: { gap: 8, padding: 9, borderRadius: 11, borderWidth: 1, borderColor: '#334155', backgroundColor: '#111827' },
});
