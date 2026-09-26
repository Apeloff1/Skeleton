/**
 * Compose panel: vision input + highlighted vision + live component graph.
 * Presentational: the parent owns the vision text and compose state.
 */
import React from 'react';
import { ActivityIndicator, StyleSheet, Text, TextInput, View } from 'react-native';
import type { ComposeState } from '../hooks';
import { VISION_MAX } from '../questionnaire';
import ComponentGraph from './ComponentGraph';
import { Banner, Card, SectionTitle } from './primitives';
import { C } from './theme';
import VisionHighlight from './VisionHighlight';

export interface ComposePanelProps {
  vision: string;
  onChangeVision?: (v: string) => void;
  compose: ComposeState;
  /** Show the text input (false when embedded next to the questionnaire). */
  editable?: boolean;
  initialWidth?: number;
  testID?: string;
}

export default function ComposePanel({ vision, onChangeVision, compose, editable = true, initialWidth, testID }: ComposePanelProps) {
  const [selected, setSelected] = React.useState<string | null>(null);
  const stale = !!compose.result && compose.vision !== vision.trim();
  const result = compose.result;
  React.useEffect(() => setSelected(null), [result?.blueprint_id]);
  return (
    <View testID={testID}>
      <SectionTitle hint="POST /api/skeleton/compose · live">🧬 Vision → systems</SectionTitle>
      {editable ? (
        <Card>
          <Text style={st.label} nativeID="compose-vision-label">Describe the game</Text>
          <TextInput
            testID="compose-vision-input"
            value={vision}
            onChangeText={onChangeVision}
            placeholder="e.g. a co-op heist where you craft gear, dodge a storm timer and a butler advises you"
            placeholderTextColor={C.dim}
            multiline
            maxLength={VISION_MAX}
            accessibilityLabel="Game vision"
            accessibilityLabelledBy="compose-vision-label"
            accessibilityHint="The component graph updates as you type"
            style={st.input}
          />
          <Text style={st.counter} accessibilityLabel={`${vision.length} of ${VISION_MAX} characters`}>{vision.length}/{VISION_MAX}</Text>
        </Card>
      ) : null}
      <Card label="Vision with trigger words highlighted">
        <View style={st.statusRow}>
          <Text style={st.summary} accessibilityLiveRegion="polite" testID="compose-summary">
            {result ? result.summary ?? `${result.features.length} systems` : vision.trim() ? 'Composing…' : 'Waiting for a vision'}
          </Text>
          {compose.loading ? <ActivityIndicator size="small" color={C.accent} accessibilityLabel="Composing" /> : null}
          {stale && !compose.loading ? <Text style={st.stale}>updating</Text> : null}
        </View>
        <VisionHighlight vision={compose.vision || vision} matches={result?.matches} testID="compose-highlight" />
      </Card>
      {compose.error ? <Banner tone="bad" testID="compose-error">Compose failed: {compose.error}</Banner> : null}
      <ComponentGraph result={result} initialWidth={initialWidth} selected={selected} onSelect={setSelected} testID="compose-graph" />
      {result?.blueprint_id ? <Text style={st.bp}>Preview blueprint {result.blueprint_id} · {result.wires.length} wires</Text> : null}
    </View>
  );
}

const st = StyleSheet.create({
  label: { color: C.mute, fontSize: 12, fontWeight: '700', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.6 },
  input: {
    minHeight: 88, color: C.text, fontSize: 15, lineHeight: 22, backgroundColor: C.cardAlt, borderRadius: 10,
    borderWidth: 1, borderColor: C.borderStrong, padding: 12, textAlignVertical: 'top',
  },
  counter: { color: C.dim, fontSize: 11, textAlign: 'right', marginTop: 4 },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  summary: { color: C.textStrong, fontWeight: '700', fontSize: 13, flexShrink: 1 },
  stale: { color: C.dim, fontSize: 11 },
  bp: { color: C.dim, fontSize: 11, marginTop: 4, marginBottom: 12 },
});
