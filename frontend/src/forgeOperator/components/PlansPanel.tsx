/**
 * Thin plans screen — POST /api/skeleton/plan via forgeOperator client.
 */
import React from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { Banner, Button, Card, SectionTitle } from '../../skeletonForge/components/primitives';
import { C } from '../../skeletonForge/components/theme';
import type { BuildPlan } from '../types';

export interface PlansPanelProps {
  vision: string;
  era: string;
  plan: BuildPlan | null;
  loading: boolean;
  error: string | null;
  onPlan: () => void;
  testID?: string;
}

export default function PlansPanel({ vision, era, plan, loading, error, onPlan, testID }: PlansPanelProps) {
  return (
    <View testID={testID}>
      <SectionTitle hint="POST /api/skeleton/plan">🗺 Build plan</SectionTitle>
      <Card>
        <Text style={st.lead}>
          Preview the Jeeves build plan for the current vision{era ? ` · era ${era}` : ''}.
        </Text>
        <Text style={st.vision} numberOfLines={4}>
          {vision.trim() || '(no vision yet — set one on Compose / Run)'}
        </Text>
        <Button
          label="Plan build"
          tone="primary"
          onPress={onPlan}
          disabled={!vision.trim() || loading}
          busy={loading}
          testID="operator-plan-run"
        />
        {loading ? <ActivityIndicator color={C.accent} style={{ marginTop: 12 }} accessibilityLabel="Planning" /> : null}
        {error ? <Banner tone="bad" testID="operator-plan-error">{error}</Banner> : null}
      </Card>
      {plan ? (
        <Card testID="operator-plan-result" label="Plan result">
          <Fact k="Era" v={plan.era} />
          <Fact k="Seed" v={plan.seed} />
          <Fact k="Oracle" v={plan.oracle_text || (plan.oracle_index != null ? `#${plan.oracle_index}` : '—')} />
          <Fact k="Briefing" v={plan.briefing || '—'} />
          <Fact k="Room bias" v={plan.room_bias || '—'} />
          <Fact k="Adapt" v={plan.adapt || '—'} />
          {plan.notes?.length ? (
            <Text style={st.notes}>{plan.notes.slice(0, 6).map((n) => `· ${n}`).join('\n')}</Text>
          ) : null}
        </Card>
      ) : null}
    </View>
  );
}

function Fact({ k, v }: { k: string; v: string }) {
  return (
    <View style={st.fact}>
      <Text style={st.k}>{k}</Text>
      <Text style={st.v}>{v}</Text>
    </View>
  );
}

const st = StyleSheet.create({
  lead: { color: C.mute, fontSize: 13, marginBottom: 8 },
  vision: { color: C.text, fontSize: 14, lineHeight: 20, marginBottom: 12, fontStyle: 'italic' },
  fact: { marginBottom: 8 },
  k: { color: C.dim, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' },
  v: { color: C.text, fontSize: 14 },
  notes: { color: C.mute, fontSize: 12, marginTop: 8, lineHeight: 18 },
});
