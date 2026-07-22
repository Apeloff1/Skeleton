/**
 * /groupchat — 🤖 Multi-Agent GroupChat: auto-build the whole pipeline with agent hand-offs.
 * Tap Run → the Orchestrator hands each stage to its agent (which recalls canon via RAG, then
 * forges its artifact). A live transcript renders the conversation + progress.
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator, StyleSheet, SafeAreaView,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import api from '../src/utils/apiClient';

const COLOR: Record<string, string> = {
  Orchestrator: '#a5b4fc', WorldForgeAgent: '#34d399', NarrativeQuestAgent: '#f472b6',
  MechanicsSystemsAgent: '#fbbf24', ProceduralAgent: '#3B82F6', AssetPipelineAgent: '#c084fc',
  QAAgent: '#f87171', BuildAgent: '#60a5fa', QuestionnaireAgent: '#93C5FD', OrchestratorAgent: '#a5b4fc',
};

export default function GroupChat() {
  const router = useRouter();
  const params = useLocalSearchParams<{ game?: string }>();
  const gameId = params?.game ? String(params.game) : '';
  const [job, setJob] = React.useState<any>(null);
  const [running, setRunning] = React.useState(false);
  const scrollRef = React.useRef<ScrollView>(null);

  const run = React.useCallback(async (onlyMissing: boolean, onlyStale = false) => {
    if (running) return;
    setRunning(true); setJob({ transcript: [], done: 0, total: 9, job_status: 'running' });
    const r = await api.post<any>(`/api/groupchat/${gameId}/run/async?only_missing=${onlyMissing}&only_stale=${onlyStale}`, {}, { timeoutMs: 15000 });
    if (!r.ok || !r.data?.job_id) { setRunning(false); return; }
    const jid = r.data.job_id;
    for (let i = 0; i < 160; i++) {
      await new Promise(res => setTimeout(res, 3000));
      const jr = await api.get<any>(`/api/groupchat/job/${jid}`, { timeoutMs: 12000 });
      if (jr.ok && jr.data && !jr.data.error) {
        setJob(jr.data);
        setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 50);
        if (jr.data.job_status === 'done') break;
      }
    }
    setRunning(false);
  }, [running, gameId]);

  // Auto-resolve: when arriving from the audit panel (?stale=1), auto-run only the stale stages
  React.useEffect(() => {
    if (params?.stale === '1' && gameId) run(false, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gameId]);

  const transcript = job?.transcript || [];
  const pct = job ? Math.round((job.done / (job.total || 9)) * 100) : 0;

  return (
    <SafeAreaView style={s.root}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.back}><Text style={s.backTxt}>‹ Back</Text></TouchableOpacity>
        <Text style={s.title}>🤖 Agent GroupChat</Text>
      </View>

      <View style={s.bar}>
        <View style={s.barTrack}><View style={[s.barFill, { width: `${pct}%` }]} /></View>
        <Text style={s.barTxt}>{job ? `${job.done}/${job.total || 9} stages · ${pct}%` : 'Ready — agents will build your game end to end'}{job?.current ? ` · now: ${job.current}` : ''}</Text>
        <View style={s.btnRow}>
          <TouchableOpacity testID="gc-run-missing" onPress={() => run(true)} disabled={running}
            style={[s.runBtn, running && s.off]} activeOpacity={0.9}>
            {running ? <ActivityIndicator size="small" color="#fff" /> : <Text style={s.runTxt}>▶ Build missing stages</Text>}
          </TouchableOpacity>
          <TouchableOpacity testID="gc-run-all" onPress={() => run(false)} disabled={running}
            style={[s.runBtn, s.runBtnAll, running && s.off]} activeOpacity={0.9}>
            <Text style={s.runTxt}>↻ Rebuild all</Text>
          </TouchableOpacity>
        </View>
      </View>

      <ScrollView ref={scrollRef} contentContainerStyle={{ padding: 14, paddingBottom: 50 }}>
        {transcript.length === 0 && !running && (
          <Text style={s.empty}>The Orchestrator will hand each stage to its specialist agent. Each agent recalls existing canon (RAG) before generating, so everything stays consistent.</Text>
        )}
        {transcript.map((m: any, i: number) => {
          const isOrch = m.agent === 'Orchestrator';
          const c = COLOR[m.agent] || '#94a3b8';
          return (
            <View key={i} testID={`gc-msg-${i}`} style={[s.msg, isOrch ? s.msgLeft : s.msgRight, m.kind === 'skip' && s.msgSkip]}>
              <Text style={[s.msgAgent, { color: c }]}>{m.agent}{m.kind === 'recall' ? ' · 🧠 RAG' : m.kind === 'handoff' ? ' · 🤝' : ''}</Text>
              <Text style={s.msgText}>{m.text}</Text>
            </View>
          );
        })}
        {running && <ActivityIndicator size="small" color="#93C5FD" style={{ marginTop: 12 }} />}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#05070d' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#141c2e', gap: 8 },
  back: { paddingVertical: 6, paddingHorizontal: 8 },
  backTxt: { color: '#60a5fa', fontSize: 15, fontWeight: '700' },
  title: { color: '#F8FAFC', fontSize: 18, fontWeight: '800' },
  bar: { padding: 14, borderBottomWidth: 1, borderBottomColor: '#141c2e' },
  barTrack: { height: 8, backgroundColor: '#1e293b', borderRadius: 4, overflow: 'hidden' },
  barFill: { height: 8, backgroundColor: '#818cf8', borderRadius: 4 },
  barTxt: { color: '#94A3B8', fontSize: 12, marginTop: 8 },
  btnRow: { flexDirection: 'row', gap: 8, marginTop: 10 },
  runBtn: { flex: 1, backgroundColor: '#6366f1', borderRadius: 10, paddingVertical: 12, alignItems: 'center', justifyContent: 'center', minHeight: 46 },
  runBtnAll: { backgroundColor: 'transparent', borderWidth: 1, borderColor: '#4338ca' },
  runTxt: { color: '#fff', fontSize: 13, fontWeight: '800' },
  off: { opacity: 0.5 },
  empty: { color: '#94A3B8', fontSize: 13, lineHeight: 20, padding: 16, textAlign: 'center' },
  msg: { borderRadius: 12, padding: 12, marginBottom: 8, maxWidth: '90%', borderWidth: 1, borderColor: '#1e293b', backgroundColor: '#0b1220' },
  msgLeft: { alignSelf: 'flex-start', backgroundColor: '#141a36' },
  msgRight: { alignSelf: 'flex-end', backgroundColor: '#0b1220' },
  msgSkip: { opacity: 0.6 },
  msgAgent: { fontSize: 11, fontWeight: '900', marginBottom: 3 },
  msgText: { color: '#E2E8F0', fontSize: 13, lineHeight: 18 },
});
