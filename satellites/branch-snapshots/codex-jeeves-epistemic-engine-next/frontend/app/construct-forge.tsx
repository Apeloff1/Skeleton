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
  text: '#eef2fb', muted: '#8a96b2', accent: '#6c8cff', construct: '#6c8cff',
  material: '#f1a208', good: '#43d39e',
};

export default function ConstructForge() {
  const router = useRouter();
  const sp = useLocalSearchParams<{ build?: string; game?: string }>();
  const [kind, setKind] = useState<'construct' | 'material'>('construct');
  const [era, setEra] = useState('modern');
  const [categories, setCategories] = useState<string[]>([]);
  const [category, setCategory] = useState<string | null>(null);
  const [spec, setSpec] = useState<any>(null);
  const [palette, setPalette] = useState<string[]>([]);
  const [selSwatch, setSelSwatch] = useState(0);
  const [prompt, setPrompt] = useState('');
  const [useLLM, setUseLLM] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedId, setSavedId] = useState<string | null>(null);
  const [buildId, setBuildId] = useState(String(sp?.build || sp?.game || ''));
  const [cap, setCap] = useState<any>(null);
  const [status, setStatus] = useState('');
  const [partColors, setPartColors] = useState<Record<number, string>>({});
  const [selectedPart, setSelectedPart] = useState<number | null>(null);
  const [presets, setPresets] = useState<any[]>([]);
  const [showPresets, setShowPresets] = useState(false);
  const [presetOffset, setPresetOffset] = useState(0);
  const [loadingPresets, setLoadingPresets] = useState(false);
  const accent = kind === 'construct' ? C.construct : C.material;

  const base = `${API}/api/galaxy-studio/${kind === 'construct' ? 'constructs' : 'materials'}`;

  const loadMeta = useCallback(async () => {
    try {
      const r = await apiFetch(`${base}/presets?era=${era}&limit=1`, { timeoutMs: 20000 });
      const d = await r.json();
      setCategories(d.categories || []);
      const c = await apiFetch(`${base}/capacity`, { timeoutMs: 15000 });
      setCap(await c.json());
    } catch { /* ignore */ }
  }, [base, era]);

  useEffect(() => { loadMeta(); }, [loadMeta]);

  const generate = useCallback(async () => {
    setBusy(true); setStatus(''); setSavedId(null);
    try {
      const body = JSON.stringify({ era, category, use_llm: useLLM, user_prompt: prompt });
      const r = await apiFetch(`${base}/generate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body,
        timeoutMs: useLLM ? 90000 : 25000,
      });
      const d = await r.json();
      setSpec(d);
      setPalette(d.palette || []);
      setSelSwatch(0); setPartColors({}); setSelectedPart(null);
      setStatus(d.llm_enriched ? '✨ AI-enriched' : 'Generated');
    } catch {
      setStatus('Generate failed');
    } finally { setBusy(false); }
  }, [base, era, category, useLLM, prompt]);

  const assignColor = useCallback((color: string) => {
    if (selectedPart !== null) {
      setPartColors((m) => ({ ...m, [selectedPart]: color }));
      return;
    }
    if (!palette.length) return;
    const next = [...palette];
    next[selSwatch % next.length] = color;
    setPalette(next);
    setSpec((s: any) => (s ? { ...s, palette: next } : s));
  }, [palette, selSwatch, selectedPart]);

  const loadPresets = useCallback(async (off = 0) => {
    setLoadingPresets(true);
    try {
      const r = await apiFetch(`${base}/presets?era=${era}&offset=${off}&limit=60${category ? `&category=${category}` : ''}`, { timeoutMs: 20000 });
      const d = await r.json();
      setPresets(d.presets || []);
      setPresetOffset(off);
      setShowPresets(true);
    } catch { setStatus('Could not load presets'); } finally { setLoadingPresets(false); }
  }, [base, era, category]);

  const loadPreset = useCallback((p: any) => {
    setSpec({ ...p, llm_enriched: false });
    setPalette(p.palette || []);
    setSelSwatch(0); setPartColors({}); setSelectedPart(null);
    setShowPresets(false);
    setStatus(`Loaded preset · ${p.name}`);
  }, []);

  // ── Saved Library (browse / re-open / bulk mount) ──
  const [showLib, setShowLib] = useState(false);
  const [libItems, setLibItems] = useState<any[]>([]);
  const [libSel, setLibSel] = useState<Record<string, boolean>>({});
  const [libBuild, setLibBuild] = useState('');
  const loadLibrary = useCallback(async () => {
    try {
      const r = await apiFetch(`${base}/list?limit=100`, { timeoutMs: 20000 });
      const d = await r.json();
      setLibItems(d.items || []);
    } catch { setStatus('Could not load library'); }
  }, [base]);
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
      const d = await r.json();
      setSavedId(d.construct_id);
      setStatus(`Saved ✓ ${d.construct_id}`);
      loadMeta();
    } catch { setStatus('Save failed'); } finally { setSaving(false); }
  }, [base, spec, palette, partColors, savedId, loadMeta]);

  const vaultAction = useCallback(async (action: 'mount' | 'save-to-gamefiles' | 'extract') => {
    if (action !== 'extract' && (!savedId || !buildId.trim())) {
      Alert.alert('Need a build', 'Save the asset and enter a Build ID first.');
      return;
    }
    if (action === 'extract' && !buildId.trim()) {
      Alert.alert('Need a build', 'Enter a Build ID to extract from.');
      return;
    }
    setStatus('');
    try {
      let r;
      if (action === 'extract') {
        r = await apiFetch(`${base}/extract/${encodeURIComponent(buildId.trim())}`, { timeoutMs: 20000 });
        const d = await r.json();
        setStatus(`Extracted ${d.extracted} asset(s) from Vault`);
      } else {
        r = await apiFetch(`${base}/${action}`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ construct_ids: [savedId], build_id: buildId.trim() }),
          timeoutMs: 20000,
        });
        const d = await r.json();
        setStatus(action === 'mount' ? `Mounted ${d.mounted} to Vault ✓` : `Wrote ${d.gamefiles} gamefile(s) ✓`);
      }
    } catch { setStatus(`${action} failed`); }
  }, [base, savedId, buildId]);

  const Chip = ({ active, label, onPress, color }: any) => (
    <TouchableOpacity onPress={onPress} activeOpacity={0.85}
      style={[styles.chip, { borderColor: active ? (color || accent) : C.border, backgroundColor: active ? (color || accent) + '22' : 'transparent' }]}>
      <Text style={[styles.chipTxt, { color: active ? (color || accent) : C.muted }]}>{label}</Text>
    </TouchableOpacity>
  );

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.iconBtn} testID="cf-back">
          <Ionicons name="chevron-back" size={22} color={C.text} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>{kind === 'construct' ? '🏰 Construct Forge' : '🧱 Material Forge'}</Text>
          <Text style={styles.sub}>Large {kind === 'construct' ? 'structures' : 'surfaces'} · 504 presets/era · 3D viewport</Text>
        </View>
        <TouchableOpacity onPress={() => { const n = !showLib; setShowLib(n); if (n) loadLibrary(); }} style={styles.iconBtn} testID="cf-library-toggle">
          <Ionicons name={showLib ? 'hammer' : 'albums'} size={19} color={showLib ? C.accent : C.text} />
        </TouchableOpacity>
      </View>

      {/* Kind toggle */}
      <View style={styles.toggleRow}>
        {(['construct', 'material'] as const).map((k) => (
          <TouchableOpacity key={k} onPress={() => { setKind(k); setSpec(null); setSavedId(null); setCategory(null); }}
            activeOpacity={0.85}
            style={[styles.toggle, { backgroundColor: kind === k ? (k === 'construct' ? C.construct : C.material) : C.alt }]}
            testID={`cf-kind-${k}`}>
            <Text style={[styles.toggleTxt, { color: kind === k ? '#0b0f1a' : C.muted }]}>
              {k === 'construct' ? 'Construct' : 'Material'}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 14, paddingBottom: 60 }}>
        {showLib ? (
          <View testID="cf-library">
            <Text style={styles.sectionLabel}>Saved library — select assets, then bulk-mount to a build</Text>
            <TextInput value={libBuild} onChangeText={setLibBuild} placeholder="Build ID to mount selected into"
              placeholderTextColor={C.muted} style={styles.inputSmall} testID="cf-lib-build" autoCapitalize="none" />
            <TouchableOpacity onPress={bulkMount} activeOpacity={0.85}
              style={[styles.primaryBtn, { backgroundColor: accent, marginTop: 10, opacity: Object.values(libSel).filter(Boolean).length ? 1 : 0.5 }]}
              testID="cf-lib-mount">
              <Ionicons name="git-merge-outline" size={17} color="#0b0f1a" />
              <Text style={styles.primaryTxt}>Mount {Object.values(libSel).filter(Boolean).length} selected</Text>
            </TouchableOpacity>
            {libItems.length === 0 ? (
              <View style={styles.emptyView}>
                <Ionicons name="albums-outline" size={40} color={C.muted} />
                <Text style={styles.emptyTxt}>No saved {kind}s yet — forge & save one</Text>
              </View>
            ) : (
              <View style={styles.gallery}>
                {libItems.map((it) => {
                  const id = it.construct_id || it.id;
                  const sel = !!libSel[id];
                  return (
                    <TouchableOpacity key={id} onPress={() => setLibSel((m) => ({ ...m, [id]: !m[id] }))}
                      activeOpacity={0.85} style={[styles.galleryCard, sel ? { borderColor: accent, borderWidth: 2 } : null]}
                      testID={`cf-lib-${id}`}>
                      <View style={styles.galleryPal}>
                        {(it.palette || []).slice(0, 4).map((c: string, i: number) => (
                          <View key={i} style={{ flex: 1, backgroundColor: c }} />
                        ))}
                      </View>
                      <Text style={styles.galleryName} numberOfLines={1}>{sel ? '✓ ' : ''}{it.name}</Text>
                      <Text style={styles.galleryCat} numberOfLines={1}>{(it.category || '').replace(/_/g, ' ')}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            )}
            {status ? <Text style={[styles.status, { color: status.includes('failed') ? '#ff6b6b' : C.good }]} testID="cf-status">{status}</Text> : null}
          </View>
        ) : (
        <>
        {/* Era */}
        <Text style={styles.sectionLabel}>Era</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 10 }}>
          {ERAS.map((e) => <Chip key={e.key} active={era === e.key} label={e.label} onPress={() => setEra(e.key)} />)}
        </ScrollView>

        {/* Category */}
        <Text style={styles.sectionLabel}>Category</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 12 }}>
          <Chip active={!category} label="Surprise me" onPress={() => setCategory(null)} color={C.good} />
          {categories.slice(0, 42).map((c) => (
            <Chip key={c} active={category === c} label={c.replace(/_/g, ' ')} onPress={() => setCategory(c)} />
          ))}
        </ScrollView>

        <TouchableOpacity onPress={() => (showPresets ? setShowPresets(false) : loadPresets(0))}
          activeOpacity={0.85} style={[styles.browseBtn, { borderColor: accent }]} testID="cf-browse-presets">
          {loadingPresets ? <ActivityIndicator size="small" color={accent} />
            : <Ionicons name="grid-outline" size={16} color={accent} />}
          <Text style={[styles.browseTxt, { color: accent }]}>
            {showPresets ? 'Hide preset gallery' : 'Browse 504 presets / era'}
          </Text>
        </TouchableOpacity>

        {showPresets && (
          <View style={styles.gallery}>
            {presets.map((p) => (
              <TouchableOpacity key={p.preset_id} onPress={() => loadPreset(p)} activeOpacity={0.85}
                style={styles.galleryCard} testID={`cf-preset-${p.preset_id}`}>
                <View style={styles.galleryPal}>
                  {(p.palette || []).slice(0, 4).map((c: string, i: number) => (
                    <View key={i} style={{ flex: 1, backgroundColor: c }} />
                  ))}
                </View>
                <Text style={styles.galleryName} numberOfLines={1}>{p.name}</Text>
                <Text style={styles.galleryCat} numberOfLines={1}>{p.category.replace(/_/g, ' ')}</Text>
              </TouchableOpacity>
            ))}
            {presets.length >= 60 && (
              <TouchableOpacity onPress={() => loadPresets(presetOffset + 60)} style={styles.galleryMore} testID="cf-presets-more">
                <Text style={[styles.browseTxt, { color: accent }]}>Load more →</Text>
              </TouchableOpacity>
            )}
          </View>
        )}

        {/* 3D viewport */}
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
                <TouchableOpacity onPress={() => setSelectedPart(null)} testID="cf-clear-part">
                  <Text style={styles.partClear}>↺ Whole model</Text>
                </TouchableOpacity>
              </View>
            )}
            <Text style={styles.specName}>{spec.name}</Text>
            <Text style={styles.specDesc} numberOfLines={3}>{spec.descriptor}</Text>
          </>
        ) : (
          <View style={styles.emptyView}>
            <Ionicons name="cube-outline" size={40} color={C.muted} />
            <Text style={styles.emptyTxt}>Generate a {kind} to preview it in 3D</Text>
          </View>
        )}

        {/* Palette editor */}
        {palette.length > 0 && (
          <View style={styles.editCard}>
            <Text style={styles.sectionLabel}>Colour edit — tap a slot, then pick a colour (live)</Text>
            <View style={styles.swatchRow}>
              {palette.map((c, i) => (
                <TouchableOpacity key={i} onPress={() => setSelSwatch(i)} activeOpacity={0.8}
                  style={[styles.swatch, { backgroundColor: c, borderColor: selSwatch === i ? C.text : '#00000040', borderWidth: selSwatch === i ? 3 : 1 }]}
                  testID={`cf-swatch-${i}`} />
              ))}
            </View>
            <View style={styles.paletteGrid}>
              {SWATCHES.map((c) => (
                <TouchableOpacity key={c} onPress={() => assignColor(c)} activeOpacity={0.8}
                  style={[styles.pgSwatch, { backgroundColor: c }]} testID={`cf-color-${c}`} />
              ))}
            </View>
          </View>
        )}

        {/* AI brief */}
        <View style={styles.editCard}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <Text style={styles.sectionLabel}>AI brief (Claude Sonnet 4.6 · up to 20,000 chars)</Text>
            <TouchableOpacity onPress={() => setUseLLM((v) => !v)} testID="cf-ai-toggle"
              style={[styles.aiToggle, { backgroundColor: useLLM ? accent : C.alt }]}>
              <Text style={[styles.aiToggleTxt, { color: useLLM ? '#0b0f1a' : C.muted }]}>{useLLM ? 'AI ON' : 'AI OFF'}</Text>
            </TouchableOpacity>
          </View>
          <TextInput
            value={prompt} onChangeText={(t) => setPrompt(t.slice(0, 20000))}
            placeholder="Describe the construct/material… (palette, materials, mood, VFX). 20k chars."
            placeholderTextColor={C.muted} multiline
            style={styles.input} testID="cf-prompt" maxLength={20000}
          />
          <Text style={styles.counter}>{prompt.length.toLocaleString()} / 20,000</Text>
        </View>

        {/* Actions */}
        <TouchableOpacity onPress={generate} disabled={busy} activeOpacity={0.85}
          style={[styles.primaryBtn, { backgroundColor: accent, opacity: busy ? 0.6 : 1 }]} testID="cf-generate">
          {busy ? <ActivityIndicator color="#0b0f1a" /> : <Ionicons name="sparkles" size={18} color="#0b0f1a" />}
          <Text style={styles.primaryTxt}>{busy ? 'Forging…' : useLLM ? 'Generate with AI' : 'Generate'}</Text>
        </TouchableOpacity>

        {spec && (
          <TouchableOpacity onPress={save} disabled={saving} activeOpacity={0.85}
            style={[styles.secondaryBtn, { borderColor: C.good }]} testID="cf-save">
            {saving ? <ActivityIndicator color={C.good} /> : <Ionicons name="save-outline" size={17} color={C.good} />}
            <Text style={[styles.secondaryTxt, { color: C.good }]}>{savedId ? 'Update saved asset' : 'Save asset'}</Text>
          </TouchableOpacity>
        )}

        {/* Vault connection */}
        {savedId && (
          <View style={styles.editCard}>
            <Text style={styles.sectionLabel}>Vault connection</Text>
            <TextInput value={buildId} onChangeText={setBuildId} placeholder="Build ID (to mount / extract)"
              placeholderTextColor={C.muted} style={styles.inputSmall} testID="cf-build-id" autoCapitalize="none" />
            <View style={{ flexDirection: 'row', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
              <TouchableOpacity onPress={() => vaultAction('mount')} style={styles.vaultBtn} testID="cf-mount">
                <Ionicons name="git-merge-outline" size={15} color={C.text} /><Text style={styles.vaultTxt}>Mount</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => vaultAction('save-to-gamefiles')} style={styles.vaultBtn} testID="cf-gamefiles">
                <Ionicons name="file-tray-full-outline" size={15} color={C.text} /><Text style={styles.vaultTxt}>Save to gamefiles</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => vaultAction('extract')} style={styles.vaultBtn} testID="cf-extract">
                <Ionicons name="download-outline" size={15} color={C.text} /><Text style={styles.vaultTxt}>Extract</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {status ? <Text style={[styles.status, { color: status.includes('failed') ? '#ff6b6b' : C.good }]} testID="cf-status">{status}</Text> : null}

        {cap && (
          <Text style={styles.capacity}>
            Store: {(cap[kind] || 0).toLocaleString()} / {(cap.capacity || 0).toLocaleString()} {kind}s
          </Text>
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
  title: { color: C.text, fontSize: 19, fontWeight: '900' },
  sub: { color: C.muted, fontSize: 11, marginTop: 1 },
  toggleRow: { flexDirection: 'row', gap: 8, paddingHorizontal: 14, marginBottom: 4 },
  toggle: { flex: 1, paddingVertical: 9, borderRadius: 10, alignItems: 'center' },
  toggleTxt: { fontWeight: '800', fontSize: 13 },
  sectionLabel: { color: C.muted, fontSize: 12, fontWeight: '800', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.4 },
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
  galleryCat: { color: C.muted, fontSize: 9, paddingHorizontal: 6, textTransform: 'capitalize' },
  galleryMore: { width: '100%', alignItems: 'center', paddingVertical: 10 },
});
