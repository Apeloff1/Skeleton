import React, { useState } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import type { ChatCooperationSummary } from '../../product/chatCooperation';

const LABELS = { plan: 'Plan', draft: 'Draft', critique: 'Review', refine: 'Refine' };

export default function ChatCooperationDetails({ summary, stopped = false }: { summary: ChatCooperationSummary; stopped?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const models = new Set(summary.artifacts.map(artifact => JSON.stringify([artifact.provider, artifact.model])));
  return <View style={s.panel}>
    <TouchableOpacity accessibilityRole="button" accessibilityLabel="Show recorded response-review stages"
      accessibilityState={{ expanded }} onPress={() => setExpanded(value => !value)} style={s.toggle}>
      <Text style={s.title}>{stopped ? 'Response review stopped' : summary.complete ? 'Review and refinement recorded' : 'Response review in progress'} · {summary.completed_stages}/{summary.total_stages} stages {expanded ? '▴' : '▾'}</Text>
    </TouchableOpacity>
    {expanded && <View style={s.details}>
      <Text style={s.text}>{models.size === 0 ? 'No completed model stages have been recorded yet.' : models.size === 1 ? 'The same configured model performed these stages.' : `${models.size} configured models performed these stages.`} All stages share the original brief and source snapshot.</Text>
      {summary.artifacts.map(artifact => <View key={artifact.stage_id} style={s.stage}>
        <Text style={s.label}>{LABELS[artifact.role]}{artifact.stage_id.includes(':') ? ` ${artifact.stage_id.split(':')[1]}` : ''}</Text>
        <Text style={s.text}>{artifact.model}</Text>
        <Text selectable style={s.digest}>Output {artifact.output_digest.slice(0, 16)}…</Text>
      </View>)}
      <Text style={s.text}>{stopped ? 'This turn ended without a committed answer. These receipts record completed stages. Start a new message to request another response.' : 'The recorded model calls confirm these stages ran. Assess the answer before acting on it.'}</Text>
    </View>}
  </View>;
}

const s = StyleSheet.create({
  panel: { borderColor: '#3d3659', borderWidth: 1, borderRadius: 10, paddingHorizontal: 10 },
  toggle: { minHeight: 44, justifyContent: 'center' }, title: { color: '#c4b5fd', fontSize: 11, fontWeight: '600', lineHeight: 17 },
  details: { gap: 8, paddingBottom: 10 }, text: { color: '#94a3b8', fontSize: 11, lineHeight: 17 },
  stage: { borderTopColor: '#28364e', borderTopWidth: 1, paddingTop: 7, gap: 3 },
  label: { color: '#cbd5e1', fontSize: 11, fontWeight: '600' }, digest: { color: '#94a3b8', fontSize: 10 },
});
