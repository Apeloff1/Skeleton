import React, { useState, useCallback, useEffect } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator,
  TextInput,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { apiFetch } from '../utils/apiController';

const API = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const C = {
  bg: '#0b0f1a', card: '#141b2e', alt: '#1b2438', border: '#2a3550',
  text: '#eef2fb', muted: '#8a96b2', accent: '#34D399', good: '#43d39e',
};

export default function ToolsHub() {
  const router = useRouter();
  const params = useLocalSearchParams<{ build?: string }>();
  const [tools, setTools] = useState<any[]>([]);
  const [pipeline, setPipeline] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState<any>(null);     // selected tool catalog
  const [activeKey, setActiveKey] = useState<string>('');
  const [catLoading, setCatLoading] = useState(false);
  const [buildId, setBuildId] = useState<string>((params.build as string) || '');
  const [count, setCount] = useState<number>(12);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [pickMode, setPickMode] = useState<'consecutive' | 'precise'>('consecutive');
  const [selectedCats, setSelectedCats] = useState<string[]>([]);
  const [matrix, setMatrix] = useState<{ axisA: string; axisB: string; cells: any[] } | null>(null);
  const [packs, setPacks] = useState<any[]>([]);
  const [appliedPack, setAppliedPack] = useState<any>(null);

  const loadPacks = useCallback(async (bid: string) => {
    if (!bid.trim()) { setPacks([]); return; }
    try {
      const r = await apiFetch(`${API}/api/galaxy-studio/forge/style-pack?build_id=${encodeURIComponent(bid.trim())}`, { timeoutMs: 10000 });
      const d = await r.json();
      setPacks(d.packs || []);
    } catch { /* ignore */ }
  }, []);
  useEffect(() => { loadPacks(buildId); }, [buildId, loadPacks]);

  const saveComboAsPack = useCallback(async (cell: any) => {
    if (!buildId.trim()) { setResult('Enter a Build ID first to save a Style Pack'); return; }
    const axes = { [cell.axA]: cell.oA, [cell.axB]: cell.oB };
    try {
      await apiFetch(`${API}/api/galaxy-studio/forge/style-pack`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ build_id: buildId.trim(), label: `${cell.a} · ${cell.b}`, axes }),
        timeoutMs: 12000,
      });
      setResult(`💾 Saved Style Pack: ${cell.a} · ${cell.b}`);
      loadPacks(buildId);
    } catch { setResult('Save failed'); }
  }, [buildId, loadPacks]);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await apiFetch(`${API}/api/galaxy-studio/tools`, { timeoutMs: 12000 });
        const d = await r.json();
        if (alive) { setTools(d.tools || []); setPipeline(d.pipeline || []); }
      } catch { /* ignore */ } finally { if (alive) setLoading(false); }
    })();
    return () => { alive = false; };
  }, []);

  const openTool = useCallback(async (key: string) => {
    setActiveKey(key); setActive(null); setCatLoading(true); setResult(null);
    setSelectedCats([]); setMatrix(null);
    try {
      const r = await apiFetch(`${API}/api/galaxy-studio/tools/${key}/catalog`, { timeoutMs: 15000 });
      const d = await r.json();
      setActive(d);
      // Axis-mutation matrix: preview the first category across the first 2
      // applicable axes (3×3) so creators dial in a cohesive look at a glance.
      const axes = d.axes || [];
      const cat = (d.categories || [])[0];
      if (cat && axes.length >= 2) {
        const aA = axes[0], aB = axes[1];
        const oA = aA.options.slice(1, 4); const oB = aB.options.slice(1, 4);
        const reqs: Promise<any>[] = [];
        const meta: any[] = [];
        oA.forEach((va: any) => oB.forEach((vb: any) => {
          const ax = JSON.stringify({ [aA.key]: va.key, [aB.key]: vb.key });
          meta.push({ a: va.label, b: vb.label, axA: aA.key, oA: va.key, axB: aB.key, oB: vb.key });
          reqs.push(apiFetch(`${API}/api/galaxy-studio/tools/${key}/asset?id=${encodeURIComponent(cat.key)}&axes=${encodeURIComponent(ax)}`, { timeoutMs: 12000 }).then((rr) => rr.json()).catch(() => null));
        }));
        const out = await Promise.allSettled(reqs);
        setMatrix({
          axisA: aA.label, axisB: aB.label,
          cells: out.map((o, i) => ({ ...meta[i], pal: (o.status === 'fulfilled' && o.value?.thumb_palette) || [] })),
        });
      }
    } catch { /* ignore */ } finally { setCatLoading(false); }
  }, []);

  const toggleCat = useCallback((k: string) => {
    setSelectedCats((p) => p.includes(k) ? p.filter((x) => x !== k) : [...p, k]);
  }, []);

  const runPipeline = useCallback(async () => {
    if (!activeKey || !buildId.trim()) { setResult('Enter a Build ID first'); return; }
    if (pickMode === 'precise' && selectedCats.length === 0) { setResult('Precise mode: pick at least one category below'); return; }
    setRunning(true); setResult(null);
    try {
      const body: any = { build_id: buildId.trim(), era: 'modern', seed: 1, count, mount: true, mode: pickMode };
      if (pickMode === 'precise') body.categories = selectedCats;
      if (appliedPack?.axes) body.axes = appliedPack.axes;
      const r = await apiFetch(`${API}/api/galaxy-studio/tools/${activeKey}/pipeline`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body), timeoutMs: 30000,
      });
      const d = await r.json();
      setResult(d.error ? `Error: ${d.error}` : `✓ Forged ${d.forged} (${d.mode}) • mounted to Vault • 7 steps OK`);
    } catch { setResult('Pipeline failed'); } finally { setRunning(false); }
  }, [activeKey, buildId, count, pickMode, selectedCats]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.iconBtn} testID="th-back">
          <Ionicons name="chevron-back" size={22} color={C.text} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>🎮 AI Game Tools</Text>
          <Text style={styles.sub}>Forge-grade tools • 7-step pipeline • mount to your build</Text>
        </View>
      </View>

      {loading ? (
        <View style={styles.center}><ActivityIndicator color={C.accent} /></View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 14, paddingBottom: 60 }}>
          <View style={styles.grid}>
            {tools.map((t) => (
              <TouchableOpacity key={t.key} onPress={() => openTool(t.key)} activeOpacity={0.85}
                style={[styles.toolCard, activeKey === t.key && { borderColor: C.accent }]} testID={`th-tool-${t.key}`}>
                <Text style={styles.toolIcon}>{t.icon}</Text>
                <Text style={styles.toolLabel} numberOfLines={1}>{t.label}</Text>
                <Text style={styles.toolBlurb} numberOfLines={2}>{t.blurb}</Text>
                <Text style={styles.toolMeta}>{t.category_count} cats · {t.axis_count} axes</Text>
              </TouchableOpacity>
            ))}
          </View>

          {catLoading && <View style={styles.center}><ActivityIndicator color={C.accent} /></View>}

          {active && !catLoading && (
            <View style={styles.panel}>
              <Text style={styles.panelTitle}>{active.tool?.icon} {active.tool?.label}</Text>

              {/* 7-step pipeline mount */}
              <View style={styles.pipeCard}>
                <Text style={styles.sectionLabel}>⚙️ 7-Step Pipeline → mount to build</Text>
                <View style={styles.pipeRow}>
                  {(active.pipeline || pipeline).map((s: any, i: number) => (
                    <View key={s.key} style={styles.pipeStep}>
                      <Text style={styles.pipeNum}>{i + 1}</Text>
                      <Text style={styles.pipeName} numberOfLines={1}>{s.label}</Text>
                    </View>
                  ))}
                </View>
                <View style={styles.modeRow}>
                  {(['consecutive', 'precise'] as const).map((m) => (
                    <TouchableOpacity key={m} onPress={() => setPickMode(m)} activeOpacity={0.85}
                      style={[styles.modeChip, pickMode === m && { borderColor: C.accent, backgroundColor: C.accent + '22' }]}
                      testID={`th-mode-${m}`}>
                      <Text style={[styles.modeTxt, pickMode === m && { color: C.accent }]}>
                        {m === 'consecutive' ? '↪ Consecutive' : '🎯 Precise'}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <Text style={styles.modeHint}>
                  {pickMode === 'consecutive'
                    ? 'Auto-spreads the batch across the catalog.'
                    : `Pick exact categories below (${selectedCats.length} selected).`}
                </Text>
                <TextInput value={buildId} onChangeText={setBuildId} placeholder="Build ID (e.g. my_game_01)"
                  placeholderTextColor={C.muted} style={styles.input} testID="th-build-input" />
                <View style={styles.countRow}>
                  {[6, 12, 24, 48].map((n) => (
                    <TouchableOpacity key={n} onPress={() => setCount(n)} activeOpacity={0.85}
                      style={[styles.countChip, count === n && { borderColor: C.accent, backgroundColor: C.accent + '22' }]} testID={`th-count-${n}`}>
                      <Text style={[styles.countTxt, count === n && { color: C.accent }]}>{n}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <TouchableOpacity onPress={runPipeline} disabled={running} activeOpacity={0.85}
                  style={[styles.runBtn, running && { opacity: 0.6 }]} testID="th-run-pipeline">
                  {running ? <ActivityIndicator color="#04140d" /> : (
                    <Text style={styles.runTxt}>🚀 Run pipeline → mount {count}</Text>
                  )}
                </TouchableOpacity>
                {!!result && <Text style={styles.result} testID="th-pipeline-result">{result}</Text>}
              </View>

              {/* Applicable axes */}
              <Text style={styles.sectionLabel}>🎚 Applicable axes · {active.axis_count}</Text>
              <View style={styles.axisWrap}>
                {(active.axes || []).map((a: any) => (
                  <View key={a.key} style={styles.axisChip}>
                    <Text style={styles.axisTxt}>{a.label} · {a.options.length}</Text>
                  </View>
                ))}
              </View>

              {/* Axis-mutation matrix — preview 2 axes at once; tap to save a Pack */}
              {matrix && (
                <View style={styles.matrixCard}>
                  <Text style={styles.sectionLabel}>🧪 Axis matrix · {matrix.axisA} × {matrix.axisB} — tap to save a Style Pack</Text>
                  <View style={styles.matrixGrid}>
                    {matrix.cells.map((cell, i) => (
                      <TouchableOpacity key={i} style={styles.matrixCell} activeOpacity={0.8}
                        onPress={() => saveComboAsPack(cell)} testID={`th-matrix-${i}`}>
                        <View style={styles.matrixStrip}>
                          {(cell.pal || []).slice(0, 5).map((col: string, j: number) => (
                            <View key={j} style={{ flex: 1, backgroundColor: col }} />
                          ))}
                        </View>
                        <Text style={styles.matrixTxt} numberOfLines={1}>{cell.a}·{cell.b}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
              )}

              {/* Saved Style Packs — apply one to the pipeline in a tap */}
              {packs.length > 0 && (
                <View style={styles.matrixCard}>
                  <Text style={styles.sectionLabel}>🎨 Style Packs · {packs.length} — apply to pipeline</Text>
                  <View style={styles.axisWrap}>
                    {packs.map((p) => (
                      <TouchableOpacity key={p.id} activeOpacity={0.85}
                        onPress={() => setAppliedPack(appliedPack?.id === p.id ? null : p)}
                        style={[styles.axisChip, appliedPack?.id === p.id && { borderColor: C.accent, backgroundColor: C.accent + '22' }]}
                        testID={`th-pack-${p.id}`}>
                        <Text style={[styles.axisTxt, appliedPack?.id === p.id && { color: C.accent }]}>
                          {appliedPack?.id === p.id ? '✓ ' : ''}{p.label}
                        </Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
              )}

              {/* Categories — tap to open in the full Forge detail (consecutive)
                  or select for a precise pipeline batch. */}
              <Text style={styles.sectionLabel}>
                🧱 Catalog · {active.category_count} — {pickMode === 'precise' ? 'tap to select' : 'tap to craft in 3D'}
              </Text>
              <View style={styles.catWrap}>
                {(active.categories || []).slice(0, 60).map((c: any) => {
                  const sel = selectedCats.includes(c.key);
                  return (
                    <TouchableOpacity key={c.key} activeOpacity={0.85}
                      style={[styles.catChip, pickMode === 'precise' && sel && { borderColor: C.accent, backgroundColor: C.accent + '18' }]}
                      onPress={() => pickMode === 'precise'
                        ? toggleCat(c.key)
                        : router.push(`/forge?category=${encodeURIComponent(c.key)}&label=${encodeURIComponent(c.label)}&era=modern${buildId.trim() ? `&build=${encodeURIComponent(buildId.trim())}` : ''}`)}
                      testID={`th-cat-${c.key}`}>
                      <Text style={styles.catTxt} numberOfLines={1}>{pickMode === 'precise' ? (sel ? '☑ ' : '☐ ') : ''}{c.label}</Text>
                      <View style={styles.catStrip}>
                        {(c.thumb_palette || []).slice(0, 5).map((col: string, i: number) => (
                          <View key={i} style={{ flex: 1, backgroundColor: col }} />
                        ))}
                      </View>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 12, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.border },
  iconBtn: { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center', backgroundColor: C.card },
  title: { color: C.text, fontSize: 18, fontWeight: '900' },
  sub: { color: C.muted, fontSize: 11, fontWeight: '600' },
  center: { paddingVertical: 30, alignItems: 'center' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  toolCard: { width: '48%', backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 12 },
  toolIcon: { fontSize: 24 },
  toolLabel: { color: C.text, fontSize: 14, fontWeight: '800', marginTop: 4 },
  toolBlurb: { color: C.muted, fontSize: 11, fontWeight: '600', marginTop: 2, minHeight: 28 },
  toolMeta: { color: C.accent, fontSize: 10, fontWeight: '700', marginTop: 4 },
  panel: { marginTop: 16, borderTopWidth: 1, borderTopColor: C.border, paddingTop: 12 },
  panelTitle: { color: C.text, fontSize: 16, fontWeight: '900', marginBottom: 8 },
  pipeCard: { backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: '#6c8cff55', padding: 12, marginBottom: 14 },
  sectionLabel: { color: C.muted, fontSize: 12, fontWeight: '800', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.4 },
  pipeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 10 },
  pipeStep: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: C.alt, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 5 },
  pipeNum: { color: C.accent, fontSize: 11, fontWeight: '900' },
  pipeName: { color: C.text, fontSize: 11, fontWeight: '700' },
  input: { backgroundColor: C.alt, borderRadius: 10, borderWidth: 1, borderColor: C.border, color: C.text, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14, marginBottom: 8 },
  countRow: { flexDirection: 'row', gap: 8, marginBottom: 10 },
  countChip: { paddingHorizontal: 16, paddingVertical: 8, borderRadius: 9, borderWidth: 1, borderColor: C.border },
  countTxt: { color: C.muted, fontSize: 13, fontWeight: '800' },
  modeRow: { flexDirection: 'row', gap: 8, marginBottom: 4 },
  modeChip: { flex: 1, alignItems: 'center', paddingVertical: 9, borderRadius: 9, borderWidth: 1, borderColor: C.border },
  modeTxt: { color: C.muted, fontSize: 12, fontWeight: '800' },
  modeHint: { color: C.muted, fontSize: 10, fontWeight: '600', marginBottom: 8 },
  matrixCard: { backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, padding: 10, marginBottom: 14 },
  matrixGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  matrixCell: { width: '31%', backgroundColor: C.alt, borderRadius: 8, padding: 5 },
  matrixStrip: { flexDirection: 'row', height: 18, borderRadius: 4, overflow: 'hidden', marginBottom: 3 },
  matrixTxt: { color: '#9aa6c0', fontSize: 8, fontWeight: '700' },
  runBtn: { backgroundColor: C.accent, borderRadius: 10, paddingVertical: 12, alignItems: 'center' },
  runTxt: { color: '#04140d', fontSize: 14, fontWeight: '900' },
  result: { color: C.good, fontSize: 12, fontWeight: '700', marginTop: 10 },
  axisWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 14 },
  axisChip: { backgroundColor: C.alt, borderRadius: 8, paddingHorizontal: 9, paddingVertical: 5, borderWidth: 1, borderColor: C.border },
  axisTxt: { color: '#aab4cc', fontSize: 10, fontWeight: '700' },
  catWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  catChip: { width: '48%', backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, padding: 9 },
  catTxt: { color: C.text, fontSize: 12, fontWeight: '700' },
  catStrip: { flexDirection: 'row', height: 6, borderRadius: 3, overflow: 'hidden', marginTop: 6 },
});
