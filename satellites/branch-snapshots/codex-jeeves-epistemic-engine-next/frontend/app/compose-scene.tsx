import React, { useState, useCallback, useEffect, useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator, TextInput, Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { apiFetch } from '../utils/apiController';
import { lazyDefault, LazyMount } from '../src/utils/lazyMount';
const Construct3DView = lazyDefault(() => import('../src/components/Construct3DView'));

const API = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const C = {
  bg: '#0b0f1a', card: '#141b2e', alt: '#1b2438', border: '#2a3550',
  text: '#eef2fb', muted: '#8a96b2', accent: '#34D399', accent2: '#A78BFA',
};
const ERAS = [
  { key: '8bit', label: '8-Bit' }, { key: '16bit', label: '16-Bit' },
  { key: 'modern', label: 'Modern' }, { key: 'nextgen', label: 'Next-Gen' },
];
// One-tap themed recipes
const RECIPES: { key: string; icon: string; name: string; items: { category: string; count: number }[] }[] = [
  { key: 'forest', icon: '🌲', name: 'Enchanted Forest', items: [{ category: 'tree', count: 12 }, { category: 'critter', count: 5 }, { category: 'boulder', count: 4 }, { category: 'plant', count: 6 }] },
  { key: 'village', icon: '🏘️', name: 'Walled Village', items: [{ category: 'house', count: 8 }, { category: 'npc', count: 6 }, { category: 'chest', count: 3 }, { category: 'tree', count: 5 }] },
  { key: 'squad', icon: '🛡️', name: 'Hero Squad', items: [{ category: 'character', count: 4 }, { category: 'sword', count: 4 }, { category: 'potion', count: 3 }] },
  { key: 'armory', icon: '⚔️', name: 'Armory', items: [{ category: 'sword', count: 5 }, { category: 'axe', count: 3 }, { category: 'bow', count: 3 }, { category: 'chest', count: 4 }] },
  { key: 'feast', icon: '🍞', name: 'Tavern Feast', items: [{ category: 'table', count: 3 }, { category: 'bread', count: 4 }, { category: 'cake', count: 2 }, { category: 'barrel', count: 4 }] },
  { key: 'lab', icon: '🤖', name: 'Robotics Lab', items: [{ category: 'robot', count: 4 }, { category: 'machine', count: 3 }, { category: 'crate', count: 5 }, { category: 'turret', count: 2 }] },
  { key: 'garden', icon: '🌸', name: 'Botanical Garden', items: [{ category: 'tree', count: 6 }, { category: 'rose_bush', count: 5 }, { category: 'sunflower', count: 5 }, { category: 'mushroom', count: 4 }, { category: 'fountain', count: 1 }] },
  { key: 'shrine', icon: '⛩️', name: 'Sacred Shrine', items: [{ category: 'shrine', count: 2 }, { category: 'altar', count: 1 }, { category: 'obelisk', count: 2 }, { category: 'torch', count: 4 }, { category: 'banner', count: 4 }] },
  { key: 'dungeon', icon: '🗝️', name: 'Dungeon Crawl', items: [{ category: 'chest', count: 4 }, { category: 'spike_trap', count: 4 }, { category: 'bat', count: 4 }, { category: 'torch', count: 5 }, { category: 'door', count: 3 }] },
  { key: 'treasury', icon: '💎', name: 'Royal Treasury', items: [{ category: 'gold_coin', count: 6 }, { category: 'diamond', count: 4 }, { category: 'chest', count: 4 }, { category: 'medallion', count: 4 }] },
];

export default function ComposeScene() {
  const router = useRouter();
  const [cats, setCats] = useState<any[]>([]);
  const [buildId, setBuildId] = useState('demo_build');
  const [era, setEra] = useState('modern');
  const [picks, setPicks] = useState<{ category: string; label: string; count: number }[]>([]);
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [diorama, setDiorama] = useState<any[]>([]);
  const [styleOpts, setStyleOpts] = useState<any>(null);
  const [skinStyle, setSkinStyle] = useState<string>('');
  const [makeVariants, setMakeVariants] = useState(false);
  const [axes, setAxes] = useState<Record<string, string>>({});
  const [treatment, setTreatment] = useState<string>('none');
  const [axisQuery, setAxisQuery] = useState('');

  useEffect(() => {
    (async () => {
      const [c, s] = await Promise.allSettled([
        apiFetch(`${API}/api/galaxy-studio/forge/catalog`, { timeoutMs: 20000 }),
        apiFetch(`${API}/api/galaxy-studio/forge/styles`, { timeoutMs: 15000 }),
      ]);
      try { if (c.status === 'fulfilled') setCats((await c.value.json()).categories || []); } catch { /* ignore */ }
      try { if (s.status === 'fulfilled') setStyleOpts(await s.value.json()); } catch { /* ignore */ }
    })();
  }, []);

  const surprise = useCallback(() => {
    if (!styleOpts?.skin_styles?.length) return;
    const pick = (a: any[]) => a[Math.floor(Math.random() * a.length)];
    setSkinStyle(pick(styleOpts.skin_styles).key);
    const pool = [...(styleOpts.axes || [])].sort(() => Math.random() - 0.5)
      .slice(0, 4 + Math.floor(Math.random() * 5));
    const nextAxes: Record<string, string> = {};
    pool.forEach((ax: any) => { nextAxes[ax.key] = pick(ax.options).key; });
    setAxes(nextAxes);
    const treats = (styleOpts.treatments || []).filter((t: any) => t.key !== 'none');
    setTreatment(treats.length ? pick(treats).key : 'none');
    setMakeVariants(true);
  }, [styleOpts]);

  const applyPack = useCallback((p: any) => {
    setSkinStyle(p.skin_style || '');
    setAxes(p.axes || {});
    setTreatment(p.treatment || 'none');
    setMakeVariants(true);
  }, []);

  const labelFor = useCallback((key: string) => (cats.find((c) => c.key === key)?.label || key.replace(/_/g, ' ')), [cats]);

  const searchResults = useMemo(() => {
    if (!q.trim()) return [];
    const s = q.trim().toLowerCase();
    return cats.filter((c) => c.label.toLowerCase().includes(s) || c.key.includes(s)).slice(0, 12);
  }, [q, cats]);

  const [remoteResults, setRemoteResults] = useState<any[]>([]);
  useEffect(() => {
    const s = q.trim();
    if (!s) { setRemoteResults([]); return; }
    const t = setTimeout(async () => {
      try {
        const r = await apiFetch(`${API}/api/galaxy-studio/forge/search?q=${encodeURIComponent(s)}&limit=24`, { timeoutMs: 12000 });
        setRemoteResults((await r.json()).results || []);
      } catch { setRemoteResults([]); }
    }, 250);
    return () => clearTimeout(t);
  }, [q]);
  const allResults = remoteResults.length ? remoteResults : searchResults;

  const addPick = useCallback((category: string, label: string) => {
    setPicks((p) => p.find((x) => x.category === category) ? p : [...p, { category, label, count: 4 }]);
    setQ('');
  }, []);
  const setCount = useCallback((category: string, delta: number) => {
    setPicks((p) => p.map((x) => x.category === category ? { ...x, count: Math.max(1, Math.min(50, x.count + delta)) } : x));
  }, []);
  const removePick = useCallback((category: string) => setPicks((p) => p.filter((x) => x.category !== category)), []);

  const applyRecipe = useCallback((r: typeof RECIPES[number]) => {
    setPicks(r.items.map((i) => ({ category: i.category, label: labelFor(i.category), count: i.count })));
  }, [labelFor]);

  const totalAssets = picks.reduce((a, p) => a + p.count, 0);

  const compose = useCallback(async () => {
    if (!picks.length || !buildId.trim()) { Alert.alert('Add items + Build ID', 'Pick at least one category and enter a Build ID.'); return; }
    setBusy(true); setResult(null);
    try {
      const r = await apiFetch(`${API}/api/galaxy-studio/forge/compose`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          build_id: buildId.trim(), era,
          items: picks.map((p) => ({ category: p.category, count: p.count })),
          style: (skinStyle || Object.keys(axes).length || treatment !== 'none')
            ? { skin_style: skinStyle || undefined, axes,
                treatment: treatment === 'none' ? undefined : treatment }
            : null,
          variants: makeVariants ? 1 : 0,
          region: makeVariants ? (skinStyle || 'scene') : null,
        }),
        timeoutMs: 60000,
      });
      setResult(await r.json());
      // Build a 3D diorama from the freshly-forged assets laid on a ground plane.
      try {
        const lr = await apiFetch(`${API}/api/galaxy-studio/forge/list?build_id=${encodeURIComponent(buildId.trim())}&limit=25`, { timeoutMs: 20000 });
        const ld = await lr.json();
        const assets = (ld.items || []).slice(0, 25);
        // family -> diorama region anchor pulled from backend (one source)
        let REG: Record<string, number[]> = {};
        try {
          const sr = await apiFetch(`${API}/api/galaxy-studio/forge/styles`, { timeoutMs: 15000 });
          REG = (await sr.json()).regions || {};
        } catch { REG = {}; }
        const perFam: Record<string, number> = {};
        const merged: any[] = [{ type: 'plane', pos: [0, -0.1, 0], size: [40, 0.2, 40], color: '#1b2438' }];
        assets.forEach((a: any) => {
          const fam = a.family || a.kind || 'structure';
          const anchor = REG[fam] || [0, 0];
          const k = perFam[fam] || 0; perFam[fam] = k + 1;
          const ang = (k * 2.39996) % 6.28318;
          const rad = 1.6 + (k % 4);
          const gx = anchor[0] + rad * Math.cos(ang);
          const gz = anchor[1] + rad * Math.sin(ang);
          (a.geometry || []).forEach((p: any) => merged.push({
            ...p, pos: [(p.pos?.[0] || 0) + gx, p.pos?.[1] || 0, (p.pos?.[2] || 0) + gz],
            // auto-color: fold the asset's skin surface into each part so neon/
            // glowing skins emit light and variants pop with their decals.
            metalness: p.metalness ?? a.surface?.metalness,
            roughness: p.roughness ?? a.surface?.roughness,
            emissive: p.emissive ?? (a.variant ? Math.max(0.22, a.surface?.emissive || 0) : (a.surface?.emissive || 0)),
          }));
        });
        setDiorama(merged);
      } catch { /* diorama is best-effort */ }
    } catch { Alert.alert('Compose failed', 'Please try again.'); } finally { setBusy(false); }
  }, [picks, buildId, era, skinStyle, makeVariants, axes, treatment]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.iconBtn} testID="cs-back">
          <Ionicons name="chevron-back" size={22} color={C.text} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>🌍 Compose a Scene</Text>
          <Text style={styles.sub}>Populate a build with a themed mix — forged & mounted in one tap</Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={{ padding: 14, paddingBottom: 60 }}>
        <Text style={styles.lbl}>Build ID</Text>
        <TextInput value={buildId} onChangeText={setBuildId} style={styles.input} placeholder="build id"
          placeholderTextColor={C.muted} testID="cs-build" autoCapitalize="none" />

        <Text style={styles.lbl}>Era</Text>
        <View style={styles.chipWrap}>
          {ERAS.map((e) => (
            <TouchableOpacity key={e.key} onPress={() => setEra(e.key)} style={[styles.chip, era === e.key && { borderColor: C.accent2, backgroundColor: C.accent2 + '22' }]}>
              <Text style={[styles.chipTxt, era === e.key && { color: C.accent2 }]}>{e.label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={styles.lbl}>Quick recipes</Text>
        <View style={styles.chipWrap}>
          {RECIPES.map((r) => (
            <TouchableOpacity key={r.key} onPress={() => applyRecipe(r)} style={styles.recipe} testID={`cs-recipe-${r.key}`}>
              <Text style={styles.recipeIcon}>{r.icon}</Text>
              <Text style={styles.recipeName}>{r.name}</Text>
              <Text style={styles.recipeMeta}>{r.items.reduce((a, i) => a + i.count, 0)} assets</Text>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={styles.lbl}>Art direction</Text>
        {styleOpts && (
          <View style={styles.styleCard} testID="cs-style">
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <Text style={styles.styleHint}>Coherent skin applied to every asset in the scene</Text>
              <TouchableOpacity onPress={surprise} style={styles.surpriseBtn} testID="cs-surprise">
                <Text style={styles.surpriseTxt}>🎲 Surprise me</Text>
              </TouchableOpacity>
            </View>
            <View style={styles.chipWrap}>
              <TouchableOpacity onPress={() => setSkinStyle('')} style={[styles.chip, !skinStyle && { borderColor: C.accent, backgroundColor: C.accent + '22' }]}>
                <Text style={[styles.chipTxt, !skinStyle && { color: C.accent }]}>Auto</Text>
              </TouchableOpacity>
              {(styleOpts.skin_styles || []).map((s: any) => (
                <TouchableOpacity key={s.key} onPress={() => setSkinStyle(s.key)} style={[styles.chip, skinStyle === s.key && { borderColor: C.accent, backgroundColor: C.accent + '22' }]} testID={`cs-skin-${s.key}`}>
                  <Text style={[styles.chipTxt, skinStyle === s.key && { color: C.accent }]}>{s.label}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <TouchableOpacity onPress={() => setMakeVariants((v) => !v)} activeOpacity={0.85}
              style={[styles.variantRow, makeVariants && { borderColor: C.accent2, backgroundColor: C.accent2 + '18' }]} testID="cs-variants">
              <Ionicons name={makeVariants ? 'checkbox' : 'square-outline'} size={18} color={makeVariants ? C.accent2 : C.muted} />
              <Text style={[styles.variantTxt, makeVariants && { color: C.accent2 }]}>Agents also forge region-specific variants</Text>
            </TouchableOpacity>

            {(styleOpts.style_packs || []).length > 0 && (
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: 10 }}>
                {styleOpts.style_packs.map((p: any) => (
                  <TouchableOpacity key={p.key} onPress={() => applyPack(p)} style={styles.pack} testID={`cs-pack-${p.key}`}>
                    <Text style={styles.packIcon}>{p.icon}</Text>
                    <Text style={styles.packTxt}>{p.label}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            )}

            <View style={{ marginTop: 8 }}>
              <Text style={styles.axisLbl}>Style axes · {(styleOpts.axes || []).length} dimensions{Object.keys(axes).length ? ` · ${Object.keys(axes).length} active` : ''}</Text>
              <TextInput value={axisQuery} onChangeText={setAxisQuery} placeholder="filter axes…"
                placeholderTextColor={C.muted} style={styles.axisFilter} testID="cs-axis-filter" />
            </View>
            {(() => {
              const all = styleOpts.axes || [];
              const ql = axisQuery.trim().toLowerCase();
              const activeKeys = Object.keys(axes);
              const shown = ql ? all.filter((a: any) => a.label.toLowerCase().includes(ql)) : all.slice(0, 6);
              const map = new Map(shown.map((a: any) => [a.key, a]));
              all.forEach((a: any) => { if (activeKeys.includes(a.key)) map.set(a.key, a); });
              const list = Array.from(map.values());
              return (
                <>
                  {list.map((ax: any) => (
                    <View key={ax.key}>
                      <Text style={styles.axisLbl}>{ax.label}{axes[ax.key] ? ' ✓' : ''}</Text>
                      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                        <TouchableOpacity onPress={() => setAxes((m) => { const n = { ...m }; delete n[ax.key]; return n; })}
                          style={[styles.chip, !axes[ax.key] && { borderColor: C.accent, backgroundColor: C.accent + '22' }]}>
                          <Text style={[styles.chipTxt, !axes[ax.key] && { color: C.accent }]}>None</Text>
                        </TouchableOpacity>
                        {ax.options.map((o: any) => (
                          <TouchableOpacity key={o.key} onPress={() => setAxes((m) => ({ ...m, [ax.key]: o.key }))}
                            style={[styles.chip, { marginLeft: 8 }, axes[ax.key] === o.key && { borderColor: C.accent, backgroundColor: C.accent + '22' }]}
                            testID={`cs-axis-${ax.key}-${o.key}`}>
                            <Text style={[styles.chipTxt, axes[ax.key] === o.key && { color: C.accent }]}>{o.label}</Text>
                          </TouchableOpacity>
                        ))}
                      </ScrollView>
                    </View>
                  ))}
                  {!ql && all.length > list.length && (
                    <Text style={styles.axisMore}>+ {all.length - list.length} more axes — type above to filter</Text>
                  )}
                </>
              );
            })()}

            {(styleOpts.treatments || []).length > 0 && (
              <>
                <Text style={styles.axisLbl}>Region treatment</Text>
                <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                  {styleOpts.treatments.map((t: any, i: number) => (
                    <TouchableOpacity key={t.key} onPress={() => setTreatment(t.key)}
                      style={[styles.chip, i > 0 && { marginLeft: 8 }, treatment === t.key && { borderColor: C.accent2, backgroundColor: C.accent2 + '22' }]}
                      testID={`cs-treat-${t.key}`}>
                      <Text style={[styles.chipTxt, treatment === t.key && { color: C.accent2 }]}>{t.label}</Text>
                    </TouchableOpacity>
                  ))}
                </ScrollView>
              </>
            )}
          </View>
        )}

        <Text style={styles.lbl}>Add categories</Text>
        <View style={styles.searchRow}>
          <Ionicons name="search" size={15} color={C.muted} />
          <TextInput value={q} onChangeText={setQ} placeholder="search 100,000+ forges — molten dragon, gilded sword…"
            placeholderTextColor={C.muted} style={styles.search} testID="cs-search" autoCapitalize="none" />
        </View>
        {allResults.length > 0 && (
          <View style={styles.chipWrap}>
            {allResults.map((c) => (
              <TouchableOpacity key={c.key} onPress={() => addPick(c.key, c.label)} style={styles.addChip} testID={`cs-add-${c.key}`}>
                <Ionicons name="add" size={13} color={C.accent} />
                <Text style={styles.addChipTxt}>{c.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        )}

        {/* Scene cart */}
        <Text style={styles.lbl}>Scene · {picks.length} types · {totalAssets} assets</Text>
        {picks.length === 0 ? (
          <View style={styles.empty}><Ionicons name="albums-outline" size={34} color={C.muted} />
            <Text style={styles.emptyTxt}>Pick a recipe or add categories above</Text></View>
        ) : picks.map((p) => (
          <View key={p.category} style={styles.cartRow} testID={`cs-pick-${p.category}`}>
            <Text style={styles.cartName} numberOfLines={1}>{p.label}</Text>
            <TouchableOpacity onPress={() => setCount(p.category, -1)} style={styles.stepBtn}><Ionicons name="remove" size={16} color={C.text} /></TouchableOpacity>
            <Text style={styles.cartCount}>{p.count}</Text>
            <TouchableOpacity onPress={() => setCount(p.category, 1)} style={styles.stepBtn} testID={`cs-inc-${p.category}`}><Ionicons name="add" size={16} color={C.text} /></TouchableOpacity>
            <TouchableOpacity onPress={() => removePick(p.category)} style={styles.delBtn}><Ionicons name="trash-outline" size={15} color="#ff6b6b" /></TouchableOpacity>
          </View>
        ))}

        <TouchableOpacity onPress={compose} disabled={busy} activeOpacity={0.85}
          style={[styles.primaryBtn, { opacity: busy ? 0.6 : 1 }]} testID="cs-compose">
          {busy ? <ActivityIndicator color="#0b0f1a" /> : <Ionicons name="color-wand" size={18} color="#0b0f1a" />}
          <Text style={styles.primaryTxt}>{busy ? 'Composing scene…' : `Compose & mount ${totalAssets} assets`}</Text>
        </TouchableOpacity>

        {diorama.length > 0 && (
          <View style={styles.dioCard} testID="cs-diorama">
            <Text style={styles.dioHead}>🏞️ Scene diorama — your forged assets, laid out</Text>
            <View style={styles.dioWrap}>
              <LazyMount><Construct3DView geometry={diorama} palette={[]} height={240} /></LazyMount>
            </View>
          </View>
        )}

        {result && (
          <View style={styles.resultCard} testID="cs-result">
            <Text style={styles.resultHead}>✨ Scene composed · {result.total} assets mounted to {result.build_id}</Text>
            <Text style={styles.resultSub}>{result.era_label} era{result.variants ? ` · ${result.primary} primary + ${result.variants} region variants` : ''}{result.style?.skin_style ? ` · ${result.style.skin_style} skin` : ''}</Text>
            <View style={styles.chipWrap}>
              {(result.composed || []).map((c: any) => (
                <View key={c.category} style={styles.resChip}><Text style={styles.resChipTxt}>{c.label} ·{c.count}</Text></View>
              ))}
            </View>
            {(result.by_region || []).length > 0 && (
              <View style={{ marginTop: 10 }}>
                <Text style={styles.axisLbl}>By region</Text>
                {result.by_region.map((r: any) => (
                  <View key={r.family} style={styles.regionRow}>
                    <View style={[styles.regionDot, { backgroundColor: r.accent || '#888' }]} />
                    <Text style={styles.regionName}>{r.family}</Text>
                    <Text style={styles.regionMeta}>{r.primary} primary{r.variants ? ` · ${r.variants} ${r.treatment} variants` : ''}</Text>
                  </View>
                ))}
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
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 10, gap: 8 },
  iconBtn: { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center', backgroundColor: C.alt },
  title: { color: C.text, fontSize: 18, fontWeight: '900' },
  sub: { color: C.muted, fontSize: 11, marginTop: 1 },
  lbl: { color: C.muted, fontSize: 12, fontWeight: '800', marginTop: 16, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.4 },
  input: { color: C.text, backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 11, fontSize: 14 },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 18, borderWidth: 1, borderColor: C.border, backgroundColor: C.card },
  chipTxt: { color: C.muted, fontSize: 12, fontWeight: '700' },
  recipe: { width: '31%', backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, padding: 10, alignItems: 'center' },
  recipeIcon: { fontSize: 24 },
  recipeName: { color: C.text, fontSize: 11, fontWeight: '800', marginTop: 4, textAlign: 'center' },
  recipeMeta: { color: C.accent, fontSize: 10, fontWeight: '700', marginTop: 2 },
  searchRow: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, paddingHorizontal: 12 },
  search: { flex: 1, color: C.text, paddingVertical: 10, fontSize: 14 },
  addChip: { flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: C.alt, borderRadius: 16, borderWidth: 1, borderColor: C.accent + '55', paddingHorizontal: 11, paddingVertical: 7, marginTop: 8 },
  addChipTxt: { color: C.text, fontSize: 12, fontWeight: '700' },
  empty: { height: 110, borderRadius: 12, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, alignItems: 'center', justifyContent: 'center', gap: 6 },
  emptyTxt: { color: C.muted, fontSize: 12 },
  cartRow: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, padding: 10, marginBottom: 8 },
  cartName: { color: C.text, fontSize: 13, fontWeight: '700', flex: 1 },
  stepBtn: { width: 30, height: 30, borderRadius: 8, backgroundColor: C.alt, alignItems: 'center', justifyContent: 'center' },
  cartCount: { color: C.text, fontSize: 14, fontWeight: '900', minWidth: 26, textAlign: 'center' },
  delBtn: { width: 30, height: 30, borderRadius: 8, alignItems: 'center', justifyContent: 'center' },
  primaryBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 14, borderRadius: 12, marginTop: 16, backgroundColor: C.accent },
  primaryTxt: { color: '#0b0f1a', fontSize: 15, fontWeight: '900' },
  resultCard: { backgroundColor: '#0e2018', borderRadius: 14, borderWidth: 1, borderColor: '#0B5138', padding: 14, marginTop: 16 },
  resultHead: { color: C.accent, fontSize: 13, fontWeight: '900' },
  resultSub: { color: C.muted, fontSize: 11, marginTop: 2, marginBottom: 8 },
  resChip: { backgroundColor: '#0b2e22', borderRadius: 8, paddingHorizontal: 9, paddingVertical: 4 },
  resChipTxt: { color: C.accent, fontSize: 11, fontWeight: '700' },
  dioCard: { backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.accent2 + '55', padding: 10, marginTop: 16 },
  dioHead: { color: C.accent2, fontSize: 12, fontWeight: '900', marginBottom: 8 },
  dioWrap: { borderRadius: 12, overflow: 'hidden' },
  styleCard: { backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 12 },
  styleHint: { color: C.muted, fontSize: 11, flex: 1, marginRight: 8 },
  surpriseBtn: { backgroundColor: '#2b2342', borderWidth: 1, borderColor: C.accent2, borderRadius: 14, paddingHorizontal: 12, paddingVertical: 6 },
  surpriseTxt: { color: C.accent2, fontSize: 11, fontWeight: '900' },
  variantRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 10, borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 10, backgroundColor: C.alt },
  variantTxt: { color: C.muted, fontSize: 12, fontWeight: '700', flex: 1 },
  pack: { backgroundColor: C.alt, borderWidth: 1, borderColor: C.accent2 + '55', borderRadius: 12, paddingHorizontal: 10, paddingVertical: 8, marginRight: 8, alignItems: 'center', minWidth: 80 },
  packIcon: { fontSize: 18 },
  packTxt: { color: C.text, fontSize: 10, fontWeight: '800', marginTop: 2, textAlign: 'center' },
  axisLbl: { color: C.muted, fontSize: 11, fontWeight: '800', marginTop: 10, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.4 },
  axisFilter: { marginTop: 4, marginBottom: 2, backgroundColor: C.bg, borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8, color: C.text, fontSize: 13 },
  axisMore: { color: C.muted, fontSize: 11, fontStyle: 'italic', marginTop: 8 },
  regionRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 4 },
  regionDot: { width: 12, height: 12, borderRadius: 4 },
  regionName: { color: C.text, fontSize: 12, fontWeight: '800', textTransform: 'capitalize', width: 90 },
  regionMeta: { color: C.muted, fontSize: 11, flex: 1 },
});
