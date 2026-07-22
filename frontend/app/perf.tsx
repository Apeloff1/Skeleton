/**
 * /perf — performance triage dashboard.
 *
 * Aggregates the in-memory perf log produced by useRenderTrace and
 * shows:
 *   • Top-N slowest screens by p95 mount latency.
 *   • A live ticker of every recent mount (name · duration · timestamp).
 *   • Per-screen avg + max + count.
 *
 * Wired into /menu under the Tools category.
 */
import { useEffect, useMemo, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, StyleSheet, SafeAreaView } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { getPerfLog, clearPerfLog, subscribePerf, PerfSample } from '../utils/perf';
import { withScreenGuard } from '../components/withScreenGuard';

interface AggRow {
  name:    string;
  count:   number;
  avg:     number;
  max:     number;
  p95:     number;
  slowPct: number;
}

function aggregate(samples: PerfSample[]): AggRow[] {
  const byName: Record<string, number[]> = {};
  for (const s of samples) {
    (byName[s.name] ||= []).push(s.ms);
  }
  const rows: AggRow[] = Object.entries(byName).map(([name, arr]) => {
    const sorted = [...arr].sort((a, b) => a - b);
    const p95Idx = Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95));
    const sum = arr.reduce((a, b) => a + b, 0);
    return {
      name,
      count:   arr.length,
      avg:     Math.round(sum / arr.length),
      max:     sorted[sorted.length - 1] ?? 0,
      p95:     sorted[p95Idx] ?? 0,
      slowPct: Math.round((arr.filter(m => m > 300).length / arr.length) * 100),
    };
  });
  rows.sort((a, b) => b.p95 - a.p95);
  return rows;
}

function PerfScreen() {
  const router = useRouter();
  const [samples, setSamples] = useState<PerfSample[]>(() => getPerfLog());

  useEffect(() => {
    return subscribePerf(setSamples);
  }, []);

  const rows = useMemo(() => aggregate(samples), [samples]);
  const tot  = samples.length;
  const slow = samples.filter(s => s.slow).length;

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.canGoBack() ? router.back() : router.replace('/menu')} hitSlop={12}>
          <Ionicons name="chevron-back" size={26} color="#e2e8f0" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.badge}>Diagnostics</Text>
          <Text style={styles.title}>Performance</Text>
          <Text style={styles.sub}>{tot} samples · {slow} slow renders · {rows.length} screens</Text>
        </View>
        <TouchableOpacity onPress={clearPerfLog} style={styles.clearBtn}>
          <Text style={styles.clearText}>Clear</Text>
        </TouchableOpacity>
      </View>

      <ScrollView style={styles.scroll} contentContainerStyle={{ padding: 12, paddingBottom: 32 }}>
        <Text style={styles.sectionLabel}>p95 leaderboard (slowest first)</Text>
        {rows.length === 0 ? (
          <Text style={styles.dim}>No renders sampled yet. Navigate to a few screens then come back.</Text>
        ) : (
          rows.slice(0, 30).map(r => (
            <View key={r.name} style={styles.row}>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={styles.rowName} numberOfLines={1}>{r.name}</Text>
                <Text style={styles.rowMeta}>
                  count {r.count} · avg {r.avg}ms · max {r.max}ms · slow {r.slowPct}%
                </Text>
              </View>
              <View style={[styles.p95Pill, r.p95 > 300 ? styles.p95Slow : null]}>
                <Text style={[styles.p95Text, r.p95 > 300 ? styles.p95TextSlow : null]}>{r.p95}ms</Text>
                <Text style={styles.p95Cap}>p95</Text>
              </View>
            </View>
          ))
        )}

        <Text style={styles.sectionLabel}>Recent samples (newest first)</Text>
        {samples.slice().reverse().slice(0, 30).map((s, i) => (
          <View key={`${s.ts}-${i}`} style={styles.tickRow}>
            <Text style={styles.tickName} numberOfLines={1}>{s.name}</Text>
            <Text style={[styles.tickMs, s.slow ? styles.tickMsSlow : null]}>{s.ms}ms</Text>
            <Text style={styles.tickT}>{new Date(s.ts).toLocaleTimeString()}</Text>
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

export default withScreenGuard(PerfScreen, 'PerfRoute');

const styles = StyleSheet.create({
  safe:    { flex: 1, backgroundColor: '#0A0A0A' },
  header:  { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingTop: 12, paddingBottom: 14, borderBottomWidth: 1, borderBottomColor: '#262626' },
  badge:   { color: '#a78bfa', fontSize: 10, fontWeight: '800', letterSpacing: 1.4, textTransform: 'uppercase' },
  title:   { fontSize: 20, fontWeight: '800', color: '#f8fafc' },
  sub:     { fontSize: 11, color: '#94a3b8', marginTop: 2 },
  clearBtn:{ backgroundColor: '#262626', paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8 },
  clearText:{ color: '#e2e8f0', fontSize: 12, fontWeight: '700' },

  scroll:  { flex: 1 },
  sectionLabel: { color: '#a78bfa', fontSize: 11, fontWeight: '800', letterSpacing: 1, textTransform: 'uppercase', marginTop: 18, marginBottom: 8 },

  row:     { flexDirection: 'row', alignItems: 'center', backgroundColor: '#141414', padding: 12, borderRadius: 10, marginBottom: 6, gap: 8 },
  rowName: { color: '#e2e8f0', fontSize: 13, fontWeight: '700' },
  rowMeta: { color: '#94a3b8', fontSize: 10, marginTop: 2 },
  p95Pill: { backgroundColor: '#262626', paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, alignItems: 'center' },
  p95Slow: { backgroundColor: '#7f1d1d' },
  p95Text: { color: '#a78bfa', fontSize: 13, fontWeight: '800' },
  p95TextSlow: { color: '#fecaca' },
  p95Cap:  { color: '#64748b', fontSize: 8, marginTop: -2 },

  tickRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 4, paddingVertical: 4, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#262626' },
  tickName:{ flex: 1, color: '#cbd5e1', fontSize: 11, fontFamily: 'monospace' },
  tickMs:  { color: '#10b981', fontSize: 11, fontWeight: '700', minWidth: 50, textAlign: 'right' },
  tickMsSlow: { color: '#f87171' },
  tickT:   { color: '#475569', fontSize: 10, minWidth: 76, textAlign: 'right' },

  dim:     { color: '#64748b', fontSize: 12, fontStyle: 'italic', paddingTop: 20, textAlign: 'center' },
});
