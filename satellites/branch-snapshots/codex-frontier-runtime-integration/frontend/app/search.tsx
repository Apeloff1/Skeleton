/**
 * Global Search — books, bibles, tracks, classes (parallel).
 */
import { useEffect, useMemo, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, ActivityIndicator, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { api } from '../utils/apiController';
import { openModalFromRoute } from '../utils/openModalFromRoute';
import theme from '../theme/tokens';
import { Screen, AppHeader, SearchBar, SectionHeader, EmptyState } from '../components/ui';

interface Hit { type: 'book' | 'bible' | 'track' | 'class' | 'feature' | 'capability' | 'dataset' | 'pipeline'; id: string; title: string; subtitle?: string; route?: string; }

const ICONS: Record<string, any> = { book: 'book', bible: 'library', track: 'git-branch', class: 'school', feature: 'apps', capability: 'hardware-chip', dataset: 'server', pipeline: 'git-network' };
const COLORS: Record<string, string> = { book: theme.colors.info, bible: theme.palette.brand[400], track: theme.colors.success, class: theme.colors.warning, feature: theme.colors.info, capability: theme.palette.brand[400], dataset: theme.colors.success, pipeline: theme.colors.warning };
const LABELS: Record<string, string> = { book: 'Books', bible: 'Bibles', track: 'Tracks', class: 'Classes', feature: 'Features & Screens', capability: 'Capability Systems', dataset: 'Datasets', pipeline: 'Pipeline Stages' };

export default function SearchScreen() {
  const router = useRouter();
  const [q, setQ] = useState('');
  const [hits, setHits] = useState<Hit[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!q.trim()) { setHits([]); return; }
    setLoading(true);
    const term = q.trim().toLowerCase();
    Promise.all([
      api.get<any>('/api/academy/reading-library', { params: { page: 1, limit: 50 }, tag: 'search.books', cacheTtlMs: 5 * 60_000 }).catch(() => null),
      api.get<any>('/api/academy/bibles', { params: { page: 1, limit: 50 }, tag: 'search.bibles', cacheTtlMs: 5 * 60_000 }).catch(() => null),
      api.get<any>('/api/academy/tracks', { params: { page: 1, limit: 50 }, tag: 'search.tracks', cacheTtlMs: 5 * 60_000 }).catch(() => null),
      api.get<any>('/api/curriculum/classes', { tag: 'search.classes', cacheTtlMs: 5 * 60_000 }).catch(() => null),
      api.get<any>('/api/search/global', { params: { q: term }, tag: 'search.global', cacheTtlMs: 60_000 }).catch(() => null),
    ]).then(([books, bibles, tracks, classes, globalRes]) => {
      const all: Hit[] = [];
      const matches = (s?: string) => !!s && s.toLowerCase().includes(term);
      (books?.books || []).forEach((b: any) => {
        if (matches(b.title) || matches(b.author) || matches(b.category))
          all.push({ type: 'book', id: b.id, title: b.title, subtitle: `${b.author || ''} · ${b.category || ''}` });
      });
      (bibles?.bibles || []).forEach((b: any) => {
        if (matches(b.title) || matches(b.category))
          all.push({ type: 'bible', id: b.id, title: b.title, subtitle: b.category || 'Bible' });
      });
      (tracks?.tracks || []).forEach((t: any) => {
        if (matches(t.title) || matches(t.category))
          all.push({ type: 'track', id: t.id, title: t.title, subtitle: `${t.category || ''} · ${t.total_hours || '?'} hrs` });
      });
      (classes?.classes || []).forEach((c: any) => {
        if (matches(c.title) || matches(c.description) || matches(c.code))
          all.push({ type: 'class', id: c.id, title: c.title, subtitle: c.code || `${c.weeks_count || c.weeks || '?'} weeks` });
      });
      const gr = (globalRes?.results || {}) as Record<string, any[]>;
      ([['feature', 'features'], ['capability', 'capabilities'], ['dataset', 'datasets'], ['pipeline', 'pipeline']] as const).forEach(([gt, key]) => {
        (gr[key] || []).forEach((it: any) => all.push({ type: gt, id: `${gt}:${it.label}`, title: it.label, subtitle: it.category, route: it.route }));
      });
      setHits(all);
      setLoading(false);
    });
  }, [q]);

  const grouped = useMemo(() => {
    const g: Record<string, Hit[]> = { feature: [], class: [], book: [], bible: [], track: [], capability: [], dataset: [], pipeline: [] };
    hits.forEach(h => g[h.type].push(h));
    return g;
  }, [hits]);

  // P3 — Route a search hit to the right destination, integrating the
  // legacy modals where no dedicated route exists yet.
  const onHitPress = (h: Hit) => {
    switch (h.type) {
      case 'class':
        // /class-week renders week 1 if no week param is supplied; pass class id so
        // the deep route opens directly into the class hub.
        router.push({ pathname: '/class-week', params: { class: h.id, title: h.title } } as any);
        break;
      case 'book':
        // /readingLibrary supports a ?book=ID deep-link.
        router.push({ pathname: '/readingLibrary', params: { book: h.id } } as any);
        break;
      case 'bible':
        // No native bible route — fall back to the integrated modal.
        openModalFromRoute(router, 'bible', { bibleId: h.id });
        break;
      case 'track':
        // Tracks live inside the Mega Academy / Build hub.
        openModalFromRoute(router, 'languageTrack', { trackId: h.id });
        break;
      case 'feature':
      case 'capability':
      case 'dataset':
      case 'pipeline':
        // App-wide results carry a direct route.
        if (h.route) router.push(h.route as any);
        break;
    }
  };

  return (
    <Screen edges={['top']}>
      <LinearGradient
        colors={['#3B82F622', '#8B5CF622', 'transparent'] as any}
        start={{ x: 0.2, y: 0 }}
        end={{ x: 0.9, y: 0.6 }}
        style={[s.aurora, { pointerEvents: 'none' }]}
      />
      <AppHeader title="Search" onBack={() => router.back()} />

      <View style={s.searchWrap}>
        <SearchBar value={q} onChangeText={setQ} placeholder="Books, bibles, tracks, classes…" autoFocus />
      </View>

      <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">
        {loading && (
          <View style={{ paddingVertical: 30, alignItems: 'center' }}>
            <ActivityIndicator color={theme.colors.primary} />
          </View>
        )}
        {!loading && q.trim() && hits.length === 0 && (
          <EmptyState
            icon="search-outline"
            title={`No results for “${q}”`}
            message="Try a different term, check the spelling, or browse the catalog from My Classes / Reading."
          />
        )}
        {!loading && q.trim() === '' && (
          <EmptyState
            icon="search"
            title="Search everything"
            message="Find books, bibles, tracks, and classes across the entire library — start typing above."
            accentColor={theme.colors.accentCyan}
          />
        )}
        {(['feature', 'class', 'book', 'bible', 'track', 'capability', 'dataset', 'pipeline'] as const).map(type => grouped[type].length > 0 && (
          <View key={type} style={s.group}>
            <SectionHeader label={LABELS[type]} count={grouped[type].length} accentColor={COLORS[type]} />
            {grouped[type].map(h => (
              <Pressable
                key={`${type}:${h.id}`}
                onPress={() => onHitPress(h)}
                style={({ pressed }) => [s.row, pressed && { opacity: 0.85, transform: [{ scale: 0.99 }] }]}
              >
                <View style={[s.iconBox, { backgroundColor: COLORS[type] + '22', borderColor: COLORS[type] + '44' }]}>
                  <Ionicons name={ICONS[type]} size={16} color={COLORS[type]} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={s.title}>{h.title}</Text>
                  {h.subtitle ? <Text style={s.subtitle}>{h.subtitle}</Text> : null}
                </View>
                <Ionicons name="chevron-forward" size={16} color={theme.colors.textDim} />
              </Pressable>
            ))}
          </View>
        ))}
      </ScrollView>
    </Screen>
  );
}

const s = StyleSheet.create({
  aurora: { position: 'absolute', top: 0, left: 0, right: 0, height: 220 },
  searchWrap: { paddingHorizontal: theme.spacing.base, paddingTop: theme.spacing.xs, paddingBottom: theme.spacing.sm },
  scroll: { padding: theme.spacing.base, paddingBottom: theme.spacing['3xl'] },
  group: { marginBottom: theme.spacing.lg },
  row: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.md,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.xs,
    gap: theme.spacing.sm,
    borderWidth: 1, borderColor: theme.colors.border,
    minHeight: 56,
  },
  iconBox: {
    width: 36, height: 36, borderRadius: theme.radii.md,
    justifyContent: 'center', alignItems: 'center',
    borderWidth: 1,
  },
  title: { color: theme.colors.text, fontSize: 14, fontWeight: '700' },
  subtitle: { color: theme.colors.textMuted, fontSize: 12, marginTop: 2 },
});
