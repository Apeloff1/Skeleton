import React, { useState, useCallback, useEffect, useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator, TextInput,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { apiFetch } from '../utils/apiController';

const API = process.env.EXPO_PUBLIC_BACKEND_URL || '';
// Light /asset preview cache + a hard budget on auto-preview fetches so a huge
// catalog never floods the network on a low-RAM device (chips past the budget
// fetch their palette only when tapped). apiFetch also caps concurrency at 6.
const _thumbCache: Record<string, string[]> = {};
let _thumbBudget = 48;
const C = {
  bg: '#0b0f1a', card: '#141b2e', alt: '#1b2438', border: '#2a3550',
  text: '#eef2fb', muted: '#8a96b2', accent: '#34D399',
};
const GROUP_ICON: Record<string, string> = {
  'Living': '🧬', 'Nature': '🌿', 'Built World': '🏙️', 'Things': '🎒', 'Atmosphere': '🌌',
};

export default function ForgeHub() {
  const router = useRouter();
  const [cat, setCat] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiFetch(`${API}/api/galaxy-studio/forge/catalog`, { timeoutMs: 20000 });
      setCat(await r.json());
    } catch { /* ignore */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const famMeta = useMemo(() => {
    const m: Record<string, any> = {};
    (cat?.families || []).forEach((f: any) => { m[f.key] = f; });
    return m;
  }, [cat]);

  const [filtered, setFiltered] = useState<any[] | null>(null);
  useEffect(() => {
    const s = q.trim();
    if (!s) { setFiltered(null); return; }
    const t = setTimeout(async () => {
      try {
        const r = await apiFetch(`${API}/api/galaxy-studio/forge/search?q=${encodeURIComponent(s)}&limit=80`, { timeoutMs: 12000 });
        setFiltered((await r.json()).results || []);
      } catch { setFiltered([]); }
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  const open = useCallback((c: any) => {
    router.push(`/forge?category=${encodeURIComponent(c.key)}&label=${encodeURIComponent(c.label)}`);
  }, [router]);

  const [rolling, setRolling] = useState(false);
  const [ecs, setEcs] = useState<Record<string, boolean>>({});
  const [code, setCode] = useState('');
  const [codeErr, setCodeErr] = useState('');
  const [decoding, setDecoding] = useState(false);
  const ECS_FILTERS = [
    { k: 'metallic', label: 'Metallic' }, { k: 'script', label: 'Glyphs' },
    { k: 'tattoo', label: 'Tattoo' }, { k: 'mesh', label: 'Mesh FX' },
    { k: 'variant', label: 'Variant' }, { k: 'descriptor', label: 'Descriptor' },
    { k: 'inscription', label: 'Inscribed' },
  ];

  const surpriseMe = useCallback(async () => {
    setRolling(true);
    try {
      const req = Object.keys(ecs).filter((k) => ecs[k]).join(',');
      const url = `${API}/api/galaxy-studio/forge/random${req ? `?require=${encodeURIComponent(req)}` : ''}`;
      const r = await apiFetch(url, { timeoutMs: 12000 });
      const d = await r.json();
      const qs = new URLSearchParams({
        category: d.category, label: d.label, surprise: '1',
        era: d.era || 'modern', skin: d.skin_style || '',
        axes: JSON.stringify(d.axes || {}),
      }).toString();
      router.push(`/forge?${qs}`);
    } catch { /* ignore */ } finally { setRolling(false); }
  }, [router, ecs]);

  const applyCode = useCallback(async () => {
    const v = code.trim();
    if (!v) return;
    setDecoding(true); setCodeErr('');
    try {
      const r = await apiFetch(`${API}/api/galaxy-studio/forge/decode`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: v }), timeoutMs: 12000,
      });
      const d = await r.json();
      if (!d.ok) { setCodeErr(d.error || 'Invalid code'); return; }
      const p = d.params || {};
      const qs = new URLSearchParams({
        category: d.category, label: d.label || d.category, surprise: '1',
        era: p.era || 'modern', skin: p.skin_style || '',
        axes: JSON.stringify(p.style_axes || {}),
      }).toString();
      router.push(`/forge?${qs}`);
    } catch { setCodeErr('Decode failed — check the code.'); } finally { setDecoding(false); }
  }, [code, router]);

  const CatChip = ({ c }: any) => {
    const [pal, setPal] = React.useState<string[] | null>(c.thumb_palette || _thumbCache[c.key] || null);
    useEffect(() => {
      if (c.thumb_palette && c.thumb_palette.length) return;   // catalog already baked it in
      let alive = true;
      if (_thumbCache[c.key]) { setPal(_thumbCache[c.key]); return; }
      if (_thumbBudget <= 0) return;             // budget spent — fetch on tap only
      _thumbBudget -= 1;
      apiFetch(`${API}/api/galaxy-studio/forge/asset?id=${encodeURIComponent(c.key)}`, { timeoutMs: 9000 })
        .then((r) => r.json())
        .then((d) => { const tp = (d && d.thumb_palette) || []; _thumbCache[c.key] = tp; if (alive) setPal(tp); })
        .catch(() => {});
      return () => { alive = false; };
    }, [c.key, c.thumb_palette]);
    return (
      <TouchableOpacity onPress={() => open(c)} activeOpacity={0.85} style={styles.chip} testID={`fh-cat-${c.key}`}>
        <Text style={styles.chipTxt} numberOfLines={1}>{c.label}</Text>
        {pal && pal.length > 0 ? (
          <View style={styles.thumbStrip}>
            {pal.slice(0, 5).map((col, i) => (
              <View key={i} style={[styles.thumbCell, { backgroundColor: col }]} />
            ))}
          </View>
        ) : (
          <View style={[styles.thumbStrip, styles.thumbStripEmpty]} />
        )}
      </TouchableOpacity>
    );
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.iconBtn} testID="fh-back">
          <Ionicons name="chevron-back" size={22} color={C.text} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>⚒️ Forge Hub</Text>
          <Text style={styles.sub} numberOfLines={2}>{cat
            ? `${Number(cat.category_count).toLocaleString()} forges · ${Number(cat.base_category_count || 0).toLocaleString()} base${cat.total_variations_pretty ? ` · ${cat.total_variations_pretty} variations` : ''}`
            : 'Loading the forge roadmap…'}</Text>
        </View>
        <TouchableOpacity onPress={surpriseMe} style={styles.diceBtn} testID="fh-surprise" disabled={rolling}>
          {rolling ? <ActivityIndicator size="small" color="#A78BFA" /> : <Text style={styles.diceTxt}>🎲</Text>}
        </TouchableOpacity>
        <TouchableOpacity onPress={() => router.push('/compose-scene')} style={styles.composeBtn} testID="fh-compose">
          <Ionicons name="color-wand" size={15} color="#0b0f1a" />
          <Text style={styles.composeTxt}>Compose</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.searchRow}>
        <Ionicons name="search" size={16} color={C.muted} />
        <TextInput value={q} onChangeText={setQ} placeholder="Search 600M+ forges — molten dragon, runed throne…"
          placeholderTextColor={C.muted} style={styles.search} testID="fh-search" autoCapitalize="none" />
        {q ? <TouchableOpacity onPress={() => setQ('')}><Ionicons name="close-circle" size={18} color={C.muted} /></TouchableOpacity> : null}
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.toolsRow}>
        {ECS_FILTERS.map((f) => (
          <TouchableOpacity key={f.k} onPress={() => setEcs((m) => ({ ...m, [f.k]: !m[f.k] }))}
            style={[styles.ecsChip, ecs[f.k] && styles.ecsChipOn]} testID={`fh-ecs-${f.k}`}>
            <Text style={[styles.ecsChipTxt, ecs[f.k] && { color: '#0b0f1a' }]}>{f.label}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      <View style={styles.searchRow}>
        <Ionicons name="git-merge" size={15} color={C.muted} />
        <TextInput value={code} onChangeText={setCode} placeholder="Paste a Forge Code to rebuild a shared forge…"
          placeholderTextColor={C.muted} style={styles.search} testID="fh-code" autoCapitalize="none" autoCorrect={false} />
        <TouchableOpacity onPress={applyCode} disabled={decoding} style={styles.codeBtn} testID="fh-code-go">
          {decoding ? <ActivityIndicator size="small" color="#0b0f1a" /> : <Text style={styles.codeBtnTxt}>Rebuild</Text>}
        </TouchableOpacity>
      </View>
      {codeErr ? <Text style={styles.codeErr}>{codeErr}</Text> : null}

      {loading ? (
        <View style={styles.center}><ActivityIndicator color={C.accent} /></View>
      ) : filtered ? (
        <ScrollView contentContainerStyle={{ padding: 14, paddingBottom: 60 }}>
          <Text style={styles.groupHead}>🔎 {filtered.length} match{filtered.length === 1 ? '' : 'es'}</Text>
          <View style={styles.chipWrap}>{filtered.map((c) => <CatChip key={c.key} c={c} />)}</View>
          {filtered.length === 0 && <Text style={styles.empty}>No forge matches “{q}”.</Text>}
        </ScrollView>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 14, paddingBottom: 60 }}>
          {(cat?.groups || []).map((g: any) => (
            <View key={g.group} style={{ marginBottom: 18 }}>
              <Text style={styles.groupHead}>{GROUP_ICON[g.group] || '•'} {g.group}</Text>
              {/* family sub-headers within the group */}
              {Object.entries(
                g.categories.reduce((acc: Record<string, any[]>, c: any) => {
                  (acc[c.family] = acc[c.family] || []).push(c); return acc;
                }, {}),
              ).map(([fam, cats]: any) => (
                <View key={fam} style={styles.famBlock}>
                  <Text style={styles.famHead}>
                    {famMeta[fam]?.icon || '•'} {famMeta[fam]?.label || fam}
                    <Text style={styles.famCount}>  {cats.length}</Text>
                  </Text>
                  <View style={styles.chipWrap}>{cats.map((c: any) => <CatChip key={c.key} c={c} />)}</View>
                </View>
              ))}
            </View>
          ))}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 10, gap: 8 },
  iconBtn: { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center', backgroundColor: C.alt },
  title: { color: C.text, fontSize: 19, fontWeight: '900' },
  sub: { color: C.muted, fontSize: 11, marginTop: 1 },
  composeBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: C.accent, borderRadius: 16, paddingHorizontal: 12, paddingVertical: 8 },
  composeTxt: { color: '#0b0f1a', fontSize: 12, fontWeight: '900' },
  diceBtn: { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center', backgroundColor: '#2b2342', borderWidth: 1, borderColor: '#7C9CFF' },
  diceTxt: { fontSize: 18 },
  toolsRow: { paddingHorizontal: 14, paddingBottom: 8, gap: 6, flexDirection: 'row' },
  ecsChip: { borderWidth: 1, borderColor: '#7C9CFF', borderRadius: 14, paddingHorizontal: 11, paddingVertical: 5 },
  ecsChipOn: { backgroundColor: '#7C9CFF' },
  ecsChipTxt: { color: '#7C9CFF', fontSize: 11, fontWeight: '800' },
  codeBtn: { backgroundColor: C.accent, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 6 },
  codeBtnTxt: { color: '#0b0f1a', fontSize: 12, fontWeight: '900' },
  codeErr: { color: '#f87171', fontSize: 11, paddingHorizontal: 16, marginTop: -2, marginBottom: 4 },
  searchRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginHorizontal: 14, marginBottom: 6, backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, paddingHorizontal: 12 },
  search: { flex: 1, color: C.text, paddingVertical: 10, fontSize: 14 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  groupHead: { color: C.text, fontSize: 15, fontWeight: '900', marginBottom: 8 },
  famBlock: { marginBottom: 12 },
  famHead: { color: C.accent, fontSize: 12, fontWeight: '800', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.4 },
  famCount: { color: C.muted, fontWeight: '700' },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 18, paddingHorizontal: 13, paddingVertical: 8, maxWidth: '48%' },
  chipTxt: { color: C.text, fontSize: 12, fontWeight: '700' },
  thumbStrip: { flexDirection: 'row', height: 6, borderRadius: 3, overflow: 'hidden', marginTop: 6, gap: 1 },
  thumbStripEmpty: { backgroundColor: C.border, opacity: 0.4 },
  thumbCell: { flex: 1, height: 6 },
  empty: { color: C.muted, fontSize: 13, marginTop: 16, textAlign: 'center' },
});
