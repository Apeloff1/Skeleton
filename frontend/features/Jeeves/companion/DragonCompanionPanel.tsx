import React, { useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { extractConversationInterests, proposeResearchMission } from './conversationInterests';
import { Ionicons } from '@expo/vector-icons';
import DragonCompanion from './DragonCompanion';
import { companionForConversation, companionFromCrawler, type DragonEventKind } from './dragonCompanion';

export interface CompanionTelemetry {
  kind: DragonEventKind;
  payload?: Record<string, unknown>;
  pages?: number;
  knowledgeItems?: number;
  quality?: number;
}

export default function DragonCompanionPanel({ draft, lastUserText, telemetry }: {
  draft: string;
  lastUserText?: string;
  telemetry?: CompanionTelemetry;
}) {
  const [showResearch, setShowResearch] = useState(false);
  const interest = draft.trim() || lastUserText || '';
  const interests = useMemo(() => extractConversationInterests([{ role: 'user', text: interest }]), [interest]);
  const proposal = useMemo(() => proposeResearchMission(interests), [interests]);
  const state = telemetry
    ? companionFromCrawler(telemetry.kind, telemetry.payload)
    : companionForConversation(interest);
  return <View style={s.panel}>
    <DragonCompanion state={state} />
    <View style={s.stats}>
      <Metric icon="chatbubble-ellipses-outline" label="Interest" value={interest ? interest.split(/\s+/).slice(0, 5).join(' ') : 'Listening'} />
      <Metric icon="globe-outline" label="Pages" value={String(telemetry?.pages ?? 0)} />
      <Metric icon="library-outline" label="Knowledge" value={String(telemetry?.knowledgeItems ?? 0)} />
      <Metric icon="diamond-outline" label="Quality" value={telemetry?.quality == null ? '—' : Math.round(telemetry.quality * 100) + '%'} />
    </View>
    <Pressable accessibilityRole="button" accessibilityLabel="Inspect suggested research interests" onPress={() => setShowResearch(v => !v)} style={s.metric}><Ionicons name="bulb-outline" size={16} color="#fb923c" /><Text style={s.value}>{showResearch ? 'Hide research interests' : 'Inspect research interests'}</Text></Pressable>
    {showResearch && <View style={s.metric}><Text style={s.value}>{proposal ? proposal.query : 'No research interest yet'}</Text><Text style={s.note}>Suggestion only · no web crawl starts without a separate explicit command.</Text></View>}
    <Text style={s.note}>Conversation creates interest signals. Only policy-compliant, provenance-preserved acquisitions may become distilled memory.</Text>
  </View>;
}
function Metric({ icon, label, value }: { icon: keyof typeof Ionicons.glyphMap; label: string; value: string }) {
  return <View style={s.metric}><Ionicons name={icon} size={14} color="#fb923c" /><View style={s.copy}><Text style={s.label}>{label}</Text><Text numberOfLines={1} style={s.value}>{value}</Text></View></View>;
}
const s = StyleSheet.create({
  panel: { gap: 10, width: '100%' },
  stats: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  metric: { flexGrow: 1, minWidth: 112, flexDirection: 'row', alignItems: 'center', gap: 7, padding: 9, borderRadius: 11, borderWidth: 1, borderColor: '#334155', backgroundColor: '#111827' },
  copy: { flex: 1 }, label: { color: '#94a3b8', fontSize: 9, fontWeight: '700', textTransform: 'uppercase' },
  value: { color: '#f8fafc', fontSize: 11, fontWeight: '700' },
  note: { color: '#64748b', fontSize: 9, lineHeight: 14, paddingHorizontal: 2 },
});
