import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

/** Read-only projection from the server's reviewed DragonNest state. */
export interface DragonNestSnapshot {
  schema: 'skeleton.dragon.nest.v1';
  stage: 'egg' | 'hatchling' | 'juvenile' | 'young_adult' | 'adult';
  level: number;
  sources_consumed: number;
  sources_total: number;
  children: readonly {
    lane: 'article' | 'video' | 'updates';
    stage: 'egg' | 'hatchling' | 'juvenile' | 'adult';
    level: number;
    knowledge_items: number;
  }[];
  history_head: string;
  last_changed_at: string;
  last_improvement: string;
  promotion_authorized: false;
}

const specialistNames: Record<string, string> = {
  article: 'Article almanac',
  video: 'Video almanac',
  updates: 'Freshness scout',
};

function valid(snapshot: DragonNestSnapshot | null | undefined): snapshot is DragonNestSnapshot {
  if (!snapshot || snapshot.schema !== 'skeleton.dragon.nest.v1' ||
      !Array.isArray(snapshot.children) ||
      typeof snapshot.history_head !== 'string' ||
      typeof snapshot.last_changed_at !== 'string' ||
      typeof snapshot.last_improvement !== 'string' ||
      snapshot.last_improvement.length > 360 ||
      !['egg', 'hatchling', 'juvenile', 'young_adult', 'adult'].includes(snapshot.stage)) return false;
  if (snapshot.promotion_authorized !== false ||
      !Number.isSafeInteger(snapshot.level) || snapshot.level < 0 || snapshot.level > 20 ||
      !Number.isSafeInteger(snapshot.sources_total) || snapshot.sources_total < 1 ||
      !Number.isSafeInteger(snapshot.sources_consumed) || snapshot.sources_consumed < 0 ||
      snapshot.sources_consumed > snapshot.sources_total ||
      !/^[0-9a-f]{64}$/.test(snapshot.history_head) ||
      !Number.isFinite(Date.parse(snapshot.last_changed_at)) ||
      !snapshot.last_improvement.startsWith('(') || !snapshot.last_improvement.endsWith(')')) return false;
  const expected = ['article', 'video', 'updates'];
  if (snapshot.children.length !== 0 && snapshot.children.length !== 3) return false;
  return snapshot.children.every((c, i) =>
    c.lane === expected[i] && Number.isSafeInteger(c.level) && c.level >= 0 && c.level <= 20 &&
    Number.isSafeInteger(c.knowledge_items) && c.knowledge_items >= 0 &&
    ['egg', 'hatchling', 'juvenile', 'adult'].includes(c.stage));
}

/** A display only: tapping or rendering this component never starts research. */
export default function DragonNestProgression({ snapshot }: {
  snapshot?: DragonNestSnapshot | null;
}) {
  if (!valid(snapshot)) return null;
  return <View style={styles.panel} accessibilityLabel="Dragon nest progression">
    <Text style={styles.title}>Dragon nest · {snapshot.stage.replace(/_/g, ' ')} · level {snapshot.level}/20</Text>
    <Text style={styles.note}>Reviewed sources {snapshot.sources_consumed}/{snapshot.sources_total}. Hatchlings unlock when the source census is complete.</Text>
    {snapshot.children.length === 3 &&
      <View style={styles.row}>{snapshot.children.map(child =>
        <View key={child.lane} style={styles.child}>
          <Text style={styles.label}>{specialistNames[child.lane]}</Text>
          <Text style={styles.value}>{child.stage} · level {child.level}/20</Text>
          <Text style={styles.note}>{child.knowledge_items} unique verified versions</Text>
        </View>)}</View>}
    <Text style={styles.note}>Hatchlings only learn during authorized idle research. No automatic model promotion.</Text>
    <Text style={styles.history}>Last change {snapshot.last_changed_at}: {snapshot.last_improvement}</Text>
    <Text style={styles.receipt}>History receipt: {snapshot.history_head.slice(0, 16)}…</Text>
  </View>;
}

const styles = StyleSheet.create({
  panel: { gap: 8, padding: 10, borderColor: '#64748b', borderWidth: 1, borderRadius: 12, backgroundColor: '#161e2e' },
  title: { color: '#fde68a', fontWeight: '800', fontSize: 13 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  child: { padding: 9, minWidth: 115, flexGrow: 1, borderRadius: 10, borderWidth: 1, borderColor: '#475569', backgroundColor: '#1f2937' },
  label: { color: '#fbbf24', fontWeight: '700', fontSize: 11 },
  value: { color: '#f8fafc', fontWeight: '700', fontSize: 11 },
  note: { color: '#cbd5e1', fontSize: 10, lineHeight: 15 },
  history: { color: '#e2e8f0', fontSize: 10 },
  receipt: { color: '#94a3b8', fontSize: 9 },
});
