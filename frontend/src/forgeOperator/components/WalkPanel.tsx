/**
 * Thin walk screen — POST /api/skeleton/walk via forgeOperator client.
 */
import React from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { Banner, Button, Card, SectionTitle } from '../../skeletonForge/components/primitives';
import { C } from '../../skeletonForge/components/theme';
import type { WalkPreview } from '../types';
import { summarizeWalk } from '../walkSummary';

export interface WalkPanelProps {
  vision: string;
  era: string;
  preview: WalkPreview | null;
  loading: boolean;
  error: string | null;
  onWalk: () => void;
  testID?: string;
}

export default function WalkPanel({ vision, era, preview, loading, error, onWalk, testID }: WalkPanelProps) {
  const summary = React.useMemo(() => summarizeWalk(preview), [preview]);
  const tone: 'ok' | 'bad' | 'warn' = summary?.verdict === 'passed' ? 'ok' : summary ? 'bad' : 'warn';

  return (
    <View testID={testID}>
      <SectionTitle hint="POST /api/skeleton/walk">🚶 Walk preview</SectionTitle>
      <Card>
        <Text style={st.lead}>
          Simulate an extraction walk for the current vision{era ? ` · era ${era}` : ''}.
        </Text>
        <Text style={st.vision} numberOfLines={4}>
          {vision.trim() || '(no vision yet — set one on Compose / Run)'}
        </Text>
        <Button
          label="Preview walk"
          tone="primary"
          onPress={onWalk}
          disabled={!vision.trim() || loading}
          busy={loading}
          testID="operator-walk-run"
        />
        {loading ? <ActivityIndicator color={C.accent} style={{ marginTop: 12 }} accessibilityLabel="Walking" /> : null}
        {error ? <Banner tone="bad" testID="operator-walk-error">{error}</Banner> : null}
      </Card>
      {summary ? (
        <Card testID="operator-walk-result" label="Walk result">
          <Banner tone={tone} testID="operator-walk-verdict">
            {summary.label} — {summary.detail}
          </Banner>
          <Fact k="Mode" v={summary.mode} />
          <Fact k="Elapsed / bound" v={`${summary.elapsed} / ${summary.bound}`} />
          <Fact k="Hops / fights" v={`${summary.hops} / ${summary.fights}`} />
          <Fact k="Cores" v={summary.cores} />
          <Fact k="Heat peak / vents" v={`${summary.heatPeak} / ${summary.vents}`} />
          <Fact k="Path" v={summary.pathLabel} />
          {summary.notes.length ? (
            <Text style={st.notes}>{summary.notes.map((n) => `· ${n}`).join('\n')}</Text>
          ) : null}
          {summary.stepsPreview.length ? (
            <View style={st.steps} testID="operator-walk-steps">
              <Text style={st.k}>Steps ({summary.stepCount})</Text>
              <Text style={st.stepsTxt}>{summary.stepsPreview.join('\n')}</Text>
            </View>
          ) : null}
        </Card>
      ) : null}
      {summary ? (
        <Card testID="operator-walk-plan" label="Plan summary">
          <Fact k="Era" v={summary.planEra} />
          <Fact k="Seed" v={summary.planSeed} />
          <Fact k="Oracle" v={summary.planOracle} />
          <Fact k="Room bias" v={summary.planBias} />
          <Fact k="Briefing" v={summary.planBriefing} />
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
  steps: { marginTop: 10 },
  stepsTxt: { color: C.mute, fontSize: 12, lineHeight: 18, fontFamily: 'monospace' },
});
