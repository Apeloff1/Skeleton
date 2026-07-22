// Item Foundry — every agent forges a full item (skin + code + placement) folded into gamefiles.
import { useState, useCallback, useEffect, useMemo } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator, TextInput, Linking } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { apiFetch } from '../utils/apiController';
import SnowballSpine, { SpineStage } from '../src/components/SnowballSpine';
import { lazyDefault, LazyMount } from '../src/utils/lazyMount';
const Construct3DView = lazyDefault(() => import('../src/components/Construct3DView'));
const GalaxyStudioFactoryModal = lazyDefault(() => import('../features/GalaxyStudioFactory/GalaxyStudioFactoryModal'));

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const T = { bg: '#0A0A0A', card: '#141414', border: '#1F2937', accent: '#7C9CFF', accent2: '#A78BFA',
  good: '#34D399', warn: '#FBBF24', text: '#E5E7EB', dim: '#94A3B8', muted: '#64748B' };

export default function ItemFoundryScreen() {
  const router = useRouter();
  const sp = useLocalSearchParams<{ build?: string; game?: string }>();
  const [buildId, setBuildId] = useState(String(sp?.build || sp?.game || 'demo_build'));
  const [genre, setGenre] = useState('rpg');
  const [busy, setBusy] = useState(false);
  const [man, setMan] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [mounting, setMounting] = useState(false);
  const [mount, setMount] = useState<any | null>(null);
  const [showGdd, setShowGdd] = useState(false);
  const [stageFilter, setStageFilter] = useState<string | null>(null);
  const [escalating, setEscalating] = useState(false);
  const [esc, setEsc] = useState<any | null>(null);
  const [eras, setEras] = useState<any[]>([]);
  const [era, setEra] = useState<string>('modern');
  const [ladder, setLadder] = useState<any | null>(null);
  const [comparing, setComparing] = useState(false);
  const [gates, setGates] = useState<any | null>(null);
  const [quiz, setQuiz] = useState<any | null>(null);
  const [advBusy, setAdvBusy] = useState(false);
  const [fin, setFin] = useState<any | null>(null);
  const [finBusy, setFinBusy] = useState(false);
  const [gstyle, setGstyle] = useState<string>('cel_shaded');
  const [dim, setDim] = useState<string>('3d');
  const [uniAssets, setUniAssets] = useState<any[]>([]);
  const [uniPreview, setUniPreview] = useState<any | null>(null);
  const [showStudio, setShowStudio] = useState(false);
  const advConfig = useMemo(() => ({ graphic_style: gstyle, dimension: dim, texture_resolution: 70, model_poly_count: 60 }), [gstyle, dim]);

  const runAdvanced = useCallback(async () => {
    setAdvBusy(true); setErr(null); setGates(null); setQuiz(null);
    try {
      const body = JSON.stringify({ build_id: buildId || 'demo_build', genre, era, seed: 1, persist: true, config: advConfig });
      const [gr, qr] = await Promise.all([
        apiFetch(`${API_URL}/api/galaxy-studio/vault-gdd/phase-gates`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, timeoutMs: 45000 }),
        apiFetch(`${API_URL}/api/galaxy-studio/vault-gdd/questionnaire`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, timeoutMs: 45000 }),
      ]);
      if (gr.ok) setGates(await gr.json());
      if (qr.ok) setQuiz(await qr.json());
    } catch (e: any) { setErr(e?.message || 'Advanced gates failed'); } finally { setAdvBusy(false); }
  }, [buildId, genre, era, advConfig]);

  const runFinalBuild = useCallback(async () => {
    setFinBusy(true); setErr(null); setFin(null);
    try {
      const r = await apiFetch(`${API_URL}/api/galaxy-studio/final-build/package`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ build_id: buildId || 'demo_build', genre, era, seed: 1, persist: true, config: advConfig }),
        timeoutMs: 60000,
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setFin(await r.json());
    } catch (e: any) { setErr(e?.message || 'Final build failed'); } finally { setFinBusy(false); }
  }, [buildId, genre, era, advConfig]);


  const compareEras = useCallback(async () => {
    setComparing(true); setErr(null);
    try {
      const r = await apiFetch(`${API_URL}/api/galaxy-studio/vault-gdd/era-ladder/${encodeURIComponent(buildId || 'demo_build')}?era_a=8bit&era_b=${era}&genre=${encodeURIComponent(genre)}&seed=1`, { timeoutMs: 45000 });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setLadder(await r.json());
    } catch (e: any) { setErr(e?.message || 'Compare failed'); } finally { setComparing(false); }
  }, [buildId, era, genre]);

  useEffect(() => {
    (async () => {
      try {
        const r = await apiFetch(`${API_URL}/api/galaxy-studio/eras`, { timeoutMs: 12000 });
        if (r.ok) { const d = await r.json(); setEras(d.eras || []); setEra(d.default || 'modern'); }
      } catch { /* non-blocking */ }
    })();
  }, []);

  const eraSpec = eras.find((e) => e.key === era) || null;

  const forge = useCallback(async () => {
    setBusy(true); setErr(null); setMount(null);
    try {
      const r = await apiFetch(`${API_URL}/api/galaxy-studio/items/forge-build`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ build_id: buildId || 'demo_build', genre, era, seed: 1, platoon_size: 4, persist: true }),
        timeoutMs: 30000,
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setMan(await r.json());
    } catch (e: any) { setErr(e?.message || 'Forge failed'); } finally { setBusy(false); }
  }, [buildId, genre, era]);

  const generateGdd = useCallback(async () => {
    setMounting(true); setErr(null);
    try {
      const r = await apiFetch(`${API_URL}/api/galaxy-studio/vault-gdd/mount`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ build_id: buildId || 'demo_build', seed: 1, forge_if_empty: true, persist: true }),
        timeoutMs: 30000,
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setMount(data); setShowGdd(true);
    } catch (e: any) { setErr(e?.message || 'GDD mount failed'); } finally { setMounting(false); }
  }, [buildId]);

  const t = man?.totals;
  const stages: string[] = (man?.stages || []).map((s: any) => s.stage);

  const escalate = useCallback(async () => {
    setEscalating(true); setErr(null);
    try {
      const r = await apiFetch(`${API_URL}/api/galaxy-studio/vault-gdd/escalate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ build_id: buildId || 'demo_build', genre, era, seed: 1, platoon_size: 4, persist: true, config: advConfig }),
        timeoutMs: 45000,
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setEsc(await r.json());
    } catch (e: any) { setErr(e?.message || 'Escalation failed'); } finally { setEscalating(false); }
  }, [buildId, genre, era, advConfig]);

  const downloadZip = useCallback(() => {
    Linking.openURL(`${API_URL}/api/galaxy-studio/vault-gdd/${encodeURIComponent(buildId || 'demo_build')}/gamefiles.zip`);
  }, [buildId]);

  // ── Gamified snowball spine ──
  const spineStages = useMemo<SpineStage[]>(() => {
    const raw = [
      { key: 'forge', title: 'Forge Items', desc: 'Every agent forges a full item (skin + code + placement) → gamefiles.', icon: 'hammer', xp: 120, done: !!man, busy, cta: 'Forge all agents' },
      { key: 'gdd', title: 'GDD & Mount', desc: 'Generate the Game Design Doc and mount items into the Vault.', icon: 'document-text', xp: 140, done: !!mount, busy: mounting, cta: 'Generate & mount' },
      { key: 'escalate', title: 'Escalate Snowball', desc: 'Quality-gated escalation — grade floor rises every level.', icon: 'trending-up', xp: 200, done: !!esc, busy: escalating, cta: 'Escalate' },
      { key: 'assets', title: 'Forge World Assets', desc: 'Mint themed characters/flora/props the phases & world build from.', icon: 'planet', xp: 160, done: uniAssets.length > 0, busy: false, cta: 'Forge assets' },
      { key: 'gates', title: '100-Phase Gates', desc: 'Runs AFTER assets — the 100 phases factor in your forged assets.', icon: 'shield-checkmark', xp: 220, done: !!(gates && quiz), busy: advBusy, cta: 'Run gates' },
      { key: 'final', title: 'Final Build & Ship', desc: '7-stage build — the world is assembled from ALL combined gamefiles.', icon: 'rocket', xp: 300, done: !!fin, busy: finBusy, cta: 'Build & ship' },
    ];
    let activeAssigned = false;
    return raw.map((s) => {
      let status: SpineStage['status'];
      if (s.done) status = 'done';
      else if (!activeAssigned) { status = 'active'; activeAssigned = true; }
      else status = 'locked';
      return { key: s.key, title: s.title, desc: s.desc, icon: s.icon as any, xp: s.xp, status, busy: s.busy, cta: s.cta };
    });
  }, [man, mount, esc, gates, quiz, fin, busy, mounting, escalating, advBusy, finBusy, uniAssets.length]);

  // ── Surface auto-seeded universal assets (characters/flora/props) ──
  const loadUni = useCallback(async (doSeed: boolean) => {
    const bid = buildId || 'demo_build';
    try {
      if (doSeed) {
        const sr = await apiFetch(`${API_URL}/api/galaxy-studio/forge/seed`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ build_id: bid, era, genre, seed: 1, mount: true }),
          timeoutMs: 60000,
        });
        if (sr.ok) setUniPreview(await sr.json());
      }
      const r = await apiFetch(`${API_URL}/api/galaxy-studio/forge/list?build_id=${encodeURIComponent(bid)}&limit=60`, { timeoutMs: 20000 });
      if (r.ok) { const d = await r.json(); setUniAssets(d.items || []); }
    } catch { /* non-blocking */ }
  }, [buildId, era, genre]);

  const runStage = useCallback((key: string) => {
    if (key === 'forge') forge();
    else if (key === 'gdd') generateGdd();
    else if (key === 'escalate') escalate();
    else if (key === 'assets') loadUni(true);
    else if (key === 'gates') runAdvanced();
    else if (key === 'final') runFinalBuild();
  }, [forge, generateGdd, escalate, runAdvanced, runFinalBuild, loadUni]);

  // Auto-seed + load themed assets right after the Forge Items stage completes.
  useEffect(() => { if (man) loadUni(true); }, [man]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.icon} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
          <Ionicons name="chevron-back" size={24} color={T.text} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>Item Foundry</Text>
          <Text style={styles.sub}>Every agent forges a full item → gamefiles + Vault</Text>
        </View>
      </View>
      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 48 }}>
        <Text style={styles.lbl}>Build ID</Text>
        <TextInput value={buildId} onChangeText={setBuildId} style={styles.input} placeholder="build id" placeholderTextColor={T.muted} />
        <Text style={styles.lbl}>Genre</Text>
        <TextInput value={genre} onChangeText={setGenre} style={styles.input} placeholder="rpg" placeholderTextColor={T.muted} />

        <Text style={styles.lbl}>Era (sets the technical envelope)</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingVertical: 4 }}>
          {eras.map((e) => (
            <TouchableOpacity key={e.key} onPress={() => setEra(e.key)} style={[styles.eraChip, era === e.key && styles.eraChipOn]} activeOpacity={0.85}>
              <Text style={[styles.eraChipTxt, era === e.key && styles.eraChipTxtOn]}>{e.label}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
        {eraSpec && (
          <View style={styles.eraSpec}>
            <Text style={styles.eraSpecTag}>{eraSpec.tagline}</Text>
            <View style={styles.eraSpecGrid}>
              <Text style={styles.eraSpecKv}>💾 {eraSpec.storage_label}</Text>
              <Text style={styles.eraSpecKv}>🎨 {eraSpec.color_label}</Text>
              <Text style={styles.eraSpecKv}>🖥 {eraSpec.resolution}</Text>
              <Text style={styles.eraSpecKv}>📐 {eraSpec.poly_label}</Text>
              <Text style={styles.eraSpecKv}>🔊 {eraSpec.audio_format}</Text>
              <Text style={styles.eraSpecKv}>📦 {eraSpec.asset_types?.length} asset types</Text>
            </View>
            <Text style={styles.eraCap}>⚡ Asset capacity {Number(eraSpec.asset_capacity).toLocaleString()} — outshines this era by +{eraSpec.outshine_pct}%</Text>
          </View>
        )}
        <Text style={styles.lbl}>Advanced choices (gated every step)</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingVertical: 4 }}>
          {['cel_shaded', 'photoreal', 'pixel_16bit', 'voxel', 'painterly', 'noir_bw'].map((g) => (
            <TouchableOpacity key={g} onPress={() => setGstyle(g)} style={[styles.fChip, gstyle === g && styles.fChipOn]}>
              <Text style={[styles.fChipTxt, gstyle === g && styles.fChipTxtOn]}>{g.replace('_', ' ')}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
        <View style={{ flexDirection: 'row', gap: 8, marginTop: 6 }}>
          {['2d', '3d'].map((d) => (
            <TouchableOpacity key={d} onPress={() => setDim(d)} style={[styles.fChip, dim === d && styles.fChipOn]}>
              <Text style={[styles.fChipTxt, dim === d && styles.fChipTxtOn]}>{d.toUpperCase()}{d === '2d' ? ' (no meshes)' : ''}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <SnowballSpine stages={spineStages} onRun={runStage} sceneTimeline={esc?.universal_scenes || uniPreview?.scenes} />

        <TouchableOpacity style={styles.studioBtn} onPress={() => setShowStudio(true)} activeOpacity={0.85} testID="if-open-studio">
          <Ionicons name="construct" size={18} color="#0A0A0A" />
          <Text style={styles.studioTxt}>🎛 Open Full Studio — deep build canvas</Text>
        </TouchableOpacity>

        {uniAssets.length > 0 && (
          <View style={styles.uniCard} testID="if-uni-assets">
            <View style={styles.mountHead}>
              <Ionicons name="planet" size={16} color={T.good} />
              <Text style={styles.mountTitle}>Themed assets in this build · {uniAssets.length}</Text>
              <TouchableOpacity onPress={() => loadUni(false)} testID="if-uni-refresh"><Ionicons name="refresh" size={16} color={T.accent} /></TouchableOpacity>
            </View>
            {uniPreview?.families?.length ? (
              <Text style={styles.mountMeta}>Auto-forged families: {uniPreview.families.join(' · ')}</Text>
            ) : null}
            {uniPreview && (
              <View style={styles.uniPreviewWrap}>
                <LazyMount><Construct3DView geometry={(uniPreview && uniAssets[0]?.geometry) || []} palette={uniAssets[0]?.palette || []} height={180} /></LazyMount>
              </View>
            )}
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingVertical: 4 }}>
              {uniAssets.slice(0, 24).map((a) => (
                <View key={a.construct_id} style={styles.uniChip} testID={`if-uni-${a.construct_id}`}>
                  <View style={styles.uniPal}>
                    {(a.palette || []).slice(0, 4).map((c: string, i: number) => (<View key={i} style={{ flex: 1, backgroundColor: c }} />))}
                  </View>
                  <Text style={styles.uniName} numberOfLines={1}>{a.name}</Text>
                  <Text style={styles.uniFam} numberOfLines={1}>{a.family || a.kind}</Text>
                </View>
              ))}
            </ScrollView>
          </View>
        )}

        <TouchableOpacity style={[styles.btn2, comparing && { opacity: 0.6 }]} onPress={compareEras} disabled={comparing} activeOpacity={0.85}>
          {comparing ? <ActivityIndicator color={T.accent} size="small" /> : <Ionicons name="git-compare" size={18} color={T.accent} />}
          <Text style={[styles.btn2Txt, { color: T.accent }]}>{comparing ? 'Comparing eras…' : `🎯 Side quest · Era ladder: 8-Bit vs ${eraSpec?.label || era}`}</Text>
        </TouchableOpacity>

        {fin && (
          <View style={[styles.ladderCard, { borderColor: fin.can_ship ? '#0B5138' : '#7F1D1D' }]}>
            <Text style={styles.ladderHead}>
              {fin.can_ship ? '✅ READY TO DOWNLOAD' : '❌ BLOCKED'} · {fin.gates_passed}/7 gates · score {fin.overall_score} (bar {fin.production_threshold})
            </Text>
            <Text style={styles.mountMeta}>{fin.totals.gamefiles} gamefiles · {fin.totals.assets} assets · {fin.totals.cooked_size} cooked · {fin.totals.retries} retries</Text>
            <View style={styles.gateWrap}>
              {fin.stages.map((s: any) => (
                <View key={s.step} style={[styles.gateChip, { borderColor: s.gate.passed ? '#0B5138' : '#7F1D1D' }]}>
                  <Ionicons name={s.gate.passed ? 'checkmark' : 'close'} size={11} color={s.gate.passed ? T.good : '#F87171'} />
                  <Text style={styles.gateTxt}>{s.step}.{s.stage.split(' ')[0]} {s.gate.score}</Text>
                </View>
              ))}
            </View>
            {fin.can_ship && fin.downloads.map((dl: any) => (
              <TouchableOpacity key={dl.platform} onPress={() => Linking.openURL(dl.url)} style={styles.quizRow} activeOpacity={0.8}>
                <Ionicons name="download" size={13} color={T.accent} />
                <Text style={[styles.quizTxt, { color: T.accent }]}>{dl.platform} · {dl.size}</Text>
              </TouchableOpacity>
            ))}
            {fin.can_ship && fin.playable?.playable && (
              <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
                <TouchableOpacity style={[styles.btn3, { flex: 1, marginTop: 0 }]} onPress={() => Linking.openURL(`${API_URL}${fin.playable.play_url}`)} activeOpacity={0.85}>
                  <Ionicons name="play" size={16} color="#0A0A0A" />
                  <Text style={styles.btn3Txt}>Play game</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[styles.btn2, { flex: 1, marginTop: 0 }]} onPress={() => Linking.openURL(`${API_URL}${fin.playable.download_url}`)} activeOpacity={0.85}>
                  <Ionicons name="download" size={16} color={T.accent2} />
                  <Text style={styles.btn2Txt}>Download game.zip</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>
        )}

        {gates && (
          <View style={styles.ladderCard}>
            <Text style={styles.ladderHead}>⚙ Advanced mode · {gates.phases_passed}/{gates.phases_total} phases green · {gates.bands_passed}/{gates.bands_total} bands</Text>
            <View style={styles.budgetBg}><View style={[styles.budgetFill, { width: `${gates.pass_pct}%`, backgroundColor: gates.all_gates_green ? T.good : T.warn }]} /></View>
            <View style={[styles.escBadge, { backgroundColor: gates.asset_grounded ? '#0B2E22' : '#3A1212', marginTop: 8 }]} testID="if-gates-assets">
              <Text style={[styles.escBadgeTxt, { color: gates.asset_grounded ? T.good : '#F87171' }]}>
                {gates.asset_grounded ? `🪐 Asset-grounded · ${gates.forged_assets} forged assets build the world` : '⚠ No forged assets — build from assets first'}
              </Text>
            </View>
            {gates.forged_families?.length ? (
              <Text style={styles.itemPlace}>Families in build: {gates.forged_families.join(' · ')}</Text>
            ) : null}
            <View style={styles.gateWrap}>
              {gates.bands.map((b: any) => (
                <View key={b.band} style={[styles.gateChip, { borderColor: b.passed ? '#0B5138' : '#7F1D1D' }]}>
                  <Ionicons name={b.passed ? 'checkmark' : 'close'} size={11} color={b.passed ? T.good : '#F87171'} />
                  <Text style={styles.gateTxt}>{b.band}</Text>
                </View>
              ))}
            </View>
          </View>
        )}

        {quiz && (
          <View style={styles.ladderCard}>
            <Text style={styles.ladderHead}>📋 Snowball questionnaire · conformance {quiz.conformance_pct}% ({quiz.passed}/{quiz.total})</Text>
            {quiz.items.slice(0, 8).map((it: any) => (
              <View key={it.id} style={styles.quizRow}>
                <Ionicons name={it.passed ? 'checkmark-circle' : 'alert-circle'} size={13} color={it.passed ? T.good : '#F87171'} />
                <Text style={styles.quizTxt} numberOfLines={2}>{it.question}</Text>
              </View>
            ))}
          </View>
        )}

        {ladder && (
          <View style={styles.ladderCard}>
            <Text style={styles.ladderHead}>{ladder.headline}</Text>
            <View style={styles.ladderCols}>
              <View style={styles.ladderCol}>
                <Text style={styles.ladderEra}>{ladder.a.era_label}</Text>
                <Text style={styles.ladderKv}>{ladder.a.assets} assets</Text>
                <Text style={styles.ladderKv}>{ladder.a.storage_used}</Text>
                <Text style={styles.ladderKv}>cap {Number(ladder.a.asset_capacity).toLocaleString()}</Text>
              </View>
              <Text style={styles.ladderArrow}>→</Text>
              <View style={styles.ladderCol}>
                <Text style={[styles.ladderEra, { color: T.accent2 }]}>{ladder.b.era_label}</Text>
                <Text style={styles.ladderKv}>{ladder.b.assets} assets</Text>
                <Text style={styles.ladderKv}>{ladder.b.storage_used}</Text>
                <Text style={styles.ladderKv}>cap {Number(ladder.b.asset_capacity).toLocaleString()}</Text>
              </View>
            </View>
            <Text style={styles.ladderGrow}>📦 {ladder.asset_multiplier}× assets · 💾 {ladder.storage_multiplier.toLocaleString()}× storage · ⚡ +{ladder.capacity_growth_pct.toLocaleString()}% capacity</Text>
          </View>
        )}

        {esc && (
          <View style={styles.escCard}>
            <View style={styles.mountHead}>
              <Ionicons name="layers" size={16} color={T.good} />
              <Text style={styles.mountTitle} numberOfLines={1}>{esc.title}</Text>
              <View style={[styles.covPill, { backgroundColor: esc.parity_locked ? '#0B2E22' : '#3A1212' }]}>
                <Text style={[styles.covTxt, { color: esc.parity_locked ? T.good : '#F87171' }]}>parity {esc.parity_pct}%</Text>
              </View>
            </View>
            <Text style={styles.mountMeta}>
              {esc.totals.gamefiles} gamefiles · {esc.totals.assets} assets ({esc.totals.assets_per_item}×) · grade {esc.totals.min_grade}→{esc.totals.max_grade} · QA {Math.round(esc.totals.quality_pass_rate * 100)}% · {esc.gdd_sections} GDD sections
            </Text>
            <View style={styles.escBadges}>
              <View style={[styles.escBadge, { backgroundColor: '#1E1633' }]}><Text style={[styles.escBadgeTxt, { color: T.accent2 }]}>🕹 {esc.era_label}</Text></View>
              {esc.grade_escalating && <View style={styles.escBadge}><Text style={styles.escBadgeTxt}>📈 grade escalating</Text></View>}
              {esc.parity_locked && <View style={styles.escBadge}><Text style={styles.escBadgeTxt}>🔒 GDD parity locked</Text></View>}
            </View>
            {esc.storage && (
              <View style={{ marginTop: 10 }}>
                <Text style={styles.eraSpecKv}>💾 Storage {esc.storage.used_label} / {esc.storage.cap_label} ({esc.storage.used_pct}%){!esc.storage.within_budget ? '  ⚠ over era budget' : ''}</Text>
                <View style={styles.budgetBg}>
                  <View style={[styles.budgetFill, { width: `${Math.min(100, esc.storage.used_pct)}%`, backgroundColor: esc.storage.within_budget ? T.good : T.warn }]} />
                </View>
              </View>
            )}
            {esc.balance_curve && (
              <View style={styles.curveRow}>
                {esc.balance_curve.map((c: any) => (
                  <View key={c.level} style={styles.curveCol}>
                    <View style={[styles.curveBar, { height: 6 + c.max_grade * 9 }]} />
                    <View style={[styles.curveFloor, { height: 6 + c.grade_floor * 9 }]} />
                    <Text style={styles.curveLbl}>L{c.level}</Text>
                  </View>
                ))}
              </View>
            )}
            {esc.ladder.map((r: any) => (
              <View key={r.stage} style={styles.ladderRow}>
                <View style={styles.lvPill}><Text style={styles.lvTxt}>Lv{r.level}</Text></View>
                <Text style={styles.ladderStage}>{r.stage}</Text>
                <Text style={styles.ladderMeta} numberOfLines={1}>floor G{r.grade_floor}→max G{r.max_grade} · {r.accepted}/{r.forged} pass · {r.assets} assets</Text>
                <Ionicons name={r.parity_ok ? 'checkmark-circle' : 'close-circle'} size={14} color={r.parity_ok ? T.good : '#F87171'} />
              </View>
            ))}
            <TouchableOpacity onPress={downloadZip} style={styles.zipBtn} activeOpacity={0.85}>
              <Ionicons name="download" size={16} color={T.accent} />
              <Text style={styles.zipTxt}>Download gamefiles.zip (code + GDD + assets)</Text>
            </TouchableOpacity>
          </View>
        )}

        {mount && (
          <View style={styles.mountCard}>
            <View style={styles.mountHead}>
              <Ionicons name="cube" size={16} color={T.accent2} />
              <Text style={styles.mountTitle} numberOfLines={1}>{mount.title} · mounted</Text>
              <View style={styles.covPill}><Text style={styles.covTxt}>{mount.coverage_pct}%</Text></View>
            </View>
            <Text style={styles.mountMeta}>
              {mount.vault_gamefiles} gamefiles · {mount.stages_covered}/{mount.stages_total} stages · grade ⌀{mount.stats?.avg_grade} · {mount.gdd_chars} chars
            </Text>
            {/* grade histogram */}
            <View style={styles.histRow}>
              {(mount.stats?.grade_histogram || []).map((g: any) => (
                <View key={g.grade} style={styles.histCol}>
                  <View style={[styles.histBar, { height: 8 + g.count * 10 }]} />
                  <Text style={styles.histLbl}>G{g.grade}</Text>
                  <Text style={styles.histCnt}>{g.count}</Text>
                </View>
              ))}
            </View>
            <View style={styles.archWrap}>
              {(mount.stats?.archetypes || []).slice(0, 6).map((a: any) => (
                <View key={a.name} style={styles.archChip}><Text style={styles.archTxt}>{a.name} ·{a.count}</Text></View>
              ))}
            </View>
            <TouchableOpacity onPress={() => setShowGdd((v) => !v)} style={styles.gddToggle} activeOpacity={0.8}>
              <Ionicons name={showGdd ? 'chevron-up' : 'chevron-down'} size={16} color={T.accent} />
              <Text style={styles.gddToggleTxt}>{showGdd ? 'Hide GDD' : 'View GDD'}</Text>
            </TouchableOpacity>
            {showGdd && (
              <ScrollView style={styles.gddBox} nestedScrollEnabled>
                <Text style={styles.gddText}>{mount.gdd}</Text>
              </ScrollView>
            )}
          </View>
        )}

        {esc && esc.choice_gates && esc.choice_gates.choices_gated > 0 && (
          <View style={styles.escBadges}>
            <View style={[styles.escBadge, { backgroundColor: esc.choice_gates.all_reflected ? '#0B2E22' : '#3A1212' }]}>
              <Text style={[styles.escBadgeTxt, { color: esc.choice_gates.all_reflected ? T.good : '#F87171' }]}>🎛 {esc.choice_gates.choices_gated} choices reflected every step · {esc.choice_gates.conformance_pct}%</Text>
            </View>
          </View>
        )}

        {err && <Text style={styles.err}>{err}</Text>}

        {t && (
          <View style={[styles.banner, { borderColor: t.grade_above_base ? '#065F46' : '#7F1D1D' }]}>
            <Ionicons name={t.grade_above_base ? 'shield-checkmark' : 'alert-circle'} size={16} color={t.grade_above_base ? T.good : '#F87171'} />
            <Text style={styles.bannerTxt}>
              {t.accepted}/{t.items_forged} items · grade ⌀{t.avg_grade} (&gt; base) · fidelity ⌀{t.avg_fidelity} · {t.distinct_archetypes} archetypes
            </Text>
          </View>
        )}

        {man?.stages && man.stages.length > 0 && (
          <View style={styles.filterRow}>
            <TouchableOpacity onPress={() => setStageFilter(null)} style={[styles.fChip, !stageFilter && styles.fChipOn]}>
              <Text style={[styles.fChipTxt, !stageFilter && styles.fChipTxtOn]}>All</Text>
            </TouchableOpacity>
            {stages.map((s) => (
              <TouchableOpacity key={s} onPress={() => setStageFilter(s)} style={[styles.fChip, stageFilter === s && styles.fChipOn]}>
                <Text style={[styles.fChipTxt, stageFilter === s && styles.fChipTxtOn]}>{s}</Text>
              </TouchableOpacity>
            ))}
          </View>
        )}

        {man?.stages?.filter((s: any) => !stageFilter || s.stage === stageFilter).map((s: any) => (
          <View key={s.stage} style={{ marginTop: 14 }}>
            <Text style={styles.stageHead}>{s.stage.toUpperCase()} · {s.agent_count} agents</Text>
            {s.items.map((it: any) => (
              <View key={it.item_id} style={styles.itemCard}>
                <View style={styles.itemTop}>
                  <View style={styles.swatchRow}>
                    {it.skin.palette.map((c: string, i: number) => (
                      <View key={i} style={[styles.swatch, { backgroundColor: c }]} />
                    ))}
                  </View>
                  <View style={[styles.gradePill, { borderColor: T.accent2 }]}>
                    <Text style={styles.gradeTxt}>{it.definition.tier} · G{it.grade}</Text>
                  </View>
                </View>
                <Text style={styles.itemName}>{it.name}</Text>
                <Text style={styles.itemMeta} numberOfLines={2}>
                  {it.definition.archetype} · {it.skin.material} · {it.skin.silhouette} · {it.skin.vfx}
                </Text>
                <Text style={styles.itemPlace}>📍 {it.placement.region} ({it.placement.spawn_rule}) · by {it.agent_code} · fid {it.skin.fidelity}</Text>
              </View>
            ))}
          </View>
        ))}
      </ScrollView>
      {showStudio && <LazyMount><GalaxyStudioFactoryModal visible={showStudio} onClose={() => setShowStudio(false)} /></LazyMount>}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: T.bg },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 10, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: T.border },
  icon: { padding: 6, minWidth: 36, minHeight: 36, alignItems: 'center', justifyContent: 'center' },
  title: { color: T.text, fontSize: 18, fontWeight: '800' },
  sub: { color: T.muted, fontSize: 11, marginTop: 1 },
  lbl: { color: T.dim, fontSize: 12, fontWeight: '700', marginTop: 10, marginBottom: 4, textTransform: 'uppercase' },
  input: { backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 10, color: T.text, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14 },
  btn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: T.accent, borderRadius: 12, paddingVertical: 13, marginTop: 16 },
  btnTxt: { color: '#0A0A0A', fontWeight: '900', fontSize: 14 },
  eraChip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, backgroundColor: T.card, borderWidth: 1, borderColor: T.border },
  eraChipOn: { backgroundColor: T.accent2, borderColor: T.accent2 },
  eraChipTxt: { color: T.dim, fontSize: 12, fontWeight: '800' },
  eraChipTxtOn: { color: '#0A0A0A' },
  eraSpec: { backgroundColor: T.card, borderRadius: 12, borderWidth: 1, borderColor: '#2A2440', padding: 12, marginTop: 8 },
  eraSpecTag: { color: T.accent2, fontSize: 12, fontWeight: '700', fontStyle: 'italic', marginBottom: 8 },
  eraSpecGrid: { gap: 4 },
  eraSpecKv: { color: T.dim, fontSize: 11, fontWeight: '600' },
  eraCap: { color: T.good, fontSize: 11, fontWeight: '800', marginTop: 8 },
  ladderCard: { backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: '#1E3A5F', padding: 12, marginTop: 10 },
  ladderHead: { color: T.text, fontSize: 12, fontWeight: '800' },
  ladderCols: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-around', marginTop: 10 },
  ladderCol: { alignItems: 'center', gap: 2 },
  ladderEra: { color: T.accent, fontSize: 12, fontWeight: '900', marginBottom: 4 },
  ladderKv: { color: T.dim, fontSize: 10 },
  ladderArrow: { color: T.muted, fontSize: 18, fontWeight: '900' },
  ladderGrow: { color: T.accent2, fontSize: 11, fontWeight: '800', marginTop: 10, textAlign: 'center' },
  gateWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 10 },
  gateChip: { flexDirection: 'row', alignItems: 'center', gap: 3, borderWidth: 1, borderRadius: 8, paddingHorizontal: 7, paddingVertical: 3, backgroundColor: '#0F172A' },
  gateTxt: { color: T.dim, fontSize: 10, fontWeight: '700' },
  quizRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 6, marginTop: 7 },
  quizTxt: { color: T.dim, fontSize: 11, flex: 1, lineHeight: 15 },
  budgetBg: { height: 8, borderRadius: 4, backgroundColor: '#0F172A', overflow: 'hidden', marginTop: 6 },
  budgetFill: { height: 8, borderRadius: 4 },
  curveRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 8, marginTop: 12, minHeight: 62, paddingHorizontal: 2 },
  curveCol: { flex: 1, alignItems: 'center', justifyContent: 'flex-end', position: 'relative' },
  curveBar: { width: 14, backgroundColor: T.accent2, borderRadius: 3 },
  curveFloor: { width: 14, backgroundColor: T.accent, borderRadius: 3, position: 'absolute', bottom: 14, opacity: 0.5 },
  curveLbl: { color: T.muted, fontSize: 9, marginTop: 4 },
  btn2: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: T.card, borderWidth: 1, borderColor: T.accent2, borderRadius: 12, paddingVertical: 12, marginTop: 10 },
  btn2Txt: { color: T.accent2, fontWeight: '800', fontSize: 13 },
  btn3: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: T.good, borderRadius: 12, paddingVertical: 12, marginTop: 10 },
  btn3Txt: { color: '#0A0A0A', fontWeight: '900', fontSize: 13 },
  escCard: { backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: '#0B5138', padding: 12, marginTop: 12 },
  escBadges: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 8 },
  escBadge: { backgroundColor: '#0B2E22', borderRadius: 8, paddingHorizontal: 8, paddingVertical: 4 },
  escBadgeTxt: { color: T.good, fontSize: 10, fontWeight: '800' },
  ladderRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8 },
  lvPill: { backgroundColor: '#0F172A', borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 },
  lvTxt: { color: T.accent, fontSize: 10, fontWeight: '900' },
  ladderStage: { color: T.text, fontSize: 12, fontWeight: '800', width: 72 },
  ladderMeta: { color: T.dim, fontSize: 10, flex: 1 },
  zipBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, marginTop: 12, paddingVertical: 10, borderRadius: 10, borderWidth: 1, borderColor: T.accent, backgroundColor: '#0B0B0B' },
  zipTxt: { color: T.accent, fontSize: 12, fontWeight: '800' },
  mountCard: { backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: '#3B2A6B', padding: 12, marginTop: 12 },
  mountHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  mountTitle: { color: T.text, fontSize: 13, fontWeight: '800', flex: 1 },
  covPill: { backgroundColor: '#1E1633', borderRadius: 999, paddingHorizontal: 10, paddingVertical: 3 },
  covTxt: { color: T.accent2, fontSize: 11, fontWeight: '900' },
  mountMeta: { color: T.dim, fontSize: 11, marginTop: 6 },
  histRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 10, marginTop: 12, minHeight: 64, paddingHorizontal: 4 },
  histCol: { alignItems: 'center', justifyContent: 'flex-end' },
  histBar: { width: 18, backgroundColor: T.accent, borderRadius: 4 },
  histLbl: { color: T.dim, fontSize: 10, marginTop: 4, fontWeight: '700' },
  histCnt: { color: T.muted, fontSize: 9 },
  archWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 10 },
  archChip: { backgroundColor: '#0F172A', borderWidth: 1, borderColor: T.border, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 4 },
  archTxt: { color: T.accent, fontSize: 10, fontWeight: '700' },
  gddToggle: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 12, alignSelf: 'flex-start' },
  gddToggleTxt: { color: T.accent, fontSize: 12, fontWeight: '800' },
  gddBox: { maxHeight: 260, backgroundColor: '#0B0B0B', borderRadius: 10, borderWidth: 1, borderColor: T.border, padding: 10, marginTop: 8 },
  gddText: { color: T.dim, fontSize: 11, fontFamily: 'monospace', lineHeight: 16 },
  filterRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 16 },
  fChip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, backgroundColor: T.card, borderWidth: 1, borderColor: T.border },
  fChipOn: { backgroundColor: T.accent2, borderColor: T.accent2 },
  fChipTxt: { color: T.dim, fontSize: 11, fontWeight: '700' },
  fChipTxtOn: { color: '#0A0A0A' },
  err: { color: '#FCA5A5', marginTop: 12, fontSize: 13 },
  banner: { flexDirection: 'row', alignItems: 'center', gap: 8, padding: 12, borderRadius: 12, borderWidth: 1, backgroundColor: T.card, marginTop: 14 },
  bannerTxt: { color: T.text, fontSize: 12, fontWeight: '700', flex: 1 },
  stageHead: { color: T.accent, fontSize: 13, fontWeight: '900', letterSpacing: 0.5, marginBottom: 8 },
  itemCard: { backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border, padding: 12, marginBottom: 8 },
  itemTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 },
  swatchRow: { flexDirection: 'row', gap: 4 },
  swatch: { width: 22, height: 22, borderRadius: 5, borderWidth: 1, borderColor: '#00000040' },
  gradePill: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 3 },
  gradeTxt: { color: T.accent2, fontSize: 11, fontWeight: '800' },
  itemName: { color: T.text, fontSize: 15, fontWeight: '800' },
  itemMeta: { color: T.dim, fontSize: 11, marginTop: 3 },
  itemPlace: { color: T.muted, fontSize: 11, marginTop: 5 },
  studioBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: T.accent2, borderRadius: 12, paddingVertical: 12, marginTop: 10 },
  studioTxt: { color: '#0A0A0A', fontWeight: '900', fontSize: 13 },
  uniCard: { backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: '#0B5138', padding: 12, marginTop: 12 },
  uniPreviewWrap: { borderRadius: 12, overflow: 'hidden', marginTop: 10, marginBottom: 4 },
  uniChip: { width: 96, backgroundColor: '#0B0B0B', borderRadius: 10, borderWidth: 1, borderColor: T.border, overflow: 'hidden', paddingBottom: 6 },
  uniPal: { flexDirection: 'row', height: 36 },
  uniName: { color: T.text, fontSize: 10, fontWeight: '700', paddingHorizontal: 6, marginTop: 5 },
  uniFam: { color: T.good, fontSize: 9, fontWeight: '700', paddingHorizontal: 6, textTransform: 'capitalize' },
});
