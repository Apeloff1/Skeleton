/**
 * /studio — 🌌 Galaxy Studio (Unified).
 * The single, clean entry point that runs the whole pipeline IN ORDER on one screen:
 *   1) Questionnaire & 100-Phase Build  (Galaxy Studio Factory)
 *   2) Snowball Quality Pipeline        (13 forge stages, embedded inline)
 *   3) Package & Export                 (Build APK + Download ZIP) — always LAST
 *
 * Launch with ?game=<playable_id> to operate on a build, or start fresh.
 */
import React from 'react';
import {
  View, Text, StyleSheet, ScrollView, SafeAreaView, TouchableOpacity,
  ActivityIndicator, Linking, Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';
import api from '../src/utils/apiClient';
import BuildJourney from '../src/components/BuildJourney';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

type Step = {
  key: string; label: string; icon: string; done?: boolean; locked?: boolean;
  is_next?: boolean; skipped?: boolean; skippable?: boolean; summary?: string;
  quality?: { score?: number } | null;
};

export default function UnifiedStudio() {
  const router = useRouter();
  const params = useLocalSearchParams<{ game?: string }>();
  const [game, setGame] = React.useState(typeof params.game === 'string' ? params.game : '');

  // Seamless handoff: if no build was passed, auto-pick the most recent one.
  React.useEffect(() => {
    if (game) return;
    (async () => {
      const r = await api.get<any>(`/api/playable/list?limit=1`, { timeoutMs: 12000 });
      const items = r.data?.items || r.data?.playables || r.data?.games || [];
      if (items[0]?.playable_id) {
        setGame(items[0].playable_id);
        if (items[0].title) setTitle(String(items[0].title));
      }
    })();
  }, [game]);

  const [title, setTitle] = React.useState('');
  const [steps, setSteps] = React.useState<Step[]>([]);
  const [nextKey, setNextKey] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [running, setRunning] = React.useState<string | null>(null);
  const [apkBusy, setApkBusy] = React.useState(false);
  const [journeyKey, setJourneyKey] = React.useState(0);
  const [axesInfo, setAxesInfo] = React.useState<{ axis_count: number; combined_choice_points: number; era: string } | null>(null);
  const pollRef = React.useRef<any>(null);

  const load = React.useCallback(async () => {
    if (!game) return;
    setLoading(true);
    const r = await api.get<any>(`/api/snowball/${game}`, { timeoutMs: 15000 });
    if (r.ok && r.data) {
      const d = r.data;
      // mount once if nothing is built yet (generates the GDD + vault)
      if (!Array.isArray(d.steps) || d.steps.length === 0) {
        await api.post<any>(`/api/snowball/${game}/mount`, {}, { timeoutMs: 20000 });
      }
      setSteps((d.steps || []).filter((s: Step) => s.key !== 'mode'));
      setNextKey(d.next || (d.steps || []).find((s: Step) => s.is_next)?.key || null);
      if (d.title) setTitle(String(d.title));
      // ── Spec-aware axes: only options that fit this build's spec + are
      //    unlocked at the current stage are surfaced (server-enforced).
      const genre = String(d.genre || d.mode || 'rpg');
      const stageIdx = (d.steps || []).filter((s: Step) => s.done).length;
      const ax = await api.get<any>(
        `/api/galaxy-studio/axes?genre=${encodeURIComponent(genre)}&era=${d.era || 'modern'}&dimension=3d&stage_index=${stageIdx}`,
        { timeoutMs: 12000 });
      if (ax.ok && ax.data && !ax.data.error) {
        setAxesInfo({
          axis_count: ax.data.axis_count || 0,
          combined_choice_points: ax.data.combined_choice_points || ax.data.total_options || 0,
          era: ax.data.spec?.era || d.era || 'modern',
        });
      }
    }
    setLoading(false);
    setJourneyKey((k) => k + 1);
  }, [game]);

  React.useEffect(() => {
    load();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [load]);

  const runStage = React.useCallback(async (key: string) => {
    if (running || !game) return;
    setRunning(key);
    const r = await api.post<any>(`/api/pipeline/${game}/forge/${key}/async`, {}, { timeoutMs: 15000 });
    const jobId = r.data?.job_id;
    if (!jobId) { setRunning(null); Alert.alert('Could not start', r.data?.error || 'Try again.'); return; }
    pollRef.current = setInterval(async () => {
      const pr = await api.get<any>(`/api/playable/job/${jobId}`, { timeoutMs: 12000 });
      const st = pr.data?.job_status || pr.data?.status;
      if (st && st !== 'running') {
        clearInterval(pollRef.current); pollRef.current = null;
        setRunning(null);
        await load();
      }
    }, 3000);
  }, [running, game, load]);

  const skipStage = React.useCallback(async (key: string, undo: boolean) => {
    if (!game) return;
    await api.post<any>(`/api/snowball/${game}/skip/${key}?undo=${undo}`, {}, { timeoutMs: 12000 });
    await load();
  }, [game, load]);

  // ── Advanced options per stage (the exhaustive alternatives the forge generated) ──
  const [openStage, setOpenStage] = React.useState<string | null>(null);
  const [opts, setOpts] = React.useState<Record<string, any[]>>({});
  const [applying, setApplying] = React.useState<string | null>(null);

  const toggleAdvanced = React.useCallback(async (key: string) => {
    if (openStage === key) { setOpenStage(null); return; }
    setOpenStage(key);
    if (!opts[key] && game) {
      const r = await api.get<any>(`/api/snowball/${game}/options/${key}`, { timeoutMs: 12000 });
      setOpts((p) => ({ ...p, [key]: r.data?.options || [] }));
    }
  }, [openStage, opts, game]);

  const applyOption = React.useCallback(async (stage: string, area: string, choice: any) => {
    if (!game || applying) return;
    setApplying(stage);
    const instruction = `For "${area}", adopt this option: ${choice.option}.` +
      (choice.pros ? ` Rationale: ${choice.pros}.` : '') + ' Re-forge the whole stage around this choice.';
    const r = await api.post<any>(`/api/pipeline/${game}/refine/${stage}/async`, { instruction }, { timeoutMs: 15000 });
    const jobId = r.data?.job_id;
    if (!jobId) { setApplying(null); Alert.alert('Could not apply', r.data?.error || 'Try again.'); return; }
    const t = setInterval(async () => {
      const pr = await api.get<any>(`/api/playable/job/${jobId}`, { timeoutMs: 12000 });
      const stt = pr.data?.job_status || pr.data?.status;
      if (stt && stt !== 'running') {
        clearInterval(t); setApplying(null); setOpts((p) => ({ ...p, [stage]: [] })); await load();
      }
    }, 3000);
  }, [game, applying, load]);

  const downloadZip = React.useCallback(async () => {
    if (!game) return;
    try { await Linking.openURL(`${BACKEND}/api/galaxy-studio/vault/zip/${game}`); }
    catch { Alert.alert('ZIP', 'Could not open the ZIP download.'); }
  }, [game]);

  const buildApk = React.useCallback(async () => {
    if (!game) return;
    setApkBusy(true);
    const r = await api.post<any>(`/api/galaxy-studio/vault/zip-to-apk/${game}`, {}, { timeoutMs: 20000 });
    if (!r.ok) { setApkBusy(false); Alert.alert('APK build', r.data?.error || 'Could not start the APK build.'); return; }
    Alert.alert('APK build started', 'Packaging your build into an installable APK. This continues in the background.');
    setApkBusy(false);
  }, [game]);

  const built = steps.filter((s) => s.done).length;
  const total = steps.length;
  const snowballComplete = total > 0 && steps.every((s) => s.done || s.skipped);

  const statusChip = (s: Step) => {
    if (s.locked) return { t: 'LOCKED', c: '#3B82F6' };
    if (s.done) return { t: 'BUILT', c: '#34d399' };
    if (s.skipped) return { t: 'SKIPPED', c: '#6b7280' };
    if (s.is_next) return { t: 'NEXT', c: '#fbbf24' };
    return { t: 'PENDING', c: '#7c7c8a' };
  };

  return (
    <SafeAreaView style={st.root}>
      <View style={st.header}>
        <TouchableOpacity testID="studio-back" onPress={() => router.back()} style={st.hBtn}>
          <Ionicons name="arrow-back" size={24} color="#F8FAFC" />
        </TouchableOpacity>
        <Text style={st.hTitle} numberOfLines={1}>🌌 Galaxy Studio</Text>
        <View style={st.hBtn} />
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 60 }}>
        {/* ── The Build Journey — one coherent, gamified flow ── */}
        <BuildJourney
          game={game}
          refreshKey={journeyKey}
          onNavigate={(route) => {
            const sep = route.includes('?') ? '&' : '?';
            const needsGame = ['/stages', '/snowball', '/forge-hub', '/construct-forge'].some((r) => route.startsWith(r));
            router.push(needsGame && game ? `${route}${sep}game=${game}` : route);
          }}
        />

        {/* ── Phase 1 ── */}
        <View style={st.phase}>
          <Text style={st.phaseNum}>1</Text>
          <View style={st.phaseBody}>
            <Text style={st.phaseTitle}>Questionnaire & 100-Phase Build</Text>
            <Text style={st.phaseSub}>Answer the AAA design questionnaire, then run the 100-phase build.</Text>
            {game ? (
              <View style={st.activePill}>
                <Ionicons name="checkmark-circle" size={15} color="#34d399" />
                <Text style={st.activeTxt} numberOfLines={1}>Active build: {title || game.slice(0, 10)}</Text>
              </View>
            ) : null}
            {axesInfo ? (
              <View style={st.activePill} testID="studio-axes-banner">
                <Ionicons name="options" size={15} color="#3B82F6" />
                <Text style={st.activeTxt} numberOfLines={1}>
                  {axesInfo.axis_count} axes · {axesInfo.combined_choice_points.toLocaleString()} spec-relevant options unlocked ({axesInfo.era})
                </Text>
              </View>
            ) : null}
            <View style={st.row}>
              <TouchableOpacity testID="studio-open-factory" onPress={() => router.push('/galaxy')} style={[st.btn, st.btnPrimary]}>
                <Ionicons name="planet" size={15} color="#0b0b12" />
                <Text style={st.btnPrimaryTxt}>{game ? 'Open Factory' : 'Start a build'}</Text>
              </TouchableOpacity>
              <TouchableOpacity testID="studio-pick-build" onPress={() => router.push('/my-builds')} style={[st.btn, st.btnGhost]}>
                <Ionicons name="albums-outline" size={15} color="#a78bfa" />
                <Text style={st.btnGhostTxt}>Pick a build</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>

        <View style={st.connector} />

        {/* ── Phase 2 — Snowball (inline) ── */}
        <View style={st.phase}>
          <Text style={st.phaseNum}>2</Text>
          <View style={st.phaseBody}>
            <Text style={st.phaseTitle}>Snowball Quality Pipeline</Text>
            <Text style={st.phaseSub}>
              {game ? `${built}/${total} stages built — each step reviews the game files and augments it.`
                    : 'Pick a build above to roll the 13-stage quality pipeline.'}
            </Text>

            {loading ? <ActivityIndicator color="#a78bfa" style={{ marginTop: 12 }} /> : null}

            {game && nextKey ? (
              <TouchableOpacity
                testID="studio-roll"
                onPress={() => runStage(nextKey)}
                disabled={!!running}
                style={[st.btn, st.btnRoll, !!running && { opacity: 0.5 }]}
              >
                {running ? <ActivityIndicator size="small" color="#fff" /> : <Ionicons name="snow-outline" size={16} color="#fff" />}
                <Text style={st.btnRollTxt}>{running ? 'Forging…' : 'Roll next stage'}</Text>
              </TouchableOpacity>
            ) : null}

            {steps.map((s) => {
              const chip = statusChip(s);
              const open = openStage === s.key;
              const stageOpts = opts[s.key] || [];
              return (
                <View key={s.key}>
                  <View style={[st.stage, s.is_next && st.stageNext]}>
                    <Text style={st.stageIcon}>{s.locked ? '🔒' : s.done ? '✅' : s.skipped ? '⏭️' : s.is_next ? '👉' : s.icon}</Text>
                    <View style={{ flex: 1 }}>
                      <Text style={st.stageLabel}>{s.label}</Text>
                      <Text style={st.stageSummary} numberOfLines={1}>
                        {s.skipped ? 'skipped' : (s.summary || 'not built yet')}
                        {s.quality?.score != null ? `  ·  Q${s.quality.score}` : ''}
                      </Text>
                    </View>
                    <Text style={[st.stageChip, { color: chip.c }]}>{chip.t}</Text>
                    {s.done ? (
                      <TouchableOpacity testID={`studio-adv-${s.key}`} onPress={() => toggleAdvanced(s.key)} style={st.advBtn}>
                        <Ionicons name={open ? 'chevron-up' : 'options-outline'} size={15} color="#3B82F6" />
                      </TouchableOpacity>
                    ) : null}
                    {!s.done && s.skippable ? (
                      <TouchableOpacity testID={`studio-skip-${s.key}`} onPress={() => skipStage(s.key, !!s.skipped)} disabled={!!running} style={st.skipBtn}>
                        <Text style={st.skipTxt}>{s.skipped ? '↩' : 'Skip'}</Text>
                      </TouchableOpacity>
                    ) : null}
                  </View>

                  {open ? (
                    <View testID={`studio-adv-panel-${s.key}`} style={st.advPanel}>
                      <Text style={st.advTitle}>Advanced — alternative directions</Text>
                      {applying === s.key ? (
                        <View style={st.advBusy}>
                          <ActivityIndicator size="small" color="#3B82F6" />
                          <Text style={st.advBusyTxt}>Re-forging this stage around your choice…</Text>
                        </View>
                      ) : null}
                      {stageOpts.length === 0 ? (
                        <Text style={st.advEmpty}>No alternatives recorded for this stage yet.</Text>
                      ) : (
                        stageOpts.map((grp: any, gi: number) => (
                          <View key={gi} style={st.advGroup}>
                            <Text style={st.advArea}>{grp.area || `Decision ${gi + 1}`}</Text>
                            {(grp.choices || []).map((c: any, ci: number) => (
                              <TouchableOpacity
                                key={ci}
                                testID={`studio-opt-${s.key}-${gi}-${ci}`}
                                onPress={() => applyOption(s.key, grp.area || `Decision ${gi + 1}`, c)}
                                disabled={!!applying}
                                style={[st.advChoice, c.recommended && st.advChoiceRec, !!applying && { opacity: 0.5 }]}
                              >
                                <View style={{ flex: 1 }}>
                                  <Text style={st.advOpt}>{c.recommended ? '★ ' : ''}{c.option}</Text>
                                  {c.pros ? <Text style={st.advPros} numberOfLines={3}>+ {Array.isArray(c.pros) ? c.pros.join(' · ') : c.pros}</Text> : null}
                                  {c.cons ? <Text style={st.advCons} numberOfLines={3}>− {Array.isArray(c.cons) ? c.cons.join(' · ') : c.cons}</Text> : null}
                                </View>
                                <Ionicons name="arrow-forward-circle" size={20} color="#7c3aed" />
                              </TouchableOpacity>
                            ))}
                          </View>
                        ))
                      )}
                    </View>
                  ) : null}
                </View>
              );
            })}
          </View>
        </View>

        <View style={st.connector} />

        {/* ── Phase 3 — Package (LAST) ── */}
        <View style={[st.phase, !snowballComplete && st.phaseDim]}>
          <Text style={st.phaseNum}>3</Text>
          <View style={st.phaseBody}>
            <Text style={st.phaseTitle}>Package & Export</Text>
            <Text style={st.phaseSub}>
              {snowballComplete ? 'Pipeline complete — package your build.'
                                : 'Finish (or skip) the Snowball stages to unlock packaging.'}
            </Text>
            <View style={st.row}>
              <TouchableOpacity
                testID="studio-apk"
                onPress={buildApk}
                disabled={!game || !snowballComplete || apkBusy}
                style={[st.btn, st.btnPrimary, (!game || !snowballComplete || apkBusy) && { opacity: 0.45 }]}
              >
                {apkBusy ? <ActivityIndicator size="small" color="#0b0b12" /> : <Ionicons name="logo-android" size={15} color="#0b0b12" />}
                <Text style={st.btnPrimaryTxt}>Build APK</Text>
              </TouchableOpacity>
              <TouchableOpacity
                testID="studio-zip"
                onPress={downloadZip}
                disabled={!game || !snowballComplete}
                style={[st.btn, st.btnGhost, (!game || !snowballComplete) && { opacity: 0.45 }]}
              >
                <Ionicons name="download-outline" size={15} color="#a78bfa" />
                <Text style={st.btnGhostTxt}>Download ZIP</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0b0b12' },
  header: { flexDirection: 'row', alignItems: 'center', padding: 12, backgroundColor: '#15131f', borderBottomWidth: 1, borderBottomColor: '#2a2640' },
  hBtn: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  hTitle: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '800', color: '#F8FAFC' },
  phase: { flexDirection: 'row', gap: 12, backgroundColor: '#15131f', borderRadius: 16, borderWidth: 1, borderColor: '#2a2640', padding: 14 },
  phaseDim: { opacity: 0.7 },
  phaseNum: { width: 28, height: 28, borderRadius: 14, backgroundColor: '#a78bfa', color: '#0b0b12', textAlign: 'center', lineHeight: 28, fontWeight: '900', fontSize: 14, overflow: 'hidden' },
  phaseBody: { flex: 1 },
  phaseTitle: { color: '#F8FAFC', fontSize: 16, fontWeight: '800' },
  phaseSub: { color: '#9ca3af', fontSize: 12, marginTop: 3, lineHeight: 17 },
  connector: { width: 2, height: 18, backgroundColor: '#2a2640', marginLeft: 27 },
  activePill: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 10, backgroundColor: '#34d39922', alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 5, borderRadius: 14 },
  activeTxt: { color: '#34d399', fontSize: 12, fontWeight: '700' },
  row: { flexDirection: 'row', gap: 10, marginTop: 12, flexWrap: 'wrap' },
  btn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, borderRadius: 11, paddingVertical: 11, paddingHorizontal: 14 },
  btnPrimary: { backgroundColor: '#a78bfa' },
  btnPrimaryTxt: { color: '#0b0b12', fontSize: 13, fontWeight: '800' },
  btnGhost: { backgroundColor: 'transparent', borderWidth: 1, borderColor: '#a78bfa55' },
  btnGhostTxt: { color: '#a78bfa', fontSize: 13, fontWeight: '700' },
  btnRoll: { backgroundColor: '#7c3aed', marginTop: 12, alignSelf: 'flex-start', paddingHorizontal: 18 },
  btnRollTxt: { color: '#fff', fontSize: 13, fontWeight: '800' },
  stage: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#221f30' },
  stageNext: { backgroundColor: '#fbbf2410', borderRadius: 8, paddingHorizontal: 6 },
  stageIcon: { fontSize: 18, width: 24, textAlign: 'center' },
  stageLabel: { color: '#e5e7eb', fontSize: 13, fontWeight: '700' },
  stageSummary: { color: '#7c7c8a', fontSize: 11, marginTop: 1 },
  stageChip: { fontSize: 9, fontWeight: '800' },
  skipBtn: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8, borderWidth: 1, borderColor: '#33303f' },
  skipTxt: { color: '#9ca3af', fontSize: 10, fontWeight: '700' },
  advBtn: { width: 30, height: 30, alignItems: 'center', justifyContent: 'center', borderRadius: 8, borderWidth: 1, borderColor: '#3B82F644' },
  advPanel: { backgroundColor: '#0f1620', borderRadius: 12, borderWidth: 1, borderColor: '#3B82F633', padding: 12, marginTop: 4, marginBottom: 8 },
  advTitle: { color: '#3B82F6', fontSize: 12, fontWeight: '800', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 },
  advBusy: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 },
  advBusyTxt: { color: '#3B82F6', fontSize: 12, fontWeight: '600' },
  advEmpty: { color: '#7c7c8a', fontSize: 12, fontStyle: 'italic' },
  advGroup: { marginBottom: 12 },
  advArea: { color: '#e5e7eb', fontSize: 13, fontWeight: '800', marginBottom: 6 },
  advChoice: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#15131f', borderRadius: 10, borderWidth: 1, borderColor: '#2a2640', padding: 10, marginBottom: 6 },
  advChoiceRec: { borderColor: '#7c3aed', backgroundColor: '#7c3aed18' },
  advOpt: { color: '#f8fafc', fontSize: 12, fontWeight: '700' },
  advPros: { color: '#34d399', fontSize: 11, marginTop: 2 },
  advCons: { color: '#f87171', fontSize: 11, marginTop: 1 },
});
