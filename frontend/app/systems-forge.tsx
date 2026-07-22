import React, { useState, useCallback, useEffect, useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator,
  TextInput, Switch, Linking, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import * as Haptics from 'expo-haptics';
import { apiFetch } from '../utils/apiController';

const API = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const SYS = `${API}/api/galaxy-studio/systems`;
const C = {
  bg: '#0b0f1a', card: '#141b2e', alt: '#1b2438', border: '#2a3550',
  text: '#eef2fb', muted: '#8a96b2', accent: '#a78bfa', good: '#43d39e', gold: '#f4c95d',
};

const tap = () => { if (Platform.OS !== 'web') Haptics.selectionAsync().catch(() => {}); };

export default function SystemsForge() {
  const router = useRouter();
  const params = useLocalSearchParams<{ build?: string }>();
  const [systems, setSystems] = useState<any[]>([]);
  const [pipeline, setPipeline] = useState<any[]>([]);
  const [bigWins, setBigWins] = useState<any[]>([]);
  const [totals, setTotals] = useState<{ k: number; o: number }>({ k: 0, o: 0 });
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');

  const [activeKey, setActiveKey] = useState<string>('');
  const [detail, setDetail] = useState<any>(null);
  const [detLoading, setDetLoading] = useState(false);
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const [knobQuery, setKnobQuery] = useState('');

  const [buildId, setBuildId] = useState<string>((params.build as string) || '');
  const [enrich, setEnrich] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [mounted, setMounted] = useState<any[]>([]);
  const [toast, setToast] = useState('');
  const [bwAi, setBwAi] = useState(false);
  const [ctx, setCtx] = useState<{ vision: string; implementation: string; quality: string }>({ vision: '', implementation: '', quality: '' });
  const [ctxMeta, setCtxMeta] = useState<any[]>([]);
  const [ctxSaving, setCtxSaving] = useState(false);
  const [ctxOpen, setCtxOpen] = useState(false);

  const flash = useCallback((m: string) => { setToast(m); setTimeout(() => setToast(''), 2200); }, []);

  const loadMounted = useCallback(async (bid: string) => {
    if (!bid.trim()) { setMounted([]); return; }
    try {
      const r = await apiFetch(`${SYS}/build/${encodeURIComponent(bid.trim())}`, { timeoutMs: 10000 });
      const d = await r.json();
      setMounted(d.systems || []);
    } catch { /* ignore */ }
  }, []);
  useEffect(() => { loadMounted(buildId); }, [buildId, loadMounted]);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [rs, rb] = await Promise.all([
          apiFetch(`${SYS}`, { timeoutMs: 12000 }),
          apiFetch(`${SYS}/big-wins`, { timeoutMs: 12000 }),
        ]);
        const d = await rs.json(); const b = await rb.json();
        if (alive) {
          setSystems(d.systems || []); setPipeline(d.pipeline || []);
          setTotals({ k: d.total_knobs || 0, o: d.total_options || 0 });
          setBigWins(b.big_wins || []);
        }
      } catch { /* ignore */ } finally { if (alive) setLoading(false); }
    })();
    return () => { alive = false; };
  }, []);

  const mountedKeys = useMemo(() => new Set(mounted.map((m) => m.system)), [mounted]);

  const filteredSystems = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return systems;
    return systems.filter((s) => `${s.label} ${s.blurb} ${s.key}`.toLowerCase().includes(q));
  }, [systems, query]);

  const openSystem = useCallback(async (key: string) => {
    tap();
    setActiveKey(key); setDetail(null); setDetLoading(true); setResult(null); setChosen({}); setKnobQuery('');
    try {
      const r = await apiFetch(`${SYS}/${key}`, { timeoutMs: 12000 });
      setDetail(await r.json());
    } catch { /* ignore */ } finally { setDetLoading(false); }
  }, []);

  const pickKnob = useCallback((kk: string, ok: string) => {
    tap();
    setChosen((p) => ({ ...p, [kk]: p[kk] === ok ? '' : ok }));
  }, []);

  const randomize = useCallback(() => {
    if (!detail?.knobs) return;
    tap();
    const next: Record<string, string> = {};
    detail.knobs.forEach((k: any) => {
      const opts = k.options || [];
      if (opts.length) next[k.key] = opts[Math.floor(Math.random() * opts.length)].key;
    });
    setChosen(next);
    flash('🎲 Knobs randomized');
  }, [detail, flash]);

  const generate = useCallback(async (withEnrich?: boolean) => {
    if (!activeKey || !buildId.trim()) { setResult({ error: 'Enter a Build ID first' }); return; }
    const useEnrich = withEnrich ?? enrich;
    setRunning(true); setResult(null);
    try {
      const knobs: Record<string, string> = {};
      Object.entries(chosen).forEach(([k, v]) => { if (v) knobs[k] = v; });
      const r = await apiFetch(`${SYS}/${activeKey}/generate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ build_id: buildId.trim(), knobs, seed: 1, mount: true, enrich: useEnrich, contexts: ctx }),
        timeoutMs: useEnrich ? 75000 : 20000,
      });
      const d = await r.json();
      setResult(d);
      loadMounted(buildId);
      if (Platform.OS !== 'web') Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    } catch { setResult({ error: 'Generation failed' }); } finally { setRunning(false); }
  }, [activeKey, buildId, chosen, enrich, loadMounted]);

  const applyBigWin = useCallback(async (bw: any) => {
    if (!buildId.trim()) { flash('⚠️ Enter a Build ID first'); return; }
    tap();
    flash(`⏳ Applying ${bw.label}${bwAi ? ' + AI' : ''}…`);
    try {
      const r = await apiFetch(`${SYS}/big-wins/${bw.key}/apply`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ build_id: buildId.trim(), enrich: bwAi }),
        timeoutMs: bwAi ? 120000 : 30000,
      });
      const d = await r.json();
      loadMounted(buildId);
      flash(`✅ ${bw.label} → ${d.applied} systems mounted${bwAi ? ' · ✨ AI enriching in background' : ''}`);
      if (Platform.OS !== 'web') Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    } catch { flash('❌ Could not apply playbook'); }
  }, [buildId, loadMounted, flash, bwAi]);

  useEffect(() => {
    if (!activeKey) return;
    let alive = true;
    (async () => {
      try {
        const r = await apiFetch(`${SYS}/${activeKey}/context?build_id=${encodeURIComponent(buildId.trim())}`, { timeoutMs: 10000 });
        const d = await r.json();
        if (alive) {
          setCtx({ vision: d.vision || '', implementation: d.implementation || '', quality: d.quality || '' });
          setCtxMeta(d.fields_meta || []);
        }
      } catch { /* ignore */ }
    })();
    return () => { alive = false; };
  }, [activeKey, buildId]);

  const saveCtx = useCallback(async () => {
    if (!buildId.trim()) { flash('⚠️ Enter a Build ID first'); return; }
    tap();
    setCtxSaving(true);
    try {
      await apiFetch(`${SYS}/${activeKey}/context`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ build_id: buildId.trim(), ...ctx }), timeoutMs: 15000,
      });
      flash('💾 Creator context saved → feeds AI + gates');
    } catch { flash('❌ Save failed'); } finally { setCtxSaving(false); }
  }, [activeKey, buildId, ctx, flash]);

  const copyJson = useCallback(async () => {
    if (!result?.blueprint) return;
    await Clipboard.setStringAsync(JSON.stringify(result.blueprint, null, 2));
    flash('📋 Blueprint JSON copied');
  }, [result, flash]);

  const exportSystemMd = useCallback(() => {
    if (!activeKey) return;
    Linking.openURL(`${SYS}/${activeKey}/export.md?build_id=${encodeURIComponent(buildId.trim())}`);
  }, [activeKey, buildId]);

  const exportBuildMd = useCallback(() => {
    if (!buildId.trim()) { flash('⚠️ Enter a Build ID first'); return; }
    Linking.openURL(`${SYS}/build/${encodeURIComponent(buildId.trim())}/export.md`);
  }, [buildId, flash]);

  const bp = result && !result.error ? result.blueprint : null;
  const model = bp?.model || null;
  const knobs = useMemo(() => {
    if (!detail?.knobs) return [];
    const q = knobQuery.trim().toLowerCase();
    if (!q) return detail.knobs;
    return detail.knobs.filter((k: any) => k.key.toLowerCase().includes(q) ||
      (k.options || []).some((o: any) => o.key.toLowerCase().includes(q)));
  }, [detail, knobQuery]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.iconBtn} testID="sf-back">
          <Ionicons name="chevron-back" size={22} color={C.text} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>🧩 Game Systems Forge</Text>
          <Text style={styles.sub}>{systems.length} systems · {totals.k} knobs · {totals.o} options · 7-step pipeline</Text>
        </View>
        <TouchableOpacity onPress={exportBuildMd} style={styles.iconBtn} testID="sf-export-build">
          <Ionicons name="download-outline" size={20} color={C.gold} />
        </TouchableOpacity>
      </View>

      {loading ? (
        <View style={styles.center}><ActivityIndicator color={C.accent} /></View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 14, paddingBottom: 80 }} keyboardShouldPersistTaps="handled">
          {/* BIG WINS */}
          <View style={styles.bwHead}>
            <Text style={[styles.sectionLabel, { marginBottom: 0, flex: 1 }]}>🏆 Big-Win Playbooks — one tap, multiple systems</Text>
            <TouchableOpacity onPress={() => { tap(); setBwAi((v) => !v); }} style={[styles.bwAiToggle, bwAi && { borderColor: C.accent, backgroundColor: C.accent + '22' }]} testID="sf-bigwin-ai">
              <Text style={[styles.bwAiTxt, bwAi && { color: C.accent }]}>✨ AI {bwAi ? 'on' : 'off'}</Text>
            </TouchableOpacity>
          </View>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10, paddingVertical: 2, paddingBottom: 6 }}>
            {bigWins.map((b) => (
              <TouchableOpacity key={b.key} onPress={() => applyBigWin(b)} activeOpacity={0.85}
                style={styles.bwCell} testID={`sf-bigwin-${b.key}`}>
                <Text style={styles.bwIcon}>{b.icon}</Text>
                <Text style={styles.bwLabel} numberOfLines={2}>{b.label}</Text>
                <Text style={styles.bwMeta}>{b.system_count} systems →</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          {!!mounted.length && (
            <View style={styles.mountedRow}>
              <Text style={styles.sectionLabel}>🔌 Mounted on this build · {mounted.length}</Text>
              <View style={styles.chipWrap}>
                {mounted.map((m, i) => (
                  <View key={`${m.system}:${i}`} style={styles.mChip}>
                    <Text style={styles.mChipTxt}>{m.label}</Text>
                  </View>
                ))}
              </View>
            </View>
          )}

          {/* SEARCH */}
          <View style={styles.searchBar}>
            <Ionicons name="search" size={16} color={C.muted} />
            <TextInput value={query} onChangeText={setQuery} placeholder="Search systems…"
              placeholderTextColor={C.muted} style={styles.searchInput} testID="sf-search" />
          </View>

          <View style={styles.grid}>
            {filteredSystems.map((sysItem) => {
              const isMounted = mountedKeys.has(sysItem.key);
              return (
                <TouchableOpacity key={sysItem.key} onPress={() => openSystem(sysItem.key)} activeOpacity={0.85}
                  style={[styles.sysCard, activeKey === sysItem.key && { borderColor: C.accent }]} testID={`sf-sys-${sysItem.key}`}>
                  {isMounted && <View style={styles.mountedBadge}><Text style={styles.mountedBadgeTxt}>✓</Text></View>}
                  <Text style={styles.sysIcon}>{sysItem.icon}</Text>
                  <Text style={styles.sysLabel} numberOfLines={1}>{sysItem.label}</Text>
                  <Text style={styles.sysBlurb} numberOfLines={2}>{sysItem.blurb}</Text>
                  <Text style={styles.sysMeta}>{sysItem.knob_count} knobs · {sysItem.option_count} options</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          {detLoading && <View style={styles.center}><ActivityIndicator color={C.accent} /></View>}

          {detail && !detLoading && (
            <View style={styles.panel}>
              <View style={styles.panelHead}>
                <Text style={styles.panelTitle}>{detail.system?.icon} {detail.system?.label}</Text>
                <TouchableOpacity onPress={randomize} style={styles.randBtn} testID="sf-randomize">
                  <Text style={styles.randTxt}>🎲 Randomize</Text>
                </TouchableOpacity>
              </View>

              <View style={styles.pipeRow}>
                {(detail.pipeline || pipeline).map((s: any, i: number) => (
                  <View key={s.key} style={styles.pipeStep}>
                    <Text style={styles.pipeNum}>{i + 1}</Text>
                    <Text style={styles.pipeName} numberOfLines={1}>{s.label}</Text>
                  </View>
                ))}
              </View>

              {detail.knobs?.length > 6 && (
                <View style={styles.searchBar}>
                  <Ionicons name="options-outline" size={15} color={C.muted} />
                  <TextInput value={knobQuery} onChangeText={setKnobQuery} placeholder="Filter knobs…"
                    placeholderTextColor={C.muted} style={styles.searchInput} testID="sf-knob-search" />
                </View>
              )}

              {knobs.map((knob: any) => (
                <View key={knob.key} style={styles.knobBlock}>
                  <Text style={styles.knobLabel}>{knob.label} {chosen[knob.key] ? '' : <Text style={styles.knobAuto}>· auto</Text>}</Text>
                  <View style={styles.chipWrap}>
                    {knob.options.map((o: any) => {
                      const sel = chosen[knob.key] === o.key;
                      return (
                        <TouchableOpacity key={o.key} activeOpacity={0.85} onPress={() => pickKnob(knob.key, o.key)}
                          style={[styles.optChip, sel && { borderColor: C.accent, backgroundColor: C.accent + '22' }]}
                          testID={`sf-knob-${knob.key}-${o.key}`}>
                          <Text style={[styles.optTxt, sel && { color: C.accent }]}>{o.label}</Text>
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                </View>
              ))}

              {/* Creator context — 3 × 20k free-text dossiers fed to AI + gates */}
              <View style={styles.ctxCard} testID="sf-context-card">
                <TouchableOpacity onPress={() => { tap(); setCtxOpen((v) => !v); }} style={styles.ctxHead} testID="sf-context-toggle">
                  <Text style={styles.ctxHeadTxt}>📝 Creator Context — 3 × 20,000 chars → drives AI + gates</Text>
                  <Text style={styles.ctxChevron}>{ctxOpen ? '▾' : '▸'}</Text>
                </TouchableOpacity>
                {ctxOpen && (
                  <>
                    {([
                      ['vision', 'Design Vision & Context', 'Your north-star, pillars, references, the experience you want.'],
                      ['implementation', 'Implementation & Tuning', 'Engine details, parameters, numbers, edge cases you care about.'],
                      ['quality', 'Quality Bar & QA Criteria', "What 'AAA / >97' means for THIS system; pitfalls to avoid."],
                    ] as const).map(([k, label, hint]) => (
                      <View key={k} style={{ marginTop: 10 }}>
                        <Text style={styles.ctxLabel}>{label}</Text>
                        <Text style={styles.ctxHint}>{hint}</Text>
                        <TextInput
                          value={(ctx as any)[k]}
                          onChangeText={(t) => setCtx((p) => ({ ...p, [k]: t.slice(0, 20000) }))}
                          placeholder={`Type your ${label.toLowerCase()}…`}
                          placeholderTextColor={C.muted}
                          style={styles.ctxInput} multiline maxLength={20000}
                          testID={`sf-context-${k}`}
                        />
                        <Text style={styles.ctxCount}>{(ctx as any)[k].length.toLocaleString()} / 20,000</Text>
                      </View>
                    ))}
                    <TouchableOpacity onPress={saveCtx} disabled={ctxSaving} style={[styles.ctxSaveBtn, ctxSaving && { opacity: 0.6 }]} testID="sf-context-save">
                      {ctxSaving ? <ActivityIndicator color="#04140d" /> : <Text style={styles.ctxSaveTxt}>💾 Save creator context</Text>}
                    </TouchableOpacity>
                  </>
                )}
              </View>

              <View style={styles.runCard}>
                <TextInput value={buildId} onChangeText={setBuildId} placeholder="Build ID (e.g. my_game_01)"
                  placeholderTextColor={C.muted} style={styles.input} testID="sf-build-input" />
                <View style={styles.enrichRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.enrichTitle}>✨ Enrich with AI</Text>
                    <Text style={styles.enrichHint}>Claude writes a designer brief + implementation notes</Text>
                  </View>
                  <Switch value={enrich} onValueChange={setEnrich}
                    trackColor={{ false: C.border, true: C.accent }} thumbColor="#fff" testID="sf-enrich-toggle" />
                </View>
                <TouchableOpacity onPress={() => generate()} disabled={running} activeOpacity={0.85}
                  style={[styles.runBtn, running && { opacity: 0.6 }]} testID="sf-generate">
                  {running ? <ActivityIndicator color="#1a1030" /> : (
                    <Text style={styles.runTxt}>{enrich ? '🚀 Forge + AI brief → mount' : '🚀 Forge blueprint → mount'}</Text>
                  )}
                </TouchableOpacity>
                {result?.error && <Text style={styles.err} testID="sf-result-err">{result.error}</Text>}
              </View>

              {bp && (
                <View style={styles.bpCard} testID="sf-blueprint">
                  <View style={styles.bpHead}>
                    <Text style={styles.bpTitle}>✓ {result.label} mounted</Text>
                    {bp.llm_enriched && <Text style={styles.bpBadge}>✨ AI</Text>}
                  </View>
                  <Text style={styles.bpBrief}>{bp.brief}</Text>

                  {!!(bp.designer_notes || []).length && (
                    <View style={styles.notesBlock}>
                      {bp.designer_notes.map((n: string, i: number) => (
                        <Text key={i} style={styles.noteLine}>• {n}</Text>
                      ))}
                    </View>
                  )}

                  {/* engine model */}
                  {model?.model && (
                    <View style={styles.modelCard} testID="sf-model">
                      <Text style={styles.modelTitle}>⚙️ Engine model · {String(model.model).replace(/_/g, ' ')}</Text>
                      {Array.isArray(model.samples) && (
                        <View style={styles.curveRow}>
                          {model.samples.slice(0, 16).map((v: number, i: number) => {
                            const max = Math.max(...model.samples.map((x: number) => Number(x) || 0), 1);
                            const h = Math.max(3, Math.round(((Number(v) || 0) / max) * 40));
                            return <View key={i} style={{ flex: 1, height: h, backgroundColor: C.accent, borderRadius: 1 }} />;
                          })}
                        </View>
                      )}
                      <View style={styles.chipWrap}>
                        {Object.entries(model).filter(([k]) => !['model', 'samples'].includes(k)).slice(0, 6).map(([k, v]) => (
                          <View key={k} style={styles.kvChip}>
                            <Text style={styles.kvTxt}>{k.replace(/_/g, ' ')}: {typeof v === 'object' ? Array.isArray(v) ? `${(v as any[]).length} items` : 'obj' : String(v)}</Text>
                          </View>
                        ))}
                      </View>
                    </View>
                  )}

                  {/* parameters + chosen knobs */}
                  <View style={styles.chipWrap}>
                    {Object.entries(bp.parameters || {}).map(([k, v]: any) => (
                      <View key={`p-${k}`} style={styles.paramChip}><Text style={styles.paramTxt}>{k.replace(/_/g, ' ')}: {String(v)}</Text></View>
                    ))}
                  </View>
                  <View style={styles.chipWrap}>
                    {Object.entries(bp.knobs || {}).map(([k, v]: any) => (
                      <View key={`k-${k}`} style={styles.kvChip}><Text style={styles.kvTxt}>{k}: {String(v)}</Text></View>
                    ))}
                  </View>

                  {/* actions */}
                  <View style={styles.actionRow}>
                    {!bp.llm_enriched && (
                      <TouchableOpacity onPress={() => generate(true)} disabled={running} style={styles.actBtn} testID="sf-regen-ai">
                        <Text style={styles.actTxt}>✨ AI brief</Text>
                      </TouchableOpacity>
                    )}
                    <TouchableOpacity onPress={copyJson} style={styles.actBtn} testID="sf-copy-json">
                      <Text style={styles.actTxt}>📋 Copy JSON</Text>
                    </TouchableOpacity>
                    <TouchableOpacity onPress={exportSystemMd} style={styles.actBtn} testID="sf-export-system">
                      <Text style={styles.actTxt}>⬇️ Export .md</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              )}
            </View>
          )}
        </ScrollView>
      )}

      {!!toast && (
        <View style={styles.toast} testID="sf-toast"><Text style={styles.toastTxt}>{toast}</Text></View>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  header: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 12, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.border },
  iconBtn: { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center', backgroundColor: C.card },
  title: { color: C.text, fontSize: 18, fontWeight: '900' },
  sub: { color: C.muted, fontSize: 11, fontWeight: '600' },
  center: { paddingVertical: 30, alignItems: 'center' },
  sectionLabel: { color: C.muted, fontSize: 12, fontWeight: '800', marginBottom: 8, marginTop: 4, textTransform: 'uppercase', letterSpacing: 0.4 },
  bwCell: { width: 140, backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.gold + '55', padding: 12 },
  bwIcon: { fontSize: 22 },
  bwLabel: { color: C.text, fontSize: 13, fontWeight: '800', marginTop: 4, minHeight: 34 },
  bwMeta: { color: C.gold, fontSize: 10, fontWeight: '800', marginTop: 4 },
  bwHead: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8, marginTop: 4 },
  bwAiToggle: { backgroundColor: C.alt, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: C.border },
  bwAiTxt: { color: C.muted, fontSize: 11, fontWeight: '800' },
  mountedRow: { marginTop: 8, marginBottom: 4 },
  mChip: { backgroundColor: C.accent + '22', borderRadius: 8, paddingHorizontal: 9, paddingVertical: 5, borderWidth: 1, borderColor: C.accent + '55' },
  mChipTxt: { color: C.accent, fontSize: 11, fontWeight: '800' },
  searchBar: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: C.alt, borderRadius: 10, borderWidth: 1, borderColor: C.border, paddingHorizontal: 12, height: 42, marginTop: 8, marginBottom: 10 },
  searchInput: { flex: 1, color: C.text, fontSize: 14, paddingVertical: 0 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  sysCard: { width: '48%', backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 12 },
  mountedBadge: { position: 'absolute', top: 8, right: 8, width: 20, height: 20, borderRadius: 10, backgroundColor: C.good, alignItems: 'center', justifyContent: 'center' },
  mountedBadgeTxt: { color: '#04140d', fontSize: 12, fontWeight: '900' },
  sysIcon: { fontSize: 24 },
  sysLabel: { color: C.text, fontSize: 14, fontWeight: '800', marginTop: 4 },
  sysBlurb: { color: C.muted, fontSize: 11, fontWeight: '600', marginTop: 2, minHeight: 28 },
  sysMeta: { color: C.accent, fontSize: 10, fontWeight: '700', marginTop: 4 },
  panel: { marginTop: 16, borderTopWidth: 1, borderTopColor: C.border, paddingTop: 12 },
  panelHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 },
  panelTitle: { color: C.text, fontSize: 16, fontWeight: '900', flex: 1 },
  randBtn: { backgroundColor: C.alt, borderRadius: 9, paddingHorizontal: 10, paddingVertical: 7, borderWidth: 1, borderColor: C.border },
  randTxt: { color: C.text, fontSize: 12, fontWeight: '800' },
  pipeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 12 },
  pipeStep: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: C.alt, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 5 },
  pipeNum: { color: C.accent, fontSize: 11, fontWeight: '900' },
  pipeName: { color: C.text, fontSize: 11, fontWeight: '700' },
  knobBlock: { marginBottom: 12 },
  knobLabel: { color: C.text, fontSize: 13, fontWeight: '800', marginBottom: 6 },
  knobAuto: { color: C.muted, fontSize: 11, fontWeight: '600' },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  optChip: { backgroundColor: C.alt, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: C.border },
  optTxt: { color: '#aab4cc', fontSize: 11, fontWeight: '700' },
  runCard: { backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: '#6c8cff55', padding: 12, marginTop: 6, marginBottom: 14 },
  input: { backgroundColor: C.alt, borderRadius: 10, borderWidth: 1, borderColor: C.border, color: C.text, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14, marginBottom: 10 },
  enrichRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 12 },
  enrichTitle: { color: C.text, fontSize: 13, fontWeight: '800' },
  enrichHint: { color: C.muted, fontSize: 10, fontWeight: '600', marginTop: 1 },
  runBtn: { backgroundColor: C.accent, borderRadius: 10, paddingVertical: 12, alignItems: 'center' },
  runTxt: { color: '#1a1030', fontSize: 14, fontWeight: '900' },
  err: { color: '#ff8585', fontSize: 12, fontWeight: '700', marginTop: 10 },
  bpCard: { backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.good + '55', padding: 12 },
  bpHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 },
  bpTitle: { color: C.good, fontSize: 14, fontWeight: '900' },
  bpBadge: { color: C.accent, fontSize: 11, fontWeight: '900', backgroundColor: C.accent + '22', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8 },
  bpBrief: { color: C.text, fontSize: 13, lineHeight: 19, fontWeight: '500', marginBottom: 10 },
  notesBlock: { marginBottom: 10, gap: 4 },
  noteLine: { color: C.muted, fontSize: 12, lineHeight: 17, fontWeight: '600' },
  modelCard: { backgroundColor: C.alt, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 10, marginBottom: 10 },
  modelTitle: { color: C.accent, fontSize: 12, fontWeight: '800', marginBottom: 8 },
  curveRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 2, height: 42, marginBottom: 8 },
  paramChip: { backgroundColor: C.accent + '15', borderRadius: 7, paddingHorizontal: 8, paddingVertical: 4, borderWidth: 1, borderColor: C.accent + '33' },
  paramTxt: { color: C.accent, fontSize: 10, fontWeight: '700' },
  kvChip: { backgroundColor: C.alt, borderRadius: 7, paddingHorizontal: 8, paddingVertical: 4, borderWidth: 1, borderColor: C.border, marginTop: 6 },
  kvTxt: { color: '#9aa6c0', fontSize: 10, fontWeight: '700' },
  actionRow: { flexDirection: 'row', gap: 8, marginTop: 12, flexWrap: 'wrap' },
  actBtn: { backgroundColor: C.alt, borderRadius: 9, paddingHorizontal: 12, paddingVertical: 8, borderWidth: 1, borderColor: C.border },
  actTxt: { color: C.text, fontSize: 12, fontWeight: '800' },
  ctxCard: { backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.gold + '44', padding: 12, marginTop: 6, marginBottom: 6 },
  ctxHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  ctxHeadTxt: { color: C.gold, fontSize: 13, fontWeight: '900', flex: 1 },
  ctxChevron: { color: C.gold, fontSize: 16, fontWeight: '900', marginLeft: 8 },
  ctxLabel: { color: C.text, fontSize: 13, fontWeight: '800' },
  ctxHint: { color: C.muted, fontSize: 10, fontWeight: '600', marginTop: 1, marginBottom: 6 },
  ctxInput: { backgroundColor: C.alt, borderRadius: 10, borderWidth: 1, borderColor: C.border, color: C.text, paddingHorizontal: 12, paddingVertical: 10, fontSize: 13, minHeight: 90, textAlignVertical: 'top' },
  ctxCount: { color: C.muted, fontSize: 10, fontWeight: '700', textAlign: 'right', marginTop: 3 },
  ctxSaveBtn: { backgroundColor: C.gold, borderRadius: 10, paddingVertical: 11, alignItems: 'center', marginTop: 12 },
  ctxSaveTxt: { color: '#04140d', fontSize: 13, fontWeight: '900' },
  toast: { position: 'absolute', bottom: 24, left: 20, right: 20, backgroundColor: '#1c2540', borderRadius: 12, borderWidth: 1, borderColor: C.accent + '66', paddingVertical: 12, paddingHorizontal: 16, alignItems: 'center' },
  toastTxt: { color: C.text, fontSize: 13, fontWeight: '800' },
});
