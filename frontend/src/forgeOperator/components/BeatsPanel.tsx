/**
 * Thin beats catalogue — GET /api/skeleton/beats via operator catalog hook.
 */
import React from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { Banner, Button, Card, SectionTitle } from '../../skeletonForge/components/primitives';
import { C } from '../../skeletonForge/components/theme';
import type { Beat } from '../types';

export interface BeatsPanelProps {
  beats: Beat[];
  loading: boolean;
  error: string | null;
  onReload: () => void;
  testID?: string;
}

export default function BeatsPanel({ beats, loading, error, onReload, testID }: BeatsPanelProps) {
  return (
    <View testID={testID}>
      <SectionTitle hint={`${beats.length} beats · GET /api/skeleton/beats`}>🎙 Questionnaire beats</SectionTitle>
      {error ? <Banner tone="bad" testID="operator-beats-error">{error}</Banner> : null}
      {error ? <Button label="Retry" tone="secondary" compact onPress={onReload} testID="operator-beats-retry" /> : null}
      {loading && !beats.length ? (
        <ActivityIndicator color={C.accent} accessibilityLabel="Loading beats" style={{ marginVertical: 20 }} />
      ) : null}
      {!loading && !error && !beats.length ? <Text style={st.empty}>No beats available.</Text> : null}
      {beats.map((b) => (
        <Card key={b.id} testID={`operator-beat-${b.id}`} label={b.id}>
          <Text style={st.id}>{b.id}</Text>
          <Text style={st.prompt}>{b.prompt}</Text>
          <View style={st.opts}>
            {(b.options || []).map((o) => (
              <Text key={o} style={st.opt}>
                · {o}
              </Text>
            ))}
          </View>
        </Card>
      ))}
    </View>
  );
}

const st = StyleSheet.create({
  empty: { color: C.mute, fontSize: 14, marginVertical: 12 },
  id: { color: C.accent, fontSize: 12, fontWeight: '800', marginBottom: 4, textTransform: 'uppercase' },
  prompt: { color: C.textStrong, fontSize: 14, lineHeight: 20, marginBottom: 8 },
  opts: { gap: 2 },
  opt: { color: C.mute, fontSize: 13 },
});
