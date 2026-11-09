/**
 * Galaxy Studio Gallery — browse all past builds.
 */
import { useEffect, useState, useCallback } from 'react';
import { View, Text, StyleSheet, ScrollView, ActivityIndicator, RefreshControl, Pressable, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { api } from '../utils/apiController';
import theme from '../theme/tokens';
import { Screen, AppHeader, EmptyState } from '../components/ui';
import { playTrailer } from '../src/utils/cinematicVoice';

export default function GalleryScreen() {
  const router = useRouter();
  const [builds, setBuilds] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const d = await api.get<any>('/api/galaxy-studio/my-builds', { params: { limit: 100 }, tag: 'gallery.list', cacheTtlMs: 30_000 });
      setBuilds(d?.builds || []);
    } catch {}
    setLoading(false);
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const onRefresh = () => { setRefreshing(true); load(); };

  return (
    <Screen edges={['top']}>
      <LinearGradient
        colors={['#8B5CF622', '#3B82F622', 'transparent'] as any}
        start={{ x: 0.2, y: 0 }}
        end={{ x: 0.9, y: 0.6 }}
        style={[st.aurora, { pointerEvents: 'none' }]}
      />
      <AppHeader
        title="Build Gallery"
        subtitle={`${builds.length} build${builds.length !== 1 ? 's' : ''}${loading ? ' · loading…' : ''}`}
        onBack={() => router.back()}
      />

      <ScrollView
        contentContainerStyle={st.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={theme.colors.primary} />}
      >
        {loading ? (
          <ActivityIndicator color={theme.colors.primary} style={{ marginTop: 40 }} />
        ) : builds.length === 0 ? (
          <EmptyState
            icon="planet-outline"
            title="No builds yet"
            message="Open Galaxy Studio from the editor to create your first game build. Every completed build will show up here."
            accentColor={theme.palette.brand[400]}
            action={{ label: 'Open editor', icon: 'arrow-forward', onPress: () => router.push('/' as any) }}
          />
        ) : (
          builds.map(b => <BuildCard key={b.build_id} build={b} />)
        )}
      </ScrollView>
    </Screen>
  );
}

function BuildCard({ build }: { build: any }) {
  const status = build.status || 'unknown';
  const [trailerBusy, setTrailerBusy] = useState(false);
  const onTrailer = async () => {
    setTrailerBusy(true);
    await playTrailer({
      pid: build.build_id || build.playable_id,
      title: build.title || 'Your Game',
      genre: build.genre,
      lore: build.description,
    });
    setTrailerBusy(false);
  };
  const color =
    status === 'completed' ? theme.colors.success :
    status === 'building'  ? theme.colors.info :
    status === 'failed'    ? theme.colors.danger :
    theme.colors.textMuted;
  const ageMs = build.created_at ? Date.now() - new Date(build.created_at).getTime() : 0;
  const ageStr = ageMs < 60000 ? 'just now'
    : ageMs < 3600000 ? `${Math.floor(ageMs / 60000)}m ago`
    : ageMs < 86400000 ? `${Math.floor(ageMs / 3600000)}h ago`
    : `${Math.floor(ageMs / 86400000)}d ago`;
  const filesLabel = (build.file_count || 0).toLocaleString();
  return (
    <Pressable style={({ pressed }) => [st.card, pressed && { transform: [{ scale: 0.99 }], opacity: 0.95 }]}>
      <LinearGradient
        colors={[color + '12', 'transparent'] as any}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={[StyleSheet.absoluteFillObject, { pointerEvents: 'none' }]}
      />
      <View style={st.cardHead}>
        <View style={[st.iconHalo, { backgroundColor: color + '22', borderColor: color + '44' }]}>
          <Ionicons name="planet" size={18} color={color} />
        </View>
        <Text style={st.cardTitle} numberOfLines={1}>{build.title || build.build_id}</Text>
        <View style={[st.statusPill, { backgroundColor: color + '22', borderColor: color + '66' }]}>
          <Text style={[st.statusText, { color }]}>{status.toUpperCase()}</Text>
        </View>
      </View>
      <View style={st.cardMeta}>
        <Text style={st.metaItem}>{build.genre || 'unknown'}</Text>
        <Text style={st.metaDot}>·</Text>
        <Text style={st.metaItem}>{filesLabel} files</Text>
        <Text style={st.metaDot}>·</Text>
        <Text style={st.metaItem}>{ageStr}</Text>
      </View>
      {build.description ? <Text style={st.cardDesc} numberOfLines={2}>{build.description}</Text> : null}
      <View style={st.cardActions}>
        <View style={st.progressTrack}>
          <View style={[st.progressFill, { width: `${Math.min(100, build.progress_percent || 0)}%`, backgroundColor: color }]} />
        </View>
        <Text style={st.progressLabel}>{Math.floor(build.progress_percent || 0)}%</Text>
        <TouchableOpacity testID={`trailer-${build.build_id || build.playable_id}`} onPress={onTrailer} style={st.trailerBtn} hitSlop={8}>
          {trailerBusy
            ? <ActivityIndicator size="small" color="#e879f9" />
            : <><Ionicons name="film-outline" size={14} color="#e879f9" /><Text style={st.trailerTxt}>Trailer</Text></>}
        </TouchableOpacity>
      </View>
    </Pressable>
  );
}

const st = StyleSheet.create({
  aurora: { position: 'absolute', top: 0, left: 0, right: 0, height: 220 },
  scroll: { padding: theme.spacing.base, paddingBottom: theme.spacing['3xl'] },
  card: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.lg,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.sm,
    borderWidth: 1,
    borderColor: theme.colors.border,
    overflow: 'hidden',
    ...theme.elevation.xs,
  },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: theme.spacing.sm },
  iconHalo: {
    width: 36, height: 36, borderRadius: theme.radii.md,
    borderWidth: 1,
    justifyContent: 'center', alignItems: 'center',
  },
  cardTitle: { color: theme.colors.text, ...theme.typography.h4, fontSize: 14, flex: 1 },
  statusPill: {
    borderRadius: theme.radii.full,
    paddingHorizontal: 8, paddingVertical: 3,
    borderWidth: 1,
  },
  statusText: { fontSize: 9, fontWeight: '800', letterSpacing: 0.5 },
  cardMeta: { flexDirection: 'row', alignItems: 'center', marginTop: 6, gap: 4 },
  metaItem: { color: theme.colors.textMuted, fontSize: 11, fontWeight: '600' },
  metaDot: { color: theme.colors.textDim },
  cardDesc: { color: theme.colors.textMuted, fontSize: 12, marginTop: 8, lineHeight: 17 },
  cardActions: { flexDirection: 'row', alignItems: 'center', marginTop: 12, gap: theme.spacing.sm },
  progressTrack: {
    flex: 1, height: 6,
    backgroundColor: theme.colors.bgSubtle,
    borderRadius: theme.radii.full,
    overflow: 'hidden',
  },
  progressFill: { height: '100%', borderRadius: theme.radii.full },
  progressLabel: { color: theme.colors.textMuted, fontSize: 11, fontWeight: '700', minWidth: 40, textAlign: 'right' },
  trailerBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: '#e879f918', borderWidth: 1, borderColor: '#e879f944', borderRadius: 8, paddingHorizontal: 8, paddingVertical: 5 },
  trailerTxt: { color: '#e879f9', fontSize: 11, fontWeight: '800' },
});
