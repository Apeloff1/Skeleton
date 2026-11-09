/**
 * /build-hub — Build · Code · AI Powerhouse Hub.
 *
 * Surfaces 16 backend services that were previously hidden behind menu
 * cards pointing to ModalType IDs without actual modal implementations.
 *
 * Same pattern as /jeeves-hub: live status dot per tile, fetch-on-mount,
 * pull-to-refresh, modal with full detail rows.
 */
import { useEffect, useState, useCallback, useMemo } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity,
  RefreshControl, StyleSheet, StatusBar, SafeAreaView, Modal,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import Skeleton from '../components/ui/Skeleton';
import RetryBanner from '../components/ui/RetryBanner';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

type Category = 'Code & Run' | 'AI Pipelines' | 'Assets & Media' | 'Education';

type Tile = {
  id: string;
  title: string;
  icon: keyof typeof Ionicons.glyphMap;
  accent: string;
  endpoint: string;
  category: Category;
  /** Optional full-screen route to navigate to instead of opening the modal. */
  route?: string;
  describe: (j: any) => string;
  details?: (j: any) => { label: string; value: string }[];
};

const TILES: Tile[] = [
  // ── Code & Run ─────────────────────────────────────────────
  {
    id: 'playground', title: 'Code Playground', icon: 'flask', accent: '#F59E0B',
    endpoint: '/api/playground/languages', category: 'Code & Run',
    route: '/playground',
    describe: j => {
      const arr = j?.languages || j || [];
      return `${Array.isArray(arr) ? arr.length : 0} languages · run code in seconds`;
    },
    details: j => {
      const arr = j?.languages || j || [];
      if (!Array.isArray(arr)) return [];
      return arr.slice(0, 10).map((l: any, i: number) => ({
        label: typeof l === 'string' ? l : (l?.name || l?.id || `Lang ${i + 1}`),
        value: typeof l === 'object' ? (l?.version || l?.runtime || 'ready') : 'ready',
      }));
    },
  },
  {
    id: 'rosetta', title: 'Rosetta Playground', icon: 'language', accent: '#8B5CF6',
    endpoint: '/api/rosetta-challenge/generate?language=python', category: 'Code & Run',
    route: '/rosetta',
    describe: j => {
      const t = j?.title || j?.challenge?.title || 'Translate the same task across every language';
      return String(t).slice(0, 100);
    },
    details: j => {
      const out: { label: string; value: string }[] = [];
      ['title', 'difficulty', 'language', 'category', 'description'].forEach(k => {
        if (j?.[k]) out.push({ label: k, value: String(j[k]).slice(0, 200) });
      });
      return out;
    },
  },
  {
    id: 'intelligence', title: 'Code Intelligence', icon: 'bulb', accent: '#F5C451',
    endpoint: '/api/intelligence/info', category: 'Code & Run',
    route: '/intelligence',
    describe: j => j?.description || j?.tagline || 'Semantic search · auto-document · refactor hints',
    details: j => {
      const out: { label: string; value: string }[] = [];
      if (j?.capabilities) (Array.isArray(j.capabilities) ? j.capabilities : Object.keys(j.capabilities)).slice(0, 6).forEach((c: any, i: number) =>
        out.push({ label: `Capability ${i + 1}`, value: String(c) })
      );
      return out;
    },
  },
  {
    id: 'debugger', title: 'Debugger', icon: 'bug', accent: '#EF4444',
    endpoint: '/api/debugger/info', category: 'Code & Run',
    route: '/debugger',
    describe: j => j?.description || 'Step through code · breakpoints · variable inspection',
    details: j => {
      const out: { label: string; value: string }[] = [];
      if (j?.features) (Array.isArray(j.features) ? j.features : Object.keys(j.features)).slice(0, 6).forEach((c: any, i: number) =>
        out.push({ label: `Feature ${i + 1}`, value: String(c) })
      );
      return out;
    },
  },
  {
    id: 'collab', title: 'Live Collaboration', icon: 'people-circle', accent: '#10B981',
    endpoint: '/api/collaboration/sessions', category: 'Code & Run',
    route: '/collab',
    describe: j => {
      const arr = j?.sessions || j || [];
      const n = Array.isArray(arr) ? arr.length : 0;
      return `${n} live session${n === 1 ? '' : 's'} · real-time pair programming`;
    },
    details: j => {
      const arr = j?.sessions || j || [];
      if (!Array.isArray(arr)) return [];
      return arr.slice(0, 8).map((s: any, i: number) => ({
        label: s?.name || s?.id || `Session ${i + 1}`,
        value: `${s?.participants?.length || 0} users · ${s?.language || ''}`.trim(),
      }));
    },
  },
  // ── AI Pipelines ─────────────────────────────────────────
  {
    id: 'codeToApp', title: 'Code → App', icon: 'apps', accent: '#3B82F6',
    endpoint: '/api/code-to-app/info', category: 'AI Pipelines',
    describe: j => j?.description || 'Scaffold a full app from a snippet',
    details: j => {
      const out: { label: string; value: string }[] = [];
      ['version', 'description', 'inputs', 'outputs'].forEach(k => {
        if (j?.[k]) out.push({ label: k, value: String(typeof j[k] === 'string' ? j[k] : JSON.stringify(j[k])).slice(0, 200) });
      });
      return out;
    },
  },
  {
    id: 'multiAgent', title: 'Multi-Agent', icon: 'people', accent: '#A78BFA',
    endpoint: '/api/agents/info', category: 'AI Pipelines',
    describe: j => j?.description || `${j?.total_agents || j?.roles_count || ''} roles · coordinated AI swarm`,
    details: j => {
      const out: { label: string; value: string }[] = [];
      ['version', 'description', 'total_agents', 'roles_count'].forEach(k => {
        if (j?.[k] != null) out.push({ label: k, value: String(j[k]) });
      });
      return out;
    },
  },
  {
    id: 'sota', title: 'SOTA 2026', icon: 'flash', accent: '#F5C451',
    endpoint: '/api/sota/info', category: 'AI Pipelines',
    describe: j => j?.description || 'Latest state-of-the-art models',
    details: j => {
      const out: { label: string; value: string }[] = [];
      Object.entries(j || {}).forEach(([k, v]) => {
        if (typeof v === 'string' || typeof v === 'number') {
          out.push({ label: k.replace(/_/g, ' '), value: String(v).slice(0, 100) });
        }
      });
      return out.slice(0, 10);
    },
  },
  {
    id: 'sotaExt', title: 'SOTA Extended', icon: 'flash-outline', accent: '#FACC15',
    endpoint: '/api/sota-extended/info', category: 'AI Pipelines',
    describe: j => j?.description || 'Specialist & fine-tuned models',
    details: j => {
      const out: { label: string; value: string }[] = [];
      Object.entries(j || {}).forEach(([k, v]) => {
        if (typeof v === 'string' || typeof v === 'number') {
          out.push({ label: k.replace(/_/g, ' '), value: String(v).slice(0, 100) });
        }
      });
      return out.slice(0, 10);
    },
  },
  {
    id: 'masterclass', title: 'Masterclass', icon: 'ribbon', accent: '#F59E0B',
    endpoint: '/api/masterclass/info', category: 'AI Pipelines',
    describe: j => j?.description || 'Long-form expert lessons',
    details: j => {
      const out: { label: string; value: string }[] = [];
      Object.entries(j || {}).forEach(([k, v]) => {
        if (typeof v === 'string' || typeof v === 'number') {
          out.push({ label: k.replace(/_/g, ' '), value: String(v).slice(0, 100) });
        }
      });
      return out.slice(0, 10);
    },
  },
  // ── Assets & Media ───────────────────────────────────────
  {
    id: 'imagine', title: 'Imagine', icon: 'image', accent: '#8B5CF6',
    endpoint: '/api/imagine/info', category: 'Assets & Media',
    route: '/imagine',
    describe: j => j?.description || 'AI image generator',
    details: j => {
      const out: { label: string; value: string }[] = [];
      Object.entries(j || {}).forEach(([k, v]) => {
        if (typeof v === 'string' || typeof v === 'number') {
          out.push({ label: k.replace(/_/g, ' '), value: String(v).slice(0, 100) });
        }
      });
      return out.slice(0, 10);
    },
  },
  {
    id: 'assets', title: 'Asset Pipeline', icon: 'images', accent: '#A78BFA',
    endpoint: '/api/assets/info', category: 'Assets & Media',
    route: '/assets',
    describe: j => j?.description || 'Game art, audio, models',
    details: j => {
      const out: { label: string; value: string }[] = [];
      Object.entries(j || {}).forEach(([k, v]) => {
        if (typeof v === 'string' || typeof v === 'number') {
          out.push({ label: k.replace(/_/g, ' '), value: String(v).slice(0, 100) });
        }
      });
      return out.slice(0, 10);
    },
  },
  {
    id: 'music', title: 'Music Pipeline', icon: 'musical-notes', accent: '#3B82F6',
    endpoint: '/api/music/info', category: 'Assets & Media',
    route: '/music',
    describe: j => j?.description || 'Score, SFX, ambient',
    details: j => {
      const out: { label: string; value: string }[] = [];
      Object.entries(j || {}).forEach(([k, v]) => {
        if (typeof v === 'string' || typeof v === 'number') {
          out.push({ label: k.replace(/_/g, ' '), value: String(v).slice(0, 100) });
        }
      });
      return out.slice(0, 10);
    },
  },
  // ── Education ────────────────────────────────────────────
  {
    id: 'bible', title: 'Bible (Code Bible)', icon: 'library', accent: '#94A3B8',
    endpoint: '/api/bible', category: 'Education',
    describe: j => {
      const n = j?.entries?.length || j?.total || (Array.isArray(j) ? j.length : 0);
      return `${n} canonical entries · CS history & lore`;
    },
    details: j => {
      const arr = j?.entries || (Array.isArray(j) ? j : []);
      return arr.slice(0, 8).map((e: any, i: number) => ({
        label: e?.title || e?.year || `Entry ${i + 1}`,
        value: String(e?.summary || e?.description || '').slice(0, 100),
      }));
    },
  },
  {
    id: 'learning', title: 'Immersive Learning', icon: 'eye', accent: '#A78BFA',
    endpoint: '/api/learning/daily-challenge', category: 'Education',
    describe: j => j?.title || j?.challenge?.title || 'Daily immersive learning challenge',
    details: j => {
      const c = j?.challenge || j || {};
      const out: { label: string; value: string }[] = [];
      ['title', 'difficulty', 'xp', 'description'].forEach(k => {
        if (c[k] != null) out.push({ label: k, value: String(c[k]).slice(0, 200) });
      });
      return out;
    },
  },
  {
    id: 'roles', title: 'Agent Roles', icon: 'people-outline', accent: '#10B981',
    endpoint: '/api/agents/roles', category: 'Education',
    describe: j => {
      const arr = j?.roles || j || [];
      return `${Array.isArray(arr) ? arr.length : 0} specialist agent roles`;
    },
    details: j => {
      const arr = j?.roles || j || [];
      if (!Array.isArray(arr)) return [];
      return arr.slice(0, 10).map((r: any, i: number) => ({
        label: r?.name || r?.id || `Role ${i + 1}`,
        value: String(r?.description || r?.specialty || '').slice(0, 80),
      }));
    },
  },
];

const CAT_COLOURS: Record<Category, string> = {
  'Code & Run':    '#3B82F6',
  'AI Pipelines':  '#A78BFA',
  'Assets & Media':'#8B5CF6',
  'Education':     '#10B981',
};

interface TileResult { tile: Tile; loading: boolean; data?: any; error?: string; }

export default function BuildHubScreen() {
  const router = useRouter();
  const [results, setResults] = useState<Record<string, TileResult>>(() =>
    Object.fromEntries(TILES.map(t => [t.id, { tile: t, loading: true }]))
  );
  const [refreshing, setRefreshing] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [activeCat, setActiveCat] = useState<Category | null>(null);

  const fetchAll = useCallback(async () => {
    setRefreshing(true);
    await Promise.all(TILES.map(async (t) => {
      try {
        const r = await fetch(`${BACKEND}${t.endpoint}`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const j = await r.json();
        setResults(prev => ({ ...prev, [t.id]: { tile: t, loading: false, data: j } }));
      } catch (e: any) {
        setResults(prev => ({ ...prev, [t.id]: { tile: t, loading: false, error: String(e?.message || e).slice(0, 80) } }));
      }
    }));
    setRefreshing(false);
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const stats = useMemo(() => {
    const total = Object.values(results).length;
    const live = Object.values(results).filter(r => !r.loading && !r.error).length;
    return { total, live };
  }, [results]);

  /** Tiles that errored on the last fetch — drives the inline RetryBanner. */
  const failedCount = useMemo(
    () => Object.values(results).filter(r => !r.loading && r.error).length,
    [results],
  );

  const filtered = useMemo(
    () => TILES.filter(t => !activeCat || t.category === activeCat),
    [activeCat]
  );

  const openModalData = open ? results[open] : null;
  const cats: Category[] = ['Code & Run', 'AI Pipelines', 'Assets & Media', 'Education'];

  return (
    <SafeAreaView style={s.root}>
      <StatusBar barStyle="light-content" backgroundColor="#0A0A0A" />

      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.backBtn} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
          <Ionicons name="chevron-back" size={22} color="#3B82F6" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={s.title}>🚀 Build · Code · AI Hub</Text>
          <Text style={s.subtitle}>
            {stats.live}/{stats.total} services live · everything wired
          </Text>
        </View>
        <TouchableOpacity onPress={fetchAll} style={s.refreshBtn} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
          <Ionicons name="refresh" size={18} color="#3B82F6" />
        </TouchableOpacity>
      </View>

      {/* Category filter chips */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.chipRow}>
        <TouchableOpacity
          style={[s.chip, !activeCat && s.chipActive]}
          onPress={() => setActiveCat(null)}
        >
          <Text style={[s.chipText, !activeCat && s.chipTextActive]}>All · {TILES.length}</Text>
        </TouchableOpacity>
        {cats.map(c => {
          const active = activeCat === c;
          const n = TILES.filter(t => t.category === c).length;
          return (
            <TouchableOpacity
              key={c}
              style={[s.chip, active && { backgroundColor: CAT_COLOURS[c] + '33', borderColor: CAT_COLOURS[c] }]}
              onPress={() => setActiveCat(active ? null : c)}
            >
              <Text style={[s.chipText, active && { color: CAT_COLOURS[c], fontWeight: '700' }]}>
                {c} · {n}
              </Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      <ScrollView
        contentContainerStyle={s.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={fetchAll} tintColor="#3B82F6" />}
      >
        {/* Harden — inline retry banner shows when any tile errored. */}
        {failedCount > 0 && !refreshing && (
          <RetryBanner
            error={`${failedCount} service${failedCount === 1 ? '' : 's'} unreachable — pull to refresh or tap retry.`}
            onRetry={fetchAll}
            retryLabel="Retry all"
          />
        )}
        {filtered.map(t => {
          const r = results[t.id];
          const live = !r?.loading && !r?.error;
          return (
            <TouchableOpacity
              key={t.id}
              activeOpacity={0.85}
              onPress={() => {
                if (t.route) {
                  router.push(t.route as any);
                } else {
                  setOpen(t.id);
                }
              }}
              style={[s.card, { borderColor: t.accent + '55' }]}
            >
              <View style={[s.iconCircle, { backgroundColor: t.accent + '22', borderColor: t.accent }]}>
                <Ionicons name={t.icon} size={22} color={t.accent} />
              </View>
              <View style={{ flex: 1 }}>
                <View style={s.cardHeader}>
                  <Text style={s.cardTitle} numberOfLines={1}>{t.title}</Text>
                  <View style={[s.catTag, { backgroundColor: CAT_COLOURS[t.category] + '22', borderColor: CAT_COLOURS[t.category] }]}>
                    <Text style={[s.catTagText, { color: CAT_COLOURS[t.category] }]}>{t.category.split(' ')[0]}</Text>
                  </View>
                  <View style={[s.statusDot, { backgroundColor: live ? '#10B981' : (r?.error ? '#f87171' : '#94a3b8') }]} />
                </View>
                {r?.loading ? (
                  <View style={{ gap: 6, marginTop: 4 }}>
                    <Skeleton width="90%" height={11} />
                    <Skeleton width="60%" height={11} />
                  </View>
                ) : r?.error ? (
                  <Text style={s.errText}>⚠ {r.error}</Text>
                ) : (
                  <Text style={s.cardDesc} numberOfLines={2}>{t.describe(r?.data)}</Text>
                )}
              </View>
              <Ionicons name="chevron-forward" size={18} color="#64748b" />
            </TouchableOpacity>
          );
        })}

        {filtered.length === 0 && (
          <Text style={s.empty}>No services in this category.</Text>
        )}

        <View style={{ height: 30 }} />
        <Text style={s.footer}>All endpoints live · pull-to-refresh for fresh data</Text>
      </ScrollView>

      {/* Detail modal */}
      <Modal visible={!!open} transparent animationType="slide" onRequestClose={() => setOpen(null)}>
        <View style={s.modalBackdrop}>
          <View style={s.modalCard}>
            <View style={s.modalHeader}>
              <View style={[s.iconCircle, { backgroundColor: (openModalData?.tile.accent || '#3B82F6') + '22', borderColor: openModalData?.tile.accent || '#3B82F6' }]}>
                <Ionicons name={openModalData?.tile.icon || 'flash'} size={18} color={openModalData?.tile.accent || '#3B82F6'} />
              </View>
              <Text style={s.modalTitle}>{openModalData?.tile.title}</Text>
              <TouchableOpacity onPress={() => setOpen(null)} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
                <Ionicons name="close" size={22} color="#94a3b8" />
              </TouchableOpacity>
            </View>
            <ScrollView style={{ maxHeight: 440 }} contentContainerStyle={{ padding: 12 }}>
              {openModalData?.error ? (
                <Text style={s.errText}>⚠ {openModalData.error}</Text>
              ) : openModalData?.data ? (
                <>
                  <Text style={s.modalDesc}>{openModalData.tile.describe(openModalData.data)}</Text>
                  {(openModalData.tile.details?.(openModalData.data) || []).map((d, i) => (
                    <View key={i} style={s.detailRow}>
                      <Text style={s.detailLabel}>{d.label}</Text>
                      <Text style={s.detailValue} numberOfLines={3}>{d.value}</Text>
                    </View>
                  ))}
                </>
              ) : (
                /* Skeleton paragraph beats a spinner for perceived speed. */
                <Skeleton.Block rows={5} gap={10} lastWidth="40%" />
              )}
            </ScrollView>
            <View style={s.modalFooter}>
              <Text style={s.modalEndpoint} numberOfLines={1}>
                <Ionicons name="link" size={11} color="#64748b" /> {openModalData?.tile.endpoint}
              </Text>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0A0A0A' },
  header: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    paddingHorizontal: 14, paddingVertical: 10,
    borderBottomColor: '#1F1F1F', borderBottomWidth: 1,
  },
  backBtn: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  refreshBtn: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  title: { color: '#f1f5f9', fontSize: 16, fontWeight: '900' },
  subtitle: { color: '#94a3b8', fontSize: 11, marginTop: 2 },
  chipRow: { paddingHorizontal: 12, paddingTop: 10, paddingBottom: 2, gap: 8 },
  chip: {
    paddingHorizontal: 12, paddingVertical: 6, borderRadius: 14,
    backgroundColor: '#141414', borderWidth: 1, borderColor: '#1F1F1F',
    marginRight: 6,
  },
  chipActive: { backgroundColor: '#3B82F633', borderColor: '#3B82F6' },
  chipText: { color: '#94a3b8', fontSize: 11, fontWeight: '600' },
  chipTextActive: { color: '#3B82F6', fontWeight: '700' },
  content: { padding: 12, paddingBottom: 30 },
  card: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: '#141414', borderRadius: 12, padding: 12,
    marginBottom: 8, borderWidth: 1,
  },
  iconCircle: {
    width: 40, height: 40, borderRadius: 20,
    alignItems: 'center', justifyContent: 'center',
    borderWidth: 1,
  },
  cardHeader: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  cardTitle: { color: '#f1f5f9', fontSize: 14, fontWeight: '800', flex: 1 },
  cardDesc: { color: '#94a3b8', fontSize: 11, marginTop: 3, lineHeight: 15 },
  catTag: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6, borderWidth: 1 },
  catTagText: { fontSize: 9, fontWeight: '700' },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  errText: { color: '#f87171', fontSize: 11, marginTop: 4 },
  empty: { color: '#94a3b8', fontSize: 12, textAlign: 'center', padding: 30, fontStyle: 'italic' },
  footer: { color: '#64748b', fontSize: 10, textAlign: 'center', marginTop: 6, fontStyle: 'italic' },
  modalBackdrop: { flex: 1, backgroundColor: '#000000aa', justifyContent: 'flex-end' },
  modalCard: {
    backgroundColor: '#141414', borderTopLeftRadius: 20, borderTopRightRadius: 20,
    borderTopWidth: 1, borderColor: '#1F1F1F', paddingBottom: 24,
  },
  modalHeader: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingHorizontal: 14, paddingVertical: 14,
    borderBottomColor: '#1F1F1F', borderBottomWidth: 1,
  },
  modalTitle: { flex: 1, color: '#f1f5f9', fontSize: 15, fontWeight: '800' },
  modalDesc: { color: '#cbd5e1', fontSize: 12, lineHeight: 18, marginBottom: 10 },
  detailRow: {
    flexDirection: 'row', justifyContent: 'space-between', gap: 10,
    paddingVertical: 7,
    borderBottomColor: '#1F1F1F', borderBottomWidth: 0.5,
  },
  detailLabel: { color: '#94a3b8', fontSize: 11, fontWeight: '600', textTransform: 'capitalize' },
  detailValue: { color: '#f1f5f9', fontSize: 11, fontWeight: '700', flex: 1, textAlign: 'right' },
  modalFooter: { paddingHorizontal: 14, paddingTop: 8 },
  modalEndpoint: { color: '#64748b', fontSize: 10, fontFamily: 'monospace' },
});

