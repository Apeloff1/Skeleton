/**
 * /jeeves-hub — Unified Jeeves Powerhouse Hub.
 *
 * Surfaces 9 backend-only Jeeves powerhouses + gamification feeds as a single
 * tappable dashboard. Each card fetches live data on mount and lets the user
 * drill in for the full payload.
 *
 * Endpoints surfaced:
 *   /api/jeeves/persona         (biography + stats)
 *   /api/jeeves-eq/info         (emotion-aware AI tutor)
 *   /api/jeeves-voice/personality
 *   /api/jeeves-hyperion/knowledge-base/stats
 *   /api/jeeves-synergy/overview
 *   /api/jeeves-build/genres    (master game-builder)
 *   /api/jeeves/camera/knowledge
 *   /api/daily/challenge
 *   /api/leaderboards/boards
 *   /api/gamification/profile/<user>
 */
import { useEffect, useState, useCallback, useMemo } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity,
  RefreshControl, StyleSheet, StatusBar, SafeAreaView, Modal,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { ModalErrorBoundary } from '../components/ModalErrorBoundary';
import { jeevesSpeak } from '../features/Academy/jeevesTts';
import { useFeatureFlag } from '../utils/featureFlags';
import Skeleton from '../components/ui/Skeleton';
import RetryBanner from '../components/ui/RetryBanner';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const USER_ID = 'default_user';

type Tile = {
  id: string;
  title: string;
  icon: keyof typeof Ionicons.glyphMap;
  accent: string;
  endpoint: string;
  describe: (j: any) => string;
  details?: (j: any) => { label: string; value: string }[];
  speakIntro?: (j: any) => string;
};

const TILES: Tile[] = [
  {
    id: 'persona', title: 'Jeeves Persona', icon: 'happy-outline', accent: '#a78bfa',
    endpoint: '/api/jeeves/persona',
    describe: j => {
      const s = j?.stats || {};
      return `${s.total_catchphrases ?? 0} catchphrases · ${s.total_quirks ?? 0} quirks · ${s.total_knowledge_entries ?? 0} knowledge entries`;
    },
    details: j => {
      const bio = j?.biography || {};
      const s = j?.stats || {};
      return [
        { label: 'Name',         value: bio.full_title || bio.name || '—' },
        { label: 'Origin',       value: bio.origin || '—' },
        { label: 'Voice tone',   value: bio.voice_template?.tone || '—' },
        { label: 'Catchphrases', value: String(s.total_catchphrases ?? '—') },
        { label: 'Mannerisms',   value: String(s.total_mannerisms ?? '—') },
        { label: 'Quirks',       value: String(s.total_quirks ?? '—') },
        { label: 'Knowledge',    value: String(s.total_knowledge_entries ?? '—') },
        { label: 'Quotes',       value: String(s.total_famous_quotes ?? '—') },
      ];
    },
    speakIntro: () => 'A pleasure to make your acquaintance again. Behold the persona dossier.',
  },
  {
    id: 'eq', title: 'Jeeves EQ', icon: 'heart-outline', accent: '#8B5CF6',
    endpoint: '/api/jeeves-eq/info',
    describe: j => j?.description || j?.tagline || 'Emotion-aware tutoring & therapeutic responses',
    details: j => {
      const out: { label: string; value: string }[] = [];
      if (j?.capabilities) {
        const caps = Array.isArray(j.capabilities) ? j.capabilities : Object.keys(j.capabilities);
        caps.slice(0, 8).forEach((c: any, i: number) =>
          out.push({ label: `Capability ${i + 1}`, value: String(c) })
        );
      }
      if (j?.emotions) out.push({ label: 'Emotion classes', value: String((j.emotions || []).length || Object.keys(j.emotions || {}).length) });
      return out;
    },
    speakIntro: () => 'Emotion module ready. Should you grow weary, I shall notice.',
  },
  {
    id: 'voice', title: 'Jeeves Voice', icon: 'mic-outline', accent: '#3B82F6',
    endpoint: '/api/jeeves-voice/personality',
    describe: j => {
      const traits = (j?.traits || j?.personality || []);
      const n = Array.isArray(traits) ? traits.length : Object.keys(traits || {}).length;
      return `${n} personality dimensions · voice synthesis ready`;
    },
    details: j => {
      const out: { label: string; value: string }[] = [];
      if (j?.voice_id)   out.push({ label: 'Default voice', value: String(j.voice_id) });
      if (j?.tone)       out.push({ label: 'Tone', value: String(j.tone) });
      if (j?.accent)     out.push({ label: 'Accent', value: String(j.accent) });
      const traits = j?.traits || j?.personality || {};
      Object.entries(traits).slice(0, 6).forEach(([k, v]) =>
        out.push({ label: k, value: String(v).slice(0, 60) })
      );
      return out;
    },
    speakIntro: () => 'Voice synthesiser primed — ready for instruction.',
  },
  {
    id: 'hyperion', title: 'Jeeves Hyperion', icon: 'planet-outline', accent: '#fbbf24',
    endpoint: '/api/jeeves-hyperion/knowledge-base/stats',
    describe: j => {
      const dom = j?.total_domains ?? j?.domains_count ?? 0;
      const ent = j?.total_entries ?? j?.entries ?? j?.row_count ?? 0;
      return `${dom} domains · ${ent.toLocaleString?.() || ent} entries in the hyperion knowledge base`;
    },
    details: j => {
      const out: { label: string; value: string }[] = [];
      Object.entries(j || {}).forEach(([k, v]) => {
        if (typeof v === 'number' || typeof v === 'string') {
          out.push({ label: k.replace(/_/g, ' '), value: String(v) });
        }
      });
      return out.slice(0, 10);
    },
    speakIntro: () => 'The Hyperion archives stand ready — every domain catalogued.',
  },
  {
    id: 'synergy', title: 'Jeeves Synergy', icon: 'git-network-outline', accent: '#10B981',
    endpoint: '/api/jeeves-synergy/overview',
    describe: j => j?.description || `${j?.modules?.length || j?.total_modules || 'Multiple'} modules orchestrated together`,
    details: j => {
      const out: { label: string; value: string }[] = [];
      const mods = j?.modules || [];
      if (Array.isArray(mods)) {
        mods.slice(0, 10).forEach((m: any, i: number) =>
          out.push({ label: `Module ${i + 1}`, value: typeof m === 'string' ? m : (m?.name || JSON.stringify(m).slice(0, 60)) })
        );
      }
      return out;
    },
    speakIntro: () => 'Synergy engine engaged — all modules harmonised.',
  },
  {
    id: 'masterbuild', title: 'Master Game Builder', icon: 'planet', accent: '#8b5cf6',
    endpoint: '/api/jeeves-build/genres',
    describe: j => {
      const arr = Array.isArray(j) ? j : j?.genres || [];
      return `${arr.length} genres available · spec-to-playable pipeline`;
    },
    details: j => {
      const arr = Array.isArray(j) ? j : j?.genres || [];
      return arr.slice(0, 12).map((g: any, i: number) => ({
        label: `Genre ${i + 1}`,
        value: typeof g === 'string' ? g : (g?.name || g?.id || JSON.stringify(g).slice(0, 50)),
      }));
    },
    speakIntro: () => 'Master builder online — every genre at our disposal.',
  },
  {
    id: 'camera', title: 'Jeeves Camera', icon: 'camera-outline', accent: '#f472b6',
    endpoint: '/api/jeeves/camera/knowledge',
    describe: j => {
      const arr = Array.isArray(j) ? j : j?.topics || j?.knowledge || [];
      return `${arr.length} camera-driven learning topics`;
    },
    details: j => {
      const arr = Array.isArray(j) ? j : j?.topics || j?.knowledge || [];
      return arr.slice(0, 8).map((t: any, i: number) => ({
        label: `Topic ${i + 1}`,
        value: typeof t === 'string' ? t : (t?.title || t?.name || JSON.stringify(t).slice(0, 60)),
      }));
    },
    speakIntro: () => 'Point a lens at the world — I shall narrate what we see.',
  },
  {
    id: 'daily', title: 'Daily Challenge', icon: 'flame-outline', accent: '#ef4444',
    endpoint: `/api/daily/challenge?user_id=${USER_ID}`,
    describe: j => {
      const c = j?.challenge || j;
      const title = c?.title || c?.problem_title || 'Today\'s coding challenge';
      const diff = c?.difficulty || '';
      return `${title}${diff ? ' · ' + diff : ''}`;
    },
    details: j => {
      const c = j?.challenge || j || {};
      const out: { label: string; value: string }[] = [];
      ['title', 'difficulty', 'language', 'category', 'time_estimate_min', 'xp_reward'].forEach(k => {
        if (c[k] != null) out.push({ label: k.replace(/_/g, ' '), value: String(c[k]) });
      });
      if (typeof c?.description === 'string') {
        out.push({ label: 'Description', value: c.description.slice(0, 240) });
      }
      return out;
    },
    speakIntro: () => 'Today\'s challenge awaits — sleeves up.',
  },
  {
    id: 'leaderboards', title: 'Leaderboards', icon: 'trophy-outline', accent: '#fbbf24',
    endpoint: '/api/leaderboards/boards',
    describe: j => {
      const arr = j?.boards || j || [];
      const n = Array.isArray(arr) ? arr.length : 0;
      return `${n} leaderboards live · weekly · monthly · all-time`;
    },
    details: j => {
      const arr = j?.boards || j || [];
      if (!Array.isArray(arr)) return [];
      return arr.slice(0, 8).map((b: any, i: number) => ({
        label: b?.name || b?.id || `Board ${i + 1}`,
        value: `${b?.metric || ''} ${b?.period ? `· ${b.period}` : ''}`.trim() || '—',
      }));
    },
    speakIntro: () => 'The leaderboards beckon — climb at your leisure.',
  },
  {
    id: 'gamification', title: 'XP · Level · Achievements', icon: 'medal-outline', accent: '#a3e635',
    endpoint: `/api/gamification/profile/${USER_ID}`,
    describe: j => {
      const xp = j?.xp ?? j?.total_xp ?? 0;
      const lvl = j?.level ?? 1;
      return `Level ${lvl} · ${xp.toLocaleString?.() || xp} XP`;
    },
    details: j => {
      const out: { label: string; value: string }[] = [];
      ['level', 'xp', 'total_xp', 'next_level_xp', 'streak', 'rank'].forEach(k => {
        if (j?.[k] != null) out.push({ label: k.replace(/_/g, ' '), value: String(j[k]) });
      });
      if (Array.isArray(j?.achievements)) {
        out.push({ label: 'Achievements', value: `${j.achievements.length} unlocked` });
      }
      return out;
    },
    speakIntro: () => 'Your XP and level — most respectable.',
  },
];

interface TileResult { tile: Tile; loading: boolean; data?: any; error?: string; }

export default function JeevesHubScreen() {
  const router = useRouter();
  const flagVoice    = useFeatureFlag('experimental_voice');
  const flagAudioTest = useFeatureFlag('jeeves_audio_test');
  /** Visible tiles depend on feature flags — Voice tile hides when experimental_voice is off. */
  const visibleTiles = useMemo(
    () => TILES.filter(t => (t.id === 'voice' ? flagVoice : true)),
    [flagVoice],
  );
  const [results, setResults] = useState<Record<string, TileResult>>(() =>
    Object.fromEntries(TILES.map(t => [t.id, { tile: t, loading: true }]))
  );
  const [refreshing, setRefreshing] = useState(false);
  const [open, setOpen] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    setRefreshing(true);
    await Promise.all(visibleTiles.map(async (t) => {
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
  }, [visibleTiles]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const stats = useMemo(() => {
    const total = visibleTiles.length;
    const live = visibleTiles.filter(t => {
      const r = results[t.id];
      return r && !r.loading && !r.error;
    }).length;
    return { total, live };
  }, [results, visibleTiles]);

  /** Tiles that errored on the last fetch — drives the inline RetryBanner. */
  const failedCount = useMemo(
    () => visibleTiles.filter(t => results[t.id]?.error).length,
    [results, visibleTiles],
  );

  const openTile = (id: string) => {
    setOpen(id);
    const r = results[id];
    if (r?.data && r.tile.speakIntro) {
      try { jeevesSpeak(r.tile.speakIntro(r.data), { context: 'lesson', prependCatchphrase: false }); } catch {}
    }
  };

  const openModalData = open ? results[open] : null;

  return (
    <SafeAreaView style={s.root}>
      <StatusBar barStyle="light-content" backgroundColor="#0A0A0A" />

      {/* Header */}
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.backBtn} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
          <Ionicons name="chevron-back" size={22} color="#a78bfa" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={s.title}>🎩 Jeeves Powerhouse Hub</Text>
          <Text style={s.subtitle}>
            {stats.live}/{stats.total} services live · all dials at your disposal
          </Text>
        </View>
        <TouchableOpacity onPress={fetchAll} style={s.refreshBtn} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
          <Ionicons name="refresh" size={18} color="#a78bfa" />
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={s.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={fetchAll} tintColor="#a78bfa" />}
      >
        {/* Harden — inline retry banner shows when any tile errored. */}
        {failedCount > 0 && !refreshing && (
          <RetryBanner
            error={`${failedCount} service${failedCount === 1 ? '' : 's'} unreachable — pull to refresh or tap retry.`}
            onRetry={fetchAll}
            retryLabel="Retry all"
          />
        )}
        {visibleTiles.map(t => {
          const r = results[t.id];
          const live = !r?.loading && !r?.error;
          return (
            <TouchableOpacity
              key={t.id}
              activeOpacity={0.85}
              onPress={() => openTile(t.id)}
              style={[s.card, { borderColor: t.accent + '55' }]}
            >
              <View style={[s.iconCircle, { backgroundColor: t.accent + '22', borderColor: t.accent }]}>
                <Ionicons name={t.icon} size={22} color={t.accent} />
              </View>
              <View style={{ flex: 1 }}>
                <View style={s.cardHeader}>
                  <Text style={s.cardTitle} numberOfLines={1}>{t.title}</Text>
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

        <View style={{ height: 30 }} />

        {/* P2 Audio diagnostics shortcut — feature-flag gated. */}
        {flagAudioTest && (
        <TouchableOpacity
          onPress={() => router.push('/jeeves-audio-test' as any)}
          activeOpacity={0.85}
          style={[s.card, { borderColor: '#3B82F666', backgroundColor: '#3B82F614' }]}
        >
          <View style={[s.iconCircle, { backgroundColor: '#3B82F622', borderColor: '#3B82F6' }]}>
            <Ionicons name="volume-high" size={22} color="#3B82F6" />
          </View>
          <View style={{ flex: 1 }}>
            <View style={s.cardHeader}>
              <Text style={s.cardTitle}>🎤 Audio Diagnostics</Text>
              <View style={[s.statusDot, { backgroundColor: '#3B82F6' }]} />
            </View>
            <Text style={s.cardDesc} numberOfLines={2}>
              Verify Jeeves TTS plays across all 19 personality contexts · catchphrase + mannerism preview
            </Text>
          </View>
          <Ionicons name="chevron-forward" size={18} color="#64748b" />
        </TouchableOpacity>
        )}

        <Text style={s.footer}>All endpoints live · pull-to-refresh for fresh data</Text>
      </ScrollView>

      {/* Detail modal — wrapped in ModalErrorBoundary so a bad payload from one
          tile doesn't take down the entire hub. The boundary's "Try again"
          re-runs the modal subtree from scratch. */}
      <Modal visible={!!open} transparent animationType="slide" onRequestClose={() => setOpen(null)}>
        <View style={s.modalBackdrop}>
          <View style={s.modalCard}>
            <ModalErrorBoundary name={openModalData?.tile.title || 'Jeeves tile'} onClose={() => setOpen(null)}>
            <View style={s.modalHeader}>
              <View style={[s.iconCircle, { backgroundColor: (openModalData?.tile.accent || '#a78bfa') + '22', borderColor: openModalData?.tile.accent || '#a78bfa' }]}>
                <Ionicons name={openModalData?.tile.icon || 'happy-outline'} size={18} color={openModalData?.tile.accent || '#a78bfa'} />
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
            </ModalErrorBoundary>
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
  cardHeader: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  cardTitle: { color: '#f1f5f9', fontSize: 14, fontWeight: '800', flex: 1 },
  cardDesc: { color: '#94a3b8', fontSize: 11, marginTop: 3, lineHeight: 15 },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  errText: { color: '#f87171', fontSize: 11, marginTop: 4 },
  footer: { color: '#64748b', fontSize: 10, textAlign: 'center', marginTop: 6, fontStyle: 'italic' },
  modalBackdrop: { flex: 1, backgroundColor: '#000000aa', justifyContent: 'flex-end' },
  modalCard: {
    backgroundColor: '#141414', borderTopLeftRadius: 20, borderTopRightRadius: 20,
    borderTopWidth: 1, borderColor: '#1F1F1F',
    paddingBottom: 24,
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
