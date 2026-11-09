/**
 * Gamefile Command Center (⌘K-style)
 * --------------------------------------------------------------------------
 * A SOTA command-palette interface over the 10 TEXT → GAMEFILE systems.
 *  • Type a command (quest, item, enemy, lore…) → compose authoritative text →
 *    Execute → a structured GAMEFILE is forged (deterministic, optional Claude
 *    AAA enrich).
 *  • Every forged gamefile can be pushed through the SAME 14-gate AAA engine
 *    (>97 bar) right from its card, with a live score gauge + gate ladder.
 *
 * Backend:
 *   GET  /api/galaxy-studio/text-gamefile/generators
 *   POST /api/galaxy-studio/text-gamefile/{key}/generate
 *   GET  /api/galaxy-studio/text-gamefile/{build_id}/list
 *   POST /api/galaxy-studio/gates/target/{build_id}/{gid}/run-all
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator,
  TextInput, Modal, Switch, KeyboardAvoidingView, Platform, SectionList,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { apiFetch } from '../utils/apiController';

const API = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const STORE_KEY = 'cc_active_build_id';

const C = {
  bg: '#070b14', card: '#101728', alt: '#161f33', deep: '#0b111e',
  border: '#26314c', text: '#eef2fb', muted: '#8593b3',
  accent: '#7c9cff', accent2: '#a78bfa', good: '#43d39e', warn: '#fbbf24',
  bad: '#ff6b6b', chip: '#1c2640',
};

type Gen = { key: string; label: string; icon: string; type: string; fields: string[]; group: string; advanced: boolean; tiers: string[] };
type Gamefile = {
  id: string; system: string; label: string; type: string; icon: string;
  fields: Record<string, any>; brief?: string; llm_enriched?: boolean;
};

function newBuildId(): string {
  return 'cc-' + Math.floor(Date.now()).toString(36) + Math.floor(Math.random() * 1296).toString(36);
}

export default function CommandCenter() {
  const router = useRouter();
  const params = useLocalSearchParams<{ build?: string }>();

  const [buildId, setBuildId] = useState<string>('');
  const [editingBuild, setEditingBuild] = useState(false);
  const [generators, setGenerators] = useState<Gen[]>([]);
  const [outputs, setOutputs] = useState<Gamefile[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  // palette / composer modal
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [recent, setRecent] = useState<string[]>([]);
  const [activeCmd, setActiveCmd] = useState<Gen | null>(null);
  const [composeText, setComposeText] = useState('');
  const [enrich, setEnrich] = useState(false);
  const [tier, setTier] = useState<string | null>(null);
  const [executing, setExecuting] = useState(false);

  // gate runs (per gamefile id)
  const [pipe, setPipe] = useState<Record<string, any>>({});
  const [piping, setPiping] = useState<Record<string, boolean>>({});
  const [autoMint, setAutoMint] = useState<Record<string, boolean>>({});
  const [history, setHistory] = useState<Record<string, any>>({});
  const [historyOpenId, setHistoryOpenId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  // ── CHURN 2.0 ──
  const [churnModels, setChurnModels] = useState<{ id: string; provider: string; band: string; tier: string }[]>([]);
  const [churnModel, setChurnModel] = useState<string | null>(null); // null = deterministic
  const [modelPickerFor, setModelPickerFor] = useState<string | null>(null);
  const [churn, setChurn] = useState<Record<string, any>>({});       // gid → churn run
  const [churning, setChurning] = useState<Record<string, boolean>>({});
  const [applying, setApplying] = useState<string | null>(null);     // variant_id in flight
  const [daemon, setDaemon] = useState<{ enabled: boolean; interval_s?: number; churned?: number } | null>(null);

  // ── boot: resolve build id + load generators ──────────────────────────
  useEffect(() => {
    (async () => {
      let bid = (params.build as string) || '';
      if (!bid) bid = (await AsyncStorage.getItem(STORE_KEY)) || '';
      if (!bid) bid = newBuildId();
      setBuildId(bid);
      await AsyncStorage.setItem(STORE_KEY, bid);
      try {
        const [adv, rec] = await Promise.all([
          AsyncStorage.getItem('cc_show_advanced'),
          AsyncStorage.getItem('cc_recent'),
        ]);
        if (adv === '1') setShowAdvanced(true);
        if (rec) { try { setRecent(JSON.parse(rec)); } catch { /* ignore */ } }
      } catch { /* ignore */ }
      try {
        const r = await apiFetch(`${API}/api/galaxy-studio/text-gamefile/generators`, { timeoutMs: 12000 });
        const d = await r.json();
        setGenerators(Array.isArray(d.generators) ? d.generators : []);
      } catch { setGenerators([]); }
    })();
  }, [params.build]);

  // ── CHURN 2.0: load model catalog + daemon status ──
  useEffect(() => {
    (async () => {
      try {
        const r = await apiFetch(`${API}/api/churn/models`, { timeoutMs: 12000 });
        const d = await r.json();
        if (Array.isArray(d.models)) setChurnModels(d.models);
      } catch { /* ignore */ }
      try {
        const r = await apiFetch(`${API}/api/churn/daemon/status`, { timeoutMs: 10000 });
        setDaemon(await r.json());
      } catch { /* ignore */ }
    })();
  }, []);

  const loadList = useCallback(async (bid: string) => {
    if (!bid) return;
    setLoadingList(true);
    try {
      const r = await apiFetch(`${API}/api/galaxy-studio/text-gamefile/${encodeURIComponent(bid)}/list`, { timeoutMs: 12000 });
      const d = await r.json();
      setOutputs(Array.isArray(d.gamefiles) ? d.gamefiles : []);
    } catch { /* keep current */ } finally { setLoadingList(false); }
  }, []);

  useEffect(() => { if (buildId) loadList(buildId); }, [buildId, loadList]);

  const saveBuild = useCallback(async (bid: string) => {
    const v = bid.trim() || newBuildId();
    setBuildId(v); setEditingBuild(false);
    await AsyncStorage.setItem(STORE_KEY, v);
  }, []);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await loadList(buildId);
    setRefreshing(false);
  }, [buildId, loadList]);

  const toggleAdvanced = useCallback(async (v: boolean) => {
    setShowAdvanced(v);
    await AsyncStorage.setItem('cc_show_advanced', v ? '1' : '0');
  }, []);

  // pool respects the advanced toggle (advanced commands hidden unless on)
  const pool = useMemo(
    () => generators.filter((g) => showAdvanced || !g.advanced),
    [generators, showAdvanced],
  );

  const sections = useMemo(() => {
    const q = query.trim().toLowerCase();
    const match = (g: Gen) =>
      g.label.toLowerCase().includes(q) ||
      g.type.toLowerCase().includes(q) ||
      g.group.toLowerCase().includes(q) ||
      g.fields.some((f) => f.toLowerCase().includes(q));
    if (q) {
      const data = pool.filter(match);
      return [{ title: `Results · ${data.length}`, data }];
    }
    const out: { title: string; data: Gen[] }[] = [];
    const byKey = new Map(pool.map((g) => [g.key, g]));
    const recentGens = recent.map((k) => byKey.get(k)).filter(Boolean) as Gen[];
    if (recentGens.length) out.push({ title: '🕘 Recently used', data: recentGens.slice(0, 5) });
    const groups: Record<string, Gen[]> = {};
    for (const g of pool) (groups[g.group] = groups[g.group] || []).push(g);
    for (const name of Object.keys(groups)) out.push({ title: name, data: groups[name] });
    return out;
  }, [pool, query, recent]);

  const openCommand = (g: Gen) => {
    setActiveCmd(g); setComposeText(''); setEnrich(false); setTier(null);
    setRecent((prev) => {
      const next = [g.key, ...prev.filter((k) => k !== g.key)].slice(0, 8);
      AsyncStorage.setItem('cc_recent', JSON.stringify(next)).catch(() => {});
      return next;
    });
  };

  const execute = async () => {
    if (!activeCmd || !composeText.trim() || executing) return;
    setExecuting(true);
    try {
      const r = await apiFetch(`${API}/api/galaxy-studio/text-gamefile/${activeCmd.key}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ build_id: buildId, text: composeText.trim(), enrich, tier }),
        timeoutMs: enrich ? 90000 : 20000,
      });
      const gf = await r.json();
      if (gf && gf.id) {
        setOutputs((prev) => [gf, ...prev.filter((p) => p.id !== gf.id)]);
        setPaletteOpen(false); setActiveCmd(null); setComposeText(''); setQuery('');
      }
    } catch { /* swallow — surfaced by empty state */ } finally { setExecuting(false); }
  };

  const closePalette = () => { setPaletteOpen(false); setActiveCmd(null); setComposeText(''); setQuery(''); };

  const runPipeline = async (gf: Gamefile) => {
    if (piping[gf.id]) return;
    setPiping((p) => ({ ...p, [gf.id]: true }));
    try {
      const r = await apiFetch(`${API}/api/galaxy-studio/gamefile-pipeline/${encodeURIComponent(buildId)}/${encodeURIComponent(gf.id)}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ persist: true, auto_mint_enhancer: !!autoMint[gf.id] }),
        timeoutMs: 30000,
      });
      const res = await r.json();
      if (res && res.stages) {
        setPipe((p) => ({ ...p, [gf.id]: res }));
        loadList(buildId);   // surface the companion gamefiles the pipeline minted
      }
    } catch { /* ignore */ } finally { setPiping((p) => ({ ...p, [gf.id]: false })); }
  };

  const openHistory = async (gf: Gamefile) => {
    setHistoryOpenId(gf.id);
    try {
      const r = await apiFetch(`${API}/api/galaxy-studio/gamefile-pipeline/${encodeURIComponent(buildId)}/${encodeURIComponent(gf.id)}/history`, { timeoutMs: 12000 });
      const d = await r.json();
      setHistory((p) => ({ ...p, [gf.id]: d }));
    } catch { /* ignore */ }
  };

  // ── CHURN 2.0 actions ──
  const pollChurnJob = async (jobId: string, gid: string) => {
    for (let i = 0; i < 40; i++) {
      await new Promise((res) => setTimeout(res, 1200));
      try {
        const r = await apiFetch(`${API}/api/churn/job/${jobId}`, { timeoutMs: 12000 });
        const d = await r.json();
        if (d.status === 'done' && d.result) {
          setChurn((p) => ({ ...p, [gid]: d.result }));
          return;
        }
        if (d.status === 'error') return;
      } catch { /* keep polling */ }
    }
  };

  const runChurn = async (gf: Gamefile) => {
    if (churning[gf.id]) return;
    setChurning((p) => ({ ...p, [gf.id]: true }));
    try {
      const r = await apiFetch(`${API}/api/churn/${encodeURIComponent(buildId)}/run/async`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ gid: gf.id, model: churnModel }), timeoutMs: 20000,
      });
      const d = await r.json();
      if (d.job_id) await pollChurnJob(d.job_id, gf.id);
    } catch { /* ignore */ } finally { setChurning((p) => ({ ...p, [gf.id]: false })); }
  };

  const applyVariant = async (gf: Gamefile, runId: string, variantId: string) => {
    if (applying) return;
    setApplying(variantId);
    try {
      const r = await apiFetch(`${API}/api/churn/${encodeURIComponent(buildId)}/${encodeURIComponent(gf.id)}/apply`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_id: runId, variant_id: variantId }), timeoutMs: 20000,
      });
      const d = await r.json();
      if (d && d.applied) {
        setChurn((p) => {
          const cur = p[gf.id]; if (!cur) return p;
          const alts = (cur.alternatives || []).map((a: any) => ({ ...a, _applied: a.variant_id === variantId }));
          return { ...p, [gf.id]: { ...cur, alternatives: alts, _appliedVersion: d.churn_version } };
        });
        loadList(buildId);
      }
    } catch { /* ignore */ } finally { setApplying(null); }
  };

  const toggleDaemon = async () => {
    const next = !(daemon?.enabled);
    try {
      const r = await apiFetch(`${API}/api/churn/daemon/toggle`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: next, interval_s: 180 }), timeoutMs: 12000,
      });
      setDaemon(await r.json());
    } catch { /* ignore */ }
  };

  // ── render helpers ────────────────────────────────────────────────────
  const scoreColor = (s: number) => (s >= 97 ? C.good : s >= 90 ? C.warn : C.bad);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      {/* header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.iconBtn} testID="cc-back">
          <Ionicons name="chevron-back" size={22} color={C.text} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>⌘ Command Center</Text>
          <Text style={styles.sub}>Text → Gamefile · 14-Gate AAA forge</Text>
        </View>
        <TouchableOpacity onPress={toggleDaemon} style={styles.iconBtn} testID="cc-daemon-toggle">
          <Ionicons name={daemon?.enabled ? 'sync-circle' : 'sync-circle-outline'} size={20}
            color={daemon?.enabled ? C.good : C.muted} />
        </TouchableOpacity>
        <TouchableOpacity onPress={() => loadList(buildId)} style={styles.iconBtn} testID="cc-refresh">
          <Ionicons name="refresh" size={18} color={C.muted} />
        </TouchableOpacity>
      </View>

      {/* build context bar */}
      <View style={styles.buildBar}>
        <Ionicons name="git-branch" size={14} color={C.accent} />
        {editingBuild ? (
          <TextInput
            value={buildId} onChangeText={setBuildId} autoFocus
            onSubmitEditing={() => saveBuild(buildId)} onBlur={() => saveBuild(buildId)}
            placeholder="build id" placeholderTextColor={C.muted}
            style={styles.buildInput} testID="cc-build-input"
          />
        ) : (
          <TouchableOpacity style={{ flex: 1 }} onPress={() => setEditingBuild(true)} testID="cc-build-edit">
            <Text style={styles.buildId} numberOfLines={1}>{buildId || '—'}</Text>
          </TouchableOpacity>
        )}
        <TouchableOpacity onPress={() => saveBuild(newBuildId())} style={styles.newBuildBtn} testID="cc-new-build">
          <Ionicons name="add" size={14} color={C.text} />
          <Text style={styles.newBuildTxt}>New</Text>
        </TouchableOpacity>
      </View>

      {/* command trigger */}
      <TouchableOpacity style={styles.cmdTrigger} onPress={() => setPaletteOpen(true)} testID="cc-open-palette">
        <Ionicons name="search" size={16} color={C.accent2} />
        <Text style={styles.cmdTriggerTxt}>Run a command… {pool.length} systems</Text>
        <View style={styles.kbd}><Text style={styles.kbdTxt}>⌘K</Text></View>
      </TouchableOpacity>

      {/* outputs feed */}
      <ScrollView
        contentContainerStyle={{ padding: 14, paddingBottom: 100 }}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={C.accent} colors={[C.accent]} />
        }>
        <View style={styles.feedHead}>
          <Text style={styles.feedTitle}>Forged Gamefiles</Text>
          <View style={styles.countPill}><Text style={styles.countTxt}>{outputs.length}</Text></View>
        </View>

        {loadingList && outputs.length === 0 && (
          <View style={styles.center}><ActivityIndicator color={C.accent} /></View>
        )}

        {!loadingList && outputs.length === 0 && (
          <View style={styles.emptyWrap}>
            <Text style={styles.emptyIcon}>🎛</Text>
            <Text style={styles.empty}>No gamefiles forged yet.</Text>
            <Text style={styles.emptyHint}>Tap “Run a command” and describe a quest, item, enemy, level, ability and more — the engine forges a structured, gate-ready gamefile.</Text>
          </View>
        )}

        {outputs.map((gf) => {
          const open = !!expanded[gf.id];
          const fieldEntries = Object.entries(gf.fields || {});
          return (
            <View key={gf.id} style={styles.gfCard} testID={`cc-gf-${gf.id}`}>
              <TouchableOpacity style={styles.gfHead} onPress={() => setExpanded((p) => ({ ...p, [gf.id]: !open }))}>
                <Text style={styles.gfIcon}>{gf.icon || '📄'}</Text>
                <View style={{ flex: 1 }}>
                  <Text style={styles.gfLabel} numberOfLines={1}>{gf.label}</Text>
                  <Text style={styles.gfType}>{gf.type}{gf.llm_enriched ? '  ·  ✦ AAA enriched' : ''}</Text>
                </View>
                {pipe[gf.id] && (
                  <View style={[styles.scoreBadge, { borderColor: scoreColor(pipe[gf.id].overall_score) }]}>
                    <Text style={[styles.scoreBadgeTxt, { color: scoreColor(pipe[gf.id].overall_score) }]}>{pipe[gf.id].overall_score}</Text>
                  </View>
                )}
                <Ionicons name={open ? 'chevron-up' : 'chevron-down'} size={18} color={C.muted} />
              </TouchableOpacity>

              {open && (
                <View style={styles.gfBody}>
                  {fieldEntries.map(([k, v]) => (
                    <View key={k} style={styles.fieldRow}>
                      <Text style={styles.fieldKey}>{k}</Text>
                      <Text style={styles.fieldVal} numberOfLines={4}>
                        {Array.isArray(v) ? v.join('\n') : typeof v === 'object' && v ? JSON.stringify(v) : String(v)}
                      </Text>
                    </View>
                  ))}

                  {/* ── THE unified pipeline · 14 crosswired gates ── */}
                  <View style={styles.autoMintRow}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.autoMintTitle}>Auto-mint enhancer requests</Text>
                      <Text style={styles.autoMintSub}>Enhancer forges its contextual gamefiles in one pass</Text>
                    </View>
                    <Switch value={!!autoMint[gf.id]} onValueChange={(v) => setAutoMint((p) => ({ ...p, [gf.id]: v }))}
                      testID={`cc-automint-${gf.id}`} trackColor={{ true: C.accent2, false: C.border }} thumbColor="#fff" />
                  </View>

                  <TouchableOpacity
                    style={[styles.pipeBtn, piping[gf.id] && { opacity: 0.6 }]}
                    onPress={() => runPipeline(gf)} disabled={!!piping[gf.id]}
                    testID={`cc-pipe-${gf.id}`}>
                    {piping[gf.id]
                      ? <ActivityIndicator color="#fff" size="small" />
                      : <><Ionicons name="git-network" size={16} color="#fff" />
                          <Text style={styles.pipeBtnTxt}>Run Pipeline · 14 gates</Text></>}
                  </TouchableOpacity>

                  <TouchableOpacity style={styles.histBtn} onPress={() => openHistory(gf)} testID={`cc-history-${gf.id}`}>
                    <Ionicons name="time-outline" size={14} color={C.accent} />
                    <Text style={styles.histBtnTxt}>Pipeline history</Text>
                  </TouchableOpacity>

                  {/* ── CHURN 2.0 · deficit-driven exhaustive alternatives ── */}
                  <View style={styles.churnBox}>
                    <View style={styles.churnHeadRow}>
                      <Text style={styles.churnTitle}>♻️ Churn 2.0</Text>
                      <TouchableOpacity
                        onPress={() => setModelPickerFor(modelPickerFor === gf.id ? null : gf.id)}
                        style={styles.modelChip} testID={`cc-churn-model-${gf.id}`}>
                        <Ionicons name="hardware-chip-outline" size={12} color={C.accent2} />
                        <Text style={styles.modelChipTxt} numberOfLines={1}>
                          {churnModel || 'Deterministic (no LLM)'}
                        </Text>
                        <Ionicons name="chevron-down" size={12} color={C.muted} />
                      </TouchableOpacity>
                    </View>

                    {modelPickerFor === gf.id && (
                      <View style={styles.modelGrid}>
                        <TouchableOpacity
                          style={[styles.modelOpt, !churnModel && styles.modelOptOn]}
                          onPress={() => { setChurnModel(null); setModelPickerFor(null); }}
                          testID="cc-churn-model-deterministic">
                          <Text style={[styles.modelOptTxt, !churnModel && { color: C.text }]}>⚡ Deterministic · free</Text>
                        </TouchableOpacity>
                        {churnModels.map((m) => (
                          <TouchableOpacity
                            key={m.id}
                            style={[styles.modelOpt, churnModel === m.id && styles.modelOptOn]}
                            onPress={() => { setChurnModel(m.id); setModelPickerFor(null); }}
                            testID={`cc-churn-model-opt-${m.id}`}>
                            <Text style={[styles.modelOptTxt, churnModel === m.id && { color: C.text }]} numberOfLines={1}>
                              {m.band === 'free' ? '○' : '◆'} {m.id}
                            </Text>
                            <Text style={styles.modelOptMeta}>{m.provider} · {m.band}</Text>
                          </TouchableOpacity>
                        ))}
                      </View>
                    )}

                    <TouchableOpacity
                      style={[styles.churnBtn, churning[gf.id] && { opacity: 0.6 }]}
                      onPress={() => runChurn(gf)} disabled={!!churning[gf.id]}
                      testID={`cc-churn-${gf.id}`}>
                      {churning[gf.id]
                        ? <><ActivityIndicator color="#fff" size="small" /><Text style={styles.churnBtnTxt}>Churning…</Text></>
                        : <><Ionicons name="sync" size={15} color="#fff" /><Text style={styles.churnBtnTxt}>Run Churn · alternatives</Text></>}
                    </TouchableOpacity>

                    {churn[gf.id] && (
                      <View style={styles.churnResult}>
                        <Text style={styles.churnMeta}>
                          Deficit: <Text style={{ color: C.warn }}>{churn[gf.id].deficit}</Text> · {churn[gf.id].alternatives_count} alternatives · QC bar {churn[gf.id].qc_bar}
                          {churn[gf.id].all_clear_qc ? <Text style={{ color: C.good }}>  ✓ all clear</Text> : null}
                        </Text>
                        {(churn[gf.id].alternatives || []).map((a: any) => (
                          <View key={a.variant_id} style={[styles.altCard, a.recommended && { borderColor: C.good }]}>
                            <View style={styles.altHead}>
                              <Text style={styles.altLabel} numberOfLines={1}>
                                {a.recommended ? '★ ' : ''}{a.label}
                                {a.llm_enriched ? '  ✦' : ''}
                              </Text>
                              <View style={[styles.altScore, { borderColor: scoreColor(a.production_score) }]}>
                                <Text style={[styles.altScoreTxt, { color: scoreColor(a.production_score) }]}>{a.production_score}</Text>
                              </View>
                            </View>
                            <Text style={styles.altSummary}>{a.summary}</Text>
                            <Text style={styles.altPros}>✓ {(a.pros || []).join(' · ')}</Text>
                            <Text style={styles.altCons}>✗ {(a.cons || []).join(' · ')}</Text>
                            <TouchableOpacity
                              style={[styles.altApply, a._applied && { backgroundColor: C.good }]}
                              onPress={() => applyVariant(gf, churn[gf.id].run_id, a.variant_id)}
                              disabled={!!applying}
                              testID={`cc-apply-${gf.id}-${a.variant_id}`}>
                              {applying === a.variant_id
                                ? <ActivityIndicator color="#fff" size="small" />
                                : <Text style={styles.altApplyTxt}>{a._applied ? '✓ Applied · re-forged' : 'Apply + re-forge'}</Text>}
                            </TouchableOpacity>
                          </View>
                        ))}
                      </View>
                    )}
                  </View>


                  {pipe[gf.id] && (
                    <View style={styles.pipeReport}>
                      <View style={styles.gateSummary}>
                        <View style={[styles.gauge, { borderColor: scoreColor(pipe[gf.id].overall_score) }]}>
                          <Text style={[styles.gaugeScore, { color: scoreColor(pipe[gf.id].overall_score) }]}>{pipe[gf.id].overall_score}</Text>
                          <Text style={styles.gaugeOf}>/100</Text>
                        </View>
                        <View style={{ flex: 1, marginLeft: 12 }}>
                          <Text style={styles.gateVerdict}>
                            {pipe[gf.id].aaa_passed
                              ? <Text style={{ color: C.good }}>✓ AAA PASSED (&gt;97)</Text>
                              : <Text style={{ color: C.warn }}>{pipe[gf.id].passed}/{pipe[gf.id].gate_count} gates cleared</Text>}
                          </Text>
                          <Text style={styles.gateNote}>
                            AAA consensus {pipe[gf.id].aaa?.overall_score ?? '—'} · {pipe[gf.id].minted_count} companion(s) minted
                          </Text>
                        </View>
                      </View>

                      <View style={styles.pipeHeadRow}>
                        <View style={styles.pagePill}>
                          <Text style={styles.pageNum}>{Number(pipe[gf.id].pages || 0).toLocaleString()}</Text>
                          <Text style={styles.pageLbl}>pages</Text>
                        </View>
                        <Text style={styles.pipeVerdict}>
                          {pipe[gf.id].volume?.choices} choices × {pipe[gf.id].volume?.effective_pages_per_choice ?? pipe[gf.id].volume?.pages_per_choice}/choice
                          {(pipe[gf.id].volume?.tier_weight > 1) ? `  ·  tier ×${pipe[gf.id].volume?.tier_weight}` : ''}
                          {pipe[gf.id].auto_mint_enhancer ? '  ·  ✦ auto-mint on' : ''}
                        </Text>
                      </View>

                      {pipe[gf.id].stages.map((s) => (
                        <View key={s.key} style={styles.pipeStage}>
                          <Text style={styles.pipeStageIcon}>{s.icon}</Text>
                          <Text style={styles.pipeStageLbl}>{s.order}. {s.label}</Text>
                          <View style={[styles.pipeScore, { borderColor: s.passed ? C.good : C.bad }]}>
                            <Text style={[styles.pipeScoreTxt, { color: s.passed ? C.good : C.bad }]}>{s.score}</Text>
                          </View>
                          <Text style={styles.pipeStageNote} numberOfLines={1}>{s.report?.note || ''}</Text>
                        </View>
                      ))}
                    </View>
                  )}
                </View>
              )}
            </View>
          );
        })}
      </ScrollView>

      {/* command palette / composer modal */}
      <Modal visible={paletteOpen} animationType="slide" transparent onRequestClose={closePalette}>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.modalWrap}>
          <View style={styles.modalCard}>
            <View style={styles.modalGrip} />
            {!activeCmd ? (
              <>
                <View style={styles.paletteSearch}>
                  <Ionicons name="search" size={18} color={C.accent2} />
                  <TextInput
                    value={query} onChangeText={setQuery} autoFocus
                    placeholder="Run a command…" placeholderTextColor={C.muted}
                    style={styles.paletteInput} testID="cc-palette-input"
                  />
                  <TouchableOpacity onPress={closePalette} testID="cc-palette-close">
                    <Ionicons name="close" size={20} color={C.muted} />
                  </TouchableOpacity>
                </View>
                <View style={styles.advBar}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.advTitle}>Show advanced commands</Text>
                    <Text style={styles.advSub}>Reveal {generators.filter((g) => g.advanced).length} pro systems · AI, procgen, netcode, rendering…</Text>
                  </View>
                  <Switch value={showAdvanced} onValueChange={toggleAdvanced} testID="cc-advanced-toggle"
                    trackColor={{ true: C.accent, false: C.border }} thumbColor="#fff" />
                </View>
                <SectionList
                  sections={sections}
                  keyExtractor={(g) => g.key}
                  keyboardShouldPersistTaps="handled"
                  stickySectionHeadersEnabled={false}
                  style={{ maxHeight: 460 }}
                  initialNumToRender={16}
                  windowSize={8}
                  ListEmptyComponent={<Text style={styles.noCmd}>No matching command</Text>}
                  renderSectionHeader={({ section }) => (
                    <View style={styles.sectionHead}>
                      <Text style={styles.sectionTitle}>{section.title}</Text>
                      <Text style={styles.sectionCount}>{section.data.length}</Text>
                    </View>
                  )}
                  renderItem={({ item }) => (
                    <TouchableOpacity style={styles.cmdRow} onPress={() => openCommand(item)} testID={`cc-cmd-${item.key}`}>
                      <Text style={styles.cmdIcon}>{item.icon}</Text>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.cmdLabel}>{item.label}{item.advanced ? '  ' : ''}
                          {item.advanced ? <Text style={styles.advTag}>ADV</Text> : null}
                        </Text>
                        <Text style={styles.cmdFields} numberOfLines={1}>{item.fields.join(' · ')}</Text>
                      </View>
                      <View style={styles.typeTag}><Text style={styles.typeTagTxt}>{item.type}</Text></View>
                    </TouchableOpacity>
                  )}
                />
              </>
            ) : (
              <ScrollView keyboardShouldPersistTaps="handled">
                <View style={styles.composeHead}>
                  <TouchableOpacity onPress={() => setActiveCmd(null)} testID="cc-compose-back">
                    <Ionicons name="chevron-back" size={20} color={C.muted} />
                  </TouchableOpacity>
                  <Text style={styles.composeIcon}>{activeCmd.icon}</Text>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.composeTitle}>{activeCmd.label}</Text>
                    <Text style={styles.composeSub}>fills: {activeCmd.fields.join(', ')}</Text>
                  </View>
                  <TouchableOpacity onPress={closePalette}>
                    <Ionicons name="close" size={20} color={C.muted} />
                  </TouchableOpacity>
                </View>

                <TextInput
                  value={composeText} onChangeText={setComposeText} multiline
                  placeholder={`Describe the ${activeCmd.type} in your own words — this text is authoritative and honored verbatim…`}
                  placeholderTextColor={C.muted} style={styles.composeInput}
                  testID="cc-compose-input"
                />

                {activeCmd.tiers && activeCmd.tiers.length > 0 && (
                  <View style={styles.tierBox}>
                    <Text style={styles.tierLabel}>Power tier · pick 1 of 5</Text>
                    <View style={styles.tierRow}>
                      {activeCmd.tiers.map((t, i) => (
                        <TouchableOpacity
                          key={t}
                          style={[styles.tierChip, tier === t && styles.tierChipOn]}
                          onPress={() => setTier(tier === t ? null : t)}
                          testID={`cc-tier-${i + 1}`}>
                          <Text style={[styles.tierIdx, tier === t && styles.tierTxtOn]}>{i + 1}</Text>
                          <Text style={[styles.tierName, tier === t && styles.tierTxtOn]} numberOfLines={1}>{t}</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  </View>
                )}

                <View style={styles.enrichRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.enrichTitle}>✦ AAA Enrich (Claude)</Text>
                    <Text style={styles.enrichSub}>Multi-pass LLM design brief for a &gt;97 result. Slower.</Text>
                  </View>
                  <Switch value={enrich} onValueChange={setEnrich} testID="cc-enrich-toggle"
                    trackColor={{ true: C.accent2, false: C.border }} thumbColor="#fff" />
                </View>

                <TouchableOpacity
                  style={[styles.execBtn, (!composeText.trim() || executing) && { opacity: 0.5 }]}
                  onPress={execute} disabled={!composeText.trim() || executing}
                  testID="cc-execute">
                  {executing
                    ? <ActivityIndicator color="#04140d" />
                    : <><Ionicons name="flash" size={18} color="#04140d" />
                        <Text style={styles.execTxt}>Execute → Forge Gamefile</Text></>}
                </TouchableOpacity>
              </ScrollView>
            )}
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* pipeline history drawer */}
      <Modal visible={!!historyOpenId} animationType="slide" transparent onRequestClose={() => setHistoryOpenId(null)}>
        <View style={styles.modalWrap}>
          <View style={styles.modalCard}>
            <View style={styles.modalGrip} />
            <View style={styles.composeHead}>
              <Ionicons name="time-outline" size={20} color={C.accent} />
              <Text style={[styles.composeTitle, { flex: 1 }]}>Pipeline History</Text>
              <TouchableOpacity onPress={() => setHistoryOpenId(null)} testID="cc-history-close">
                <Ionicons name="close" size={20} color={C.muted} />
              </TouchableOpacity>
            </View>
            {(() => {
              const h = historyOpenId ? history[historyOpenId] : null;
              if (!h) return <View style={styles.center}><ActivityIndicator color={C.accent} /></View>;
              const runs = (h.runs || []).slice().reverse();
              const d = h.delta || {};
              return (
                <ScrollView style={{ maxHeight: 460 }}>
                  {runs.length === 0 && <Text style={styles.noCmd}>No runs yet — run the pipeline to start tracking.</Text>}
                  {d.needle_gate && (
                    <View style={styles.needleCard}>
                      <Text style={styles.needleTitle}>🪡 Needle-mover (last vs previous)</Text>
                      <Text style={styles.needleGate}>{d.needle_gate}  <Text style={{ color: d.needle_delta >= 0 ? C.good : C.bad }}>{d.needle_delta >= 0 ? '+' : ''}{d.needle_delta}</Text></Text>
                      <Text style={styles.needleRow}>
                        overall <Text style={{ color: d.overall >= 0 ? C.good : C.bad }}>{d.overall >= 0 ? '+' : ''}{d.overall}</Text>
                        {'   '}AAA <Text style={{ color: d.aaa >= 0 ? C.good : C.bad }}>{d.aaa >= 0 ? '+' : ''}{d.aaa}</Text>
                        {'   '}pages <Text style={{ color: C.text }}>{d.pages >= 0 ? '+' : ''}{Number(d.pages || 0).toLocaleString()}</Text>
                        {'   '}minted <Text style={{ color: C.text }}>{d.minted >= 0 ? '+' : ''}{d.minted}</Text>
                      </Text>
                    </View>
                  )}
                  {runs.map((r: any, i: number) => (
                    <View key={i} style={styles.runRow}>
                      <View style={[styles.runScore, { borderColor: scoreColor(r.overall_score) }]}>
                        <Text style={[styles.runScoreTxt, { color: scoreColor(r.overall_score) }]}>{r.overall_score}</Text>
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.runMeta}>#{runs.length - i} · AAA {r.aaa_score ?? '—'} · {Number(r.pages || 0).toLocaleString()} pages</Text>
                        <Text style={styles.runSub}>{r.minted_count} minted · {r.passed}/14 gates{r.auto_mint_enhancer ? ' · ✦ auto-mint' : ''}</Text>
                      </View>
                      {r.aaa_passed && <View style={styles.aaaTag}><Text style={styles.aaaTagTxt}>AAA</Text></View>}
                    </View>
                  ))}
                </ScrollView>
              );
            })()}
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  header: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 12, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.border },
  iconBtn: { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center', backgroundColor: C.card },
  title: { color: C.text, fontSize: 18, fontWeight: '900' },
  sub: { color: C.muted, fontSize: 11, fontWeight: '600' },

  buildBar: { flexDirection: 'row', alignItems: 'center', gap: 8, marginHorizontal: 12, marginTop: 10, backgroundColor: C.deep, borderRadius: 10, borderWidth: 1, borderColor: C.border, paddingHorizontal: 12, paddingVertical: 8 },
  buildId: { color: C.text, fontSize: 12, fontWeight: '700', fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
  buildInput: { flex: 1, color: C.text, fontSize: 12, fontWeight: '700', padding: 0 },
  newBuildBtn: { flexDirection: 'row', alignItems: 'center', gap: 2, backgroundColor: C.chip, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 5 },
  newBuildTxt: { color: C.text, fontSize: 11, fontWeight: '800' },

  cmdTrigger: { flexDirection: 'row', alignItems: 'center', gap: 10, marginHorizontal: 12, marginTop: 10, backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, paddingHorizontal: 14, paddingVertical: 13 },
  cmdTriggerTxt: { flex: 1, color: C.muted, fontSize: 13, fontWeight: '600' },
  kbd: { backgroundColor: C.chip, borderRadius: 6, paddingHorizontal: 7, paddingVertical: 3 },
  kbdTxt: { color: C.muted, fontSize: 11, fontWeight: '800' },

  feedHead: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 },
  feedTitle: { color: C.text, fontSize: 15, fontWeight: '900' },
  countPill: { backgroundColor: C.chip, borderRadius: 10, paddingHorizontal: 9, paddingVertical: 2 },
  countTxt: { color: C.accent, fontSize: 12, fontWeight: '900' },
  center: { paddingVertical: 30, alignItems: 'center' },

  emptyWrap: { alignItems: 'center', paddingVertical: 40, paddingHorizontal: 20 },
  emptyIcon: { fontSize: 40, marginBottom: 10 },
  empty: { color: C.text, fontSize: 14, fontWeight: '800', marginBottom: 6 },
  emptyHint: { color: C.muted, fontSize: 12, textAlign: 'center', lineHeight: 18 },

  gfCard: { backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, marginBottom: 10, overflow: 'hidden' },
  gfHead: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 12 },
  gfIcon: { fontSize: 22 },
  gfLabel: { color: C.text, fontSize: 14, fontWeight: '800' },
  gfType: { color: C.muted, fontSize: 11, fontWeight: '600', marginTop: 2 },
  scoreBadge: { borderWidth: 1.5, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 3 },
  scoreBadgeTxt: { fontSize: 13, fontWeight: '900' },

  gfBody: { paddingHorizontal: 12, paddingBottom: 12, borderTopWidth: 1, borderTopColor: C.border },
  fieldRow: { marginTop: 10 },
  fieldKey: { color: C.accent2, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.5 },
  fieldVal: { color: C.text, fontSize: 12, lineHeight: 17, marginTop: 3 },

  gateBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: C.good, borderRadius: 10, paddingVertical: 12, marginTop: 16 },
  gateBtnTxt: { color: '#04140d', fontSize: 14, fontWeight: '900' },

  autoMintRow: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: C.deep, borderRadius: 10, borderWidth: 1, borderColor: C.border, paddingHorizontal: 12, paddingVertical: 9, marginTop: 14 },
  autoMintTitle: { color: C.text, fontSize: 12, fontWeight: '800' },
  autoMintSub: { color: C.muted, fontSize: 10, marginTop: 2 },
  pipeScore: { borderWidth: 1, borderRadius: 7, paddingHorizontal: 6, paddingVertical: 2, minWidth: 34, alignItems: 'center' },
  pipeScoreTxt: { fontSize: 10, fontWeight: '900' },
  histBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 9, marginTop: 8 },
  histBtnTxt: { color: C.accent, fontSize: 12, fontWeight: '800' },
  needleCard: { backgroundColor: C.chip, borderRadius: 12, borderWidth: 1, borderColor: C.accent2, padding: 12, marginBottom: 12 },
  needleTitle: { color: C.accent2, fontSize: 11, fontWeight: '900', textTransform: 'uppercase', letterSpacing: 0.5 },
  needleGate: { color: C.text, fontSize: 16, fontWeight: '900', marginTop: 4 },
  needleRow: { color: C.muted, fontSize: 12, fontWeight: '700', marginTop: 6 },
  runRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 9, borderBottomWidth: 1, borderBottomColor: C.border },
  runScore: { width: 42, height: 42, borderRadius: 21, borderWidth: 2, alignItems: 'center', justifyContent: 'center' },
  runScoreTxt: { fontSize: 13, fontWeight: '900' },
  runMeta: { color: C.text, fontSize: 13, fontWeight: '800' },
  runSub: { color: C.muted, fontSize: 11, marginTop: 2 },
  aaaTag: { backgroundColor: C.chip, borderRadius: 7, borderWidth: 1, borderColor: C.good, paddingHorizontal: 7, paddingVertical: 3 },
  aaaTagTxt: { color: C.good, fontSize: 10, fontWeight: '900' },

  pipeBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: '#5b6ee8', borderRadius: 10, paddingVertical: 12, marginTop: 10 },
  pipeBtnTxt: { color: '#fff', fontSize: 14, fontWeight: '900' },
  pipeReport: { marginTop: 12, backgroundColor: C.deep, borderRadius: 12, borderWidth: 1, borderColor: C.border, padding: 12 },
  pipeHeadRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 10 },
  pagePill: { alignItems: 'center', justifyContent: 'center', backgroundColor: C.chip, borderRadius: 10, borderWidth: 1, borderColor: C.accent, paddingHorizontal: 12, paddingVertical: 6, marginRight: 12 },
  pageNum: { color: C.accent, fontSize: 18, fontWeight: '900' },
  pageLbl: { color: C.muted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 },
  pipeVerdict: { color: C.text, fontSize: 13, fontWeight: '800' },
  pipeStage: { flexDirection: 'row', alignItems: 'center', gap: 7, paddingVertical: 4, borderTopWidth: 1, borderTopColor: C.border },
  pipeStageIcon: { fontSize: 13 },
  pipeStageLbl: { color: C.text, fontSize: 11, fontWeight: '700', width: 104 },
  pipeStageNote: { color: C.muted, fontSize: 10, flex: 1 },

  gateReport: { marginTop: 14, backgroundColor: C.deep, borderRadius: 12, borderWidth: 1, borderColor: C.border, padding: 12 },
  gateSummary: { flexDirection: 'row', alignItems: 'center' },
  gauge: { width: 64, height: 64, borderRadius: 32, borderWidth: 3, alignItems: 'center', justifyContent: 'center' },
  gaugeScore: { fontSize: 19, fontWeight: '900' },
  gaugeOf: { color: C.muted, fontSize: 9, fontWeight: '700' },
  gateVerdict: { fontSize: 13, fontWeight: '900' },
  gateNote: { color: C.muted, fontSize: 11, marginTop: 3, lineHeight: 15 },
  gateLadder: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 12 },
  gateChip: { flexDirection: 'row', alignItems: 'center', gap: 3, borderWidth: 1, borderRadius: 8, paddingHorizontal: 6, paddingVertical: 3 },
  gateChipIcon: { fontSize: 11 },
  gateChipScore: { fontSize: 10, fontWeight: '900' },

  // modal
  modalWrap: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  modalCard: { backgroundColor: C.bg, borderTopLeftRadius: 20, borderTopRightRadius: 20, borderWidth: 1, borderColor: C.border, paddingHorizontal: 14, paddingTop: 8, paddingBottom: 28, maxHeight: '88%' },
  modalGrip: { alignSelf: 'center', width: 40, height: 4, borderRadius: 2, backgroundColor: C.border, marginBottom: 12 },

  paletteSearch: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, paddingHorizontal: 12, paddingVertical: 12, marginBottom: 10 },
  advBar: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: C.deep, borderRadius: 10, borderWidth: 1, borderColor: C.border, paddingHorizontal: 12, paddingVertical: 9, marginBottom: 8 },
  advTitle: { color: C.text, fontSize: 12, fontWeight: '800' },
  advSub: { color: C.muted, fontSize: 10, marginTop: 2 },
  advTag: { color: C.accent, fontSize: 9, fontWeight: '900' },
  sectionHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: C.bg, paddingTop: 12, paddingBottom: 4, paddingHorizontal: 4 },
  sectionTitle: { color: C.accent2, fontSize: 11, fontWeight: '900', textTransform: 'uppercase', letterSpacing: 0.6 },
  sectionCount: { color: C.muted, fontSize: 10, fontWeight: '800' },
  paletteInput: { flex: 1, color: C.text, fontSize: 15, fontWeight: '600', padding: 0 },
  noCmd: { color: C.muted, fontSize: 13, textAlign: 'center', paddingVertical: 24 },
  cmdRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 11, paddingHorizontal: 6, borderBottomWidth: 1, borderBottomColor: C.border },
  cmdIcon: { fontSize: 22 },
  cmdLabel: { color: C.text, fontSize: 14, fontWeight: '800' },
  cmdFields: { color: C.muted, fontSize: 11, fontWeight: '500', marginTop: 2 },
  typeTag: { backgroundColor: C.chip, borderRadius: 7, paddingHorizontal: 8, paddingVertical: 3 },
  typeTagTxt: { color: C.accent, fontSize: 10, fontWeight: '800' },

  composeHead: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 12 },
  composeIcon: { fontSize: 24 },
  composeTitle: { color: C.text, fontSize: 16, fontWeight: '900' },
  composeSub: { color: C.muted, fontSize: 11, fontWeight: '600', marginTop: 2 },
  composeInput: { backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, color: C.text, fontSize: 14, lineHeight: 20, padding: 14, minHeight: 130, textAlignVertical: 'top' },
  tierBox: { marginTop: 12 },
  tierLabel: { color: C.accent2, fontSize: 11, fontWeight: '900', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 },
  tierRow: { flexDirection: 'row', gap: 6 },
  tierChip: { flex: 1, alignItems: 'center', backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border, paddingVertical: 8, paddingHorizontal: 2 },
  tierChipOn: { backgroundColor: C.chip, borderColor: C.accent },
  tierIdx: { color: C.muted, fontSize: 14, fontWeight: '900' },
  tierName: { color: C.muted, fontSize: 8.5, fontWeight: '700', marginTop: 2, textAlign: 'center' },
  tierTxtOn: { color: C.accent },
  enrichRow: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, padding: 12, marginTop: 12 },
  enrichTitle: { color: C.text, fontSize: 13, fontWeight: '800' },
  enrichSub: { color: C.muted, fontSize: 11, marginTop: 2 },
  execBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: C.accent2, borderRadius: 12, paddingVertical: 15, marginTop: 16 },
  execTxt: { color: '#04140d', fontSize: 15, fontWeight: '900' },

  // ── CHURN 2.0 ──
  churnBox: { marginTop: 12, padding: 12, borderRadius: 12, backgroundColor: C.deep, borderWidth: 1, borderColor: C.border },
  churnHeadRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  churnTitle: { color: C.text, fontSize: 13, fontWeight: '900' },
  modelChip: { flexDirection: 'row', alignItems: 'center', gap: 5, maxWidth: 200, backgroundColor: C.chip, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 5, borderWidth: 1, borderColor: C.border },
  modelChipTxt: { color: C.accent2, fontSize: 11, fontWeight: '700', flexShrink: 1 },
  modelGrid: { marginTop: 8, gap: 6 },
  modelOpt: { backgroundColor: C.alt, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8, borderWidth: 1, borderColor: C.border },
  modelOptOn: { borderColor: C.accent2, backgroundColor: '#1d1635' },
  modelOptTxt: { color: C.muted, fontSize: 12, fontWeight: '700' },
  modelOptMeta: { color: C.muted, fontSize: 10, marginTop: 1 },
  churnBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: C.accent2, borderRadius: 10, paddingVertical: 11, marginTop: 10 },
  churnBtnTxt: { color: '#fff', fontSize: 13, fontWeight: '900' },
  churnResult: { marginTop: 12 },
  churnMeta: { color: C.muted, fontSize: 12, fontWeight: '700', marginBottom: 8 },
  altCard: { backgroundColor: C.card, borderRadius: 10, padding: 10, marginBottom: 8, borderWidth: 1, borderColor: C.border },
  altHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  altLabel: { color: C.text, fontSize: 13, fontWeight: '800', flex: 1 },
  altScore: { borderWidth: 1.5, borderRadius: 8, paddingHorizontal: 7, paddingVertical: 2, marginLeft: 8 },
  altScoreTxt: { fontSize: 12, fontWeight: '900' },
  altSummary: { color: C.text, fontSize: 12, marginTop: 5, lineHeight: 17 },
  altPros: { color: C.good, fontSize: 11, marginTop: 5 },
  altCons: { color: C.bad, fontSize: 11, marginTop: 2 },
  altApply: { backgroundColor: C.accent, borderRadius: 8, paddingVertical: 9, alignItems: 'center', marginTop: 8 },
  altApplyTxt: { color: '#fff', fontSize: 12, fontWeight: '800' },
});
