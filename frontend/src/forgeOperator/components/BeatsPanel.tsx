/**
 * Interactive beats questionnaire — GET /api/skeleton/beats via catalog hook.
 * Local answer state; Surprise / Clear / Apply use catalog + beatSummary helpers.
 */
import React from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { Banner, Button, Card, Chip, SectionTitle, StatusPill } from '../../skeletonForge/components/primitives';
import { C } from '../../skeletonForge/components/theme';
import { seededAnswers } from '../catalog';
import { isOptionSelected, summarizeBeats } from '../beatSummary';
import type { Beat } from '../types';

export interface BeatsPanelProps {
  beats: Beat[];
  loading: boolean;
  error: string | null;
  onReload: () => void;
  /** Optional: apply cleaned answers (e.g. pin era + jump to compose). */
  onApplyAnswers?: (cleaned: Record<string, string>) => void;
  testID?: string;
}

export default function BeatsPanel({
  beats,
  loading,
  error,
  onReload,
  onApplyAnswers,
  testID,
}: BeatsPanelProps) {
  const [answers, setAnswers] = React.useState<Record<string, string>>({});
  const summary = React.useMemo(() => summarizeBeats(beats, answers), [beats, answers]);

  const toggleOption = React.useCallback((beatId: string, option: string) => {
    setAnswers((prev) => {
      if (prev[beatId] === option) {
        const next = { ...prev };
        delete next[beatId];
        return next;
      }
      return { ...prev, [beatId]: option };
    });
  }, []);

  const onSurprise = React.useCallback(() => {
    if (!beats.length) return;
    setAnswers(seededAnswers(beats, Date.now() >>> 0));
  }, [beats]);

  const onClear = React.useCallback(() => {
    setAnswers({});
  }, []);

  const onApply = React.useCallback(() => {
    if (!summary || !onApplyAnswers) return;
    onApplyAnswers(summary.cleaned);
  }, [summary, onApplyAnswers]);

  const progressTone = !summary
    ? 'idle'
    : summary.complete
      ? 'ok'
      : summary.answered > 0
        ? 'warn'
        : 'idle';

  return (
    <View testID={testID}>
      <SectionTitle hint={`${beats.length} beats · GET /api/skeleton/beats`}>🎙 Questionnaire beats</SectionTitle>
      {error ? <Banner tone="bad" testID="operator-beats-error">{error}</Banner> : null}
      {error ? <Button label="Retry" tone="secondary" compact onPress={onReload} testID="operator-beats-retry" /> : null}
      {loading && !beats.length ? (
        <ActivityIndicator color={C.accent} accessibilityLabel="Loading beats" style={{ marginVertical: 20 }} />
      ) : null}
      {!loading && !error && !beats.length ? <Text style={st.empty}>No beats available.</Text> : null}

      {beats.length ? (
        <Card testID="operator-beats-controls">
          {summary ? (
            <View style={st.progressRow} testID="operator-beats-progress">
              <StatusPill tone={progressTone} label={summary.progressLabel} />
              {summary.complete ? (
                <Text style={st.completeHint}>Required beats complete</Text>
              ) : summary.missing.length ? (
                <Text style={st.missingHint} numberOfLines={2}>
                  Missing: {summary.missing.join(', ')}
                </Text>
              ) : null}
            </View>
          ) : null}
          <View style={st.actions}>
            <Button label="Surprise me" tone="secondary" compact onPress={onSurprise} testID="operator-beats-surprise" />
            <Button
              label="Clear answers"
              tone="ghost"
              compact
              onPress={onClear}
              disabled={!Object.keys(answers).length}
              testID="operator-beats-clear"
            />
            {onApplyAnswers ? (
              <Button
                label="Use in forge"
                tone="primary"
                compact
                onPress={onApply}
                disabled={!summary || summary.cleanedCount === 0}
                testID="operator-beats-apply"
              />
            ) : null}
          </View>
          {summary && summary.answerSheet.length ? (
            <View style={st.sheet} testID="operator-beats-sheet">
              <Text style={st.k}>Cleaned answers ({summary.cleanedCount})</Text>
              <Text style={st.sheetTxt}>{summary.answerSheet.join('\n')}</Text>
            </View>
          ) : null}
        </Card>
      ) : null}

      {beats.map((b) => (
        <Card key={b.id} testID={`operator-beat-${b.id}`} label={b.id}>
          <Text style={st.id}>{b.id}</Text>
          <Text style={st.prompt}>{b.prompt}</Text>
          <View style={st.chips} accessibilityRole="radiogroup" accessibilityLabel={b.prompt}>
            {(b.options || []).map((o) => {
              const selected = isOptionSelected(answers, b.id, o);
              return (
                <Chip
                  key={o}
                  label={o}
                  selected={selected}
                  color={C.green}
                  onPress={() => toggleOption(b.id, o)}
                  testID={`operator-beat-${b.id}-${o}`}
                  a11yLabel={`${o}${selected ? ', selected' : ''}`}
                />
              );
            })}
          </View>
        </Card>
      ))}
    </View>
  );
}

const st = StyleSheet.create({
  empty: { color: C.mute, fontSize: 14, marginVertical: 12 },
  progressRow: { marginBottom: 10, gap: 6 },
  completeHint: { color: C.green, fontSize: 12, fontWeight: '600' },
  missingHint: { color: C.mute, fontSize: 12 },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 4 },
  sheet: { marginTop: 10 },
  k: { color: C.dim, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', marginBottom: 4 },
  sheetTxt: { color: C.mute, fontSize: 12, lineHeight: 18, fontFamily: 'monospace' },
  id: { color: C.accent, fontSize: 12, fontWeight: '800', marginBottom: 4, textTransform: 'uppercase' },
  prompt: { color: C.textStrong, fontSize: 14, lineHeight: 20, marginBottom: 8 },
  chips: { flexDirection: 'row', flexWrap: 'wrap' },
});
