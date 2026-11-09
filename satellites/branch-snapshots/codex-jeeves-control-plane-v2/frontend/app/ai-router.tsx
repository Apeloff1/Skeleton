/**
 * /ai-router — Model Router & Ensemble dashboard (Backlog Phase I.1).
 *
 * Shows the live routing policy (task → model ensemble), the model catalog with
 * list prices, real-time telemetry (calls, cache hit-rate, est. spend, per-model
 * latency/cost), and a quick test-prompt box that exercises the router so you can
 * watch the normalized-semantic cache turn a repeat prompt into a 0ms hit.
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator, TextInput,
  StyleSheet, SafeAreaView, Platform, RefreshControl, KeyboardAvoidingView,
} from 'react-native';
import { useRouter } from 'expo-router';
import api from '../src/utils/apiClient';
import { useHaptics } from '../src/hooks/useHaptics';

interface Policy {
  policy: Record<string, string[]>;
  models: Record<string, { provider: string; cost_in: number; cost_out: number; tier: string }>;
  cache: { ttl_s: number; max: number; size: number };
  key_configured: boolean;
}
interface Stats {
  total_calls: number; cache_hits: number; cache_hit_rate: number; errors: number;
  est_total_cost_usd: number;
  by_model: { model: string; calls: number; cost_usd: number; avg_latency_ms: number }[];
  by_task: { task: string; calls: number; cost_usd: number }[];
}

const TASK_COLORS: Record<string, string> = {
  code: '#3B82F6', reasoning: '#8B5CF6', creative: '#f472b6',
  fast: '#10B981', classify: '#fbbf24', bulk: '#3B82F6', default: '#94a3b8',
};

export default function AiRouterScreen() {
  const router = useRouter();
  const haptics = useHaptics();
  const [policy, setPolicy] = React.useState<Policy | null>(null);
  const [stats, setStats] = React.useState<Stats | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [prompt, setPrompt] = React.useState('Reply with exactly one word: PONG');
  const [task, setTask] = React.useState('fast');
  const [testing, setTesting] = React.useState(false);
  const [result, setResult] = React.useState<{ model?: string; cached?: boolean; latency_ms?: number; content?: string; error?: string } | null>(null);

  const load = React.useCallback(async () => {
    const [p, s] = await Promise.all([
      api.get<Policy>('/api/llm-router/policy'),
      api.get<Stats>('/api/llm-router/stats'),
    ]);
    if (p.ok && p.data) setPolicy(p.data);
    if (s.ok && s.data) setStats(s.data);
    setLoading(false);
  }, []);

  React.useEffect(() => { load(); }, [load]);

  const runTest = React.useCallback(async () => {
    if (!prompt.trim() || testing) return;
    haptics.selection();
    setTesting(true);
    setResult(null);
    const r = await api.post<any>('/api/llm-router/complete', { task, prompt });
    setResult(r.ok && r.data ? r.data : { error: r.error || `HTTP ${r.status}` });
    setTesting(false);
    load();
  }, [prompt, task, testing, haptics, load]);

  const tasks = policy ? Object.keys(policy.policy) : [];

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <TouchableOpacity testID="router-back" onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backTxt}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Model Router</Text>
        <TouchableOpacity testID="router-refresh" onPress={() => { haptics.selection(); load(); }} style={styles.backBtn}>
          <Text style={[styles.backTxt, { textAlign: 'right' }]}>↻</Text>
        </TouchableOpacity>
      </View>

      {stats ? (
        <View style={styles.statsRow}>
          <Stat label="Calls" value={String(stats.total_calls)} color="#3B82F6" />
          <Stat label="Cache hit" value={`${stats.cache_hit_rate}%`} color="#10B981" />
          <Stat label="Est. spend" value={`$${stats.est_total_cost_usd.toFixed(3)}`} color="#fbbf24" />
        </View>
      ) : null}

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={{ paddingBottom: 40 }}
          keyboardShouldPersistTaps="handled"
          refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor="#8B5CF6" />}
        >
          {loading && !policy ? (
            <View style={styles.center}><ActivityIndicator color="#8B5CF6" size="large" /></View>
          ) : null}

          {policy && !policy.key_configured ? (
            <View style={styles.warnBox}>
              <Text style={styles.warnTxt}>⚠️ EMERGENT_LLM_KEY not configured — completions will return an error.</Text>
            </View>
          ) : null}

          {/* Test bench */}
          <Section title="Test bench">
            <View style={styles.taskChips}>
              {tasks.map((t) => (
                <TouchableOpacity
                  key={t}
                  testID={`task-${t}`}
                  onPress={() => { haptics.selection(); setTask(t); }}
                  style={[styles.taskChip, task === t && { backgroundColor: (TASK_COLORS[t] || '#404040') + '33', borderColor: TASK_COLORS[t] || '#475569' }]}
                >
                  <Text style={[styles.taskChipTxt, task === t && { color: TASK_COLORS[t] || '#fff' }]}>{t}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <TextInput
              testID="router-prompt"
              style={styles.input}
              value={prompt}
              onChangeText={setPrompt}
              placeholder="Enter a prompt to route…"
              placeholderTextColor="#475569"
              multiline
            />
            <TouchableOpacity testID="router-run" style={[styles.runBtn, testing && { opacity: 0.5 }]} onPress={runTest} disabled={testing}>
              {testing ? <ActivityIndicator color="#fff" /> : <Text style={styles.runTxt}>Route completion →</Text>}
            </TouchableOpacity>
            {result ? (
              <View style={styles.resultBox} testID="router-result">
                {result.error ? (
                  <Text style={styles.resultErr}>{result.error}</Text>
                ) : (
                  <>
                    <View style={styles.resultMeta}>
                      <Text style={styles.metaPill}>{result.model}</Text>
                      <Text style={[styles.metaPill, { color: result.cached ? '#10B981' : '#94a3b8' }]}>
                        {result.cached ? 'CACHE HIT' : 'live'}
                      </Text>
                      <Text style={styles.metaPill}>{result.latency_ms}ms</Text>
                    </View>
                    <Text style={styles.resultContent}>{result.content}</Text>
                  </>
                )}
              </View>
            ) : null}
          </Section>

          {/* Routing policy */}
          {policy ? (
            <Section title="Routing policy">
              {Object.entries(policy.policy).map(([t, models]) => (
                <View key={t} style={styles.polRow} testID={`policy-${t}`}>
                  <Text style={[styles.polTask, { color: TASK_COLORS[t] || '#cbd5e1' }]}>{t}</Text>
                  <Text style={styles.polModels}>{models.join('  →  ')}</Text>
                </View>
              ))}
            </Section>
          ) : null}

          {/* Per-model telemetry */}
          {stats && stats.by_model.length > 0 ? (
            <Section title="By model">
              {stats.by_model.map((m) => (
                <View key={m.model} style={styles.modelRow} testID={`model-${m.model}`}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.modelName}>{m.model}</Text>
                    <Text style={styles.modelSub}>{m.calls} calls · avg {m.avg_latency_ms}ms</Text>
                  </View>
                  <Text style={styles.modelCost}>${m.cost_usd.toFixed(4)}</Text>
                </View>
              ))}
            </Section>
          ) : null}

          {/* Model catalog */}
          {policy ? (
            <Section title="Model catalog ($/1K tok)">
              {Object.entries(policy.models).map(([name, m]) => (
                <View key={name} style={styles.catRow}>
                  <Text style={styles.catName}>{name}</Text>
                  <Text style={styles.catTier}>{m.tier}</Text>
                  <Text style={styles.catCost}>in ${m.cost_in} · out ${m.cost_out}</Text>
                </View>
              ))}
            </Section>
          ) : null}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}
function Stat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <View style={styles.stat}>
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
  backTxt: { color: '#93c5fd', fontSize: 16 },
  title: { color: '#fff', fontSize: 18, fontWeight: '700' },
  statsRow: { flexDirection: 'row', paddingHorizontal: 12, paddingVertical: 12, gap: 8 },
  stat: { flex: 1, backgroundColor: '#0A0A0A', borderRadius: 12, paddingVertical: 12, alignItems: 'center' },
  statValue: { fontSize: 20, fontWeight: '800' },
  statLabel: { color: '#64748b', fontSize: 11, marginTop: 2 },
  scroll: { flex: 1 },
  center: { padding: 40, alignItems: 'center' },
  warnBox: { margin: 12, backgroundColor: '#3f1d1d', borderRadius: 10, padding: 12 },
  warnTxt: { color: '#fca5a5', fontSize: 12 },
  section: { marginHorizontal: 12, marginTop: 14 },
  sectionTitle: { color: '#cbd5e1', fontSize: 13, fontWeight: '700', marginBottom: 8 },
  taskChips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 10 },
  taskChip: { borderWidth: 1, borderColor: '#404040', borderRadius: 18, paddingHorizontal: 12, paddingVertical: 6 },
  taskChipTxt: { color: '#94a3b8', fontSize: 12, fontWeight: '700' },
  input: {
    backgroundColor: '#0A0A0A', borderRadius: 10, color: '#e2e8f0', padding: 12,
    minHeight: 64, fontSize: 14, textAlignVertical: 'top', borderWidth: 1, borderColor: '#1F1F1F',
  },
  runBtn: { backgroundColor: '#8B5CF6', borderRadius: 10, paddingVertical: 12, alignItems: 'center', marginTop: 10 },
  runTxt: { color: '#fff', fontWeight: '700', fontSize: 14 },
  resultBox: { backgroundColor: '#0A0A0A', borderRadius: 10, padding: 12, marginTop: 10, borderWidth: 1, borderColor: '#1F1F1F' },
  resultMeta: { flexDirection: 'row', gap: 8, marginBottom: 8 },
  metaPill: { color: '#cbd5e1', fontSize: 11, fontWeight: '700', backgroundColor: '#262626', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10, overflow: 'hidden' },
  resultContent: { color: '#e2e8f0', fontSize: 14, lineHeight: 20 },
  resultErr: { color: '#fca5a5', fontSize: 13 },
  polRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#0A0A0A', borderRadius: 10, padding: 12, marginBottom: 8 },
  polTask: { fontSize: 13, fontWeight: '800', width: 92 },
  polModels: { color: '#94a3b8', fontSize: 12, flex: 1 },
  modelRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#0A0A0A', borderRadius: 10, padding: 12, marginBottom: 8 },
  modelName: { color: '#fff', fontSize: 14, fontWeight: '600' },
  modelSub: { color: '#64748b', fontSize: 11, marginTop: 2 },
  modelCost: { color: '#fbbf24', fontSize: 14, fontWeight: '800' },
  catRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 8, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#1F1F1F' },
  catName: { color: '#e2e8f0', fontSize: 13, fontWeight: '600', flex: 1 },
  catTier: { color: '#8B5CF6', fontSize: 11, width: 64 },
  catCost: { color: '#64748b', fontSize: 11 },
});
