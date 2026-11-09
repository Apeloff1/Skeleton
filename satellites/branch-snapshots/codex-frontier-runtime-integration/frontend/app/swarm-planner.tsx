// ─────────────────────────────────────────────────────────────────────────
//  Hierarchical Swarm Planner — visualises the director→leads→platoons→
//  workers task DAG with provable 100% coverage, dependency waves and a
//  deterministic plan hash.  (Backlog I.3)
// ─────────────────────────────────────────────────────────────────────────
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  ActivityIndicator, RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { apiFetch } from '../utils/apiController';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

const T = {
  bg: '#0A0A0A', card: '#141414', cardAlt: '#15203A',
  border: '#1F2937', accent: '#7C9CFF', accent2: '#A78BFA',
  good: '#34D399', warn: '#FBBF24', text: '#E5E7EB', dim: '#94A3B8', muted: '#64748B',
};

const PHASE_OPTS = [6, 12, 24, 50];
const SIZE_OPTS = [3, 5, 8];

type Worker = { code: string; agent?: string; category?: string };
type Node = {
  id: string; tier: string; title?: string; phase_id?: string;
  lead_id?: string; wave?: number; size?: number; workers?: Worker[];
  legion_id?: string; lead_agent?: string;
};
type Plan = {
  phase_count: number; lead_count: number; critical_path_len: number;
  distinct_workers: number; max_worker_load: number; plan_hash: string; seed: number;
  nodes: Node[];
  waves: { wave: number; phases: string[] }[];
  lead_load: Record<string, number>;
  coverage: { coverage_pct: number; all_covered: boolean; phases_covered: number; phases_total: number };
  verification?: { valid: boolean; acyclic: boolean; fully_reachable: boolean; coverage_ok: boolean };
};

export default function SwarmPlannerScreen() {
  const router = useRouter();
  const [phases, setPhases] = useState(12);
  const [size, setSize] = useState(5);
  const [seed, setSeed] = useState(0);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [exec, setExec] = useState<any | null>(null);
  const [part, setPart] = useState<any | null>(null);
  const [job, setJob] = useState<any | null>(null);
  const [jobBusy, setJobBusy] = useState(false);
  const [diff, setDiff] = useState<any | null>(null);
  const [diffBusy, setDiffBusy] = useState(false);
  const pollRef = useRef<any>(null);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const load = useCallback(async (p: number, s: number, sd: number) => {
    setLoading(true); setErr(null);
    try {
      const r = await apiFetch(
        `${API_URL}/api/galaxy-studio/swarm/planner/preview?phases=${p}&platoon_size=${s}&seed=${sd}`,
        { timeoutMs: 15000 },
      );
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setPlan(await r.json());
    } catch (e: any) {
      setErr(e?.message || 'Failed to plan');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(phases, size, seed); setExec(null); setPart(null); }, [phases, size, seed, load]);

  const runLive = useCallback(async () => {
    setRunning(true); setErr(null);
    try {
      const body = {
        build_id: `planner_${seed}`,
        phases: Array.from({ length: phases }, (_, i) => `p${String(i + 1).padStart(2, '0')}`),
        seed, platoon_size: size, rounds: 1,
      };
      const r = await apiFetch(`${API_URL}/api/galaxy-studio/swarm/planner/execute`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body), timeoutMs: 60000,
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setExec(data.execution);
      setPart(data.participation);
    } catch (e: any) {
      setErr(e?.message || 'Live run failed');
    } finally {
      setRunning(false);
    }
  }, [phases, size, seed]);

  const runAsync = useCallback(async () => {
    setJobBusy(true); setErr(null); setJob(null); setExec(null); setPart(null);
    if (pollRef.current) clearInterval(pollRef.current);
    try {
      const body = {
        build_id: `planner_async_${seed}`,
        phases: Array.from({ length: phases }, (_, i) => `p${String(i + 1).padStart(2, '0')}`),
        seed, platoon_size: size, rounds: 1,
      };
      const r = await apiFetch(`${API_URL}/api/galaxy-studio/swarm/planner/execute/async`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body), timeoutMs: 15000,
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const { job_id } = await r.json();
      setJob({ job_id, status: 'running' });
      pollRef.current = setInterval(async () => {
        try {
          const jr = await apiFetch(`${API_URL}/api/galaxy-studio/swarm/planner/job/${job_id}`, { timeoutMs: 15000 });
          if (!jr.ok) return;
          const jd = await jr.json();
          setJob(jd);
          if (jd.status === 'done' || jd.status === 'error') {
            clearInterval(pollRef.current); pollRef.current = null;
            setJobBusy(false);
            if (jd.status === 'done' && jd.result) {
              setExec(jd.result.execution); setPart(jd.result.participation);
            }
            if (jd.status === 'error') setErr(jd.error || 'Async job failed');
          }
        } catch { /* keep polling */ }
      }, 2000);
    } catch (e: any) {
      setErr(e?.message || 'Async run failed'); setJobBusy(false);
    }
  }, [phases, size, seed]);

  const compareSeeds = useCallback(async () => {
    setDiffBusy(true); setErr(null);
    try {
      const r = await apiFetch(
        `${API_URL}/api/galaxy-studio/swarm/planner/plan-diff?phases=${phases}&platoon_size=${size}&seed_a=${seed}&seed_b=${seed + 1}`,
        { timeoutMs: 15000 });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setDiff(await r.json());
    } catch (e: any) { setErr(e?.message || 'Compare failed'); } finally { setDiffBusy(false); }
  }, [phases, size, seed]);

  const platoonsByWave = (w: number): Node[] =>
    (plan?.nodes || []).filter((n) => n.tier === 'platoon' && n.wave === w);
  const leadNodes = (plan?.nodes || []).filter((n) => n.tier === 'lead');
  const leadTitle = (id?: string) => leadNodes.find((l) => l.id === id)?.title || id;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.iconBtn} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
          <Ionicons name="chevron-back" size={24} color={T.text} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>Swarm Planner</Text>
          <Text style={styles.subtitle}>Director → Leads → Platoons → Workers</Text>
        </View>
        <TouchableOpacity
          onPress={() => setSeed(Math.floor(Math.random() * 100000))}
          style={styles.iconBtn}
          hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
        >
          <Ionicons name="shuffle" size={22} color={T.accent} />
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: 16, paddingBottom: 48 }}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={() => load(phases, size, seed)} tintColor={T.accent} />}
      >
        {/* Controls */}
        <Text style={styles.ctrlLabel}>Phases</Text>
        <View style={styles.chipRow}>
          {PHASE_OPTS.map((p) => (
            <Chip key={p} label={`${p}`} active={phases === p} onPress={() => setPhases(p)} />
          ))}
        </View>
        <Text style={styles.ctrlLabel}>Platoon size</Text>
        <View style={styles.chipRow}>
          {SIZE_OPTS.map((s) => (
            <Chip key={s} label={`${s}`} active={size === s} onPress={() => setSize(s)} />
          ))}
          <View style={styles.seedPill}>
            <Text style={styles.seedTxt}>seed {seed}</Text>
          </View>
        </View>

        <TouchableOpacity
          style={[styles.runBtn, running && { opacity: 0.6 }]}
          onPress={runLive}
          disabled={running}
          activeOpacity={0.85}
        >
          {running
            ? <ActivityIndicator color="#0A0A0A" size="small" />
            : <Ionicons name="play" size={18} color="#0A0A0A" />}
          <Text style={styles.runBtnTxt}>{running ? 'Running real platoons…' : 'Run live (real platoons)'}</Text>
        </TouchableOpacity>

        <View style={styles.btnRow}>
          <TouchableOpacity style={[styles.altBtn, jobBusy && { opacity: 0.6 }]} onPress={runAsync} disabled={jobBusy} activeOpacity={0.85}>
            {jobBusy ? <ActivityIndicator color={T.accent} size="small" /> : <Ionicons name="cloud-upload" size={16} color={T.accent} />}
            <Text style={styles.altBtnTxt}>{jobBusy ? 'Streaming…' : 'Run async (stream)'}</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.altBtn, diffBusy && { opacity: 0.6 }]} onPress={compareSeeds} disabled={diffBusy} activeOpacity={0.85}>
            {diffBusy ? <ActivityIndicator color={T.accent2} size="small" /> : <Ionicons name="git-compare" size={16} color={T.accent2} />}
            <Text style={[styles.altBtnTxt, { color: T.accent2 }]}>{diffBusy ? 'Diffing…' : 'Replay / diff'}</Text>
          </TouchableOpacity>
        </View>

        {job && (
          <View style={[styles.jobCard, { borderColor: job.status === 'error' ? '#7F1D1D' : job.status === 'done' ? '#065F46' : '#1E3A5F' }]}>
            <View style={styles.execHead}>
              <Ionicons
                name={job.status === 'done' ? 'checkmark-circle' : job.status === 'error' ? 'alert-circle' : 'sync'}
                size={16}
                color={job.status === 'done' ? T.good : job.status === 'error' ? '#F87171' : T.accent}
              />
              <Text style={styles.execTitle}>
                Async job {job.status === 'done' ? 'complete' : job.status === 'error' ? 'failed' : 'running…'}
                {job.result?.execution ? ` · ${job.result.execution.phases_executed}/${job.result.execution.phases_planned} phases` : ''}
              </Text>
            </View>
            <Text style={styles.jobMeta}>job {String(job.job_id).slice(0, 10)} · {job.kind || 'execute'}</Text>
          </View>
        )}

        {diff && (
          <View style={styles.diffCard}>
            <View style={styles.execHead}>
              <Ionicons name="git-compare" size={16} color={T.accent2} />
              <Text style={styles.execTitle}>
                Seed {diff.seed_a} → {diff.seed_b} · stability {diff.stability_pct}% · {diff.stable_phases}/{diff.phase_count} stable
              </Text>
            </View>
            <Text style={styles.diffHashes} numberOfLines={1}>{String(diff.plan_hash_a).slice(0, 8)} ⇄ {String(diff.plan_hash_b).slice(0, 8)}</Text>
            {diff.rows.slice(0, 12).map((r: any) => (
              <View key={r.phase_id} style={styles.diffRow}>
                <Text style={styles.diffPhase}>{r.phase_id}</Text>
                <View style={styles.diffBarBg}>
                  <View style={[styles.diffBarFill, { width: `${r.similarity * 100}%`, backgroundColor: r.unchanged ? T.good : T.warn }]} />
                </View>
                <Text style={styles.diffPct}>{Math.round(r.similarity * 100)}%</Text>
              </View>
            ))}
          </View>
        )}

        {exec && (
          <View style={styles.execCard}>
            <View style={styles.execHead}>
              <Ionicons
                name={exec.execution_complete ? 'checkmark-circle' : 'time'}
                size={18}
                color={exec.execution_complete ? T.good : T.warn}
              />
              <Text style={styles.execTitle}>
                Live run · {exec.phases_executed}/{exec.phases_planned} phases · {exec.wave_count} waves
              </Text>
            </View>
            {exec.waves.map((w: any) => (
              <View key={w.wave} style={styles.execWave}>
                <Text style={styles.execWaveLabel}>WAVE {w.wave + 1}</Text>
                {w.rows.map((r: any) => (
                  <View key={r.phase_id} style={styles.execRow}>
                    <Text style={styles.execPhase}>{r.phase_id}</Text>
                    <Text style={styles.execMembers} numberOfLines={1}>
                      {(r.member_codes || []).join(' · ')}
                    </Text>
                    <Text style={styles.execMeta}>{r.utterances}u</Text>
                  </View>
                ))}
              </View>
            ))}
          </View>
        )}

        {part && (
          <View style={styles.partCard}>
            <View style={styles.execHead}>
              <Ionicons name="people" size={16} color={T.accent2} />
              <Text style={styles.execTitle}>Participation · {part.distinct_agents} agents · balance {part.legion_balance_pct}%</Text>
            </View>
            {part.legions.map((l: any) => {
              const max = Math.max(...part.legions.map((x: any) => x.seats), 1);
              return (
                <View key={l.legion_id} style={styles.legRow}>
                  <Text style={styles.legName} numberOfLines={1}>{l.legion_name}</Text>
                  <View style={styles.legBarBg}>
                    <View style={[styles.legBarFill, { width: `${(l.seats / max) * 100}%` }]} />
                  </View>
                  <Text style={styles.legSeats}>{l.seats}</Text>
                </View>
              );
            })}
            <Text style={styles.partTopLabel}>Top contributors</Text>
            <View style={styles.workerWrap}>
              {part.top_agents.slice(0, 6).map((a: any) => (
                <View key={a.code} style={styles.workerChip}>
                  <Text style={styles.workerCode}>{a.code} · {a.seats}</Text>
                  <Text style={styles.workerCat} numberOfLines={1}>{a.legion_name}</Text>
                </View>
              ))}
            </View>
          </View>
        )}

        {err && (
          <View style={[styles.banner, { borderColor: '#7F1D1D', backgroundColor: '#1A0E0E' }]}>
            <Ionicons name="warning" size={16} color="#F87171" />
            <Text style={[styles.bannerTxt, { color: '#FCA5A5' }]}>{err}</Text>
          </View>
        )}

        {loading && !plan && (
          <View style={{ paddingVertical: 48 }}>
            <ActivityIndicator color={T.accent} />
          </View>
        )}

        {plan && (
          <>
            {/* Coverage proof */}
            <View style={[styles.banner, {
              borderColor: plan.coverage.all_covered ? '#065F46' : '#7F1D1D',
              backgroundColor: plan.coverage.all_covered ? '#082A22' : '#1A0E0E',
            }]}>
              <Ionicons
                name={plan.coverage.all_covered ? 'shield-checkmark' : 'alert-circle'}
                size={18}
                color={plan.coverage.all_covered ? T.good : '#F87171'}
              />
              <Text style={[styles.bannerTxt, { color: plan.coverage.all_covered ? T.good : '#FCA5A5' }]}>
                {plan.coverage.coverage_pct}% coverage · {plan.coverage.phases_covered}/{plan.coverage.phases_total} phases
                {plan.verification?.valid ? ' · DAG verified ✓' : ''}
              </Text>
            </View>

            <View style={styles.statRow}>
              <Stat label="Critical path" value={`${plan.critical_path_len}`} hint="waves" />
              <Stat label="Workers" value={`${plan.distinct_workers}`} hint="distinct" />
              <Stat label="Max load" value={`${plan.max_worker_load}`} hint="per agent" />
            </View>
            <View style={styles.hashRow}>
              <Ionicons name="finger-print" size={13} color={T.muted} />
              <Text style={styles.hashTxt}>deterministic hash · {plan.plan_hash}</Text>
            </View>

            {/* Director */}
            <View style={styles.directorCard}>
              <Text style={styles.tierTag}>DIRECTOR</Text>
              <Text style={styles.directorTitle}>Build Director</Text>
              <Text style={styles.directorSub}>orchestrating {plan.phase_count} phases across {plan.lead_count} leads</Text>
            </View>

            {/* Leads */}
            <Text style={styles.sectionTitle}>Leads</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10, paddingVertical: 4 }}>
              {leadNodes.map((l) => (
                <View key={l.id} style={styles.leadCard}>
                  <Text style={styles.leadName} numberOfLines={1}>{l.title}</Text>
                  <Text style={styles.leadAgent} numberOfLines={1}>{l.lead_agent || '—'}</Text>
                  <View style={styles.leadLoadPill}>
                    <Text style={styles.leadLoadTxt}>{plan.lead_load[l.id] ?? 0} phases</Text>
                  </View>
                </View>
              ))}
            </ScrollView>

            {/* Waves → platoons → workers */}
            <Text style={styles.sectionTitle}>Execution waves</Text>
            {plan.waves.map((w) => (
              <View key={w.wave} style={styles.waveBlock}>
                <View style={styles.waveHeader}>
                  <View style={styles.waveBadge}><Text style={styles.waveBadgeTxt}>WAVE {w.wave + 1}</Text></View>
                  <Text style={styles.waveMeta}>{w.phases.length} parallel · runs together</Text>
                </View>
                {platoonsByWave(w.wave).map((pl) => (
                  <View key={pl.id} style={styles.platoonCard}>
                    <View style={styles.platoonTop}>
                      <Text style={styles.platoonPhase}>{pl.phase_id}</Text>
                      <Text style={styles.platoonLead} numberOfLines={1}>{leadTitle(pl.lead_id)}</Text>
                    </View>
                    <View style={styles.workerWrap}>
                      {(pl.workers || []).map((wk) => (
                        <View key={wk.code} style={styles.workerChip}>
                          <Text style={styles.workerCode}>{wk.code}</Text>
                          <Text style={styles.workerCat} numberOfLines={1}>{wk.category}</Text>
                        </View>
                      ))}
                    </View>
                  </View>
                ))}
              </View>
            ))}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function Chip({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <TouchableOpacity onPress={onPress} style={[styles.chip, active && styles.chipActive]}>
      <Text style={[styles.chipTxt, active && styles.chipTxtActive]}>{label}</Text>
    </TouchableOpacity>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <View style={styles.statCard}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={styles.statHint}>{hint}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: T.bg },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 10, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: T.border },
  iconBtn: { padding: 6, minWidth: 36, minHeight: 36, alignItems: 'center', justifyContent: 'center' },
  title: { color: T.text, fontSize: 18, fontWeight: '800' },
  subtitle: { color: T.muted, fontSize: 11, marginTop: 1 },

  ctrlLabel: { color: T.dim, fontSize: 12, fontWeight: '700', marginTop: 10, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'center' },
  chip: { paddingHorizontal: 16, paddingVertical: 8, borderRadius: 999, backgroundColor: T.card, borderWidth: 1, borderColor: T.border },
  chipActive: { backgroundColor: T.accent, borderColor: T.accent },
  chipTxt: { color: T.dim, fontWeight: '700', fontSize: 13 },
  chipTxtActive: { color: '#0A0A0A' },
  seedPill: { marginLeft: 'auto', paddingHorizontal: 12, paddingVertical: 7, borderRadius: 999, backgroundColor: '#0F172A', borderWidth: 1, borderColor: T.border },
  seedTxt: { color: T.accent2, fontSize: 12, fontWeight: '700' },

  banner: { flexDirection: 'row', alignItems: 'center', gap: 8, padding: 12, borderRadius: 12, borderWidth: 1, marginTop: 14 },
  bannerTxt: { fontSize: 13, fontWeight: '700', flex: 1 },

  statRow: { flexDirection: 'row', gap: 10, marginTop: 12 },
  statCard: { flex: 1, backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border, paddingVertical: 14, alignItems: 'center' },
  statValue: { color: T.accent, fontSize: 22, fontWeight: '900' },
  statLabel: { color: T.text, fontSize: 12, fontWeight: '700', marginTop: 2 },
  statHint: { color: T.muted, fontSize: 10, marginTop: 1 },
  hashRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 8, justifyContent: 'center' },
  hashTxt: { color: T.muted, fontSize: 11, fontFamily: 'monospace' },

  directorCard: { backgroundColor: T.cardAlt, borderRadius: 16, borderWidth: 1, borderColor: T.accent, padding: 16, marginTop: 18 },
  tierTag: { color: T.accent, fontSize: 10, fontWeight: '900', letterSpacing: 1.5 },
  directorTitle: { color: T.text, fontSize: 18, fontWeight: '900', marginTop: 4 },
  directorSub: { color: T.dim, fontSize: 12, marginTop: 2 },

  sectionTitle: { color: T.text, fontSize: 15, fontWeight: '800', marginTop: 22, marginBottom: 8 },
  leadCard: { width: 140, backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border, padding: 12 },
  leadName: { color: T.accent2, fontSize: 13, fontWeight: '800' },
  leadAgent: { color: T.dim, fontSize: 11, marginTop: 2 },
  leadLoadPill: { marginTop: 8, alignSelf: 'flex-start', backgroundColor: '#0F172A', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8 },
  leadLoadTxt: { color: T.text, fontSize: 11, fontWeight: '700' },

  waveBlock: { marginBottom: 14 },
  waveHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  waveBadge: { backgroundColor: '#1E293B', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  waveBadgeTxt: { color: T.accent, fontSize: 11, fontWeight: '900', letterSpacing: 0.5 },
  waveMeta: { color: T.muted, fontSize: 11 },
  platoonCard: { backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border, padding: 12, marginBottom: 8 },
  platoonTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 },
  platoonPhase: { color: T.text, fontSize: 14, fontWeight: '900' },
  platoonLead: { color: T.muted, fontSize: 11, maxWidth: '60%' },
  workerWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  workerChip: { backgroundColor: '#0F172A', borderWidth: 1, borderColor: T.border, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 4, maxWidth: 110 },
  workerCode: { color: T.accent, fontSize: 11, fontWeight: '800' },
  workerCat: { color: T.muted, fontSize: 9 },

  runBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: T.good, borderRadius: 12, paddingVertical: 13, marginTop: 16 },
  runBtnTxt: { color: '#0A0A0A', fontWeight: '900', fontSize: 14 },
  btnRow: { flexDirection: 'row', gap: 10, marginTop: 10 },
  altBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 12, paddingVertical: 11 },
  altBtnTxt: { color: T.accent, fontWeight: '800', fontSize: 12 },
  jobCard: { backgroundColor: T.card, borderRadius: 12, borderWidth: 1, padding: 12, marginTop: 12 },
  jobMeta: { color: T.muted, fontSize: 10, fontFamily: 'monospace', marginTop: 4 },
  diffCard: { backgroundColor: T.card, borderRadius: 12, borderWidth: 1, borderColor: '#3B2A6B', padding: 12, marginTop: 12 },
  diffHashes: { color: T.muted, fontSize: 10, fontFamily: 'monospace', marginBottom: 8 },
  diffRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 5 },
  diffPhase: { color: T.text, fontSize: 11, fontWeight: '800', width: 34 },
  diffBarBg: { flex: 1, height: 8, borderRadius: 4, backgroundColor: '#0F172A', overflow: 'hidden' },
  diffBarFill: { height: 8, borderRadius: 4 },
  diffPct: { color: T.dim, fontSize: 10, width: 34, textAlign: 'right' },
  execCard: { backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: '#065F46', padding: 12, marginTop: 14 },
  execHead: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 },
  execTitle: { color: T.text, fontSize: 13, fontWeight: '800', flex: 1 },
  execWave: { marginBottom: 8 },
  execWaveLabel: { color: T.accent, fontSize: 10, fontWeight: '900', letterSpacing: 0.5, marginBottom: 4 },
  execRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 3 },
  execPhase: { color: T.text, fontSize: 12, fontWeight: '800', width: 38 },
  execMembers: { color: T.dim, fontSize: 11, flex: 1 },
  execMeta: { color: T.muted, fontSize: 10 },

  partCard: { backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: '#3B2A6B', padding: 12, marginTop: 12 },
  legRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  legName: { color: T.dim, fontSize: 11, width: 92 },
  legBarBg: { flex: 1, height: 8, borderRadius: 4, backgroundColor: '#0F172A', overflow: 'hidden' },
  legBarFill: { height: 8, borderRadius: 4, backgroundColor: T.accent2 },
  legSeats: { color: T.text, fontSize: 11, fontWeight: '700', width: 26, textAlign: 'right' },
  partTopLabel: { color: T.dim, fontSize: 11, fontWeight: '700', marginTop: 8, marginBottom: 6 },
});
