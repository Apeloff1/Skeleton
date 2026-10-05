import React, { useState, useCallback, useEffect, useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator, TextInput, Switch, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { apiFetch } from '../../utils/apiController';

const API = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const GATES = `${API}/api/galaxy-studio/gates`;
const SYS = `${API}/api/galaxy-studio/systems`;
const C = {
  bg: '#0b0f1a', card: '#141b2e', alt: '#1b2438', border: '#2a3550',
  text: '#eef2fb', muted: '#8a96b2', accent: '#a78bfa', good: '#43d39e', warn: '#f4a261', gold: '#f4c95d',
};
const tap = () => { if (Platform.OS !== 'web') Haptics.selectionAsync().catch(() => {}); };

export default function GateStage({ stage: stageProp }: { stage?: string }) {
  const router = useRouter();
  const params = useLocalSearchParams<{ build?: string; stage?: string }>();
  const stage = (stageProp || (params.stage as string) || 'refine');
  const [def, setDef] = useState<any>(null);
  const [buildId, setBuildId] = useState<string>((params.build as string) || '');
  const [mounted, setMounted] = useState<any[]>([]);
  const [target, setTarget] = useState<string>('');
  const [kind, setKind] = useState<'system' | 'construct'>('system');
  const [constructId, setConstructId] = useState<string>('');
  const [ai, setAi] = useState(false);
  const [running, setRunning] = useState(false);
  const [report, setReport] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const meta = useMemo(() => (def?.stages || []).find((s: any) => s.key === stage), [def, stage]);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await apiFetch(`${GATES}/stages`, { timeoutMs: 12000 });
        if (alive) setDef(await r.json());
      } catch { /* ignore */ } finally { if (alive) setLoading(false); }
    })();
    return () => { alive = false; };
  }, []);

  const loadMounted = useCallback(async (bid: string) => {
    if (!bid.trim()) { setMounted([]); return; }
    try {
      const r = await apiFetch(`${SYS}/build/${encodeURIComponent(bid.trim())}`, { timeoutMs: 10000 });
      const d = await r.json();
      setMounted(d.systems || []);
      if ((d.systems || []).length && !target) setTarget(d.systems[0].system);
    } catch { /* ignore */ }
  }, [target]);
  useEffect(() => { loadMounted(buildId); }, [buildId]); // eslint-disable-line react-hooks/exhaustive-deps

  const run = useCallback(async () => {
    const tgt = kind === 'construct' ? constructId.trim() : target;
    if (!buildId.trim() || !tgt) { setReport({ error: kind === 'construct' ? 'Enter a build & a construct id' : 'Pick a build & a mounted system first' }); return; }
    tap();
    setRunning(true); setReport(null);
    try {
      const r = await apiFetch(`${GATES}/${stage}/run`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ build_id: buildId.trim(), kind, key: tgt, seed: 1, ai }),
        timeoutMs: ai ? 60000 : 18000,
      });
      const d = await r.json();
      setReport(d);
      if (Platform.OS !== 'web') Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    } catch { setReport({ error: 'Gate run failed' }); } finally { setRunning(false); }
  }, [buildId, target, constructId, kind, stage, ai]);

  if (loading || !meta) {
    return <SafeAreaView style={styles.safe} edges={['top']}><View style={styles.center}><ActivityIndicator color={C.accent} /></View></SafeAreaView>;
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.iconBtn} testID="gate-back">
          <Ionicons name="chevron-back" size={22} color={C.text} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>{meta.icon} {meta.label}</Text>
          <Text style={styles.sub}>{meta.blurb} · {meta.panel ? `${(def.panel || []).length} reviewers` : `${(meta.segments || []).length} segments`} · Query→Acquire→Refine</Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={{ padding: 14, paddingBottom: 70 }} keyboardShouldPersistTaps="handled">
        {/* gate switcher — jump to any gate */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6, paddingBottom: 10 }}>
          {(def.stages || []).map((st: any) => {
            const on = st.key === stage;
            return (
              <TouchableOpacity key={st.key} onPress={() => router.push(`/gate/${st.key}?build=${encodeURIComponent(buildId)}`)}
                style={[styles.switchChip, on && { borderColor: C.accent, backgroundColor: C.accent + '22' }]} testID={`gate-switch-${st.key}`}>
                <Text style={[styles.switchTxt, on && { color: C.accent }]}>{st.icon} {st.label}</Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>

        {/* gate chain explainer */}
        <View style={styles.chainRow}>
          <Text style={styles.chainQg}>AAA Quality Gate</Text>
          <Text style={styles.chainArrow}>→</Text>
          {(def.gates || []).map((g: any, i: number) => (
            <React.Fragment key={g.key}>
              <View style={styles.chainGate}><Text style={styles.chainGateTxt}>{g.icon} {g.label}</Text></View>
              {i < def.gates.length - 1 && <Text style={styles.chainArrow}>→</Text>}
            </React.Fragment>
          ))}
        </View>

        {/* segments preview (or panel preview) */}
        {meta.panel ? (
          <>
            <Text style={styles.sectionLabel}>👥 Review Board — group-chat consensus</Text>
            <View style={styles.segGrid}>
              {(def.panel || []).map((m: any, i: number) => (
                <View key={m.role} style={styles.segChip}>
                  <Text style={styles.segNum}>{i + 1}</Text>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.segName}>{m.role}</Text>
                    <Text style={styles.segBlurb} numberOfLines={1}>{m.lens}</Text>
                  </View>
                </View>
              ))}
            </View>
          </>
        ) : (
          <>
            <Text style={styles.sectionLabel}>
              {meta.segments.length} Segments{meta.passes > 1 ? ` · ${meta.passes} parsed passes` : ''}
              {meta.intensity ? ` · ${meta.intensity}` : ''}{meta.samples ? ` · ${meta.samples}× samples` : ''}
            </Text>
            <View style={styles.segGrid}>
              {meta.segments.map((s: any, i: number) => (
                <View key={s.key} style={styles.segChip} testID={`gate-segment-${s.key}`}>
                  <Text style={styles.segNum}>{i + 1}</Text>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.segName}>{s.label}</Text>
                    <Text style={styles.segBlurb} numberOfLines={1}>{s.blurb}</Text>
                  </View>
                </View>
              ))}
            </View>
          </>
        )}

        {/* run controls */}
        <View style={styles.runCard}>
          <TextInput value={buildId} onChangeText={setBuildId} placeholder="Build ID"
            placeholderTextColor={C.muted} style={styles.input} testID="gate-build-input" />
          {/* System / Construct gate target toggle */}
          <Text style={styles.pickLabel}>Gate target</Text>
          <View style={styles.kindRow}>
            {(['system', 'construct'] as const).map((kk) => {
              const on = kind === kk;
              return (
                <TouchableOpacity key={kk} onPress={() => { tap(); setKind(kk); }}
                  style={[styles.kindChip, on && { borderColor: C.accent, backgroundColor: C.accent + '22' }]}
                  testID={`gate-kind-${kk}`}>
                  <Text style={[styles.kindTxt, on && { color: C.accent }]}>{kk === 'system' ? '🧩 System' : '🧱 3D Construct'}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
          {kind === 'construct' ? (
            <>
              <Text style={styles.pickLabel}>Construct id / preset id</Text>
              <TextInput value={constructId} onChangeText={setConstructId} placeholder="e.g. construct_abc123"
                placeholderTextColor={C.muted} style={styles.input} testID="gate-construct-input" />
              <Text style={styles.hint}>Routes a 3D construct through this gate (Refine/Polish/QC … all 14).</Text>
            </>
          ) : mounted.length > 0 ? (
            <>
              <Text style={styles.pickLabel}>Target system</Text>
              <View style={styles.chipWrap}>
                {mounted.map((m) => {
                  const sel = target === m.system;
                  return (
                    <TouchableOpacity key={m.system} onPress={() => { tap(); setTarget(m.system); }}
                      style={[styles.tChip, sel && { borderColor: C.accent, backgroundColor: C.accent + '22' }]}
                      testID={`gate-target-${m.system}`}>
                      <Text style={[styles.tTxt, sel && { color: C.accent }]}>{m.label}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </>
          ) : (
            <Text style={styles.hint}>No systems mounted on this build yet — forge some in the Systems Forge first.</Text>
          )}
          <View style={styles.aiRow}>
            <Text style={styles.aiTitle}>✨ AI expert review</Text>
            <Switch value={ai} onValueChange={setAi} trackColor={{ false: C.border, true: C.accent }} thumbColor="#fff" testID="gate-ai-toggle" />
          </View>
          <TouchableOpacity onPress={run} disabled={running} style={[styles.runBtn, running && { opacity: 0.6 }]} testID="gate-run">
            {running ? <ActivityIndicator color="#1a1030" /> : <Text style={styles.runTxt}>{meta.icon} Run {meta.label}</Text>}
          </TouchableOpacity>
          {report?.error && <Text style={styles.err} testID="gate-error">{report.error}</Text>}
        </View>

        {/* report */}
        {report && !report.error && (
          <View style={styles.report} testID="gate-report">
            <View style={styles.scoreHead}>
              <Text style={[styles.scoreBig, { color: report.passed ? C.good : C.warn }]}>{report.final_score}</Text>
              <View style={{ flex: 1 }}>
                <Text style={styles.scoreLabel}>{report.passed ? '✓ PASSED' : '⚠ NEEDS WORK'} · {report.total_issues_fixed} issues fixed</Text>
                <Text style={styles.scoreSub}>Quality gate {report.quality_gate.score} → final {report.final_score}{report.ai_reviewed ? ' · ✨ AI reviewed' : ''}</Text>
              </View>
            </View>

            {!!(report.pass_scores || []).length && report.pass_scores.length > 1 && (
              <View style={styles.passRow}>
                {report.pass_scores.map((ps: number, i: number) => (
                  <View key={i} style={styles.passChip}><Text style={styles.passTxt}>pass {i + 1}: {ps}</Text></View>
                ))}
              </View>
            )}

            {report.panel && (
              <View style={styles.panelBox} testID="gate-panel">
                <Text style={styles.panelTitle}>{report.panel.mode === 'llm_group_chat' ? '🤝 LLM group chat' : '🤝 Review board'} · consensus {report.panel.consensus_score} · {Math.round(report.panel.agreement * 100)}% agreement</Text>
                {(report.panel.votes || []).map((v: any, i: number) => (
                  <View key={i} style={styles.voteRow}>
                    <Text style={styles.voteRole} numberOfLines={1}>{v.verdict === 'approve' ? '✅' : '🔁'} {v.role}</Text>
                    <Text style={styles.voteScore}>{v.score}</Text>
                  </View>
                ))}
              </View>
            )}

            {(report.segments || []).map((seg: any, i: number) => (
              <View key={seg.segment} style={styles.segReport}>
                <View style={styles.segReportHead}>
                  <Text style={styles.segReportName}>{i + 1}. {seg.label}</Text>
                  <Text style={styles.segReportScore}>{seg.inbound_score} → {seg.outbound_score}</Text>
                </View>
                <View style={styles.gateChain}>
                  {seg.gates.map((g: any) => (
                    <View key={g.gate} style={styles.gateBox}>
                      <Text style={styles.gateName}>{g.gate}</Text>
                      <Text style={styles.gateDetail}>
                        {g.gate === 'query' ? `${g.found_issues} found`
                          : g.gate === 'acquire' ? `${g.samples_gathered} samples · ${g.confidence}`
                          : `+${g.score_delta} · ${g.issues_fixed} fixed`}
                      </Text>
                    </View>
                  ))}
                </View>
              </View>
            ))}

            {!!(report.ai_notes || []).length && (
              <View style={styles.aiNotes}>
                <Text style={styles.aiNotesTitle}>✨ AI review notes</Text>
                {report.ai_notes.map((n: string, i: number) => <Text key={i} style={styles.aiNoteLine}>• {n}</Text>)}
              </View>
            )}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 12, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.border },
  iconBtn: { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center', backgroundColor: C.card },
  title: { color: C.text, fontSize: 18, fontWeight: '900' },
  sub: { color: C.muted, fontSize: 11, fontWeight: '600' },
  chainRow: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 4, marginBottom: 14, backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, padding: 10 },
  switchChip: { backgroundColor: C.alt, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: C.border },
  switchTxt: { color: '#aab4cc', fontSize: 11, fontWeight: '800' },
  chainQg: { color: C.gold, fontSize: 10, fontWeight: '900', backgroundColor: C.gold + '22', paddingHorizontal: 7, paddingVertical: 4, borderRadius: 7 },
  chainArrow: { color: C.muted, fontSize: 12, fontWeight: '900' },
  chainGate: { backgroundColor: C.accent + '22', paddingHorizontal: 8, paddingVertical: 4, borderRadius: 7, borderWidth: 1, borderColor: C.accent + '44' },
  chainGateTxt: { color: C.accent, fontSize: 10, fontWeight: '800' },
  sectionLabel: { color: C.muted, fontSize: 12, fontWeight: '800', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.4 },
  segGrid: { gap: 6, marginBottom: 14 },
  segChip: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 9 },
  segNum: { color: C.accent, fontSize: 13, fontWeight: '900', width: 18, textAlign: 'center' },
  segName: { color: C.text, fontSize: 13, fontWeight: '800' },
  segBlurb: { color: C.muted, fontSize: 11, fontWeight: '600' },
  runCard: { backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: '#6c8cff55', padding: 12, marginBottom: 14 },
  input: { backgroundColor: C.alt, borderRadius: 10, borderWidth: 1, borderColor: C.border, color: C.text, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14, marginBottom: 10 },
  pickLabel: { color: C.text, fontSize: 12, fontWeight: '800', marginBottom: 6 },
  hint: { color: C.muted, fontSize: 12, fontWeight: '600', marginBottom: 8 },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 6 },
  tChip: { backgroundColor: C.alt, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: C.border },
  tTxt: { color: '#aab4cc', fontSize: 11, fontWeight: '700' },
  kindRow: { flexDirection: 'row', gap: 8, marginBottom: 10 },
  kindChip: { flex: 1, backgroundColor: C.alt, borderRadius: 10, paddingVertical: 9, alignItems: 'center', borderWidth: 1, borderColor: C.border },
  kindTxt: { color: '#aab4cc', fontSize: 12, fontWeight: '800' },
  aiRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginVertical: 10 },
  aiTitle: { color: C.text, fontSize: 13, fontWeight: '800' },
  runBtn: { backgroundColor: C.accent, borderRadius: 10, paddingVertical: 12, alignItems: 'center' },
  runTxt: { color: '#1a1030', fontSize: 14, fontWeight: '900' },
  err: { color: '#ff8585', fontSize: 12, fontWeight: '700', marginTop: 10 },
  report: { backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.good + '44', padding: 12 },
  scoreHead: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 12 },
  scoreBig: { fontSize: 34, fontWeight: '900' },
  scoreLabel: { color: C.text, fontSize: 13, fontWeight: '900' },
  scoreSub: { color: C.muted, fontSize: 11, fontWeight: '600', marginTop: 2 },
  segReport: { backgroundColor: C.alt, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 9, marginBottom: 7 },
  segReportHead: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 },
  segReportName: { color: C.text, fontSize: 12, fontWeight: '800' },
  segReportScore: { color: C.accent, fontSize: 11, fontWeight: '800' },
  gateChain: { flexDirection: 'row', gap: 6 },
  gateBox: { flex: 1, backgroundColor: C.bg, borderRadius: 7, padding: 6, borderWidth: 1, borderColor: C.border },
  gateName: { color: C.accent, fontSize: 9, fontWeight: '900', textTransform: 'uppercase' },
  gateDetail: { color: C.muted, fontSize: 10, fontWeight: '600', marginTop: 2 },
  aiNotes: { marginTop: 6, backgroundColor: C.accent + '12', borderRadius: 10, padding: 10, borderWidth: 1, borderColor: C.accent + '33' },
  aiNotesTitle: { color: C.accent, fontSize: 12, fontWeight: '800', marginBottom: 6 },
  aiNoteLine: { color: C.text, fontSize: 12, lineHeight: 17, fontWeight: '500' },
  passRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 10 },
  passChip: { backgroundColor: C.accent + '18', borderRadius: 7, paddingHorizontal: 8, paddingVertical: 4, borderWidth: 1, borderColor: C.accent + '33' },
  passTxt: { color: C.accent, fontSize: 10, fontWeight: '800' },
  panelBox: { backgroundColor: C.alt, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 10, marginBottom: 10 },
  panelTitle: { color: C.accent, fontSize: 12, fontWeight: '800', marginBottom: 8 },
  voteRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 4 },
  voteRole: { color: C.text, fontSize: 12, fontWeight: '700', flex: 1 },
  voteScore: { color: C.gold, fontSize: 12, fontWeight: '900' },
});
