import React from 'react';
import {StyleSheet, Text, View} from 'react-native';

/** Historical, read-only projection of mother Dragon's reviewed subtext. */
export interface MotherGleanSummary {
  schema: 'skeleton.dragon.mother_glean_summary.v1';
  observed_at: string;
  source_count: number;
  search_count: number;
  hypothesis_count: number;
  synergy_count: number;
  research_gap_count: number;
  lenses: string[];
  questions: string[];
  synergy_questions: string[];
  last_improvement: string;
  evidence_digest: string;
  model_promotion_authorized: false;
}

const bounded = (x: unknown, max: number): x is number =>
  Number.isSafeInteger(x) && typeof x === 'number' && x >= 0 && x <= max;

export function normalizeMotherGleanSummary(raw: unknown): MotherGleanSummary | null {
  if (raw === null || typeof raw !== 'object') return null;
  const p = raw as Partial<MotherGleanSummary>;
  const short = (a: unknown, max: number): a is string[] =>
    Array.isArray(a) && a.length <= max &&
    a.every(x => typeof x === 'string' && x.length >= 1 && x.length <= 240);
  if (p.schema !== 'skeleton.dragon.mother_glean_summary.v1' ||
      p.model_promotion_authorized !== false ||
      typeof p.observed_at !== 'string' ||
      !Number.isFinite(Date.parse(p.observed_at)) ||
      typeof p.evidence_digest !== 'string' ||
      !/^[0-9a-f]{64}$/.test(p.evidence_digest) ||
      !bounded(p.source_count, 6) || p.source_count === 0 ||
      !bounded(p.search_count, 216) || p.search_count === 0 ||
      p.search_count % 3 !== 0 ||
      !bounded(p.hypothesis_count, 72) ||
      !bounded(p.synergy_count, 42) ||
      !bounded(p.research_gap_count, 72) ||
      !short(p.lenses, 12) ||
      p.lenses.some(v => !/^[a-z_]{1,32}$/.test(v)) ||
      !short(p.questions, 8) || !short(p.synergy_questions, 6) ||
      typeof p.last_improvement !== 'string' ||
      p.last_improvement.length > 350 ||
      !p.last_improvement.startsWith('(') ||
      !p.last_improvement.endsWith(')')) return null;
  return p as MotherGleanSummary;
}

/** Displays hypotheses, never executes acquisition or asserts learned truth. */
export default function DragonMotherGleanPanel({summary}: {
  summary?: MotherGleanSummary | null;
}) {
  const glean = normalizeMotherGleanSummary(summary);
  if (!glean) return null;
  return <View style={styles.panel} accessibilityLabel="Mother Dragon glean matrix">
    <Text style={styles.title}>🐉 Mother Dragon · wisdom lenses</Text>
    <Text style={styles.meta}>{glean.source_count} child acquisitions · {glean.search_count} reviewed searches · {glean.lenses.length} lenses</Text>
    <View style={styles.row}>
      <Text style={styles.metric}>{glean.hypothesis_count} hypotheses</Text>
      <Text style={styles.metric}>{glean.synergy_count} synergies</Text>
      <Text style={styles.metric}>{glean.research_gap_count} research gaps</Text>
    </View>
    {glean.questions.slice(0, 3).map((question, index) =>
      <Text key={'q' + index} style={styles.question}>🔍 {question}</Text>)}
    {glean.synergy_questions.slice(0, 2).map((question, index) =>
      <Text key={'s' + index} style={styles.synergy}>✨ {question}</Text>)}
    <Text style={styles.disclaimer}>Unconfirmed insights are shadow hypotheses, not verified discoveries or model training.</Text>
    <Text style={styles.note}>{glean.observed_at} · {glean.last_improvement}</Text>
    <Text style={styles.receipt}>Evidence: {glean.evidence_digest.slice(0, 16)}…</Text>
  </View>;
}

const styles = StyleSheet.create({
  panel: {padding: 11, gap: 8, borderRadius: 12,
    backgroundColor: '#1e2233', borderColor: '#7c3f25', borderWidth: 1},
  title: {color: '#fcd34d', fontSize: 13, fontWeight: '800'},
  meta: {color: '#cbd5e1', fontSize: 10},
  row: {flexDirection: 'row', flexWrap: 'wrap', gap: 6},
  metric: {color: '#fde68a', fontWeight: '700', fontSize: 10,
    padding: 6, backgroundColor: '#334155', borderRadius: 7},
  question: {color: '#e2e8f0', fontSize: 11, lineHeight: 16},
  synergy: {color: '#bbf7d0', fontSize: 11, lineHeight: 16},
  disclaimer: {color: '#94a3b8', fontSize: 10},
  note: {color: '#94a3b8', fontSize: 9},
  receipt: {color: '#64748b', fontSize: 9},
});
