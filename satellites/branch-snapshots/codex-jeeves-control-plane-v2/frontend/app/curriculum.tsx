/**
 * /curriculum — Unified Curriculum Hub
 * -------------------------------------------------------------------
 * One-screen browseable index of all CS classes + linked reading tracks
 * + quick links to AI reader and education endpoints. Reads from the
 * /curriculum/unified-index aggregator endpoint in a single round-trip.
 */
import { useEffect, useState, useCallback, useMemo } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  RefreshControl, StyleSheet, StatusBar, SafeAreaView, TextInput,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface LinkedReading {
  track_id?: string;
  title?: string;
  chapters?: number;
}
interface ClassRow {
  id: string;
  code: string;
  title: string;
  subtitle: string;
  hours: number;
  weeks: number;
  level: string;
  prerequisites: string[];
  linked_reading: LinkedReading[];
}
interface ReadingTrack {
  track_id?: string;
  id?: string;
  title?: string;
  description?: string;
  total_chapters?: number;
  chapters_count?: number;
  tags?: string[];
}
interface UnifiedIndex {
  version: string;
  total_classes: number;
  total_reading_tracks: number;
  classes: ClassRow[];
  reading_tracks: ReadingTrack[];
}

const LEVEL_TINT: Record<string, string> = {
  'beginner':     '#10B981',
  'intermediate': '#3B82F6',
  'advanced':     '#f59e0b',
  'expert':       '#f43f5e',
};

export default function CurriculumScreen() {
  const router = useRouter();
  const [data, setData] = useState<UnifiedIndex | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [err, setErr] = useState('');
  const [progress, setProgress] = useState<Record<string, number>>({});
  const [query, setQuery] = useState('');

  const fetchIndex = useCallback(async () => {
    setErr('');
    try {
      const r = await fetch(`${BACKEND}/api/curriculum/unified-index`);
      const j = await r.json();
      setData(j);
      // After we have the class list, fire off progress fetches in parallel
      const classes: ClassRow[] = j?.classes || [];
      const results = await Promise.allSettled(
        classes.map(async (c) => {
          try {
            const pr = await fetch(`${BACKEND}/api/class-progress/class/${encodeURIComponent(c.id)}?user_id=default_user`);
            const pj = await pr.json();
            return [c.id, pj?.completion_count || 0] as [string, number];
          } catch {
            return [c.id, 0] as [string, number];
          }
        })
      );
      const out: Record<string, number> = {};
      results.forEach((res) => {
        if (res.status === 'fulfilled' && res.value) out[res.value[0]] = res.value[1];
      });
      setProgress(out);
    } catch (e: any) {
      setErr(String(e?.message || e).slice(0, 120));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { fetchIndex(); }, [fetchIndex]);

  const openClass = (id: string) => {
    router.push({ pathname: '/class-week', params: { class_id: id, week: 1 } } as any);
  };
  const openReading = (trackId?: string, fromClassId?: string) => {
    // Reading library route — track filtering hooks into the modal's existing state
    const params: any = {};
    if (trackId) params.track = trackId;
    if (fromClassId) params.from_class = fromClassId;
    router.push({ pathname: '/readingLibrary', params } as any);
  };

  // Apply search filter
  const filteredClasses = useMemo(() => {
    if (!data?.classes) return [];
    const q = query.trim().toLowerCase();
    if (!q) return data.classes;
    return data.classes.filter(c =>
      (c.title + ' ' + c.code + ' ' + c.subtitle + ' ' + c.level).toLowerCase().includes(q)
    );
  }, [data?.classes, query]);

  const filteredTracks = useMemo(() => {
    if (!data?.reading_tracks) return [];
    const q = query.trim().toLowerCase();
    if (!q) return data.reading_tracks;
    return data.reading_tracks.filter(t =>
      ((t.title || '') + ' ' + (t.description || '') + ' ' + ((t.tags || []).join(' '))).toLowerCase().includes(q)
    );
  }, [data?.reading_tracks, query]);

  if (loading) {
    return (
      <View style={styles.loadingWrap}>
        <ActivityIndicator size="large" color="#a78bfa" />
        <Text style={styles.loadingText}>Loading curriculum…</Text>
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar barStyle="light-content" />
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
          <Ionicons name="arrow-back-outline" size={22} color="#fff" />
        </TouchableOpacity>
        <View style={{ flex: 1, marginLeft: 8 }}>
          <Text style={styles.title}>Curriculum</Text>
          <Text style={styles.subtitle}>
            {data?.total_classes ?? 0} classes · {data?.total_reading_tracks ?? 0} reading tracks
          </Text>
        </View>
        <TouchableOpacity
          onPress={() => openReading()}
          style={styles.libraryBtn}
          activeOpacity={0.8}
        >
          <Ionicons name="library-outline" size={16} color="#fff" />
          <Text style={styles.libraryBtnText}>Library</Text>
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); fetchIndex(); }} tintColor="#a78bfa" />}
      >
        {err ? (
          <View style={styles.errBox}>
            <Ionicons name="warning-outline" size={16} color="#f87171" />
            <Text style={styles.errText}>{err}</Text>
          </View>
        ) : null}

        {/* Classes section */}
        <Text style={styles.sectionTitle}>
          Classes {query ? `(${filteredClasses.length})` : ''}
        </Text>
        {filteredClasses.map(c => {
          const tint = LEVEL_TINT[c.level?.toLowerCase()] || '#94a3b8';
          const completionCount = progress[c.id] || 0;
          return (
            <View key={c.id} style={[styles.card, { borderColor: tint + '50' }]}>
              <TouchableOpacity activeOpacity={0.85} onPress={() => openClass(c.id)} style={styles.cardHeader}>
                <View style={[styles.codeBadge, { backgroundColor: tint + '22', borderColor: tint }]}>
                  <Text style={[styles.codeText, { color: tint }]}>{c.code}</Text>
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.classTitle} numberOfLines={1}>{c.title}</Text>
                  <Text style={styles.classSub} numberOfLines={2}>{c.subtitle}</Text>
                </View>
                {completionCount > 0 ? (
                  <View style={styles.completionBadge}>
                    <Ionicons name="checkmark-circle" size={12} color="#10B981" />
                    <Text style={styles.completionText}>{completionCount}×</Text>
                  </View>
                ) : (
                  <Ionicons name="chevron-forward-outline" size={20} color="#94a3b8" />
                )}
              </TouchableOpacity>

              <View style={styles.metaRow}>
                <Text style={styles.metaText}><Ionicons name="time-outline" size={11} color="#a78bfa" /> {c.hours}h · {c.weeks}w</Text>
                <Text style={[styles.metaText, { color: tint }]}>{c.level}</Text>
              </View>

              {/* Linked reading */}
              {c.linked_reading && c.linked_reading.length > 0 && (
                <View style={styles.readingBlock}>
                  <Text style={styles.readingTitle}>📖 Linked reading</Text>
                  {c.linked_reading.map(lr => (
                    <TouchableOpacity
                      key={lr.track_id || lr.title || Math.random().toString()}
                      style={styles.readingRow}
                      onPress={() => openReading(lr.track_id, c.id)}
                      activeOpacity={0.7}
                    >
                      <Ionicons name="book-outline" size={14} color="#fcd34d" />
                      <Text style={styles.readingRowText} numberOfLines={1}>{lr.title || 'Untitled track'}</Text>
                      <Text style={styles.readingChapters}>{lr.chapters || 0}ch</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              )}

              <TouchableOpacity
                style={styles.openReadingCTA}
                onPress={() => openReading(undefined, c.id)}
                activeOpacity={0.7}
              >
                <Ionicons name="library-outline" size={14} color="#a78bfa" />
                <Text style={styles.openReadingText}>Browse all reading for {c.code}</Text>
              </TouchableOpacity>
            </View>
          );
        })}
        {filteredClasses.length === 0 && query ? (
          <Text style={styles.emptyState}>No classes match &quot;{query}&quot;.</Text>
        ) : null}

        {/* Reading-only tracks (not linked to any class) */}
        {filteredTracks.length > 0 && (
          <>
            <Text style={[styles.sectionTitle, { marginTop: 16 }]}>
              All Reading Tracks {query ? `(${filteredTracks.length})` : ''}
            </Text>
            {filteredTracks.slice(0, 12).map(t => {
              const tid = t.track_id || t.id;
              return (
                <TouchableOpacity
                  key={tid}
                  style={styles.trackCard}
                  onPress={() => openReading(tid)}
                  activeOpacity={0.85}
                >
                  <Ionicons name="book" size={18} color="#fcd34d" />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.trackTitle} numberOfLines={1}>{t.title || 'Untitled'}</Text>
                    {!!t.description && <Text style={styles.trackDesc} numberOfLines={2}>{t.description}</Text>}
                  </View>
                  <Text style={styles.trackMeta}>{t.total_chapters || t.chapters_count || 0}ch</Text>
                </TouchableOpacity>
              );
            })}
          </>
        )}

        {/* Quick links */}
        <Text style={[styles.sectionTitle, { marginTop: 18 }]}>Quick Links</Text>
        <View style={styles.quickRow}>
          <TouchableOpacity style={styles.quickBtn} onPress={() => router.push('/my-classes' as any)} activeOpacity={0.7}>
            <Ionicons name="school-outline" size={20} color="#3B82F6" />
            <Text style={styles.quickText}>My Classes</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.quickBtn} onPress={() => openReading()} activeOpacity={0.7}>
            <Ionicons name="library-outline" size={20} color="#fcd34d" />
            <Text style={styles.quickText}>Reading Library</Text>
          </TouchableOpacity>
        </View>
        <View style={styles.quickRow}>
          <TouchableOpacity style={styles.quickBtn} onPress={() => router.push('/menu' as any)} activeOpacity={0.7}>
            <Ionicons name="apps-outline" size={20} color="#a78bfa" />
            <Text style={styles.quickText}>All Features</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.quickBtn} onPress={() => router.push('/' as any)} activeOpacity={0.7}>
            <Ionicons name="home-outline" size={20} color="#10B981" />
            <Text style={styles.quickText}>Hub</Text>
          </TouchableOpacity>
        </View>

        <View style={{ height: 40 }} />
      </ScrollView>

      <View style={styles.searchBox}>
        <Ionicons name="search-outline" size={16} color="#94a3b8" />
        <TextInput
          value={query}
          onChangeText={setQuery}
          placeholder="Search classes & reading tracks…"
          placeholderTextColor="#64748b"
          style={styles.searchInput}
          autoCorrect={false}
          autoCapitalize="none"
        />
        {!!query && (
          <TouchableOpacity onPress={() => setQuery('')} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Ionicons name="close-circle" size={16} color="#94a3b8" />
          </TouchableOpacity>
        )}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#0A0A0A' },
  loadingWrap: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#0A0A0A' },
  loadingText: { color: '#94a3b8', marginTop: 10, fontSize: 13 },
  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 14, paddingVertical: 12,
    borderBottomWidth: 1, borderBottomColor: '#1F1F1F',
    backgroundColor: '#0f0f1e',
  },
  backBtn: { padding: 4 },
  title: { color: '#fff', fontSize: 17, fontWeight: '800', letterSpacing: -0.2 },
  subtitle: { color: '#a78bfa', fontSize: 11, marginTop: 1 },
  libraryBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    backgroundColor: '#8B5CF6', paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8,
  },
  libraryBtnText: { color: '#fff', fontSize: 12, fontWeight: '700' },
  content: { paddingHorizontal: 14, paddingTop: 14 },
  errBox: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: '#7f1d1d33', borderColor: '#f87171',
    borderWidth: 1, padding: 10, borderRadius: 8, marginBottom: 10,
  },
  errText: { color: '#fecaca', fontSize: 11, flex: 1 },
  searchBox: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: '#1F1F1F', borderColor: '#404040', borderWidth: 1,
    paddingHorizontal: 12, paddingVertical: 9, borderRadius: 10,
    marginBottom: 12,
  },
  searchInput: { flex: 1, color: '#f1f5f9', fontSize: 13, padding: 0 },
  completionBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 3,
    paddingHorizontal: 7, paddingVertical: 4,
    borderRadius: 10, backgroundColor: '#10B98122', borderColor: '#10B981', borderWidth: 1,
  },
  completionText: { color: '#10B981', fontSize: 10, fontWeight: '800' },
  emptyState: {
    color: '#94a3b8', fontSize: 12, textAlign: 'center', paddingVertical: 24, fontStyle: 'italic',
  },
  sectionTitle: {
    color: '#94a3b8', fontSize: 11, fontWeight: '800',
    textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8,
  },
  card: {
    backgroundColor: '#13131f',
    borderWidth: 1, borderRadius: 12,
    padding: 12, marginBottom: 10,
  },
  cardHeader: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  codeBadge: {
    paddingHorizontal: 8, paddingVertical: 4,
    borderRadius: 6, borderWidth: 1,
    minWidth: 56, alignItems: 'center',
  },
  codeText: { fontSize: 11, fontWeight: '800', letterSpacing: 0.5 },
  classTitle: { color: '#f1f5f9', fontSize: 14, fontWeight: '800' },
  classSub:   { color: '#94a3b8', fontSize: 11, marginTop: 2, lineHeight: 15 },
  metaRow: {
    flexDirection: 'row', justifyContent: 'space-between',
    marginTop: 8, paddingTop: 8,
    borderTopWidth: 0.5, borderTopColor: '#1F1F1F',
  },
  metaText: { color: '#cbd5e1', fontSize: 11, fontWeight: '600' },
  readingBlock: { marginTop: 8, paddingTop: 8, borderTopWidth: 0.5, borderTopColor: '#1F1F1F' },
  readingTitle: { color: '#fcd34d', fontSize: 11, fontWeight: '800', marginBottom: 5 },
  readingRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingVertical: 6, paddingHorizontal: 8,
    backgroundColor: '#fcd34d12', borderRadius: 6, marginBottom: 4,
  },
  readingRowText: { flex: 1, color: '#fde68a', fontSize: 12, fontWeight: '600' },
  readingChapters: { color: '#fcd34daa', fontSize: 10, fontWeight: '700' },
  openReadingCTA: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    marginTop: 8, paddingVertical: 8,
    borderRadius: 6, borderWidth: 1, borderColor: '#a78bfa40',
    backgroundColor: '#a78bfa10',
  },
  openReadingText: { color: '#a78bfa', fontSize: 12, fontWeight: '700' },
  trackCard: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: '#13131f',
    borderWidth: 1, borderColor: '#1F1F1F',
    padding: 11, borderRadius: 10, marginBottom: 8,
  },
  trackTitle: { color: '#f1f5f9', fontSize: 13, fontWeight: '700' },
  trackDesc:  { color: '#94a3b8', fontSize: 11, marginTop: 2 },
  trackMeta:  { color: '#fcd34daa', fontSize: 10, fontWeight: '800' },
  quickRow: { flexDirection: 'row', gap: 8, marginBottom: 8 },
  quickBtn: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    paddingVertical: 14, borderRadius: 10,
    backgroundColor: '#13131f', borderWidth: 1, borderColor: '#1F1F1F',
  },
  quickText: { color: '#f1f5f9', fontSize: 12, fontWeight: '700' },
});
