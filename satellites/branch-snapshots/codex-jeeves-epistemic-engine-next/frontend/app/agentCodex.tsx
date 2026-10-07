/**
 * /agentCodex — Frontend browser for all 28 agent-knowledge collections.
 *
 * Lists every Mongo knowledge collection the Galaxy Studio agents pull from
 * (patches, github snippets, code templates, diagnostics, procgen recipes,
 * content catalogues, design patterns, balance curves, engine schemas,
 * gamestate schemas, QA oracles, AI weights, build recipes, input/haptics,
 * physics/materials, audio DSP, security/crypto, legal, variation,
 * emotional dialogue, historical meta, director/pacing, visual juice,
 * cognitive psychographics, deep lore, ecosystems, publishing assets).
 *
 * Tap a tile → drill into rows with search.
 */
import { useEffect, useState, useCallback } from 'react';
import { View, Text, StyleSheet, FlatList, TouchableOpacity, TextInput, ActivityIndicator, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { apiFetch } from '../utils/apiController';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

type Coll = { slug: string; collection: string; count: number };

const SLUG_EMOJI: Record<string, string> = {
  'patch-notes': '📰', 'github-code-refs': '🐙', 'language-classes': '💬',
  'code-synthesis-templates': '🧬', 'code-diagnostics-rules': '🛡️',
  'procgen-recipes': '🌀', 'content-catalogues': '📦',
  'game-design-patterns': '🎯', 'game-balance-curves': '⚖️',
  'engine-api-schemas': '⚙️', 'gamestate-schemas': '💾',
  'qa-oracles': '🔍', 'ai-generative-weights': '🧠',
  'build-recipes': '🛠️', 'input-haptics': '🎮',
  'physics-materials-sim': '🧱', 'audio-dsp': '🔊',
  'security-crypto': '🔐', 'legal-compliance': '📜',
  'variation-mutation': '🌈', 'emotional-dialogue': '🎭',
  'historical-meta': '⏳', 'director-pacing': '🎬',
  'visual-juice': '✨', 'cognitive-psychographics': '🧩',
  'deep-lore': '📖', 'ecosystems-biology': '🌿',
  'publishing-assets': '🚀',
};

const T = {
  bg: '#0A0A0A', card: '#141414', cardHover: '#15203A',
  border: '#1F1F1F', accent: '#7C9CFF', accent2: '#A78BFA',
  text: '#E5E7EB', dim: '#94A3B8', muted: '#64748B',
};

const EXT_SLUGS = new Set([
  'input-haptics','physics-materials-sim','audio-dsp','security-crypto',
  'legal-compliance','variation-mutation','emotional-dialogue','historical-meta',
  'director-pacing','visual-juice','cognitive-psychographics','deep-lore',
  'ecosystems-biology','publishing-assets',
]);

export default function AgentCodexRoute() {
  const router = useRouter();
  const [colls, setColls] = useState<Coll[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeSlug, setActiveSlug] = useState<string | null>(null);
  const [rows, setRows] = useState<any[]>([]);
  const [drillLoading, setDrillLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [totalRows, setTotalRows] = useState(0);

  useEffect(() => {
    (async () => {
      try {
        const r = await apiFetch(`${API_URL}/api/knowledge/collections`);
        const d = await r.json();
        setColls(d.collections || []);
        setTotalRows(d.total_rows || 0);
      } catch (e) {
        console.warn('codex.collections failed', e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const openCollection = useCallback(async (slug: string, q = '') => {
    setActiveSlug(slug);
    setDrillLoading(true);
    try {
      // Use generic /c/{slug} for extension collections,
      // domain-specific endpoint for the older ones.
      let url: string;
      if (EXT_SLUGS.has(slug)) {
        url = `${API_URL}/api/knowledge/c/${slug}?limit=30${q ? `&q=${encodeURIComponent(q)}` : ''}`;
      } else {
        // Older collections expose their own endpoint
        const map: Record<string, string> = {
          'patch-notes': '/api/knowledge/patch-notes',
          'github-code-refs': '/api/knowledge/github-code',
          'language-classes': '/api/languages-academy/all',
          'code-synthesis-templates': '/api/knowledge/templates',
          'code-diagnostics-rules': '/api/knowledge/diagnostics',
          'procgen-recipes': '/api/knowledge/procgen',
          'content-catalogues': '/api/knowledge/catalogues',
          'game-design-patterns': '/api/knowledge/design',
          'game-balance-curves': '/api/knowledge/balance-curves',
          'engine-api-schemas': '/api/knowledge/engines',
          'gamestate-schemas': '/api/knowledge/gamestate-schemas',
          'qa-oracles': '/api/knowledge/qa-oracles',
          'ai-generative-weights': '/api/knowledge/ai-weights',
          'build-recipes': '/api/knowledge/build-recipes',
        };
        url = `${API_URL}${map[slug] || ''}?limit=30`;
      }
      const r = await apiFetch(url);
      const d = await r.json();
      const arr = d.rows || d.refs || d.patches || d.templates || d.diagnostics
                  || d.recipes || d.items || d.patterns || d.curves || d.engines
                  || d.schemas || d.oracles || d.weights || d.languages || [];
      setRows(arr);
    } catch (e) {
      console.warn('codex.drill failed', e);
      setRows([]);
    } finally {
      setDrillLoading(false);
    }
  }, []);

  const close = () => {
    if (activeSlug) { setActiveSlug(null); setRows([]); setQuery(''); }
    else router.back();
  };

  return (
    <SafeAreaView style={s.root} edges={['top','left','right']}>
      <View style={s.header}>
        <TouchableOpacity onPress={close} hitSlop={12} style={s.iconBtn}>
          <Ionicons name={activeSlug ? 'chevron-back' : 'close'} size={22} color={T.text} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={s.headerTitle} numberOfLines={1}>
            {activeSlug ? colls.find(c => c.slug === activeSlug)?.collection || activeSlug : 'Agent Codex'}
          </Text>
          <Text style={s.headerSub} numberOfLines={1}>
            {activeSlug ? `${rows.length} rows shown` : `${colls.length} collections • ${totalRows.toLocaleString()} rows`}
          </Text>
        </View>
      </View>

      {activeSlug && (
        <View style={s.searchRow}>
          <Ionicons name="search" size={14} color={T.muted} style={{ marginRight: 6 }} />
          <TextInput
            value={query}
            onChangeText={setQuery}
            onSubmitEditing={() => openCollection(activeSlug, query)}
            placeholder="Filter rows…"
            placeholderTextColor={T.muted}
            style={s.searchInput}
            returnKeyType="search"
          />
        </View>
      )}

      {loading ? (
        <ActivityIndicator color={T.accent} style={{ marginTop: 80 }} />
      ) : !activeSlug ? (
        <FlatList
          data={colls}
          keyExtractor={c => c.slug}
          numColumns={2}
          columnWrapperStyle={{ gap: 10, paddingHorizontal: 16 }}
          contentContainerStyle={{ paddingVertical: 16, gap: 10, paddingBottom: 40 }}
          renderItem={({ item }) => (
            <TouchableOpacity style={s.tile} onPress={() => openCollection(item.slug)} activeOpacity={0.8}>
              <Text style={s.tileEmoji}>{SLUG_EMOJI[item.slug] || '📚'}</Text>
              <Text style={s.tileTitle} numberOfLines={2}>
                {item.slug.replace(/-/g, ' ')}
              </Text>
              <Text style={s.tileCount}>{item.count.toLocaleString()} rows</Text>
            </TouchableOpacity>
          )}
        />
      ) : drillLoading ? (
        <ActivityIndicator color={T.accent} style={{ marginTop: 60 }} />
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, gap: 10, paddingBottom: 60 }}>
          {rows.length === 0 ? (
            <Text style={s.empty}>No rows match.</Text>
          ) : (
            rows.map((row, idx) => (
              <View key={row.id || idx} style={s.rowCard}>
                <Text style={s.rowTitle} numberOfLines={2}>
                  {row.title || row.name || row.invariant_name || row.pattern || row.curve
                   || row.repo || row.game || row.engine || row.preset || row.fx || row.beat
                   || row.archetype || row.factor || row.species || row.interaction
                   || row.effect || row.filter_name || row.rule || row.kind || row.id || `Row ${idx+1}`}
                </Text>
                {row.description ? (
                  <Text style={s.rowDesc} numberOfLines={4}>{row.description}</Text>
                ) : null}
                <Text style={s.rowMeta} numberOfLines={2}>
                  {(row.tags || []).slice(0, 6).join(' · ')}
                </Text>
              </View>
            ))
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: T.bg },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: T.border, gap: 10 },
  iconBtn: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center', borderRadius: 10, backgroundColor: T.card },
  headerTitle: { color: T.text, fontSize: 16, fontWeight: '700' },
  headerSub: { color: T.dim, fontSize: 11, marginTop: 1 },
  searchRow: { flexDirection: 'row', alignItems: 'center', marginHorizontal: 16, marginTop: 10, marginBottom: 4, backgroundColor: T.card, borderRadius: 10, paddingHorizontal: 12, borderWidth: 1, borderColor: T.border },
  searchInput: { flex: 1, color: T.text, paddingVertical: 8, fontSize: 13 },
  tile: { flex: 1, backgroundColor: T.card, borderRadius: 14, padding: 14, borderWidth: 1, borderColor: T.border, minHeight: 110 },
  tileEmoji: { fontSize: 22, marginBottom: 6 },
  tileTitle: { color: T.text, fontSize: 13, fontWeight: '700', textTransform: 'capitalize', lineHeight: 17 },
  tileCount: { color: T.accent, fontSize: 11, marginTop: 6, fontWeight: '600' },
  rowCard: { backgroundColor: T.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: T.border },
  rowTitle: { color: T.text, fontSize: 13, fontWeight: '700', textTransform: 'capitalize' },
  rowDesc: { color: T.dim, fontSize: 12, marginTop: 6, lineHeight: 17 },
  rowMeta: { color: T.muted, fontSize: 10, marginTop: 8, fontStyle: 'italic' },
  empty: { color: T.dim, textAlign: 'center', marginTop: 40, fontSize: 13 },
});
