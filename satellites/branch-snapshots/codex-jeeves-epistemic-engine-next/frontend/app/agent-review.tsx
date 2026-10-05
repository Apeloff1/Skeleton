/**
 * /agent-review — Specialist Agent Once-Over.
 *
 * Triggers a consecutive cadence review across ALL specialised platform agents
 * (POST /api/galaxy-studio/agents/once-over) and shows a consolidated report.
 * Bottom-anchored search filters the agent results (search-at-bottom UX).
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, TextInput, ActivityIndicator,
  StyleSheet, SafeAreaView, Platform, KeyboardAvoidingView,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import api from '../src/utils/apiClient';
import { useHaptics } from '../src/hooks/useHaptics';

interface AgentResult {
  agent: string; path: string; ok: boolean; status: number;
  latency_ms: number | null; attempts: number; finding: string;
}
interface Report {
  ok: boolean; ran_at: number; duration_ms: number; total_agents: number;
  healthy: number; degraded: number; health_pct: number;
  avg_latency_ms: number | null; results: AgentResult[]; blockers: string[];
}
interface HistoryPoint {
  ran_at: number; health_pct: number; healthy: number;
  total_agents: number; avg_latency_ms: number | null;
}

export default function AgentReviewScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ focus?: string }>();
  const haptics = useHaptics();
  const [report, setReport] = React.useState<Report | null>(null);
  const [history, setHistory] = React.useState<HistoryPoint[]>([]);
  const [running, setRunning] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [query, setQuery] = React.useState('');
  const [degradedOnly, setDegradedOnly] = React.useState(params.focus === 'degraded');

  const loadHistory = React.useCallback(async () => {
    const r = await api.get<{ ok: boolean; count: number; history: HistoryPoint[] }>(
      '/api/galaxy-studio/agents/once-over/history?limit=30',
    );
    if (r.ok && r.data?.history) setHistory(r.data.history);
  }, []);

  const loadLast = React.useCallback(async () => {
    const r = await api.get<{ ok: boolean; ran: boolean; report: Report | null }>(
      '/api/galaxy-studio/agents/once-over/last',
    );
    if (r.ok && r.data?.report) setReport(r.data.report);
  }, []);

  React.useEffect(() => { loadLast(); loadHistory(); }, [loadLast, loadHistory]);

  // Arriving from the home degradation chip: auto-run a fresh once-over so the
  // user immediately sees which agents are degraded (no manual tap needed).
  React.useEffect(() => {
    if (params.focus === 'degraded') runOnceOver();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.focus]);

  const runOnceOver = React.useCallback(async () => {
    haptics.impact('medium');
    setRunning(true);
    setError(null);
    const r = await api.post<Report>('/api/galaxy-studio/agents/once-over', {});
    if (r.ok && r.data?.ok) {
      setReport(r.data);
      haptics.notify('success');
      loadHistory();
    } else {
      setError(r.error || `HTTP ${r.status}`);
      haptics.notify('error');
    }
    setRunning(false);
  }, [haptics, loadHistory]);

  const filtered = React.useMemo(() => {
    if (!report) return [] as AgentResult[];
    let rows = report.results;
    if (degradedOnly) rows = rows.filter((a) => !a.ok);
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (a) => a.agent.includes(q) || a.path.includes(q) || a.finding.toLowerCase().includes(q),
    );
  }, [report, query, degradedOnly]);

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={styles.header} testID="agent-review-header">
          <TouchableOpacity testID="agent-review-back" onPress={() => router.back()} style={styles.backBtn}>
            <Text style={styles.backTxt}>← Back</Text>
          </TouchableOpacity>
          <Text style={styles.title}>Agent Once-Over</Text>
          <View style={{ width: 56 }} />
        </View>

        {report ? (
          <View style={styles.statsRow}>
            <Stat testID="stat-agents" label="Agents" value={String(report.total_agents)} color="#3B82F6" />
            <Stat testID="stat-healthy" label="Healthy" value={String(report.healthy)} color="#10B981" />
            <Stat testID="stat-health" label="Health" value={`${report.health_pct}%`} color={report.health_pct >= 90 ? '#10B981' : '#f59e0b'} />
            <Stat testID="stat-avg-ms" label="Avg ms" value={report.avg_latency_ms != null ? String(report.avg_latency_ms) : '—'} color="#8B5CF6" />
          </View>
        ) : null}

        {history.length >= 2 ? (
          <HealthSparkline points={history} />
        ) : null}

        {report ? (
          <View style={styles.filterRow}>
            <TouchableOpacity
              testID="filter-degraded"
              style={[styles.filterChip, degradedOnly && styles.filterChipActive]}
              onPress={() => { haptics.selection(); setDegradedOnly((v) => !v); }}
            >
              <Text style={[styles.filterChipTxt, degradedOnly && styles.filterChipTxtActive]}>
                {degradedOnly ? '✓ ' : ''}Degraded only{report.degraded ? ` (${report.degraded})` : ''}
              </Text>
            </TouchableOpacity>
            {degradedOnly && report.degraded === 0 ? (
              <Text style={styles.filterHint}>All agents healthy 🎉</Text>
            ) : null}
          </View>
        ) : null}

        <ScrollView style={styles.scroll} contentContainerStyle={{ paddingBottom: 24 }}>
          {!report && !running ? (
            <View style={styles.center}>
              <Text style={styles.hint}>Run a consecutive once-over across all specialist agents in cadence.</Text>
            </View>
          ) : null}

          {running ? (
            <View style={styles.center}>
              <ActivityIndicator color="#8B5CF6" size="large" />
              <Text style={styles.hint}>Probing agents in cadence…</Text>
            </View>
          ) : null}

          {error ? (
            <View style={styles.center}>
              <Text style={styles.errTitle}>Once-over failed</Text>
              <Text style={styles.errSub}>{error}</Text>
            </View>
          ) : null}

          {report && report.blockers.length > 0 ? (
            <View style={styles.blockerBar}>
              <Text style={styles.blockerTxt}>⚠ {report.blockers.length} degraded: {report.blockers.join(', ')}</Text>
            </View>
          ) : null}

          {filtered.map((a) => (
            <View testID={`agent-row-${a.agent}`} key={a.agent} style={[styles.row, { borderLeftColor: a.ok ? '#10B981' : '#ef4444' }]}>
              <View style={{ flex: 1 }}>
                <Text style={styles.agentName}>{a.agent}</Text>
                <Text style={styles.agentPath}>{a.path}</Text>
              </View>
              <View style={styles.rowRight}>
                <Text style={[styles.statusPill, { color: a.ok ? '#10B981' : '#ef4444' }]}>
                  {a.ok ? `${a.status} ok` : a.finding}
                </Text>
                <Text style={styles.latency}>{a.latency_ms != null ? `${a.latency_ms}ms` : '—'} · {a.attempts}x</Text>
              </View>
            </View>
          ))}
        </ScrollView>

        {/* ── Bottom action + search (search-at-bottom UX) ── */}
        <View style={styles.bottomBar}>
          <TextInput
            testID="agent-search"
            style={styles.search}
            value={query}
            onChangeText={setQuery}
            placeholder="Search agents…"
            placeholderTextColor="#64748b"
            autoCapitalize="none"
            autoCorrect={false}
          />
          <TouchableOpacity testID="run-once-over-btn" style={[styles.runBtn, running && { opacity: 0.6 }]} onPress={runOnceOver} disabled={running}>
            <Text style={styles.runTxt}>{running ? 'Running…' : 'Run Once-Over'}</Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function HealthSparkline({ points }: { points: HistoryPoint[] }) {
  const data = points.slice(-30);
  const last = data[data.length - 1];
  const min = Math.min(...data.map((p) => p.health_pct));
  const max = Math.max(...data.map((p) => p.health_pct));
  const trend = data.length >= 2 ? data[data.length - 1].health_pct - data[0].health_pct : 0;
  const barColor = (pct: number) => (pct >= 90 ? '#10B981' : pct >= 70 ? '#f59e0b' : '#ef4444');
  return (
    <View style={styles.sparkCard} testID="health-sparkline">
      <View style={styles.sparkHeader}>
        <Text style={styles.sparkTitle}>Health trend · last {data.length} runs</Text>
        <Text style={[styles.sparkTrend, { color: trend >= 0 ? '#10B981' : '#ef4444' }]}>
          {trend >= 0 ? '▲' : '▼'} {Math.abs(trend).toFixed(0)}%
        </Text>
      </View>
      <View style={styles.sparkBars}>
        {data.map((p, i) => {
          // Scale bar height within the observed range; floor at 8% for visibility.
          const span = max - min || 1;
          const h = 8 + ((p.health_pct - min) / span) * 92;
          return (
            <View
              key={`${p.ran_at}-${i}`}
              style={[styles.sparkBar, { height: `${h}%`, backgroundColor: barColor(p.health_pct) }]}
            />
          );
        })}
      </View>
      <View style={styles.sparkFooter}>
        <Text style={styles.sparkMeta}>min {min.toFixed(0)}%</Text>
        <Text style={styles.sparkMeta}>now {last.health_pct.toFixed(0)}%</Text>
        <Text style={styles.sparkMeta}>max {max.toFixed(0)}%</Text>
      </View>
    </View>
  );
}

function Stat({ label, value, color, testID }: { label: string; value: string; color: string; testID?: string }) {
  return (
    <View style={styles.stat} testID={testID}>
      <Text style={[styles.statValue, { color }]}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#0A0A0A' },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingTop: Platform.OS === 'ios' ? 8 : 16, paddingBottom: 12,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#1F1F1F',
  },
  backBtn: { paddingVertical: 6, paddingHorizontal: 10, width: 56 },
  backTxt: { color: '#93c5fd', fontSize: 15 },
  title: { color: '#fff', fontSize: 18, fontWeight: '700' },
  statsRow: { flexDirection: 'row', paddingHorizontal: 12, paddingVertical: 12, gap: 8 },
  stat: { flex: 1, backgroundColor: '#0A0A0A', borderRadius: 12, paddingVertical: 12, alignItems: 'center' },
  statValue: { fontSize: 18, fontWeight: '800' },
  statLabel: { color: '#64748b', fontSize: 11, marginTop: 2 },
  sparkCard: {
    marginHorizontal: 12, marginBottom: 4, backgroundColor: '#0A0A0A',
    borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12,
  },
  sparkHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  sparkTitle: { color: '#94a3b8', fontSize: 12, fontWeight: '600' },
  sparkTrend: { fontSize: 12, fontWeight: '800' },
  sparkBars: { flexDirection: 'row', alignItems: 'flex-end', height: 48, gap: 2 },
  sparkBar: { flex: 1, minWidth: 3, borderRadius: 2 },
  sparkFooter: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 8 },
  sparkMeta: { color: '#64748b', fontSize: 10, fontWeight: '600' },
  filterRow: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingTop: 4, paddingBottom: 8, gap: 10 },
  filterChip: {
    paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20,
    backgroundColor: '#0A0A0A', borderWidth: 1, borderColor: '#1F1F1F',
  },
  filterChipActive: { backgroundColor: '#ef444422', borderColor: '#ef4444' },
  filterChipTxt: { color: '#94a3b8', fontSize: 12, fontWeight: '700' },
  filterChipTxtActive: { color: '#fca5a5' },
  filterHint: { color: '#10B981', fontSize: 12, fontWeight: '600' },
  scroll: { flex: 1 },
  center: { padding: 40, alignItems: 'center', gap: 12 },
  hint: { color: '#94a3b8', fontSize: 13, textAlign: 'center' },
  errTitle: { color: '#e2e8f0', fontSize: 15, fontWeight: '600' },
  errSub: { color: '#64748b', fontSize: 12 },
  blockerBar: { marginHorizontal: 12, marginBottom: 8, backgroundColor: '#3f1d1d', borderRadius: 8, padding: 10 },
  blockerTxt: { color: '#fca5a5', fontSize: 12 },
  row: {
    flexDirection: 'row', alignItems: 'center', marginHorizontal: 12, marginBottom: 8,
    backgroundColor: '#0A0A0A', borderRadius: 10, padding: 12, borderLeftWidth: 3,
  },
  agentName: { color: '#fff', fontSize: 14, fontWeight: '600' },
  agentPath: { color: '#64748b', fontSize: 11, marginTop: 2 },
  rowRight: { alignItems: 'flex-end' },
  statusPill: { fontSize: 12, fontWeight: '700' },
  latency: { color: '#64748b', fontSize: 11, marginTop: 2 },
  bottomBar: {
    flexDirection: 'row', gap: 8, padding: 12,
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#1F1F1F', backgroundColor: '#0A0A0A',
  },
  search: {
    flex: 1, backgroundColor: '#262626', color: '#fff', borderRadius: 8,
    paddingHorizontal: 12, paddingVertical: Platform.OS === 'ios' ? 10 : 6, fontSize: 13,
  },
  runBtn: { backgroundColor: '#8B5CF6', paddingHorizontal: 16, justifyContent: 'center', borderRadius: 8 },
  runTxt: { color: '#fff', fontWeight: '700', fontSize: 13 },
});
