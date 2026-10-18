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

const specialistSymbols: Record<string, string> = {
  article: '📖',
  video: '🎞️',
  updates: '🔎',
};

const dragonForm = (stage: string): string => stage === 'egg' ? '🥚' : '🐉';
const percentage = (value: number, total: number): number =>
  total > 0 ? Math.min(100, Math.round(value * 100 / total)) : 0;
// React Native expects a DimensionValue percentage template, not an arbitrary
// string. Keep values bounded by the verified nest progress contract.
const progressWidth = (value: number, total: number): `${number}%` =>
  `${percentage(value, total)}%`;

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
      snapshot.sources_total > 10000 ||
      !/^[0-9a-f]{64}$/.test(snapshot.history_head) ||
      !Number.isFinite(Date.parse(snapshot.last_changed_at)) ||
      !snapshot.last_improvement.startsWith('(') || !snapshot.last_improvement.endsWith(')')) return false;
  const expected = ['article', 'video', 'updates'];
  if (snapshot.children.length !== 0 && snapshot.children.length !== 3) return false;
  if ((snapshot.stage === 'adult') !== (snapshot.children.length === 3)) return false;
  return snapshot.children.every((c, i) =>
    c != null && typeof c === 'object' && c.lane === expected[i] &&
    Number.isSafeInteger(c.level) && c.level >= 0 && c.level <= 20 &&
    Number.isSafeInteger(c.knowledge_items) && c.knowledge_items >= 0 &&
    c.knowledge_items <= 8192 &&
    ['egg', 'hatchling', 'juvenile', 'adult'].includes(c.stage));
}

/** Reject stale, malformed or incomplete API payloads instead of inventing pet progress. */
export function normalizeDragonNestSnapshot(value: unknown): DragonNestSnapshot | null {
  if (value === null || typeof value !== 'object') return null;
  const candidate = value as DragonNestSnapshot;
  return valid(candidate) ? candidate : null;
}

/** A display only: tapping or rendering this component never starts research. */
export default function DragonNestProgression({ snapshot }: {
  snapshot?: DragonNestSnapshot | null;
}) {
  if (!valid(snapshot)) return null;
  const collected = percentage(snapshot.sources_consumed, snapshot.sources_total);
  return <View style={styles.panel} accessibilityLabel="Dragon nest progression">
    <View style={styles.hero}>
      <Text style={styles.parentIcon} accessibilityLabel={snapshot.stage === 'egg' ? 'Dragon egg' : 'Dragon parent'}>
        {dragonForm(snapshot.stage)}
      </Text>
      <View style={styles.parentText}>
        <Text style={styles.title}>Dragon nest · {snapshot.stage.replace(/_/g, ' ')} · level {snapshot.level}/20</Text>
        <Text style={styles.note}>Reviewed source expedition: {snapshot.sources_consumed}/{snapshot.sources_total}</Text>
        <View accessible accessibilityRole="progressbar" accessibilityValue={{min: 0, max: 100, now: collected}}
          accessibilityLabel="Parent Dragon source progression" style={styles.track}>
          <View style={[styles.fill, {width: progressWidth(snapshot.sources_consumed, snapshot.sources_total)}]} />
        </View>
      </View>
    </View>
    {snapshot.children.length === 0 ?
      <Text style={styles.note}>Complete the reviewed source census to unlock three specialist eggs.</Text> :
      <View style={styles.row}>{snapshot.children.map(child =>
        <View key={child.lane} style={styles.child} accessibilityLabel={specialistNames[child.lane] + ', ' + child.stage + ', level ' + child.level}>
          <Text style={styles.petIcon}>{dragonForm(child.stage)}</Text>
          <Text style={styles.label}>{specialistSymbols[child.lane]} {specialistNames[child.lane]}</Text>
          <Text style={styles.value}>{child.stage} · level {child.level}/20</Text>
          <View accessible accessibilityRole="progressbar"
            accessibilityLabel={specialistNames[child.lane] + ' progression'}
            accessibilityValue={{min: 0, max: 20, now: child.level}} style={styles.track}>
            <View style={[styles.childFill, {width: progressWidth(child.level, 20)}]} />
          </View>
          <Text style={styles.note}>{child.knowledge_items} unique verified versions</Text>
        </View>)}</View>}
    <Text style={styles.note}>Hatchlings grow only from new verified information during permitted idle research. Model learning requires independent approval.</Text>
    <Text style={styles.history}>Last change {snapshot.last_changed_at}: {snapshot.last_improvement}</Text>
    <Text style={styles.receipt}>History receipt: {snapshot.history_head.slice(0, 16)}…</Text>
  </View>;
}

const styles = StyleSheet.create({
  panel: { gap: 8, padding: 10, borderColor: '#64748b', borderWidth: 1, borderRadius: 12, backgroundColor: '#161e2e' },
  title: { color: '#fde68a', fontWeight: '800', fontSize: 13 },
  hero: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  parentIcon: { fontSize: 36 },
  parentText: { flex: 1, gap: 5 },
  petIcon: { fontSize: 28, alignSelf: 'center' },
  track: { width: '100%', height: 6, borderRadius: 6, backgroundColor: '#334155', overflow: 'hidden' },
  fill: { height: '100%', borderRadius: 6, backgroundColor: '#f59e0b' },
  childFill: { height: '100%', borderRadius: 6, backgroundColor: '#60a5fa' },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  child: { padding: 9, minWidth: 115, flexGrow: 1, borderRadius: 10, borderWidth: 1, borderColor: '#475569', backgroundColor: '#1f2937' },
  label: { color: '#fbbf24', fontWeight: '700', fontSize: 11 },
  value: { color: '#f8fafc', fontWeight: '700', fontSize: 11 },
  note: { color: '#cbd5e1', fontSize: 10, lineHeight: 15 },
  history: { color: '#e2e8f0', fontSize: 10 },
  receipt: { color: '#94a3b8', fontSize: 9 },
});
