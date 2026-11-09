/**
 * ═══════════════════════════════════════════════════════════════════════
 *  My Builds Gallery — every completed Galaxy Studio build, auto-saved.
 * ═══════════════════════════════════════════════════════════════════════
 *
 *  Lists builds from `/api/galaxy-studio/my-builds`. Each card shows the
 *  game title, genre, file count, vault state, timestamps, and quick
 *  actions: Open (re-opens the Galaxy Studio modal in Done step with
 *  Browse-Code/Vault/Download wired up), Re-zip, and Delete (vault only).
 *
 *  Pull-to-refresh, status filter chips (All / Completed / Building /
 *  Failed), and a search box. 2026 SOTA visuals — glass cards, semantic
 *  status pills, optimistic UI.
 * ═══════════════════════════════════════════════════════════════════════
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View, Text, FlatList, RefreshControl, Pressable, ActivityIndicator,
  TextInput, StyleSheet, Linking, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Screen, AppHeader, EmptyState, Chip } from '../components/ui';
import theme from '../theme/tokens';
import { apiFetch } from '../utils/apiController';
import { LinearGradient } from 'expo-linear-gradient';
import { toast } from '../components/Toast';

const BACKEND =
  (typeof window !== 'undefined' ? window.location.origin : '') ||
  (process.env.EXPO_PUBLIC_BACKEND_URL as string) || '';

type BuildRow = {
  build_id: string;
  title: string;
  genre: string;
  subgenre?: string;
  status: string;
  bg_status?: string;
  file_count: number;
  vault_present: boolean;
  completed_at?: string | null;
  created_at?: string | null;
  current_phase?: number;
  total_phases?: number;
};

const STATUS_TABS: { id: string; label: string; query: string }[] = [
  { id: 'all',       label: 'All',        query: '' },
  { id: 'completed', label: 'Completed',  query: 'completed' },
  { id: 'building',  label: 'In Progress',query: 'building'  },
  { id: 'failed',    label: 'Failed',     query: 'failed'    },
];

const fmtNum = (n: number) => (n || 0).toLocaleString();
const fmtDate = (iso?: string | null) => {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    const now = new Date();
    const diff = (now.getTime() - d.getTime()) / 1000;
    if (diff < 60) return 'just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
    return d.toLocaleDateString();
  } catch { return '—'; }
};

const statusColor = (status: string) => {
  switch (status) {
    case 'completed': return theme.palette.success[500];
    case 'building':  return theme.palette.brand[500];
    case 'paused':    return theme.palette.warning[500];
    case 'failed':    return theme.palette.danger[500];
    default:          return theme.palette.ink[400];
  }
};

const statusIcon = (status: string): keyof typeof Ionicons.glyphMap => {
  switch (status) {
    case 'completed': return 'checkmark-circle';
    case 'building':  return 'sync-circle';
    case 'paused':    return 'pause-circle';
    case 'failed':    return 'alert-circle';
    default:          return 'help-circle';
  }
};

export default function MyBuildsScreen() {
  const router = useRouter();
  const [tab, setTab] = useState<string>('all');
  const [search, setSearch] = useState('');
  const [builds, setBuilds] = useState<BuildRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [zipBusy, setZipBusy] = useState<string | null>(null);

  const fetchBuilds = useCallback(async (status: string) => {
    try {
      setError(null);
      const q = status ? `&status=${encodeURIComponent(status)}` : '';
      const r = await apiFetch(
        `${BACKEND}/api/galaxy-studio/my-builds?limit=100${q}`,
        { credentials: 'omit' },
      );
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setBuilds(data.builds || []);
    } catch (e: any) {
      setError(String(e?.message || e).slice(0, 200));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    const t = STATUS_TABS.find((x) => x.id === tab);
    fetchBuilds(t?.query || '');
  }, [tab, fetchBuilds]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    const t = STATUS_TABS.find((x) => x.id === tab);
    fetchBuilds(t?.query || '');
  }, [tab, fetchBuilds]);

  const filtered = useMemo(() => {
    if (!search.trim()) return builds;
    const q = search.toLowerCase();
    return builds.filter(
      (b) =>
        b.title?.toLowerCase().includes(q) ||
        b.genre?.toLowerCase().includes(q) ||
        b.build_id?.toLowerCase().includes(q),
    );
  }, [search, builds]);

  const openBuild = useCallback(
    async (b: BuildRow) => {
      if (Platform.OS !== 'web') {
        try { await Haptics.selectionAsync(); } catch {}
      }
      // Persist the active build_id so the Galaxy Studio modal resumes here.
      try {
        await AsyncStorage.setItem(
          '@galaxy_studio_active_build_v1',
          JSON.stringify({ build_id: b.build_id, title: b.title, resumed: true }),
        );
      } catch {}
      router.push('/galaxy');
    },
    [router],
  );

  const downloadZip = useCallback(async (b: BuildRow) => {
    setZipBusy(b.build_id);
    try {
      const r = await apiFetch(
        `${BACKEND}/api/galaxy-studio/vault/zip/${b.build_id}`,
        { method: 'POST', credentials: 'omit' },
      );
      if (!r.ok) {
        const t = await r.text();
        throw new Error(t.slice(0, 200));
      }
      const data = await r.json();
      const url = `${BACKEND}${data.download_url}`;
      try { await Linking.openURL(url); } catch {}
    } catch (e: any) {
      toast.error(`ZIP failed: ${String(e?.message || e)}`);
    } finally {
      setZipBusy(null);
    }
  }, []);

  const renderItem = useCallback(
    ({ item: b }: { item: BuildRow }) => {
      const sc = statusColor(b.status);
      const icon = statusIcon(b.status);
      const fileCountStr = b.file_count > 0 ? fmtNum(b.file_count) : '—';
      return (
        <Pressable
          onPress={() => openBuild(b)}
          style={({ pressed }) => [
            s.card,
            pressed && { opacity: 0.85, transform: [{ scale: 0.99 }] },
          ]}
          android_ripple={{ color: theme.colors.surfaceHover, borderless: false }}
        >
          {/* Top row: title + status pill */}
          <View style={s.cardTop}>
            <View style={{ flex: 1, marginRight: 10 }}>
              <Text style={s.title} numberOfLines={1}>
                {b.title || 'Untitled Build'}
              </Text>
              <Text style={s.subtitle} numberOfLines={1}>
                {b.genre || 'unknown genre'}{b.subgenre ? ` · ${b.subgenre.replace(/_/g, ' ')}` : ''}
              </Text>
            </View>
            <View style={[s.statusPill, { backgroundColor: sc + '22', borderColor: sc + '55' }]}>
              <Ionicons name={icon} size={11} color={sc} />
              <Text style={[s.statusText, { color: sc }]} numberOfLines={1}>
                {b.status}
              </Text>
            </View>
          </View>

          {/* Metrics row */}
          <View style={s.metricsRow}>
            <View style={s.metric}>
              <Ionicons name="document-text-outline" size={12} color={theme.palette.cyan[400]} />
              <Text style={s.metricVal}>{fileCountStr}</Text>
              <Text style={s.metricLbl}>files</Text>
            </View>
            <View style={s.metric}>
              <Ionicons
                name={b.vault_present ? 'cloud-done-outline' : 'cloud-offline-outline'}
                size={12}
                color={b.vault_present ? theme.palette.success[400] : theme.palette.ink[400]}
              />
              <Text
                style={[
                  s.metricLbl,
                  { color: b.vault_present ? theme.palette.success[400] : theme.palette.ink[400] },
                ]}
              >
                {b.vault_present ? 'vault' : 'no vault'}
              </Text>
            </View>
            <View style={s.metric}>
              <Ionicons name="time-outline" size={12} color={theme.palette.ink[300]} />
              <Text style={s.metricLbl}>{fmtDate(b.completed_at || b.created_at)}</Text>
            </View>
          </View>

          {/* Action row */}
          <View style={s.actionRow}>
            <Pressable
              onPress={() => openBuild(b)}
              style={({ pressed }) => [s.actionBtn, s.actionPrimary, pressed && { opacity: 0.85 }]}
              hitSlop={theme.hitSlop.md}
            >
              <Ionicons name="open-outline" size={13} color={theme.palette.ink[0]} />
              <Text style={s.actionPrimaryText}>Open</Text>
            </Pressable>
            <Pressable
              onPress={() => router.push({
                pathname: '/cover-studio',
                params: { pid: b.build_id, title: b.title || 'Your Game', genre: b.genre || '' },
              })}
              style={({ pressed }) => [s.actionBtn, s.actionGhost, pressed && { opacity: 0.85 }]}
              hitSlop={theme.hitSlop.md}
            >
              <Ionicons name="image-outline" size={13} color={theme.colors.text} />
              <Text style={s.actionGhostText}>Cover</Text>
            </Pressable>
            <Pressable
              onPress={() => router.push({
                pathname: '/camera-director',
                params: { pid: b.build_id, title: b.title || 'Your Game' },
              })}
              style={({ pressed }) => [s.actionBtn, s.actionGhost, pressed && { opacity: 0.85 }]}
              hitSlop={theme.hitSlop.md}
            >
              <Ionicons name="videocam-outline" size={13} color={theme.colors.text} />
              <Text style={s.actionGhostText}>Camera</Text>
            </Pressable>
            <Pressable
              onPress={() => router.push({
                pathname: '/physics-studio',
                params: { pid: b.build_id, title: b.title || 'Your Game' },
              })}
              style={({ pressed }) => [s.actionBtn, s.actionGhost, pressed && { opacity: 0.85 }]}
              hitSlop={theme.hitSlop.md}
            >
              <Ionicons name="planet-outline" size={13} color={theme.colors.text} />
              <Text style={s.actionGhostText}>Physics</Text>
            </Pressable>
            <Pressable
              onPress={() => downloadZip(b)}
              disabled={!b.vault_present || zipBusy === b.build_id}
              style={({ pressed }) => [
                s.actionBtn,
                s.actionGhost,
                (!b.vault_present || zipBusy === b.build_id) && { opacity: 0.4 },
                pressed && { opacity: 0.85 },
              ]}
              hitSlop={theme.hitSlop.md}
            >
              {zipBusy === b.build_id ? (
                <ActivityIndicator size="small" color={theme.colors.text} />
              ) : (
                <Ionicons name="download-outline" size={13} color={theme.colors.text} />
              )}
              <Text style={s.actionGhostText}>ZIP</Text>
            </Pressable>
          </View>
        </Pressable>
      );
    },
    [openBuild, downloadZip, zipBusy, router],
  );

  return (
    <Screen edges={['top']}>
      <AppHeader
        title="My Builds"
        subtitle={`${builds.length} saved · ${builds.filter((b) => b.vault_present).length} with vault`}
        onBack={() => router.back()}
        right={
          <Pressable onPress={onRefresh} hitSlop={theme.hitSlop.md} style={s.headerBtn}>
            <Ionicons name="refresh-outline" size={20} color={theme.colors.text} />
          </Pressable>
        }
      />

      {/* Tabs */}
      <View style={s.tabsRowWrap}>
        <View style={s.tabsRow}>
          {STATUS_TABS.map((t) => (
            <Chip
              key={t.id}
              label={t.label}
              active={tab === t.id}
              onPress={() => setTab(t.id)}
              size="sm"
            />
          ))}
        </View>
        <LinearGradient
          colors={['transparent', theme.colors.bg]}
          start={{ x: 0, y: 0.5 }}
          end={{ x: 1, y: 0.5 }}
          style={[s.tabsRowFade, { pointerEvents: 'none' }]}
        />
      </View>

      {/* List */}
      <View style={{ flex: 1 }}>
      {loading ? (
        <View style={s.center}>
          <ActivityIndicator size="large" color={theme.colors.primary} />
          <Text style={s.muted}>Loading your builds…</Text>
        </View>
      ) : error ? (
        <View style={s.center}>
          <Ionicons name="cloud-offline-outline" size={36} color={theme.palette.danger[400]} />
          <Text style={[s.muted, { color: theme.palette.danger[400] }]}>Couldn&apos;t load: {error}</Text>
          <Pressable onPress={onRefresh} style={s.retryBtn}>
            <Text style={s.retryText}>Retry</Text>
          </Pressable>
        </View>
      ) : filtered.length === 0 ? (
        <EmptyState
          icon="rocket-outline"
          title={search ? 'No matching builds' : 'No builds yet'}
          message={
            search
              ? 'Try a different keyword or clear the search.'
              : 'Open Galaxy Studio from the menu and build your first game.'
          }
          action={{
            label: search ? 'Clear search' : 'Open Galaxy Studio',
            onPress: () => (search ? setSearch('') : router.push('/galaxy')),
            icon: search ? 'close-circle-outline' : 'rocket-outline',
          }}
        />
      ) : (
        <FlatList
          data={filtered}
          keyExtractor={(b) => b.build_id}
          renderItem={renderItem}
          contentContainerStyle={s.listContent}
          ItemSeparatorComponent={() => <View style={{ height: 10 }} />}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              tintColor={theme.colors.primary}
              colors={[theme.colors.primary]}
            />
          }
        />
      )}
      </View>

      <View style={s.searchWrap}>
        <Ionicons name="search-outline" size={14} color={theme.palette.ink[400]} />
        <TextInput
          value={search}
          onChangeText={setSearch}
          placeholder="Search title, genre, or build id…"
          placeholderTextColor={theme.palette.ink[400]}
          style={s.searchInput}
          autoCapitalize="none"
          autoCorrect={false}
        />
        {search ? (
          <Pressable onPress={() => setSearch('')} hitSlop={theme.hitSlop.md}>
            <Ionicons name="close-circle" size={16} color={theme.palette.ink[400]} />
          </Pressable>
        ) : null}
      </View>
    </Screen>
  );
}

const s = StyleSheet.create({
  headerBtn: { padding: 6, borderRadius: 10 },
  tabsRowWrap: { position: 'relative' },
  tabsRowFade: {
    position: 'absolute',
    right: 0, top: 0, bottom: 0,
    width: 28,
  },
  tabsRow: {
    flexDirection: 'row',
    gap: 6,
    paddingLeft: theme.spacing.lg,
    paddingRight: theme.spacing.lg + 24,
    paddingTop: theme.spacing.sm,
    paddingBottom: theme.spacing.xs,
    flexWrap: 'wrap',
  },
  searchWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginHorizontal: theme.spacing.lg,
    marginBottom: theme.spacing.sm,
    paddingHorizontal: 12,
    paddingVertical: 9,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radii.lg,
  },
  searchInput: {
    flex: 1,
    color: theme.colors.text,
    fontSize: 13,
    paddingVertical: 0,
  },
  listContent: {
    paddingHorizontal: theme.spacing.lg,
    paddingBottom: theme.spacing['2xl'],
  },
  card: {
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radii.xl,
    padding: 14,
    gap: 10,
  },
  cardTop: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  title: {
    color: theme.colors.text,
    fontSize: 15,
    fontWeight: '800',
    marginBottom: 2,
  },
  subtitle: {
    color: theme.colors.textMuted,
    fontSize: 11,
    fontWeight: '600',
  },
  statusPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 999,
    borderWidth: 1,
  },
  statusText: {
    fontSize: 10,
    fontWeight: '800',
    textTransform: 'capitalize',
  },
  metricsRow: {
    flexDirection: 'row',
    gap: 14,
    flexWrap: 'wrap',
  },
  metric: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  metricVal: {
    color: theme.colors.text,
    fontSize: 12,
    fontWeight: '800',
  },
  metricLbl: {
    color: theme.colors.textMuted,
    fontSize: 10,
    fontWeight: '600',
  },
  actionRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 2,
  },
  actionBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 9,
    borderRadius: theme.radii.md,
    borderWidth: 1,
  },
  actionPrimary: {
    backgroundColor: theme.colors.primary,
    borderColor: theme.colors.primary,
  },
  actionPrimaryText: {
    color: theme.palette.ink[0],
    fontSize: 12,
    fontWeight: '800',
  },
  actionGhost: {
    backgroundColor: theme.colors.surfaceAlt,
    borderColor: theme.colors.border,
  },
  actionGhostText: {
    color: theme.colors.text,
    fontSize: 12,
    fontWeight: '700',
  },
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
    padding: 24,
  },
  muted: {
    color: theme.colors.textMuted,
    fontSize: 13,
    fontWeight: '600',
    textAlign: 'center',
  },
  retryBtn: {
    paddingHorizontal: 18,
    paddingVertical: 10,
    backgroundColor: theme.colors.primary,
    borderRadius: theme.radii.md,
    marginTop: 8,
  },
  retryText: {
    color: theme.palette.ink[0],
    fontSize: 13,
    fontWeight: '800',
  },
});
