import React, { useState, useCallback, useEffect } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator,
  TextInput, Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { apiFetch } from '../utils/apiController';
import { lazyDefault, LazyMount } from '../src/utils/lazyMount';
const Construct3DView = lazyDefault(() => import('../src/components/Construct3DView'));
import * as Clipboard from 'expo-clipboard';

const API = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const ERAS = [
  { key: '8bit', label: '8-Bit' }, { key: '16bit', label: '16-Bit' },
  { key: 'early3d', label: 'Early 3D' }, { key: '64bit', label: '64-Bit' },
  { key: 'earlyhd', label: 'Early HD' }, { key: 'modern', label: 'Modern' },
  { key: 'nextgen', label: 'Next-Gen' },
];
const SWATCHES = [
  '#e63946', '#f1a208', '#ffd60a', '#90be6d', '#43aa8b', '#4cc9f0', '#4361ee',
  '#7209b7', '#b5179e', '#f72585', '#ffffff', '#c8c8c8', '#8a8a8a', '#3a3a3a',
  '#202020', '#5b3a1a', '#a05a2c', '#d9a066', '#6e8a72', '#9aa6b2', '#e6d2b0',
  '#7a3a2a', '#2b2b40', '#0e1424',
];
const C = {
  bg: '#0b0f1a', card: '#141b2e', alt: '#1b2438', border: '#2a3550',
  text: '#eef2fb', muted: '#8a96b2', accent: '#34D399', good: '#43d39e',
};

export default function UniversalForge() {
  const router = useRouter();
  const params = useLocalSearchParams<{ category?: string; label?: string; surprise?: string; era?: string; skin?: string; axes?: string; build?: string }>();
  const category = (params.category as string) || 'tree';
  const label = (params.label as string) || category.replace(/_/g, ' ');

  const [era, setEra] = useState((params.era as string) || 'modern');
  const [spec, setSpec] = useState<any>(null);
  const [dnaCopied, setDnaCopied] = useState(false);
  const [palette, setPalette] = useState<string[]>([]);
  const [selSwatch, setSelSwatch] = useState(0);
  const [prompt, setPrompt] = useState('');
  const [useLLM, setUseLLM] = useState(true);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedId, setSavedId] = useState<string | null>(null);
  const [buildId, setBuildId] = useState((params.build as string) || '');
  const [status, setStatus] = useState('');
  const [partColors, setPartColors] = useState<Record<number, string>>({});
  const [selectedPart, setSelectedPart] = useState<number | null>(null);
  const [presets, setPresets] = useState<any[]>([]);
  const [showPresets, setShowPresets] = useState(false);
  const [presetOffset, setPresetOffset] = useState(0);
  const [loadingPresets, setLoadingPresets] = useState(false);
  const [cap, setCap] = useState<any>(null);
  const [styleOpts, setStyleOpts] = useState<any>(null);
  const [variants, setVariants] = useState<any[]>([]);
  const [skinStyle, setSkinStyle] = useState<string>((params.skin as string) || '');
  const [complexity, setComplexity] = useState<string>('standard');
  const [intricacy, setIntricacy] = useState<string>('subtle');
  const [detailLevel, setDetailLevel] = useState<string>('standard');
  const [axes, setAxes] = useState<Record<string, string>>(() => {
    try { return params.axes ? JSON.parse(params.axes as string) : {}; } catch { return {}; }
  });
  const [treatment, setTreatment] = useState<string>('none');
  const [inscribe, setInscribe] = useState(false);
  const [advAxes, setAdvAxes] = useState<Record<string, boolean>>({});
  const [inscScript, setInscScript] = useState('');
  const [inscText, setInscText] = useState('');
  const [inscPlace, setInscPlace] = useState('auto');
  const [inscCustomPlace, setInscCustomPlace] = useState('');
  const [savingPack, setSavingPack] = useState(false);
  const [buildPacks, setBuildPacks] = useState<any[]>([]);
  const [axisQuery, setAxisQuery] = useState('');

  const base = `${API}/api/galaxy-studio/forge`;

  const loadMeta = useCallback(async () => {
    const [c, s] = await Promise.allSettled([
      apiFetch(`${base}/capacity`, { timeoutMs: 15000 }),
      apiFetch(`${base}/styles`, { timeoutMs: 15000 }),
    ]);
    try { if (c.status === 'fulfilled') setCap(await c.value.json()); } catch { /* ignore */ }
    try { if (s.status === 'fulfilled') setStyleOpts(await s.value.json()); } catch { /* ignore */ }
  }, [base]);
  useEffect(() => { loadMeta(); }, [loadMeta]);

  const generate = useCallback(async () => {
    setBusy(true); setStatus(''); setSavedId(null);
    try {
      const body = JSON.stringify({ category, era, use_llm: useLLM, user_prompt: prompt,
        skin_style: skinStyle || null, complexity, intricacy, detail_level: detailLevel,
        axes, treatment: treatment === 'none' ? null : treatment, region: category,
        inscribe: inscribe ? (palette[selSwatch] || '#e6d2b0') : null,
        inscription: inscText.trim() ? { script: inscScript || 'runic', text: inscText.trim(),
          placement: inscPlace === 'custom' ? (inscCustomPlace.trim() || 'auto') : inscPlace } : null });
      const r = await apiFetch(`${base}/generate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body,
        timeoutMs: useLLM ? 90000 : 25000,
      });
      const d = await r.json();
      setSpec(d); setPalette(d.palette || []);
      setSelSwatch(0); setPartColors({}); setSelectedPart(null);
      if (d.detail) {
        setSkinStyle(d.skin_style || '');
        setComplexity(d.detail.complexity || 'standard');
        setIntricacy(d.detail.intricacy || 'subtle');
        setDetailLevel(d.detail.detail_level || 'standard');
        setAxes(d.style_axes || {});
        setTreatment(d.treatment || 'none');
        setInscribe(!!d.inscription);
      }
      setStatus(d.llm_enriched ? '✨ AI-enriched' : 'Generated');
    } catch { setStatus('Generate failed'); } finally { setBusy(false); }
  }, [base, category, era, useLLM, prompt, skinStyle, complexity, intricacy, detailLevel, axes, treatment, inscribe, palette, selSwatch, inscScript, inscText, inscPlace, inscCustomPlace]);

  // ── Variations carousel — 6 deterministic seed-mutated previews (light,
  //    concurrency-capped) so a creator can pick a game-ready look fast. ──
  const loadVariants = useCallback(async () => {
    if (!category) { setVariants([]); return; }
    const axStr = encodeURIComponent(JSON.stringify(axes || {}));
    const seeds = [3, 17, 42, 88, 131, 207];
    try {
      const res = await Promise.allSettled(seeds.map((s) =>
        apiFetch(`${base}/asset?id=${encodeURIComponent(category)}&era=${era}&seed=${s}&axes=${axStr}`, { timeoutMs: 12000 }).then((r) => r.json())));
      setVariants(res.map((r, i) => r.status === 'fulfilled'
        ? { seed: seeds[i], name: r.value?.name, pal: r.value?.thumb_palette || [] } : null).filter(Boolean) as any[]);
    } catch { /* ignore */ }
  }, [base, category, era, axes]);
  useEffect(() => { loadVariants(); }, [loadVariants]);

  const pickVariant = useCallback(async (seed: number) => {
    setBusy(true); setStatus('');
    try {
      const axStr = encodeURIComponent(JSON.stringify(axes || {}));
      const r = await apiFetch(`${base}/asset?id=${encodeURIComponent(category)}&era=${era}&seed=${seed}&axes=${axStr}&full=1`, { timeoutMs: 20000 });
      const d = await r.json();
      setSpec(d); setPalette(d.palette || []); setSelSwatch(0); setPartColors({}); setSelectedPart(null);
      setStatus(`Variant ✓`);
    } catch { setStatus('Variant failed'); } finally { setBusy(false); }
  }, [base, category, era, axes]);

  // Forge Hub "Surprise Me" → auto-generate this random forge once styles load.
  const didAutoGen = React.useRef(false);
  useEffect(() => {
    if (params.surprise === '1' && styleOpts && !didAutoGen.current) {
      didAutoGen.current = true;
      setStatus('🎲 Surprise forge!');
      generate();
    }
  }, [params.surprise, styleOpts, generate]);

  const surprise = useCallback(() => {
    if (!styleOpts) return;
    const pick = (a: any[]) => a[Math.floor(Math.random() * a.length)];
    setSkinStyle(pick(styleOpts.skin_styles).key);
    setComplexity(pick(styleOpts.complexity));
    setIntricacy(pick(styleOpts.intricacy));
    setDetailLevel(pick(styleOpts.detail_level));
    // randomize each style axis (or leave off ~40% of the time)
    // randomize a punchy random subset of axes (with 115 axes, applying all
    // would be chaotic) — pick 4-8 random dimensions.
    const pool = [...(styleOpts.axes || [])].sort(() => Math.random() - 0.5)
      .slice(0, 4 + Math.floor(Math.random() * 5));
    const nextAxes: Record<string, string> = {};
    pool.forEach((ax: any) => { nextAxes[ax.key] = pick(ax.options).key; });
    setAxes(nextAxes);
    const treats = (styleOpts.treatments || []).map((t: any) => t.key);
    setTreatment(treats.length ? pick(treats) : 'none');
    setStatus('🎲 Surprised! Hit Generate');
  }, [styleOpts]);

  const applyPack = useCallback((p: any) => {
    setSkinStyle(p.skin_style || '');
    setAxes(p.axes || {});
    setTreatment(p.treatment || 'none');
    if (p.intricacy) setIntricacy(p.intricacy);
    setStatus(`🎨 ${p.label} pack — hit Generate`);
  }, []);

  // Per-build Style Packs saved from the Tool Forge — pre-fill axes in one tap.
  useEffect(() => {
    if (!buildId) { setBuildPacks([]); return; }
    let alive = true;
    apiFetch(`${base}/style-pack?build_id=${encodeURIComponent(buildId)}`, { timeoutMs: 10000 })
      .then((r) => r.json()).then((d) => { if (alive) setBuildPacks(d.packs || []); }).catch(() => {});
    return () => { alive = false; };
  }, [buildId, base]);

  const savePack = useCallback(async () => {
    setSavingPack(true);
    try {
      await apiFetch(`${base}/style-packs`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: `${label} look`, icon: '⭐', skin_style: skinStyle || null,
          axes, treatment: treatment === 'none' ? null : treatment, intricacy }),
        timeoutMs: 15000,
      });
      await loadMeta();
      setStatus('⭐ Saved as a Style Pack');
    } catch { setStatus('Pack save failed'); } finally { setSavingPack(false); }
  }, [base, label, skinStyle, axes, treatment, intricacy, loadMeta]);

  const assignColor = useCallback((color: string) => {
    if (selectedPart !== null) { setPartColors((m) => ({ ...m, [selectedPart]: color })); return; }
    if (!palette.length) return;
    const next = [...palette]; next[selSwatch % next.length] = color;
    setPalette(next); setSpec((s: any) => (s ? { ...s, palette: next } : s));
  }, [palette, selSwatch, selectedPart]);

  const loadPresets = useCallback(async (off = 0) => {
    setLoadingPresets(true);
    try {
      const r = await apiFetch(`${base}/presets?category=${encodeURIComponent(category)}&era=${era}&offset=${off}&limit=60`, { timeoutMs: 20000 });
      const d = await r.json();
      setPresets(d.presets || []); setPresetOffset(off); setShowPresets(true);
    } catch { setStatus('Could not load presets'); } finally { setLoadingPresets(false); }
  }, [base, category, era]);

  const loadPreset = useCallback((p: any) => {
    setSpec({ ...p, llm_enriched: false }); setPalette(p.palette || []);
    setSelSwatch(0); setPartColors({}); setSelectedPart(null);
    setShowPresets(false); setStatus(`Loaded preset · ${p.name}`);
  }, []);

  // ── Saved Library ──
  const [showLib, setShowLib] = useState(false);
  const [libItems, setLibItems] = useState<any[]>([]);
  const [libSel, setLibSel] = useState<Record<string, boolean>>({});
  const [libBuild, setLibBuild] = useState('');
  const loadLibrary = useCallback(async () => {
    try {
      const r = await apiFetch(`${base}/list?category=${encodeURIComponent(category)}&limit=100`, { timeoutMs: 20000 });
      const d = await r.json(); setLibItems(d.items || []);
    } catch { setStatus('Could not load library'); }
  }, [base, category]);
  const bulkMount = useCallback(async () => {
    const ids = Object.keys(libSel).filter((k) => libSel[k]);
    if (!ids.length || !libBuild.trim()) { Alert.alert('Pick assets + Build ID', 'Select assets and enter a Build ID.'); return; }
    try {
      const r = await apiFetch(`${base}/mount`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ construct_ids: ids, build_id: libBuild.trim() }), timeoutMs: 20000,
      });
      const d = await r.json(); setStatus(`Mounted ${d.mounted} to ${libBuild.trim()} ✓`); setLibSel({});
    } catch { setStatus('Bulk mount failed'); }
  }, [base, libSel, libBuild]);

  const save = useCallback(async () => {
    if (!spec) return;
    setSaving(true); setStatus('');
    try {
      const baked = (spec.geometry || []).map((g: any, i: number) => ({
        ...g, color: partColors[i] || (palette.length ? palette[i % palette.length] : g.color),
      }));
      const r = await apiFetch(`${base}/save`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ spec: { ...spec, palette, geometry: baked }, construct_id: savedId }),
        timeoutMs: 20000,
      });
      const d = await r.json(); setSavedId(d.construct_id);
      setStatus(`Saved ✓ ${d.construct_id}`); loadMeta();
    } catch { setStatus('Save failed'); } finally { setSaving(false); }
  }, [base, spec, palette, partColors, savedId, loadMeta]);

  const vaultAction = useCallback(async (action: 'mount' | 'save-to-gamefiles' | 'extract') => {
    if (action !== 'extract' && (!savedId || !buildId.trim())) { Alert.alert('Need a build', 'Save the asset and enter a Build ID first.'); return; }
    if (action === 'extract' && !buildId.trim()) { Alert.alert('Need a build', 'Enter a Build ID to extract from.'); return; }
    setStatus('');
    try {
      if (action === 'extract') {
        const r = await apiFetch(`${base}/extract/${encodeURIComponent(buildId.trim())}`, { timeoutMs: 20000 });
        const d = await r.json(); setStatus(`Extracted ${d.extracted} asset(s) from Vault`);
      } else {
        const r = await apiFetch(`${base}/${action}`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ construct_ids: [savedId], build_id: buildId.trim() }), timeoutMs: 20000,
        });
        const d = await r.json();
        setStatus(action === 'mount' ? `Mounted ${d.mounted} to Vault ✓` : `Wrote ${d.gamefiles} gamefile(s) ✓`);
      }
    } catch { setStatus(`${action} failed`); }
  }, [base, savedId, buildId]);

  const Chip = ({ active, label: l, onPress, testID }: any) => (
    <TouchableOpacity onPress={onPress} activeOpacity={0.85} testID={testID}
      style={[styles.chip, { borderColor: active ? C.accent : C.border, backgroundColor: active ? C.accent + '22' : 'transparent' }]}>
      <Text style={[styles.chipTxt, { color: active ? C.accent : C.muted }]}>{l}</Text>
    </TouchableOpacity>
  );

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.iconBtn} testID="uf-back">
          <Ionicons name="chevron-back" size={22} color={C.text} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.title} numberOfLines={1}>⚒️ {label} Forge</Text>
          <Text style={styles.sub}>Universal forge · AI-enriched 3D · 36 presets/era · Vault mount</Text>
        </View>
        <TouchableOpacity onPress={() => { const n = !showLib; setShowLib(n); if (n) loadLibrary(); }} style={styles.iconBtn} testID="uf-library-toggle">
          <Ionicons name={showLib ? 'hammer' : 'albums'} size={19} color={showLib ? C.accent : C.text} />
        </TouchableOpacity>
      </View>

      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 14, paddingBottom: 60 }}>
        {showLib ? (
          <View testID="uf-library">
            <Text style={styles.sectionLabel}>Saved {label} — select, then bulk-mount to a build</Text>
            <TextInput value={libBuild} onChangeText={setLibBuild} placeholder="Build ID to mount selected into"
              placeholderTextColor={C.muted} style={styles.inputSmall} testID="uf-lib-build" autoCapitalize="none" />
            <TouchableOpacity onPress={bulkMount} activeOpacity={0.85}
              style={[styles.primaryBtn, { backgroundColor: C.accent, marginTop: 10, opacity: Object.values(libSel).filter(Boolean).length ? 1 : 0.5 }]}
              testID="uf-lib-mount">
              <Ionicons name="git-merge-outline" size={17} color="#0b0f1a" />
              <Text style={styles.primaryTxt}>Mount {Object.values(libSel).filter(Boolean).length} selected</Text>
            </TouchableOpacity>
            {libItems.length === 0 ? (
              <View style={styles.emptyView}>
                <Ionicons name="albums-outline" size={40} color={C.muted} />
                <Text style={styles.emptyTxt}>No saved {label} yet — forge & save one</Text>
              </View>
            ) : (
              <View style={styles.gallery}>
                {libItems.map((it) => {
                  const id = it.construct_id || it.id; const sel = !!libSel[id];
                  return (
                    <TouchableOpacity key={id} onPress={() => setLibSel((m) => ({ ...m, [id]: !m[id] }))}
                      activeOpacity={0.85} style={[styles.galleryCard, sel ? { borderColor: C.accent, borderWidth: 2 } : null]}
                      testID={`uf-lib-${id}`}>
                      <View style={styles.galleryPal}>
                        {(it.palette || []).slice(0, 4).map((c: string, i: number) => (<View key={i} style={{ flex: 1, backgroundColor: c }} />))}
                      </View>
                      <Text style={styles.galleryName} numberOfLines={1}>{sel ? '✓ ' : ''}{it.name}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            )}
            {status ? <Text style={[styles.status, { color: status.includes('failed') ? '#ff6b6b' : C.good }]} testID="uf-status">{status}</Text> : null}
          </View>
        ) : (
        <>
        <Text style={styles.sectionLabel}>Era</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 12 }}>
          {ERAS.map((e) => <Chip key={e.key} active={era === e.key} label={e.label} onPress={() => setEra(e.key)} />)}
        </ScrollView>

        <TouchableOpacity onPress={() => (showPresets ? setShowPresets(false) : loadPresets(0))}
          activeOpacity={0.85} style={[styles.browseBtn, { borderColor: C.accent }]} testID="uf-browse-presets">
          {loadingPresets ? <ActivityIndicator size="small" color={C.accent} /> : <Ionicons name="grid-outline" size={16} color={C.accent} />}
          <Text style={[styles.browseTxt, { color: C.accent }]}>{showPresets ? 'Hide preset gallery' : 'Browse presets'}</Text>
        </TouchableOpacity>

        {showPresets && (
          <View style={styles.gallery}>
            {presets.map((p) => (
              <TouchableOpacity key={p.preset_id} onPress={() => loadPreset(p)} activeOpacity={0.85}
                style={styles.galleryCard} testID={`uf-preset-${p.preset_id}`}>
                <View style={styles.galleryPal}>
                  {(p.palette || []).slice(0, 4).map((c: string, i: number) => (<View key={i} style={{ flex: 1, backgroundColor: c }} />))}
                </View>
                <Text style={styles.galleryName} numberOfLines={1}>{p.name}</Text>
              </TouchableOpacity>
            ))}
            {presets.length >= 60 && (
              <TouchableOpacity onPress={() => loadPresets(presetOffset + 60)} style={styles.galleryMore} testID="uf-presets-more">
                <Text style={[styles.browseTxt, { color: C.accent }]}>Load more →</Text>
              </TouchableOpacity>
            )}
          </View>
        )}

        {spec ? (
          <>
            <LazyMount>
              <Construct3DView geometry={spec.geometry || []} palette={palette}
                partColors={partColors} selectedPart={selectedPart}
                surface={spec.surface} vfx={spec.vfx}
                onSelectPart={(i) => setSelectedPart(i)} height={300} />
            </LazyMount>
            {selectedPart !== null && (
              <View style={styles.partRow}>
                <Text style={styles.partTxt}>Editing part #{selectedPart} — pick a colour below</Text>
                <TouchableOpacity onPress={() => setSelectedPart(null)} testID="uf-clear-part">
                  <Text style={styles.partClear}>↺ Whole model</Text>
                </TouchableOpacity>
              </View>
            )}
            <Text style={styles.specName}>{spec.name}</Text>
            <Text style={styles.specDesc} numberOfLines={3}>{spec.descriptor}</Text>
            {!!spec.dna && (
              <View style={styles.dnaCard}>
                <View style={styles.dnaHead}>
                  <Text style={styles.dnaTitle}>🧬 Procedural DNA · {spec.dna.bits}-bit</Text>
                  <TouchableOpacity onPress={async () => {
                    try { await Clipboard.setStringAsync(spec?.forge_code || ''); setDnaCopied(true); setTimeout(() => setDnaCopied(false), 1500); } catch { /* ignore */ }
                  }} style={styles.dnaCopy} testID="uf-dna-copy">
                    <Text style={styles.dnaCopyTxt}>{dnaCopied ? '✓ Copied' : 'Copy code'}</Text>
                  </TouchableOpacity>
                </View>
                <Text style={styles.dnaHex} numberOfLines={1}>{spec.dna.short}  ·  chk {spec.dna.checksum}</Text>
                {!!(spec.components && spec.components.length) && (
                  <View style={styles.ecsRow}>
                    {spec.components.map((c: string) => (
                      <View key={c} style={styles.ecsChip}><Text style={styles.ecsChipTxt}>{c}</Text></View>
                    ))}
                  </View>
                )}
                {!!(spec.pruned_axes && spec.pruned_axes.length) && (
                  <Text style={styles.dnaPruned}>semantically pruned: {spec.pruned_axes.join(', ')}</Text>
                )}
              </View>
            )}
          </>
        ) : (
          <View style={styles.emptyView}>
            <Ionicons name="cube-outline" size={40} color={C.muted} />
            <Text style={styles.emptyTxt}>Generate a {label} to preview it in 3D</Text>
          </View>
        )}

        {variants.length > 0 && (
          <View style={styles.varCard}>
            <Text style={styles.sectionLabel}>✨ Variations — tap to preview a game-ready look</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10, paddingVertical: 2 }}>
              {variants.map((v, vi) => (
                <TouchableOpacity key={`var-${v?.seed ?? vi}`} onPress={() => pickVariant(v.seed)} activeOpacity={0.85}
                  style={styles.varCell} testID={`uf-variant-${v.seed}`}>
                  <View style={styles.varStrip}>
                    {(v.pal || []).slice(0, 5).map((c: string, i: number) => (
                      <View key={`${vi}-${i}`} style={{ flex: 1, backgroundColor: c }} />
                    ))}
                  </View>
                  <Text style={styles.varName} numberOfLines={1}>{v.name || `Seed ${v.seed}`}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>
        )}

        {palette.length > 0 && (
          <View style={styles.editCard}>
            <Text style={styles.sectionLabel}>Colour edit — tap a slot, then pick a colour (live)</Text>
            <View style={styles.swatchRow}>
              {palette.map((c, i) => (
                <TouchableOpacity key={i} onPress={() => setSelSwatch(i)} activeOpacity={0.8}
                  style={[styles.swatch, { backgroundColor: c, borderColor: selSwatch === i ? C.text : '#00000040', borderWidth: selSwatch === i ? 3 : 1 }]}
                  testID={`uf-swatch-${i}`} />
              ))}
            </View>
            <View style={styles.paletteGrid}>
              {SWATCHES.map((c) => (
                <TouchableOpacity key={c} onPress={() => assignColor(c)} activeOpacity={0.8}
                  style={[styles.pgSwatch, { backgroundColor: c }]} testID={`uf-color-${c}`} />
              ))}
            </View>
            <TouchableOpacity onPress={() => setInscribe((v) => !v)} activeOpacity={0.85}
              style={[styles.inscribeRow, inscribe && { borderColor: C.accent, backgroundColor: C.accent + '18' }]} testID="uf-inscribe">
              <Ionicons name={inscribe ? 'checkbox' : 'square-outline'} size={18} color={inscribe ? C.accent : C.muted} />
              <Text style={[styles.inscribeTxt, inscribe && { color: C.accent }]}>Inscribe with selected colour</Text>
              <View style={[styles.inscribeDot, { backgroundColor: palette[selSwatch] || '#e6d2b0' }]} />
            </TouchableOpacity>
          </View>
        )}

        {styleOpts && (
          <View style={styles.editCard} testID="uf-detail-card">
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <Text style={styles.sectionLabel}>Skin style</Text>
              <TouchableOpacity onPress={surprise} testID="uf-surprise" style={styles.surpriseBtn}>
                <Text style={styles.surpriseTxt}>🎲 Surprise me</Text>
              </TouchableOpacity>
            </View>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 8 }}>
              <Chip key="auto" active={!skinStyle} label="Auto" onPress={() => setSkinStyle('')} />
              {styleOpts.skin_styles.map((s: any) => (
                <Chip key={s.key} active={skinStyle === s.key} label={s.label} onPress={() => setSkinStyle(s.key)} testID={`uf-skin-${s.key}`} />
              ))}
            </ScrollView>
            <Text style={styles.sectionLabel}>Complexity</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 8 }}>
              {styleOpts.complexity.map((c: string) => (
                <Chip key={c} active={complexity === c} label={c} onPress={() => setComplexity(c)} />
              ))}
            </ScrollView>
            <Text style={styles.sectionLabel}>Intricacy</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 8 }}>
              {styleOpts.intricacy.map((c: string) => (
                <Chip key={c} active={intricacy === c} label={c} onPress={() => setIntricacy(c)} />
              ))}
            </ScrollView>
            <Text style={styles.sectionLabel}>Detail level</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}>
              {styleOpts.detail_level.map((c: string) => (
                <Chip key={c} active={detailLevel === c} label={c} onPress={() => setDetailLevel(c)} />
              ))}
            </ScrollView>

            {(styleOpts.style_packs || []).length > 0 && (
              <>
                <Text style={[styles.sectionLabel, { marginTop: 12 }]}>Style packs · one-tap looks</Text>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 4 }}>
                  {styleOpts.style_packs.map((p: any) => (
                    <TouchableOpacity key={p.key} onPress={() => applyPack(p)} style={styles.pack} testID={`uf-pack-${p.key}`}>
                      <Text style={styles.packIcon}>{p.icon}</Text>
                      <Text style={styles.packTxt}>{p.label}</Text>
                    </TouchableOpacity>
                  ))}
                </ScrollView>
              </>
            )}

            {buildPacks.length > 0 && (
              <>
                <Text style={[styles.sectionLabel, { marginTop: 12 }]}>🎨 Build Style Packs · forge with a saved look</Text>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 4 }}>
                  {buildPacks.map((p: any) => (
                    <TouchableOpacity key={p.id} onPress={() => applyPack(p)} style={styles.pack} testID={`uf-buildpack-${p.id}`}>
                      <Text style={styles.packIcon}>🎨</Text>
                      <Text style={styles.packTxt} numberOfLines={1}>{p.label}</Text>
                    </TouchableOpacity>
                  ))}
                </ScrollView>
              </>
            )}

            <View style={styles.axisHead}>
              <Text style={styles.sectionLabel}>Style axes · {(styleOpts.axes || []).length} dimensions{Object.keys(axes).length ? ` · ${Object.keys(axes).length} active` : ''}</Text>
              <TextInput value={axisQuery} onChangeText={setAxisQuery} placeholder="filter axes…"
                placeholderTextColor={C.muted} style={styles.axisFilter} testID="uf-axis-filter" />
            </View>
            {(() => {
              const all = styleOpts.axes || [];
              const ql = axisQuery.trim().toLowerCase();
              const activeKeys = Object.keys(axes);
              const shown = ql ? all.filter((a: any) => a.label.toLowerCase().includes(ql)) : all.slice(0, 8);
              const map = new Map(shown.map((a: any) => [a.key, a]));
              all.forEach((a: any) => { if (activeKeys.includes(a.key)) map.set(a.key, a); });
              const list = Array.from(map.values());
              return (
                <>
                  {list.map((ax: any) => {
                    const adv = !!advAxes[ax.key];
                    const opts = adv ? ax.options : ax.options.filter((o: any) => o.tier !== 'advanced');
                    const advCount = ax.options.length - (ax.basic_count || ax.options.length);
                    return (
                    <View key={ax.key}>
                      <View style={styles.axisRowHead}>
                        <Text style={[styles.sectionLabel, { marginTop: 10, flex: 1 }]}>{ax.label}{axes[ax.key] ? ' ✓' : ''}</Text>
                        {advCount > 0 && (
                          <TouchableOpacity onPress={() => setAdvAxes((m) => ({ ...m, [ax.key]: !m[ax.key] }))}
                            style={[styles.advToggle, adv && styles.advToggleOn]} testID={`uf-adv-${ax.key}`}>
                            <Text style={[styles.advToggleTxt, adv && { color: '#0b0f1a' }]}>{adv ? `Advanced · ${ax.options.length}` : `Basic · ${ax.basic_count}`}</Text>
                          </TouchableOpacity>
                        )}
                      </View>
                      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 4 }}>
                        <Chip key="none" active={!axes[ax.key]} label="None" onPress={() => setAxes((m) => { const n = { ...m }; delete n[ax.key]; return n; })} />
                        {opts.map((o: any) => (
                          <Chip key={o.key} active={axes[ax.key] === o.key} label={o.label}
                            onPress={() => setAxes((m) => ({ ...m, [ax.key]: o.key }))} testID={`uf-axis-${ax.key}-${o.key}`} />
                        ))}
                      </ScrollView>
                    </View>
                  ); })}
                  {!ql && all.length > list.length && (
                    <Text style={styles.axisMore}>+ {all.length - list.length} more axes — type above to filter</Text>
                  )}
                </>
              );
            })()}

            {(styleOpts.treatments || []).length > 0 && (
              <>
                <Text style={[styles.sectionLabel, { marginTop: 10 }]}>Region treatment · markings & etchings</Text>
                <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                  {styleOpts.treatments.map((t: any) => (
                    <Chip key={t.key} active={treatment === t.key} label={t.label} onPress={() => setTreatment(t.key)} testID={`uf-treat-${t.key}`} />
                  ))}
                </ScrollView>
              </>
            )}

            {styleOpts.inscription && (
              <View style={styles.inscSection}>
                <Text style={[styles.sectionLabel, { marginTop: 10 }]}>✒️ Dead-language inscription · your own text</Text>
                <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                  <Chip key="none" active={!inscScript} label="None" onPress={() => setInscScript('')} />
                  {styleOpts.inscription.scripts.filter((s: any) => s.key !== 'none').map((s: any) => (
                    <Chip key={s.key} active={inscScript === s.key} label={s.label} onPress={() => setInscScript(s.key)} testID={`uf-script-${s.key}`} />
                  ))}
                </ScrollView>
                <TextInput value={inscText} onChangeText={setInscText} placeholder="Type the text/phrase to engrave…"
                  placeholderTextColor={C.muted} style={styles.inscInput} testID="uf-insc-text" maxLength={120} />
                <Text style={[styles.sectionLabel, { marginTop: 6 }]}>Placement</Text>
                <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                  {styleOpts.inscription.placements.map((p: any) => (
                    <Chip key={p.key} active={inscPlace === p.key} label={p.label} onPress={() => setInscPlace(p.key)} testID={`uf-place-${p.key}`} />
                  ))}
                </ScrollView>
                {inscPlace === 'custom' && (
                  <TextInput value={inscCustomPlace} onChangeText={setInscCustomPlace} placeholder="Custom placement label…"
                    placeholderTextColor={C.muted} style={styles.inscInput} testID="uf-insc-place-custom" maxLength={40} />
                )}
              </View>
            )}

            <TouchableOpacity onPress={savePack} disabled={savingPack} activeOpacity={0.85}
              style={styles.savePackBtn} testID="uf-save-pack">
              <Ionicons name="bookmark" size={15} color="#A78BFA" />
              <Text style={styles.savePackTxt}>{savingPack ? 'Saving…' : 'Save this combo as a Style Pack'}</Text>
            </TouchableOpacity>
          </View>
        )}

        <View style={styles.editCard}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <Text style={styles.sectionLabel}>AI brief (Claude Sonnet 4.6 · up to 20,000 chars)</Text>
            <TouchableOpacity onPress={() => setUseLLM((v) => !v)} testID="uf-ai-toggle"
              style={[styles.aiToggle, { backgroundColor: useLLM ? C.accent : C.alt }]}>
              <Text style={[styles.aiToggleTxt, { color: useLLM ? '#0b0f1a' : C.muted }]}>{useLLM ? 'AI ON' : 'AI OFF'}</Text>
            </TouchableOpacity>
          </View>
          <TextInput value={prompt} onChangeText={(t) => setPrompt(t.slice(0, 20000))}
            placeholder={`Describe the ${label}… (palette, materials, mood, VFX). 20k chars.`}
            placeholderTextColor={C.muted} multiline style={styles.input} testID="uf-prompt" maxLength={20000} />
          <Text style={styles.counter}>{prompt.length.toLocaleString()} / 20,000</Text>
        </View>

        <TouchableOpacity onPress={generate} disabled={busy} activeOpacity={0.85}
          style={[styles.primaryBtn, { backgroundColor: C.accent, opacity: busy ? 0.6 : 1 }]} testID="uf-generate">
          {busy ? <ActivityIndicator color="#0b0f1a" /> : <Ionicons name="sparkles" size={18} color="#0b0f1a" />}
          <Text style={styles.primaryTxt}>{busy ? 'Forging…' : useLLM ? 'Generate with AI' : 'Generate'}</Text>
        </TouchableOpacity>

        {spec && (
          <TouchableOpacity onPress={save} disabled={saving} activeOpacity={0.85}
            style={[styles.secondaryBtn, { borderColor: C.good }]} testID="uf-save">
            {saving ? <ActivityIndicator color={C.good} /> : <Ionicons name="save-outline" size={17} color={C.good} />}
            <Text style={[styles.secondaryTxt, { color: C.good }]}>{savedId ? 'Update saved asset' : 'Save asset'}</Text>
          </TouchableOpacity>
        )}

        {savedId && (
          <View style={styles.editCard}>
            <Text style={styles.sectionLabel}>Vault connection</Text>
            <TextInput value={buildId} onChangeText={setBuildId} placeholder="Build ID (to mount / extract)"
              placeholderTextColor={C.muted} style={styles.inputSmall} testID="uf-build-id" autoCapitalize="none" />
            <View style={{ flexDirection: 'row', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
              <TouchableOpacity onPress={() => vaultAction('mount')} style={styles.vaultBtn} testID="uf-mount">
                <Ionicons name="git-merge-outline" size={15} color={C.text} /><Text style={styles.vaultTxt}>Mount</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => vaultAction('save-to-gamefiles')} style={styles.vaultBtn} testID="uf-gamefiles">
                <Ionicons name="file-tray-full-outline" size={15} color={C.text} /><Text style={styles.vaultTxt}>Save to gamefiles</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => vaultAction('extract')} style={styles.vaultBtn} testID="uf-extract">
                <Ionicons name="download-outline" size={15} color={C.text} /><Text style={styles.vaultTxt}>Extract</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {status ? <Text style={[styles.status, { color: status.includes('failed') ? '#ff6b6b' : C.good }]} testID="uf-status">{status}</Text> : null}

        {cap && (
          <Text style={styles.capacity}>Forge store: {(cap.forge || 0).toLocaleString()} / {(cap.capacity || 0).toLocaleString()} assets</Text>
        )}
        </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 10, gap: 8 },
  iconBtn: { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center', backgroundColor: C.alt },
  title: { color: C.text, fontSize: 18, fontWeight: '900' },
  sub: { color: C.muted, fontSize: 11, marginTop: 1 },
  sectionLabel: { color: C.muted, fontSize: 12, fontWeight: '800', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.4 },
  varCard: { backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 14, padding: 12, marginTop: 12 },
  varCell: { width: 92, backgroundColor: C.alt, borderRadius: 10, padding: 8, borderWidth: 1, borderColor: C.border },
  varStrip: { flexDirection: 'row', height: 22, borderRadius: 6, overflow: 'hidden', marginBottom: 6 },
  varName: { color: C.text, fontSize: 11, fontWeight: '700' },
  chip: { paddingHorizontal: 13, paddingVertical: 7, borderRadius: 18, borderWidth: 1, marginRight: 7 },
  chipTxt: { fontSize: 12, fontWeight: '700', textTransform: 'capitalize' },
  specName: { color: C.text, fontSize: 16, fontWeight: '800', marginTop: 10 },
  specDesc: { color: C.muted, fontSize: 12, lineHeight: 17, marginTop: 3 },
  emptyView: { height: 200, borderRadius: 14, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, alignItems: 'center', justifyContent: 'center', gap: 8 },
  emptyTxt: { color: C.muted, fontSize: 13 },
  editCard: { backgroundColor: C.card, borderRadius: 14, padding: 12, marginTop: 12, borderWidth: 1, borderColor: C.border },
  swatchRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 10 },
  swatch: { width: 40, height: 40, borderRadius: 9 },
  paletteGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  pgSwatch: { width: 30, height: 30, borderRadius: 7, borderWidth: 1, borderColor: '#ffffff22' },
  aiToggle: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 14 },
  surpriseBtn: { backgroundColor: '#2b2342', borderWidth: 1, borderColor: '#7C9CFF', borderRadius: 14, paddingHorizontal: 12, paddingVertical: 6 },
  surpriseTxt: { color: '#A78BFA', fontSize: 11, fontWeight: '900' },
  pack: { backgroundColor: C.alt, borderWidth: 1, borderColor: '#A78BFA55', borderRadius: 12, paddingHorizontal: 10, paddingVertical: 8, marginRight: 8, alignItems: 'center', minWidth: 78 },
  packIcon: { fontSize: 18 },
  packTxt: { color: C.text, fontSize: 10, fontWeight: '800', marginTop: 2, textAlign: 'center' },
  inscribeRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 10, borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 10, backgroundColor: C.alt },
  inscribeTxt: { color: C.muted, fontSize: 12, fontWeight: '700', flex: 1 },
  inscribeDot: { width: 22, height: 22, borderRadius: 6, borderWidth: 1, borderColor: '#00000040' },
  savePackBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, marginTop: 14, borderWidth: 1, borderColor: '#A78BFA66', borderRadius: 12, paddingVertical: 11, backgroundColor: '#A78BFA14' },
  savePackTxt: { color: '#A78BFA', fontSize: 13, fontWeight: '900' },
  axisHead: { marginTop: 12 },
  axisFilter: { marginTop: 6, backgroundColor: C.alt, borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8, color: C.text, fontSize: 13 },
  axisMore: { color: C.muted, fontSize: 11, fontStyle: 'italic', marginTop: 8 },
  axisRowHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  advToggle: { borderWidth: 1, borderColor: '#7C9CFF', borderRadius: 12, paddingHorizontal: 10, paddingVertical: 4, marginTop: 8 },
  advToggleOn: { backgroundColor: '#7C9CFF' },
  advToggleTxt: { color: '#7C9CFF', fontSize: 11, fontWeight: '800' },
  inscSection: { marginTop: 12, borderTopWidth: 1, borderTopColor: C.border, paddingTop: 8 },
  inscInput: { marginTop: 8, backgroundColor: C.alt, borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 9, color: C.text, fontSize: 14 },
  aiToggleTxt: { fontSize: 11, fontWeight: '900' },
  input: { color: C.text, backgroundColor: C.alt, borderRadius: 10, padding: 10, minHeight: 80, marginTop: 8, textAlignVertical: 'top', fontSize: 13 },
  inputSmall: { color: C.text, backgroundColor: C.alt, borderRadius: 10, padding: 10, fontSize: 13 },
  counter: { color: C.muted, fontSize: 10, textAlign: 'right', marginTop: 4 },
  primaryBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 14, borderRadius: 12, marginTop: 14 },
  primaryTxt: { color: '#0b0f1a', fontSize: 15, fontWeight: '900' },
  secondaryBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 12, borderRadius: 12, marginTop: 10, borderWidth: 1.5 },
  secondaryTxt: { fontSize: 14, fontWeight: '800' },
  vaultBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: C.alt, paddingHorizontal: 12, paddingVertical: 9, borderRadius: 10, borderWidth: 1, borderColor: C.border },
  vaultTxt: { color: C.text, fontSize: 12, fontWeight: '700' },
  status: { fontSize: 13, fontWeight: '700', marginTop: 12, textAlign: 'center' },
  capacity: { color: C.muted, fontSize: 11, textAlign: 'center', marginTop: 14 },
  partRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 8, backgroundColor: C.alt, borderRadius: 9, paddingHorizontal: 10, paddingVertical: 7 },
  partTxt: { color: C.text, fontSize: 12, fontWeight: '700' },
  partClear: { color: C.accent, fontSize: 12, fontWeight: '800' },
  browseBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderWidth: 1.5, borderRadius: 10, paddingVertical: 10, marginBottom: 4 },
  browseTxt: { fontSize: 13, fontWeight: '800' },
  gallery: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 },
  galleryCard: { width: '31%', backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border, overflow: 'hidden', paddingBottom: 6 },
  galleryPal: { flexDirection: 'row', height: 38 },
  galleryName: { color: C.text, fontSize: 10, fontWeight: '700', paddingHorizontal: 6, marginTop: 5 },
  galleryMore: { width: '100%', alignItems: 'center', paddingVertical: 10 },
});

