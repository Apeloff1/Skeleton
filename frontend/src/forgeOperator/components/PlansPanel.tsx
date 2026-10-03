/**
 * Thin plans screen — POST /api/skeleton/plan via forgeOperator client.
 */
import React from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { Banner, Button, Card, SectionTitle } from '../../skeletonForge/components/primitives';
import { C } from '../../skeletonForge/components/theme';
import type { BuildPlan } from '../types';
import { summarizePlan } from '../planSummary';

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
  const summary = React.useMemo(() => summarizePlan(plan), [plan]);

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
      {summary ? (
        <Card testID="operator-plan-result" label="Plan result">
          <Fact k="Era" v={summary.era} />
          <Fact k="Seed" v={summary.seed} />
          <Fact k="Tensor" v={summary.tensorFp} />
          <Fact k="Oracle" v={summary.oracle} />
          <Fact k="Briefing" v={summary.briefing} />
          <Fact k="Room bias" v={summary.roomBias} />
          <Fact k="Adapt" v={summary.adapt} />
          <Fact k="Slack" v={summary.slack} />
          <Fact k="Authored" v={summary.authored} />
          <Fact k="Enemy mix" v={summary.enemyMixLabel} />
          <Fact k="Recipes" v={summary.recipesLabel} />
          {summary.flagLabels.length ? (
            <View style={st.flags} testID="operator-plan-flags">
              <Text style={st.k}>Flags</Text>
              <View style={st.flagRow}>
                {summary.flagLabels.map((label) => (
                  <View key={label} style={st.flagChip}>
                    <Text style={st.flagTxt}>{label}</Text>
                  </View>
                ))}
              </View>
            </View>
          ) : null}
          {summary.notes.length ? (
            <Text style={st.notes}>{summary.notes.map((n) => `· ${n}`).join('\n')}</Text>
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
  flags: { marginTop: 4, marginBottom: 8 },
  flagRow: { flexDirection: 'row', flexWrap: 'wrap', marginTop: 4 },
  flagChip: {
    borderWidth: 1,
    borderColor: C.border,
    backgroundColor: C.cardAlt,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 4,
    marginRight: 6,
    marginBottom: 6,
  },
  flagTxt: { color: C.text, fontSize: 12, fontWeight: '600' },
});
