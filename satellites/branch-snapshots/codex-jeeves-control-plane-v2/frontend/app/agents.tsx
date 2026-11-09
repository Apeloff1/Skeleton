/**
 * /agents — Multi-Agent Systems
 * GET /api/agents/systems • POST /api/agents/run/{system_id}
 */
import { useState, useEffect, useCallback } from 'react';
import {
  View, Text, TextInput, ScrollView, TouchableOpacity, ActivityIndicator,
  StyleSheet, StatusBar, SafeAreaView, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useRouteHistory } from '../utils/routeHistory';
import { shareResult, copyToClipboard } from '../utils/shareResult';
import { jeevesSpeak } from '../features/Academy/jeevesTts';
import Skeleton from '../components/ui/Skeleton';
import RetryBanner from '../components/ui/RetryBanner';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

export default function AgentsScreen() {
  const router = useRouter();
  const [systems, setSystems] = useState<Record<string, any>>({});
  const [roles, setRoles] = useState<Record<string, any>>({});
  const [systemId, setSystemId] = useState<string>('');
  const [task, setTask] = useState('Build a function that returns the nth Fibonacci number, with tests');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [err, setErr] = useState('');
  const [bootLoading, setBootLoading] = useState(true);
  const [bootError, setBootError] = useState<string | null>(null);
  const history = useRouteHistory<{ systemId: string; task: string }>('agents');

  const loadCatalog = useCallback(() => {
    setBootLoading(true);
    setBootError(null);
    Promise.all([
      fetch(`${BACKEND}/api/agents/systems`).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }),
      fetch(`${BACKEND}/api/agents/roles`).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }),
    ]).then(([sys, rl]) => {
      const sysMap = sys?.systems || {};
      setSystems(sysMap);
      setRoles(rl?.roles || {});
      const first = Object.keys(sysMap)[0];
      if (first && !systemId) setSystemId(first);
    }).catch(e => {
      setBootError(String(e?.message || e).slice(0, 100));
    }).finally(() => setBootLoading(false));
  }, [systemId]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadCatalog();   }, []);

  const run = useCallback(async () => {
    if (!systemId) return;
    setBusy(true); setErr(''); setResult(null);
    try {
      const r = await fetch(`${BACKEND}/api/agents/run/${systemId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task, context: '' }),
      });
      const j = await r.json();
      setResult(j);
      if (j?.error) setErr(String(j.error).slice(0, 200));
      else {
        const stepCount = Array.isArray(j.steps) ? j.steps.length : 0;
        await history.push({
          label: `${systems[systemId]?.name || systemId} · ${stepCount} steps`,
          preview: task.slice(0, 60),
          payload: { systemId, task },
        });
        jeevesSpeak(
          `Swarm complete. ${stepCount} agent ${stepCount === 1 ? 'step' : 'steps'} executed.`,
          { context: 'celebration', prependCatchphrase: false },
        );
      }
    } catch (e: any) {
      setErr(String(e?.message || e).slice(0, 200));
    } finally { setBusy(false); }
  }, [systemId, task, systems, history]);

  // Pull the most code-like text from the agent steps for forwarding.
  const extractCode = (res: any): string => {
    if (!res) return '';
    if (Array.isArray(res.steps)) {
      for (const st of res.steps.slice().reverse()) {
        const t = String(st.output || st.result || st.message || '');
        if (t.includes('def ') || t.includes('function ') || t.includes('class ') || t.includes('```')) return t;
      }
    }
    return JSON.stringify(res, null, 2);
  };

  const current = systems[systemId];

  return (
    <SafeAreaView style={s.root}>
      <StatusBar barStyle="light-content" backgroundColor="#0A0A0A" />
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={s.header}>
          <TouchableOpacity onPress={() => router.back()} style={s.backBtn} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
            <Ionicons name="chevron-back" size={22} color="#A78BFA" />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={s.title}>👥 Multi-Agent</Text>
            <Text style={s.subtitle}>{Object.keys(systems).length} systems · {Object.keys(roles).length} roles · coordinated AI swarms</Text>
          </View>
        </View>

        <ScrollView contentContainerStyle={{ padding: 14, paddingBottom: 80 }}>
          {bootError && !bootLoading && (
            <RetryBanner
              error={`Couldn't load agent catalog: ${bootError}`}
              onRetry={loadCatalog}
              retryLabel="Retry"
            />
          )}
          <Text style={s.label}>Choose a system</Text>
          {bootLoading && Object.keys(systems).length === 0 ? (
            <View style={{ gap: 8 }}>
              {[0, 1, 2].map(i => (
                <View key={i} style={s.sysCard}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <Skeleton width={16} height={16} radius={8} />
                    <Skeleton width="40%" height={13} />
                  </View>
                  <View style={{ marginTop: 6, gap: 6 }}>
                    <Skeleton width="90%" height={11} />
                    <Skeleton width="65%" height={11} />
                  </View>
                </View>
              ))}
            </View>
          ) : (
          Object.entries(systems).map(([id, sys]: [string, any]) => {
            const active = id === systemId;
            return (
              <TouchableOpacity
                key={id}
                style={[s.sysCard, active && s.sysCardActive]}
                onPress={() => setSystemId(id)}
                activeOpacity={0.85}
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons name={active ? 'radio-button-on' : 'radio-button-off'} size={16} color={active ? '#A78BFA' : '#64748b'} />
                  <Text style={[s.sysName, active && { color: '#A78BFA' }]}>{sys?.name || id}</Text>
                  <Text style={s.sysFlow}>{sys?.flow}</Text>
                </View>
                <Text style={s.sysDesc} numberOfLines={2}>{sys?.description}</Text>
                <View style={s.agentRow}>
                  {(sys?.agents || []).map((a: string) => (
                    <View key={a} style={s.agentChip}>
                      <Text style={s.agentText}>{a}</Text>
                    </View>
                  ))}
                </View>
              </TouchableOpacity>
            );
          })
          )}

          <Text style={[s.label, { marginTop: 12 }]}>Task</Text>
          <TextInput
            value={task}
            onChangeText={setTask}
            multiline
            style={s.editor}
            placeholder="Describe the task for the agent swarm…"
            placeholderTextColor="#475569"
            textAlignVertical="top"
          />

          <TouchableOpacity
            onPress={run}
            disabled={busy || !task.trim() || !systemId}
            style={[s.runBtn, (busy || !task.trim() || !systemId) && { opacity: 0.4 }]}
          >
            {busy ? <ActivityIndicator color="#0A0A0A" /> : (
              <>
                <Ionicons name="git-network" size={16} color="#0A0A0A" />
                <Text style={s.runText}>Run {current?.name || 'system'}</Text>
              </>
            )}
          </TouchableOpacity>

          {err ? <View style={s.errBox}><Text style={s.errText}>⚠ {err}</Text></View> : null}
          {result && (
            <View style={s.resultBox}>
              <View style={s.resultHead}>
                <Ionicons name="sparkles" size={16} color="#A78BFA" />
                <Text style={s.resultHeadText}>{current?.name} · {result.status || 'complete'}</Text>
              </View>
              {Array.isArray(result.steps) && result.steps.map((st: any, i: number) => (
                <View key={i} style={s.step}>
                  <Text style={s.stepHead}>{i + 1}. {st.agent || st.role || `Step ${i+1}`}</Text>
                  <Text style={s.stepText}>{String(st.output || st.result || st.message || '').slice(0, 1200)}</Text>
                </View>
              ))}
              {!Array.isArray(result.steps) && (
                <Text style={s.stepText}>{JSON.stringify(result, null, 2).slice(0, 2500)}</Text>
              )}
              <View style={s.bridgeRow}>
                <TouchableOpacity
                  style={[s.bridgeBtn, { backgroundColor: '#F59E0B22', borderColor: '#F59E0B' }]}
                  onPress={() => router.push({ pathname: '/playground', params: { lang: 'python', code: extractCode(result) } } as any)}
                >
                  <Ionicons name="flask" size={13} color="#F59E0B" />
                  <Text style={[s.bridgeText, { color: '#F59E0B' }]}>Playground</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.bridgeBtn, { backgroundColor: '#EF444422', borderColor: '#EF4444' }]}
                  onPress={() => router.push({ pathname: '/debugger', params: { lang: 'python', code: extractCode(result) } } as any)}
                >
                  <Ionicons name="bug" size={13} color="#EF4444" />
                  <Text style={[s.bridgeText, { color: '#EF4444' }]}>Debug</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.bridgeBtn, { backgroundColor: '#10B98122', borderColor: '#10B981' }]}
                  onPress={() => copyToClipboard(JSON.stringify(result, null, 2), 'Result copied')}
                >
                  <Ionicons name="copy" size={13} color="#10B981" />
                  <Text style={[s.bridgeText, { color: '#10B981' }]}>Copy</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.bridgeBtn, { backgroundColor: '#A78BFA22', borderColor: '#A78BFA' }]}
                  onPress={() => shareResult(JSON.stringify(result, null, 2), 'Agent swarm result')}
                >
                  <Ionicons name="share-social" size={13} color="#A78BFA" />
                  <Text style={[s.bridgeText, { color: '#A78BFA' }]}>Share</Text>
                </TouchableOpacity>
              </View>
            </View>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0A0A0A' },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 14, paddingVertical: 10, borderBottomColor: '#1F1F1F', borderBottomWidth: 1 },
  backBtn: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  title: { color: '#f1f5f9', fontSize: 16, fontWeight: '900' },
  subtitle: { color: '#94a3b8', fontSize: 11, marginTop: 2 },
  label: { color: '#94a3b8', fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6 },
  sysCard: { padding: 12, borderRadius: 10, backgroundColor: '#141414', borderWidth: 1, borderColor: '#1F1F1F', marginBottom: 6 },
  sysCardActive: { borderColor: '#A78BFA', backgroundColor: '#A78BFA15' },
  sysName: { color: '#f1f5f9', fontSize: 13, fontWeight: '700', flex: 1 },
  sysFlow: { color: '#94a3b8', fontSize: 9, paddingHorizontal: 6, paddingVertical: 2, backgroundColor: '#1F1F1F', borderRadius: 6 },
  sysDesc: { color: '#94a3b8', fontSize: 11, marginTop: 4 },
  agentRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 6 },
  agentChip: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6, backgroundColor: '#A78BFA22', borderColor: '#A78BFA', borderWidth: 1 },
  agentText: { color: '#A78BFA', fontSize: 9, fontWeight: '700' },
  editor: { minHeight: 90, color: '#f1f5f9', fontSize: 13, lineHeight: 18, padding: 14, backgroundColor: '#141414', borderRadius: 10, borderWidth: 1, borderColor: '#1F1F1F' },
  runBtn: { marginTop: 14, paddingVertical: 12, borderRadius: 10, backgroundColor: '#A78BFA', alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8 },
  runText: { color: '#0A0A0A', fontSize: 14, fontWeight: '900' },
  errBox: { marginTop: 10, padding: 10, borderRadius: 8, backgroundColor: '#f8717122', borderColor: '#f87171', borderWidth: 1 },
  errText: { color: '#fecaca', fontSize: 11 },
  resultBox: { marginTop: 12, padding: 14, backgroundColor: '#141414', borderRadius: 12, borderWidth: 1, borderColor: '#A78BFA55' },
  resultHead: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 },
  resultHeadText: { color: '#A78BFA', fontSize: 11, fontWeight: '900', textTransform: 'uppercase', letterSpacing: 1 },
  step: { marginTop: 8, paddingTop: 8, borderTopColor: '#1F1F1F', borderTopWidth: 1 },
  stepHead: { color: '#A78BFA', fontSize: 11, fontWeight: '800', marginBottom: 4 },
  stepText: { color: '#cbd5e1', fontSize: 12, lineHeight: 17, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
  bridgeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 },
  bridgeBtn: { flex: 1, minWidth: 80, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 10, paddingHorizontal: 8, borderRadius: 8, borderWidth: 1 },
  bridgeText: { fontSize: 10, fontWeight: '800' },
});
