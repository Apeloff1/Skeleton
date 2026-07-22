/**
 * /snowball — ☃️ Snowball Build (manual, stage-by-stage).
 *
 * The creator rolls the snowball one stage at a time: tap "Run this stage" → the forge runs
 * and accumulates into the KB → review/refine → 🔒 Lock → the next stage unlocks. A GROWING
 * Game Design Document (recompiled from everything built so far) sits at the top and gets
 * bigger with every stage. Run/refine/lock reuse the existing pipeline forge endpoints.
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator, StyleSheet,
  SafeAreaView, RefreshControl, TextInput, Linking, Platform,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import api from '../src/utils/apiClient';
import CoverageMeter from '../src/components/CoverageMeter';
import { speakCinematic, stopCinematic } from '../src/utils/cinematicVoice';

export default function Snowball() {
  const router = useRouter();
  const params = useLocalSearchParams<{ game?: string }>();
  const gameId = params?.game ? String(params.game) : '';

  const [snow, setSnow] = React.useState<any>(null);
  const [loadErr, setLoadErr] = React.useState<string | null>(null);
  const [refreshing, setRefreshing] = React.useState(false);
  const [running, setRunning] = React.useState<string | null>(null);
  const [status, setStatus] = React.useState<Record<string, string>>({});
  const [refineKey, setRefineKey] = React.useState<string | null>(null);
  const [refineDraft, setRefineDraft] = React.useState('');
  const [locking, setLocking] = React.useState<string | null>(null);
  const [gddOpen, setGddOpen] = React.useState(true);
  const [flow, setFlow] = React.useState<any>(null);
  const [modeBusy, setModeBusy] = React.useState(false);

  // ── 100-phase ladder (crosswired to this game) — the snowball LANDING view ──
  const [phases, setPhases] = React.useState<any>(null);
  const [phaseEra, setPhaseEra] = React.useState('modern');
  const [phasesBusy, setPhasesBusy] = React.useState(false);
  const [phasesOpen, setPhasesOpen] = React.useState(true);

  const loadPhases = React.useCallback(async (eraKey: string) => {
    if (!gameId) return;
    setPhasesBusy(true);
    const r = await api.get<any>(
      `/api/snowball/${gameId}/phases?era=${encodeURIComponent(eraKey)}&seed=1`,
      { timeoutMs: 20000 });
    if (r.ok && r.data && !r.data.error) setPhases(r.data);
    setPhasesBusy(false);
  }, [gameId]);

  React.useEffect(() => { loadPhases(phaseEra); }, [loadPhases, phaseEra]);

  const loadFlow = React.useCallback(async () => {
    if (!gameId) return;
    const fr = await api.get<any>(`/api/snowball/${gameId}/flow`, { timeoutMs: 12000 });
    if (fr.ok && fr.data && !fr.data.error) {
      if (!fr.data.mounted) {
        await api.post<any>(`/api/snowball/${gameId}/mount?exec_mode=${fr.data.exec_mode || 'manual'}`, {}, { timeoutMs: 15000 });
      }
      setFlow(fr.data);
    }
  }, [gameId]);

  const setExecMode = React.useCallback(async (mode: string) => {
    if (!gameId) return;
    setModeBusy(true);
    await api.post<any>(`/api/snowball/${gameId}/mode?exec_mode=${mode}`, {}, { timeoutMs: 12000 });
    await loadFlow();
    setModeBusy(false);
  }, [gameId, loadFlow]);

  const [runAllBusy, setRunAllBusy] = React.useState(false);
  const [warroom, setWarroom] = React.useState<any[]>([]);
  const [wins, setWins] = React.useState<any>(null);

  const loadWins = React.useCallback(async () => {
    if (!gameId) return;
    const [rd, nba] = await Promise.all([
      api.get<any>(`/api/wins/${gameId}/readiness`, { timeoutMs: 10000 }),
      api.get<any>(`/api/wins/${gameId}/next-best-action`, { timeoutMs: 10000 }),
    ]);
    setWins({ readiness: rd.ok ? rd.data : null, nba: nba.ok ? nba.data : null });
  }, [gameId]);

  const load = React.useCallback(async () => {
    if (!gameId) { setLoadErr('No build selected — open a build from Galaxy Studio first.'); return; }
    const r = await api.get<any>(`/api/snowball/${gameId}`, { timeoutMs: 12000 });
    if (r.ok && r.data && !r.data.error) { setSnow(r.data); setLoadErr(null); }
    else setLoadErr(r.data?.error || 'Could not load this build.');
  }, [gameId]);

  // ⚡ AUTO / 🤵 JEEVES: kick the full autonomous build via groupchat, stream the
  // live war-room transcript, and (in Jeeves mode) narrate each line in-voice.
  const onRunAll = React.useCallback(async () => {
    if (!gameId) return;
    setRunAllBusy(true); setWarroom([]);
    const agentic = flow?.exec_mode === 'agentic';
    const r = await api.post<any>(`/api/groupchat/${gameId}/run/async`, {}, { timeoutMs: 15000 });
    const jid = r.data?.job_id;
    if (!jid) { setRunAllBusy(false); return; }
    let spoken = 0;
    for (let i = 0; i < 120; i++) {
      await new Promise(res => setTimeout(res, 4000));
      const jr = await api.get<any>(`/api/groupchat/job/${jid}`, { timeoutMs: 12000 });
      const j = jr.data || {};
      const t: any[] = j.transcript || [];
      setWarroom(t.slice(-12));
      if (agentic && t.length > spoken) {
        const latest = t[t.length - 1];
        if (latest?.text && latest.kind !== 'status') {
          speakCinematic(latest.text, { tone: latest.tone || 'butler' });
        }
        spoken = t.length;
      }
      if (j.job_status && j.job_status !== 'running') break;
    }
    await load(); await loadFlow();
    setRunAllBusy(false);
  }, [gameId, flow, load, loadFlow]);

  React.useEffect(() => () => { stopCinematic(); }, []);

  const [nbaBusy, setNbaBusy] = React.useState(false);
  const [gates14Busy, setGates14Busy] = React.useState(false);
  const [gates14, setGates14] = React.useState<any>(null);
  const [coverageKey, setCoverageKey] = React.useState(0);

  // 🚦 Sweep EVERY mounted system through all 14 AAA gates in one tap.
  // Deterministic (ai:false) so the public ingress (30s) never times out.
  const runAll14 = React.useCallback(async () => {
    if (!gameId || gates14Busy) return;
    setGates14Busy(true); setGates14(null);
    const r = await api.post<any>(`/api/galaxy-studio/gates/build/${gameId}/run-all`,
      { build_id: gameId, seed: 1, ai: false, include_panel: true }, { timeoutMs: 60000 });
    if (r.ok && r.data && !r.data.error) setGates14(r.data);
    else setGates14({ error: r.data?.error || 'run failed' });
    setCoverageKey(k => k + 1);
    setGates14Busy(false);
  }, [gameId, gates14Busy]);
  const onNextAction = React.useCallback(async () => {
    const nba = wins?.nba;
    if (!nba?.action || !gameId) return;
    setNbaBusy(true);
    try {
      if (nba.action === 'mount') {
        await api.post<any>(`/api/snowball/${gameId}/mount`, {}, { timeoutMs: 20000 });
      } else if (nba.action === 'run_stage' && nba.stage) {
        await api.post<any>(`/api/pipeline/${gameId}/forge/${nba.stage}/async`, {}, { timeoutMs: 20000 });
      } else if (nba.action === 'remaster') {
        await api.post<any>(`/api/snowball/${gameId}/remaster`, {}, { timeoutMs: 90000 });
      } else if (nba.action === 'trailer') {
        await api.post<any>(`/api/jeeves-voice/trailer`, { pid: gameId, title: snow?.title || 'Your Game' }, { timeoutMs: 60000 });
      }
    } catch {}
    await load(); await loadFlow(); await loadWins();
    setNbaBusy(false);
  }, [wins, gameId, snow, load, loadFlow, loadWins]);

  React.useEffect(() => { load(); loadFlow(); loadWins(); }, [load, loadFlow, loadWins]);

  const onRefresh = React.useCallback(async () => {
    setRefreshing(true); await load(); setRefreshing(false);
  }, [load]);

  // RUN or REFINE a stage via the existing forge endpoints, then poll + reload
  const pollJob = React.useCallback(async (key: string, jid: string, verb: string) => {
    const t0 = Date.now();
    for (let i = 0; i < 60; i++) {
      await new Promise(res => setTimeout(res, 4000));
      const jr = await api.get<any>(`/api/playable/job/${jid}`, { timeoutMs: 12000 });
      const d = jr.data || {};
      if (d.job_status === 'error') { setStatus(p => ({ ...p, [key]: `❌ ${d.error || 'failed'}` })); break; }
      if (d.job_status === 'done') {
        setStatus(p => ({ ...p, [key]: d.ok === false ? `⚠️ ${d.error || 'kept previous'}` : `✅ ${verb} — ${d.summary || 'done'}` }));
        setRefineKey(null); setRefineDraft(''); await load(); break;
      }
      setStatus(p => ({ ...p, [key]: `⏳ ${verb}… ${Math.round((Date.now() - t0) / 1000)}s` }));
    }
    setRunning(null);
  }, [load]);

  const runStage = React.useCallback(async (key: string) => {
    if (running) return;
    setRunning(key); setStatus(p => ({ ...p, [key]: '🎬 Starting…' }));
    const r = await api.post<any>(`/api/pipeline/${gameId}/forge/${key}/async`, {}, { timeoutMs: 15000 });
    if (!r.ok || !r.data?.job_id) { setStatus(p => ({ ...p, [key]: `❌ ${r.data?.error || 'could not start'}` })); setRunning(null); return; }
    await pollJob(key, r.data.job_id, 'Built');
  }, [running, gameId, pollJob]);

  const refineStage = React.useCallback(async (key: string) => {
    const note = refineDraft.trim();
    if (running || !note) return;
    setRunning(key); setStatus(p => ({ ...p, [key]: '💬 Refining…' }));
    const r = await api.post<any>(`/api/pipeline/${gameId}/refine/${key}/async`, { instruction: note }, { timeoutMs: 15000 });
    if (!r.ok || !r.data?.job_id) { setStatus(p => ({ ...p, [key]: `❌ ${r.data?.error || 'could not start'}` })); setRunning(null); return; }
    await pollJob(key, r.data.job_id, 'Refined');
  }, [running, gameId, refineDraft, pollJob]);

  const lockStage = React.useCallback(async (key: string, currentlyLocked: boolean) => {
    if (locking) return;
    setLocking(key);
    const r = await api.post<any>(`/api/pipeline/${gameId}/approve/${key}`, { approved: !currentlyLocked }, { timeoutMs: 12000 });
    if (r.ok && r.data?.ok) await load();
    setLocking(null);
  }, [locking, gameId, load]);

  const skipStage = React.useCallback(async (key: string, undo: boolean) => {
    await api.post<any>(`/api/snowball/${gameId}/skip/${key}?undo=${undo}`, {}, { timeoutMs: 12000 });
    await load();
  }, [gameId, load]);

  const lockAll = React.useCallback(async () => {
    const r = await api.post<any>(`/api/snowball/${gameId}/lock-all`, {}, { timeoutMs: 12000 });
    if (r.ok && r.data?.ok) await load();
  }, [gameId, load]);

  const rollSnowball = React.useCallback(() => {
    if (snow?.next && !running) runStage(snow.next);
  }, [snow, running, runStage]);

  const exportGdd = React.useCallback(() => {
    const base = process.env.EXPO_PUBLIC_BACKEND_URL || '';
    Linking.openURL(`${base}/api/snowball/${gameId}/gdd.md`);
  }, [gameId]);

  // 🚀 SHIP IT — one tap: Package ZIP + Build APK, then open the artifact bay.
  const [shipBusy, setShipBusy] = React.useState(false);
  const [shipMsg, setShipMsg] = React.useState('');
  const shipIt = React.useCallback(async () => {
    if (shipBusy || !gameId) return;
    setShipBusy(true);
    setShipMsg('📦 Packaging ZIP + 📱 building APK…');
    const r = await api.post<any>('/api/binary/package',
      { build_id: gameId, kinds: ['zip', 'apk'] }, { timeoutMs: 180000 });
    if (r.ok && r.data && !r.data.error) {
      const n = (r.data.artifacts || []).length;
      setShipMsg(`✅ Shipped ${n} artifact${n === 1 ? '' : 's'}! Opening your build…`);
      setTimeout(() => router.push(
        `/apk-build?build=${encodeURIComponent(gameId)}&game=${encodeURIComponent(gameId)}` as any), 700);
    } else {
      setShipMsg(`❌ ${r.data?.error || r.data?.detail || 'Ship failed — build & lock the stages first.'}`);
    }
    setShipBusy(false);
  }, [shipBusy, gameId, router]);

  if (!snow) {
    return (
      <SafeAreaView style={s.root}>
        <View style={s.header}>
          <TouchableOpacity onPress={() => router.back()} style={s.back}><Text style={s.backTxt}>‹ Back</Text></TouchableOpacity>
          <Text style={s.title}>☃️ Snowball Build</Text>
        </View>
        {loadErr ? (
          <View style={{ padding: 32, alignItems: 'center' }}>
            <Text style={{ fontSize: 40, marginBottom: 12 }}>🫥</Text>
            <Text style={{ color: '#E2E8F0', fontSize: 16, fontWeight: '800', textAlign: 'center' }}>Build not found</Text>
            <Text style={{ color: '#94A3B8', fontSize: 13, textAlign: 'center', marginTop: 8, lineHeight: 19 }}>{loadErr}</Text>
            <View style={{ flexDirection: 'row', gap: 10, marginTop: 20 }}>
              <TouchableOpacity testID="snow-err-retry" onPress={() => { setLoadErr(null); load(); }}
                style={[s.mBtn, s.mBtnRoll]} activeOpacity={0.9}>
                <Text style={s.mBtnTxt}>↻ Retry</Text>
              </TouchableOpacity>
              <TouchableOpacity testID="snow-err-back" onPress={() => router.back()}
                style={[s.mBtn, s.mBtnExport]} activeOpacity={0.9}>
                <Text style={s.mBtnExportTxt}>‹ Go back</Text>
              </TouchableOpacity>
            </View>
          </View>
        ) : (
          <View style={{ padding: 40, alignItems: 'center' }}>
            <ActivityIndicator size="large" color="#93C5FD" />
          </View>
        )}
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.root}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.back}><Text style={s.backTxt}>‹ Back</Text></TouchableOpacity>
        <Text style={s.title}>☃️ Snowball Build</Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 60 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#93C5FD" />}>

        {/* ── 100-PHASE LADDER — the snowball landing (crosswired to this game).
              Era-scaled industry-standard file output + 8-band / 100-phase ladder. */}
        <View style={s.phasesCard} testID="snow-phases-card">
          <TouchableOpacity style={s.phasesHead} onPress={() => setPhasesOpen(o => !o)} activeOpacity={0.85}>
            <Text style={s.phasesTitle}>🧮 100-Phase Build</Text>
            <Text style={s.phasesPct}>
              {phases ? `${phases.pass_pct}% · ${phases.bands_passed}/${phases.bands_total} bands` : '…'}
            </Text>
            <Text style={s.phasesChev}>{phasesOpen ? '▾' : '▸'}</Text>
          </TouchableOpacity>

          {/* Era selector — drives the industry-standard file count */}
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: 10 }}
            contentContainerStyle={{ gap: 6 }}>
            {(phases?.eras || []).map((e: any) => (
              <TouchableOpacity key={e.key} testID={`snow-phase-era-${e.key}`}
                onPress={() => setPhaseEra(e.key)}
                style={[s.eraChip, phaseEra === e.key && s.eraChipOn]} activeOpacity={0.85}>
                <Text style={[s.eraChipTxt, phaseEra === e.key && s.eraChipTxtOn]}>{e.label}</Text>
                <Text style={[s.eraChipNum, phaseEra === e.key && s.eraChipTxtOn]}>
                  {Number(e.file_count_standard).toLocaleString()}
                </Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          {phasesBusy && !phases && (
            <ActivityIndicator color="#93C5FD" style={{ marginVertical: 16 }} />
          )}

          {phases?.file_plan && (
            <View style={{ marginTop: 12 }}>
              <View style={s.filePlanRow}>
                <Text style={s.filePlanBig}>{Number(phases.file_plan.file_target).toLocaleString()}</Text>
                <Text style={s.filePlanMuted}> files · {phases.file_plan.era_label} industry standard</Text>
              </View>
              <View style={s.barTrack}>
                <View style={[s.barFill, { width: `${phases.file_plan.produced_pct}%` }]} />
              </View>
              <Text style={s.filePlanSub}>
                📦 {Number(phases.file_plan.files_produced).toLocaleString()} produced ({phases.file_plan.produced_pct}%) across 100 phases
              </Text>

              {phasesOpen && (
                <View style={{ marginTop: 10 }}>
                  {(phases.bands || []).map((b: any) => (
                    <View key={b.band} style={s.bandRow} testID={`snow-band-${b.gate}`}>
                      <Text style={[s.bandDot, { color: b.passed ? '#34D399' : '#f59e0b' }]}>
                        {b.passed ? '●' : '○'}
                      </Text>
                      <View style={{ flex: 1 }}>
                        <Text style={s.bandName}>{b.band} <Text style={s.bandPhase}>· p{b.phase_range[0]}–{b.phase_range[1]}</Text></Text>
                        <Text style={s.bandDetail} numberOfLines={1}>{b.detail}</Text>
                      </View>
                      <Text style={s.bandFiles}>{Number(b.file_target).toLocaleString()}</Text>
                    </View>
                  ))}
                  {phases.asset_grounded === false && (
                    <Text style={s.bandWarn}>⚠️ No forged assets yet — Assets band stays amber until the build mints them.</Text>
                  )}
                </View>
              )}
            </View>
          )}
        </View>

        {/* snowball size meter */}
        <View style={s.meter}>
          <Text style={s.meterTitle} numberOfLines={1}>{snow.title || 'Untitled'}</Text>
          <Text style={s.meterSub}>{snow.size_label}</Text>
          <View style={s.barTrack}><View style={[s.barFill, { width: `${snow.percent}%` }]} /></View>
          <Text style={s.meterNext}>{snow.next ? <>Next stage → <Text style={s.meterNextBold}>{snow.next_label}</Text></> : '🎉 Snowball complete!'}</Text>
          {snow.stale_count > 0 && <Text style={s.meterStale}>⚠️ {snow.stale_count} stage(s) stale — upstream changed, re-run to keep canon consistent</Text>}
          <View style={s.meterBtns}>
            <TouchableOpacity testID="snow-roll" onPress={rollSnowball} disabled={!snow.next || !!running}
              style={[s.mBtn, s.mBtnRoll, (!snow.next || !!running) && s.btnOff]} activeOpacity={0.9}>
              <Text style={s.mBtnTxt}>🎲 Roll snowball</Text>
            </TouchableOpacity>
            <TouchableOpacity testID="snow-lock-all" onPress={lockAll} style={[s.mBtn, s.mBtnLock]} activeOpacity={0.9}>
              <Text style={s.mBtnTxt}>🔒 Lock all built</Text>
            </TouchableOpacity>
            <TouchableOpacity testID="snow-export" onPress={exportGdd} style={[s.mBtn, s.mBtnExport]} activeOpacity={0.9}>
              <Text style={s.mBtnExportTxt}>⬇️ Export GDD</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Stage Builder — lay out the game spine; building each stage mints
            the first gamefiles (the beginning of the build process). */}
        <TouchableOpacity testID="snow-stage-builder" activeOpacity={0.9}
          onPress={() => router.push(`/stages?game=${encodeURIComponent(gameId)}`)}
          style={[s.toolsCta, { backgroundColor: '#0e2630', borderColor: '#1f5a6e' }]}>
          <Text style={s.toolsCtaIcon}>🎬</Text>
          <View style={{ flex: 1 }}>
            <Text style={[s.toolsCtaTitle, { color: '#DBEAFE' }]}>Stage Builder</Text>
            <Text style={[s.toolsCtaSub, { color: '#93A9C9' }]}>63 stage types (boss · cutscene · interlude…) — building a stage mints its first gamefiles</Text>
          </View>
          <Text style={[s.toolsCtaArrow, { color: '#3B82F6' }]}>→</Text>
        </TouchableOpacity>

        {/* AI Game Tools — Forge-grade tools (NPC, World, VFX, …) with a
            7-step pipeline that mounts forged batches to this build's Vault. */}
        <TouchableOpacity testID="snow-ai-tools" activeOpacity={0.9}
          onPress={() => router.push(`/tools-hub?build=${encodeURIComponent(gameId)}`)}
          style={s.toolsCta}>
          <Text style={s.toolsCtaIcon}>🎮</Text>
          <View style={{ flex: 1 }}>
            <Text style={s.toolsCtaTitle}>AI Game Tools</Text>
            <Text style={s.toolsCtaSub}>NPC · World · VFX · Combat · Loot · Sci-Fi — forge & mount to this build</Text>
          </View>
          <Text style={s.toolsCtaArrow}>→</Text>
        </TouchableOpacity>

        {/* Review & edit the build's gamefiles before the Build phase. */}
        <TouchableOpacity testID="snow-edit-gamefiles" activeOpacity={0.9}
          onPress={() => router.push(`/edit-gamefiles?build=${encodeURIComponent(gameId)}`)}
          style={[s.toolsCta, { backgroundColor: '#231c10', borderColor: '#5a4a1f' }]}>
          <Text style={s.toolsCtaIcon}>📝</Text>
          <View style={{ flex: 1 }}>
            <Text style={[s.toolsCtaTitle, { color: '#ffe9c0' }]}>Edit Gamefiles</Text>
            <Text style={[s.toolsCtaSub, { color: '#b8a482' }]}>Review & curate the Vault before building</Text>
          </View>
          <Text style={[s.toolsCtaArrow, { color: '#f4a261' }]}>→</Text>
        </TouchableOpacity>

        {/* Game Systems Forge — non-3D systems (narrative, economy, AI-director,
            quests, progression…) with a 7-step pipeline that mounts blueprints. */}
        <TouchableOpacity testID="snow-systems-forge" activeOpacity={0.9}
          onPress={() => router.push(`/systems-forge?build=${encodeURIComponent(gameId)}`)}
          style={[s.toolsCta, { backgroundColor: '#19142b', borderColor: '#4a3a6e' }]}>
          <Text style={s.toolsCtaIcon}>🧩</Text>
          <View style={{ flex: 1 }}>
            <Text style={[s.toolsCtaTitle, { color: '#e7ddff' }]}>Game Systems Forge</Text>
            <Text style={[s.toolsCtaSub, { color: '#a99cce' }]}>Narrative · Economy · AI-Director · Quests · Progression — blueprint & mount</Text>
          </View>
          <Text style={[s.toolsCtaArrow, { color: '#a78bfa' }]}>→</Text>
        </TouchableOpacity>

        {/* 🚀 SHIP IT — one tap from build to installable: ZIP + APK, then opens
              the artifact bay so the creator can download immediately. */}
        <TouchableOpacity testID="snow-ship-it" activeOpacity={0.9} onPress={shipIt} disabled={shipBusy}
          style={[s.shipCta, shipBusy && { opacity: 0.7 }]}>
          {shipBusy ? <ActivityIndicator color="#021019" /> : <Text style={s.shipIcon}>🚀</Text>}
          <View style={{ flex: 1 }}>
            <Text style={s.shipTitle}>Ship It</Text>
            <Text style={s.shipSub} numberOfLines={2}>
              {shipMsg || 'One tap → Package ZIP + Build APK → download your installable'}
            </Text>
          </View>
          <Text style={s.shipArrow}>→</Text>
        </TouchableOpacity>

        {/* 🏭 FORGE & SHIP BAY — every forge + export/packaging, surfaced here
              (moved off the Hub per user request). Each route is code-split by
              expo-router, so it is auto lazy-loaded on tap (memory-safe). */}
        <Text style={s.bayTitle}>🏭 Forge & Ship Bay</Text>
        <View style={s.bayGrid}>
          {[
            ['🏗️', 'Construct Forge', '3D props & materials', '/construct-forge', '#0e2630', '#1f5a6e', '#3B82F6'],
            ['⚒️', 'Item Foundry', 'Items · gear · economy', '/item-foundry', '#231c10', '#5a4a1f', '#f4a261'],
            ['🌍', 'World Forge', 'Procedural terrain', '/worldforge', '#10231c', '#1f5a44', '#43d39e'],
            ['🎨', 'Asset Genesis', 'AI art & textures', '/asset-genesis', '#19142b', '#4a3a6e', '#a78bfa'],
            ['🏛️', 'Factions', 'Social simulation', '/factions', '#231405', '#5a3a1f', '#d97706'],
            ['🪞', 'Agent Reflection', 'Once-over self-review', '/agent-review', '#1a1424', '#4a2f6e', '#c79bff'],
            ['📦', 'Zip Export', 'Bundle gamefiles', '/zip-export', '#0a1620', '#1f3a4a', '#93C5FD'],
            ['📱', 'APK Build', 'Installable Android', '/apk-build', '#120e22', '#3a2f6e', '#A78BFA'],
            ['🗂️', 'My Builds', 'All saved builds', '/my-builds', '#0b1220', '#1e293b', '#94a3b8'],
            ['🔬', 'APK Inspector', 'Bytecode & manifest', '/apk-inspector', '#0f1a24', '#27435a', '#60a5fa'],
          ].map(([icon, title, sub, route, bg, bd, fg]) => (
            <TouchableOpacity key={route} testID={`bay${route}`} activeOpacity={0.88}
              onPress={() => router.push(`${route}?build=${encodeURIComponent(gameId)}&game=${encodeURIComponent(gameId)}` as any)}
              style={[s.bayCard, { backgroundColor: bg, borderColor: bd }]}>
              <Text style={s.bayIcon}>{icon}</Text>
              <Text style={[s.bayCardTitle, { color: fg }]} numberOfLines={1}>{title}</Text>
              <Text style={s.bayCardSub} numberOfLines={2}>{sub}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* ── 3 pre-build gate pages: Refine → Polish → Quality Control.
              Each is a 7-segment pipeline whose segments pass through the
              Query→Acquire→Refine gate chain (runs right after the quality gate). */}
        <Text style={{ color: '#8a96b2', fontSize: 12, fontWeight: '800', marginTop: 6, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.4 }}>🚦 Pre-Build Gates — Query · Acquire · Refine</Text>
        {[
          ['refine', '🔧', 'Refine', 'Structural correctness — 7 segments', '#16241c', '#2f5a3f', '#43d39e'],
          ['polish', '✨', 'Polish', 'Feel & presentation — 7 segments', '#241f10', '#5a4a1f', '#f4c95d'],
          ['quality-control', '🛡️', 'Quality Control', 'Ship-readiness audit — 7 segments', '#1a1424', '#4a2f6e', '#c79bff'],
        ].map(([route, icon, title, sub, bg, bd, fg]) => (
          <TouchableOpacity key={route} testID={`snow-gate-${route}`} activeOpacity={0.9}
            onPress={() => router.push(`/${route}?build=${encodeURIComponent(gameId)}`)}
            style={[s.toolsCta, { backgroundColor: bg, borderColor: bd }]}>
            <Text style={s.toolsCtaIcon}>{icon}</Text>
            <View style={{ flex: 1 }}>
              <Text style={[s.toolsCtaTitle, { color: fg }]}>{title}</Text>
              <Text style={[s.toolsCtaSub, { color: '#9aa6c0' }]}>{sub}</Text>
            </View>
            <Text style={[s.toolsCtaArrow, { color: fg }]}>→</Text>
          </TouchableOpacity>
        ))}

        {/* 🚦 One-tap release checklist: sweep every mounted system × all 14 gates. */}
        <TouchableOpacity testID="snow-run-all-14" activeOpacity={0.9} onPress={runAll14} disabled={gates14Busy}
          style={[s.toolsCta, { backgroundColor: '#0f2433', borderColor: '#2f6e8a', marginTop: 10 }, gates14Busy && { opacity: 0.6 }]}>
          {gates14Busy ? <ActivityIndicator color="#93C5FD" /> : <Text style={s.toolsCtaIcon}>🚦</Text>}
          <View style={{ flex: 1 }}>
            <Text style={[s.toolsCtaTitle, { color: '#93C5FD' }]}>Run All 14 Gates</Text>
            <Text style={[s.toolsCtaSub, { color: '#9aa6c0' }]}>
              {gates14Busy ? 'Sweeping every mounted system…'
                : gates14?.error ? `⚠️ ${gates14.error}`
                : gates14 ? `${gates14.passed}/${gates14.ran} passed · ${gates14.systems} systems × ${gates14.gate_count} gates`
                : 'Strict AAA release checklist — every system × 14 gates (>97)'}
            </Text>
          </View>
          <Text style={[s.toolsCtaArrow, { color: '#93C5FD' }]}>→</Text>
        </TouchableOpacity>
        {gates14 && !gates14.error && gates14.passed < gates14.ran && (
          <Text style={{ color: '#f4a35d', fontSize: 11, fontWeight: '800', marginTop: 6 }}>
            ⛔ {gates14.ran - gates14.passed} gate{gates14.ran - gates14.passed === 1 ? '' : 's'} below 97 — clear these before Build.
          </Text>
        )}

        {/* Systems coverage meter — which systems are mounted & gate-passed before build. */}
        <CoverageMeter key={coverageKey} build={gameId} />
        {flow && (
          <View style={s.modeCard}>
            <View style={s.modeHeadRow}>
              <Text style={s.modeTitle}>⚙️ Build mode</Text>
              <Text style={s.modeVault}>🔌 Vault {flow.vault_coverage_pct ?? 100}%</Text>
            </View>
            <View style={s.modeRow}>
              {[['manual', '✋', 'Manual'], ['auto', '⚡', 'Auto'], ['agentic', '🤵', 'Jeeves']].map(([id, icon, label]) => {
                const on = flow.exec_mode === id;
                return (
                  <TouchableOpacity key={id} testID={`mode-${id}`} disabled={modeBusy}
                    onPress={() => setExecMode(id)} activeOpacity={0.85}
                    style={[s.modeBtn, on && s.modeBtnOn]}>
                    <Text style={s.modeIcon}>{icon}</Text>
                    <Text style={[s.modeLabel, on && s.modeLabelOn]}>{label}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
            {!!flow.mode_meta?.desc && <Text style={s.modeDesc}>{flow.mode_meta.desc}</Text>}
            {flow.exec_mode !== 'manual' && (
              <TouchableOpacity testID="snow-run-all" onPress={onRunAll} disabled={runAllBusy}
                style={[s.runAllBtn, runAllBusy && s.btnOff]} activeOpacity={0.9}>
                {runAllBusy
                  ? <><ActivityIndicator color="#fff" size="small" /><Text style={s.runAllTxt}>  Building… {flow.exec_mode === 'agentic' ? '🤵 narrating' : ''}</Text></>
                  : <Text style={s.runAllTxt}>{flow.exec_mode === 'agentic' ? '🤵 Run all — Jeeves narrates' : '⚡ Run all stages'}</Text>}
              </TouchableOpacity>
            )}
            {warroom.length > 0 && (
              <View style={s.warroom}>
                <Text style={s.warroomTitle}>🗣️ War-room</Text>
                {warroom.map((m, i) => (
                  <Text key={i} style={s.warroomLine}>
                    <Text style={s.warroomAgent}>{m.agent || 'Agent'}: </Text>
                    {String(m.text || '').slice(0, 160)}
                  </Text>
                ))}
              </View>
            )}
          </View>
        )}

        {/* 🏆 Build wins — readiness + next-best-action */}
        {wins?.readiness && (
          <View style={s.winsCard}>
            <View style={s.winsTop}>
              <View style={s.winsScoreBox}>
                <Text style={s.winsScore}>{wins.readiness.readiness}</Text>
                <Text style={s.winsScoreLbl}>readiness</Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={s.winsTier}>{(wins.readiness.tier || 'early').toUpperCase()}</Text>
                <Text style={s.winsMeta}>Build {wins.readiness.build_pct}% · Locked {wins.readiness.lock_pct}% · Audit {wins.readiness.audit}</Text>
              </View>
            </View>
            {wins?.nba?.label && (
              <TouchableOpacity testID="snow-nba" onPress={onNextAction} disabled={nbaBusy} style={s.nbaRow} activeOpacity={0.85}>
                {nbaBusy
                  ? <ActivityIndicator color="#BFDBFE" size="small" />
                  : <Text style={s.nbaLabel}>👉 {wins.nba.label}  ›</Text>}
              </TouchableOpacity>
            )}
          </View>
        )}

        {/* growing GDD */}
        <TouchableOpacity testID="snow-gdd-toggle" onPress={() => setGddOpen(o => !o)} style={s.gddHead} activeOpacity={0.85}>
          <Text style={s.gddTitle}>📜 Growing GDD <Text style={s.gddChars}>· {snow.gdd_chars} chars</Text></Text>
          <Text style={s.gddChev}>{gddOpen ? '▾' : '▸'}</Text>
        </TouchableOpacity>
        {gddOpen && (
          <View style={s.gddBox}>
            <Text testID="snow-gdd-text" style={s.gddText} selectable>{snow.gdd}</Text>
          </View>
        )}

        {/* manual ladder */}
        <Text style={s.ladderTitle}>Build ladder</Text>
        {(snow.steps || []).map((st: any) => {
          const isMode = st.key === 'mode';
          const stStatus = status[st.key];
          return (
            <View key={st.key} testID={`snow-step-${st.key}`}
              style={[s.step, st.is_next && s.stepNext, st.locked && s.stepLocked, st.stale && s.stepStale]}>
              <View style={s.stepHead}>
                <Text style={s.stepIcon}>{st.stale ? '⚠️' : st.locked ? '🔒' : st.done ? '✅' : st.is_next ? '👉' : st.icon}</Text>
                <View style={{ flex: 1 }}>
                  <Text style={s.stepLabel}>{st.label}</Text>
                  <Text style={s.stepSummary} numberOfLines={1}>{st.summary}</Text>
                  {!!st.provenance && <Text style={s.prov}>by {st.provenance.agent}{st.provenance.model ? ` · ${st.provenance.model}` : ''}</Text>}
                  {!!st.quality && <Text style={{ color: st.quality.score >= 95 ? '#4ade80' : '#fbbf24', fontSize: 10, fontWeight: '800', marginTop: 2 }}>💎 quality {st.quality.score}/100{st.quality.score >= 95 ? ' ✓ exquisite' : ' (regenerating to ≥95)'}</Text>}
                </View>
                <Text style={[s.stepTag, st.stale ? s.tagStale : st.locked ? s.tagLocked : st.done ? s.tagDone : st.is_next ? s.tagNext : s.tagTodo]}>
                  {st.stale ? '⚠️ STALE' : st.locked ? 'LOCKED' : st.done ? 'BUILT' : st.is_next ? 'NEXT' : 'PENDING'}
                </Text>
              </View>

              {!!stStatus && <Text style={s.stepStatus}>{stStatus}</Text>}

              {/* refine input */}
              {refineKey === st.key && (
                <View style={{ marginTop: 8 }}>
                  <TextInput testID={`snow-refine-input-${st.key}`} value={refineDraft} onChangeText={setRefineDraft}
                    placeholder="Describe a tweak (e.g. add a boss, make it harder)…" placeholderTextColor="#475569"
                    style={s.refineInput} multiline />
                  <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
                    <TouchableOpacity testID={`snow-refine-submit-${st.key}`} onPress={() => refineStage(st.key)}
                      disabled={!!running || !refineDraft.trim()} style={[s.btn, s.btnRefine, (!!running || !refineDraft.trim()) && s.btnOff]} activeOpacity={0.9}>
                      {running === st.key ? <ActivityIndicator size="small" color="#fff" /> : <Text style={s.btnTxt}>💬 Refine</Text>}
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => { setRefineKey(null); setRefineDraft(''); }} style={[s.btn, s.btnCancel]} activeOpacity={0.9}>
                      <Text style={s.btnCancelTxt}>Cancel</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              )}

              {/* actions */}
              {!isMode && refineKey !== st.key && (
                <View style={s.actions}>
                  {st.is_next && (
                    <TouchableOpacity testID={`snow-run-${st.key}`} onPress={() => runStage(st.key)} disabled={!!running}
                      style={[s.btn, s.btnRun, !!running && s.btnOff]} activeOpacity={0.9}>
                      {running === st.key ? <ActivityIndicator size="small" color="#fff" /> : <Text style={s.btnTxt}>▶ Run this stage</Text>}
                    </TouchableOpacity>
                  )}
                  {!st.done && st.skippable && (
                    <TouchableOpacity testID={`snow-skip-${st.key}`} onPress={() => skipStage(st.key, !!st.skipped)} disabled={!!running}
                      style={[s.btn, s.btnGhost]} activeOpacity={0.85}>
                      <Text style={s.btnGhostTxt}>{st.skipped ? '↩ Un-skip' : '⏭ Skip'}</Text>
                    </TouchableOpacity>
                  )}
                  {st.done && (
                    <>
                      <TouchableOpacity testID={`snow-rerun-${st.key}`} onPress={() => runStage(st.key)} disabled={!!running}
                        style={[s.btn, s.btnGhost, !!running && s.btnOff]} activeOpacity={0.85}>
                        <Text style={s.btnGhostTxt}>↻ Re-run</Text>
                      </TouchableOpacity>
                      <TouchableOpacity testID={`snow-refine-${st.key}`} onPress={() => { setRefineKey(st.key); setRefineDraft(''); }} disabled={!!running}
                        style={[s.btn, s.btnGhost]} activeOpacity={0.85}>
                        <Text style={s.btnGhostTxt}>💬 Refine</Text>
                      </TouchableOpacity>
                      <TouchableOpacity testID={`snow-lock-${st.key}`} onPress={() => lockStage(st.key, st.locked)} disabled={locking === st.key}
                        style={[s.btn, st.locked ? s.btnUnlock : s.btnLock]} activeOpacity={0.85}>
                        {locking === st.key ? <ActivityIndicator size="small" color="#fff" /> : (
                          <Text style={st.locked ? s.btnUnlockTxt : s.btnTxt}>{st.locked ? '🔓 Unlock' : '🔒 Lock'}</Text>
                        )}
                      </TouchableOpacity>
                    </>
                  )}
                </View>
              )}
            </View>
          );
        })}
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
  meter: { backgroundColor: '#0b1220', borderRadius: 14, borderWidth: 1, borderColor: '#1e293b', padding: 16 },
  phasesCard: { backgroundColor: '#0a1020', borderRadius: 14, borderWidth: 1, borderColor: '#243a5e', padding: 16, marginBottom: 14 },
  phasesHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  phasesTitle: { color: '#cfe9ff', fontSize: 16, fontWeight: '800', flex: 1 },
  phasesPct: { color: '#93C5FD', fontSize: 12, fontWeight: '800' },
  phasesChev: { color: '#93C5FD', fontSize: 14, fontWeight: '800', width: 16, textAlign: 'right' },
  eraChip: { borderWidth: 1, borderColor: '#243a5e', backgroundColor: '#0b1628', borderRadius: 9, paddingHorizontal: 10, paddingVertical: 6, alignItems: 'center', minWidth: 64 },
  eraChipOn: { backgroundColor: '#1d4ed8', borderColor: '#3b82f6' },
  eraChipTxt: { color: '#9fb6d4', fontSize: 11, fontWeight: '800' },
  eraChipTxtOn: { color: '#eaf2ff' },
  eraChipNum: { color: '#6f86a8', fontSize: 10, fontWeight: '700', marginTop: 2 },
  filePlanRow: { flexDirection: 'row', alignItems: 'baseline' },
  filePlanBig: { color: '#60A5FA', fontSize: 24, fontWeight: '900' },
  filePlanMuted: { color: '#94A3B8', fontSize: 12 },
  filePlanSub: { color: '#cbd5e1', fontSize: 12, fontWeight: '600', marginTop: 8 },
  bandRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6, borderTopWidth: 1, borderTopColor: '#13233c' },
  bandDot: { fontSize: 14, width: 16, textAlign: 'center' },
  bandName: { color: '#e2e8f0', fontSize: 12, fontWeight: '700' },
  bandPhase: { color: '#64748b', fontSize: 11, fontWeight: '600' },
  bandDetail: { color: '#7c8aa3', fontSize: 11, marginTop: 1 },
  bandFiles: { color: '#93C5FD', fontSize: 12, fontWeight: '800' },
  bandWarn: { color: '#fbbf24', fontSize: 11, fontWeight: '700', marginTop: 8 },
  meterTitle: { color: '#F8FAFC', fontSize: 16, fontWeight: '800' },
  meterSub: { color: '#93C5FD', fontSize: 12, fontWeight: '700', marginTop: 3 },
  barTrack: { height: 8, backgroundColor: '#1e293b', borderRadius: 4, marginTop: 10, overflow: 'hidden' },
  barFill: { height: 8, backgroundColor: '#60A5FA', borderRadius: 4 },
  meterNext: { color: '#94A3B8', fontSize: 12, marginTop: 8 },
  meterNextBold: { color: '#E2E8F0', fontWeight: '800' },
  meterStale: { color: '#fbbf24', fontSize: 12, marginTop: 8, fontWeight: '700' },
  meterBtns: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 },
  mBtn: { borderRadius: 9, paddingVertical: 9, paddingHorizontal: 12, alignItems: 'center', justifyContent: 'center', minHeight: 38, flexGrow: 1 },
  mBtnRoll: { backgroundColor: '#60A5FA' },
  mBtnLock: { backgroundColor: '#16A34A' },
  mBtnExport: { borderWidth: 1, borderColor: '#475569', backgroundColor: 'transparent' },
  mBtnTxt: { color: '#fff', fontSize: 12, fontWeight: '800' },
  mBtnExportTxt: { color: '#cbd5e1', fontSize: 12, fontWeight: '800' },
  prov: { color: '#475569', fontSize: 10, marginTop: 2, fontStyle: 'italic' },
  stepStale: { borderColor: '#f59e0b', backgroundColor: '#231a05' },
  tagStale: { color: '#fbbf24', backgroundColor: '#2a210a' },
  gddHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 16, backgroundColor: '#0a1528', borderRadius: 10, borderWidth: 1, borderColor: '#1e3a5f', paddingVertical: 12, paddingHorizontal: 14 },
  modeCard: { marginTop: 14, backgroundColor: '#0a1528', borderRadius: 12, borderWidth: 1, borderColor: '#1e3a5f', padding: 12 },
  toolsCta: { marginTop: 14, flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#10231c', borderRadius: 12, borderWidth: 1, borderColor: '#1f5a44', padding: 14 },
  bayTitle: { color: '#cfe9ff', fontSize: 14, fontWeight: '900', marginTop: 18, marginBottom: 10 },
  shipCta: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#3B82F6', borderRadius: 14, padding: 16, marginTop: 16,
    ...(Platform.OS === 'web'
      // @ts-ignore — web-only style key
      ? { boxShadow: '0px 4px 12px rgba(59,130,246,0.4)' }
      : { shadowColor: '#3B82F6', shadowOpacity: 0.4, shadowRadius: 12, shadowOffset: { width: 0, height: 4 }, elevation: 8 }) },
  shipIcon: { fontSize: 28 },
  shipTitle: { color: '#021019', fontSize: 17, fontWeight: '900' },
  shipSub: { color: '#063a47', fontSize: 11, fontWeight: '700', marginTop: 2 },
  shipArrow: { color: '#021019', fontSize: 24, fontWeight: '900' },
  bayGrid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between' },
  bayCard: { width: '48%', borderRadius: 12, borderWidth: 1, padding: 12, marginBottom: 10, minHeight: 96 },
  bayIcon: { fontSize: 24, marginBottom: 6 },
  bayCardTitle: { fontSize: 13, fontWeight: '900' },
  bayCardSub: { color: '#8a96b2', fontSize: 11, marginTop: 3, lineHeight: 15 },
  toolsCtaIcon: { fontSize: 26 },
  toolsCtaTitle: { color: '#d6ffe9', fontSize: 15, fontWeight: '900' },
  toolsCtaSub: { color: '#82b8a0', fontSize: 11, fontWeight: '600', marginTop: 2 },
  toolsCtaArrow: { color: '#43d39e', fontSize: 22, fontWeight: '900' },
  modeHeadRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 },
  modeTitle: { color: '#93C5FD', fontSize: 14, fontWeight: '800' },
  modeVault: { color: '#34d399', fontSize: 12, fontWeight: '700' },
  modeRow: { flexDirection: 'row', gap: 8 },
  modeBtn: { flex: 1, alignItems: 'center', backgroundColor: '#0b1220', borderRadius: 10, borderWidth: 2, borderColor: '#1e293b', paddingVertical: 10 },
  modeBtnOn: { borderColor: '#60A5FA', backgroundColor: '#0c2438' },
  modeIcon: { fontSize: 20, marginBottom: 3 },
  modeLabel: { color: '#94a3b8', fontSize: 12, fontWeight: '700' },
  modeLabelOn: { color: '#93C5FD' },
  modeDesc: { color: '#94a3b8', fontSize: 11, lineHeight: 16, marginTop: 10 },
  runAllBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', backgroundColor: '#2563eb', borderRadius: 10, paddingVertical: 12, marginTop: 12 },
  runAllTxt: { color: '#fff', fontSize: 14, fontWeight: '800' },
  warroom: { marginTop: 12, backgroundColor: '#070b16', borderRadius: 10, borderWidth: 1, borderColor: '#1e293b', padding: 10 },
  warroomTitle: { color: '#93C5FD', fontSize: 12, fontWeight: '800', marginBottom: 6 },
  warroomLine: { color: '#cbd5e1', fontSize: 11, lineHeight: 16, marginBottom: 3 },
  warroomAgent: { color: '#a78bfa', fontWeight: '800' },
  winsCard: { marginTop: 14, backgroundColor: '#0a1528', borderRadius: 12, borderWidth: 1, borderColor: '#1e3a5f', padding: 12 },
  winsTop: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  winsScoreBox: { width: 64, height: 64, borderRadius: 32, borderWidth: 3, borderColor: '#60A5FA', alignItems: 'center', justifyContent: 'center' },
  winsScore: { color: '#93C5FD', fontSize: 22, fontWeight: '900' },
  winsScoreLbl: { color: '#64748b', fontSize: 8, fontWeight: '700', textTransform: 'uppercase' },
  winsTier: { color: '#34d399', fontSize: 15, fontWeight: '900', letterSpacing: 0.6 },
  winsMeta: { color: '#94a3b8', fontSize: 11, marginTop: 4 },
  nbaRow: { marginTop: 10, backgroundColor: '#0c2438', borderRadius: 8, padding: 10 },
  nbaLabel: { color: '#BFDBFE', fontSize: 12, fontWeight: '700' },
  gddTitle: { color: '#93C5FD', fontSize: 14, fontWeight: '800' },
  gddChars: { color: '#475569', fontSize: 12, fontWeight: '600' },
  gddChev: { color: '#93C5FD', fontSize: 16 },
  gddBox: { backgroundColor: '#070b16', borderRadius: 10, borderWidth: 1, borderColor: '#1e293b', borderTopWidth: 0, padding: 14, marginTop: -2 },
  gddText: { color: '#cbd5e1', fontSize: 12, lineHeight: 19, fontFamily: 'monospace' },
  ladderTitle: { color: '#94A3B8', fontSize: 13, fontWeight: '800', marginTop: 20, marginBottom: 8 },
  step: { backgroundColor: '#0b1220', borderRadius: 12, borderWidth: 1, borderColor: '#1e293b', padding: 14, marginBottom: 10 },
  stepNext: { borderColor: '#60A5FA', backgroundColor: '#0d1b2e' },
  stepLocked: { borderColor: '#16A34A', opacity: 0.95 },
  stepHead: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  stepIcon: { fontSize: 22 },
  stepLabel: { color: '#E2E8F0', fontSize: 15, fontWeight: '800' },
  stepSummary: { color: '#64748b', fontSize: 12, marginTop: 2 },
  stepTag: { fontSize: 10, fontWeight: '900', paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, overflow: 'hidden' },
  tagLocked: { color: '#4ade80', backgroundColor: '#0d2818' },
  tagDone: { color: '#93C5FD', backgroundColor: '#0a1f30' },
  tagNext: { color: '#fbbf24', backgroundColor: '#2a210a' },
  tagTodo: { color: '#64748b', backgroundColor: '#0f1626' },
  stepStatus: { color: '#cbd5e1', fontSize: 12, marginTop: 8 },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 },
  btn: { borderRadius: 9, paddingVertical: 10, paddingHorizontal: 14, alignItems: 'center', justifyContent: 'center', minHeight: 40 },
  btnTxt: { color: '#fff', fontSize: 13, fontWeight: '800' },
  btnRun: { backgroundColor: '#60A5FA', flexGrow: 1 },
  btnRefine: { backgroundColor: '#6366f1', flexGrow: 1 },
  btnGhost: { borderWidth: 1, borderColor: '#334155', backgroundColor: 'transparent' },
  btnGhostTxt: { color: '#94A3B8', fontSize: 13, fontWeight: '700' },
  btnLock: { backgroundColor: '#16A34A' },
  btnUnlock: { borderWidth: 1, borderColor: '#16A34A', backgroundColor: 'transparent' },
  btnUnlockTxt: { color: '#4ade80', fontSize: 13, fontWeight: '700' },
  btnCancel: { borderWidth: 1, borderColor: '#334155', backgroundColor: 'transparent' },
  btnCancelTxt: { color: '#94A3B8', fontSize: 13, fontWeight: '700' },
  btnOff: { opacity: 0.5 },
  refineInput: { backgroundColor: '#070b16', borderRadius: 8, borderWidth: 1, borderColor: '#27324A', color: '#E2E8F0', fontSize: 13, padding: 10, minHeight: 60, textAlignVertical: 'top' },
});
