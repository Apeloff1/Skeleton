import { useEffect, useState, useCallback, useRef } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, SafeAreaView,
  ActivityIndicator, Switch,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { toast } from '../../components/Toast';
import { actionSheet } from '../../components/ActionSheet';
import {
  syncAllOffline, getSyncState, getOfflineFootprint, clearOfflineCache,
  pauseSync, SyncState,
} from '../../utils/offlineSync';

type ItemType = 'book' | 'bible' | 'track' | 'subject';

function fmtBytes(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  if (b < 1024 * 1024 * 1024) return `${(b / 1024 / 1024).toFixed(1)} MB`;
  return `${(b / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export default function OfflineSettings() {
  const router = useRouter();
  const [state, setState] = useState<SyncState | null>(null);
  const [footprint, setFootprint] = useState<{ files: number; bytes: number }>({ files: 0, bytes: 0 });
  const [busy, setBusy] = useState(false);
  const [chaptersPerItem, setChaptersPerItem] = useState<5 | 10 | 999>(999);
  const [includeBooks, setIncludeBooks] = useState(true);
  const [includeBibles, setIncludeBibles] = useState(true);
  const [includeTracks, setIncludeTracks] = useState(true);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const refresh = useCallback(async () => {
    const [st, fp] = await Promise.all([getSyncState(), getOfflineFootprint()]);
    if (!mountedRef.current) return;
    setState(st);
    setFootprint(fp);
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 1500);
    return () => clearInterval(t);
  }, [refresh]);

  const startSync = useCallback(async () => {
    const types: ItemType[] = [];
    if (includeBooks) types.push('book');
    if (includeBibles) types.push('bible');
    if (includeTracks) types.push('track');
    if (types.length === 0) {
      toast.info('Select Books, Bibles, or Tracks before starting.');
      return;
    }
    setBusy(true);
    try {
      await syncAllOffline(
        (st) => { if (mountedRef.current) setState(st); },
        { chaptersPerItem: chaptersPerItem === 999 ? Infinity as any : chaptersPerItem, itemTypes: types },
      );
    } finally {
      if (mountedRef.current) {
        setBusy(false);
        refresh();
      }
    }
  }, [includeBooks, includeBibles, includeTracks, chaptersPerItem, refresh]);

  const onPause = useCallback(() => {
    pauseSync();
  }, []);

  const onClear = useCallback(() => {
    actionSheet.show({
      title: 'Clear offline cache?',
      message: `This will delete ${footprint.files} cached chapters (${fmtBytes(footprint.bytes)}). You can re-download anytime.`,
      options: [
        { label: 'Cancel', kind: 'cancel' },
        {
          label: 'Clear cache', kind: 'destructive', onPress: async () => {
            await clearOfflineCache();
            await refresh();
            toast.warn('Offline cache cleared');
          },
        },
      ],
    });
  }, [footprint, refresh]);

  const pct = state && state.total > 0 ? Math.min(100, Math.round((state.downloaded / state.total) * 100)) : 0;
  const isDownloading = state?.status === 'downloading';

  return (
    <SafeAreaView style={s.container}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.headerBtn} hitSlop={{ top: 8, left: 8, right: 8, bottom: 8 }}>
          <Ionicons name="arrow-back" size={24} color="#F8FAFC" />
        </TouchableOpacity>
        <Text style={s.headerTitle}>Sync for Offline</Text>
        <View style={{ width: 44 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 60 }}>
        <Text style={s.intro}>
          Download Academy content (books, bibles, tracks) to your device so you can read &amp; listen
          without a network connection. Chapters open instantly from cache once downloaded.
          Storage is shared with your browser/app — works on Web preview AND installed APK.
        </Text>

        {/* Footprint card */}
        <View style={s.card}>
          <View style={s.cardHeader}>
            <Ionicons name="cube" size={18} color="#F472B6" />
            <Text style={s.cardTitle}>Local cache</Text>
          </View>
          <View style={s.statsRow}>
            <View style={s.stat}>
              <Text style={s.statValue}>{footprint.files}</Text>
              <Text style={s.statLabel}>files</Text>
            </View>
            <View style={s.statDivider} />
            <View style={s.stat}>
              <Text style={s.statValue}>{fmtBytes(footprint.bytes)}</Text>
              <Text style={s.statLabel}>on disk</Text>
            </View>
            <View style={s.statDivider} />
            <View style={s.stat}>
              <Text style={s.statValue}>{state?.last_run ? new Date(state.last_run).toLocaleDateString() : '—'}</Text>
              <Text style={s.statLabel}>last sync</Text>
            </View>
          </View>
        </View>

        {/* Progress card */}
        {state && (state.status === 'downloading' || state.status === 'completed' || state.status === 'paused' || state.status === 'failed') && (
          <View style={s.card}>
            <View style={s.cardHeader}>
              <Ionicons
                name={state.status === 'completed' ? 'checkmark-circle' : state.status === 'failed' ? 'alert-circle' : state.status === 'paused' ? 'pause-circle' : 'cloud-download'}
                size={18}
                color={state.status === 'completed' ? '#10B981' : state.status === 'failed' ? '#EF4444' : state.status === 'paused' ? '#F59E0B' : '#3B82F6'}
              />
              <Text style={s.cardTitle}>
                {state.status === 'downloading' && `Downloading… ${state.downloaded}/${state.total}`}
                {state.status === 'completed' && `Sync complete — ${state.downloaded} chapters`}
                {state.status === 'paused' && `Paused — ${state.downloaded}/${state.total}`}
                {state.status === 'failed' && `Sync failed`}
              </Text>
            </View>
            <View style={s.progressTrack}>
              <View style={[
                s.progressFill,
                { width: `${pct}%`, backgroundColor: state.status === 'failed' ? '#EF4444' : state.status === 'completed' ? '#10B981' : '#3B82F6' },
              ]} />
            </View>
            <Text style={s.progressLabel}>
              {pct}%   •   {state.manifest_books} items planned   •   {state.manifest_chapters} chapters planned
            </Text>
            {state.error && <Text style={s.errorText}>Error: {state.error}</Text>}
          </View>
        )}

        {/* Plan card */}
        <View style={s.card}>
          <View style={s.cardHeader}>
            <Ionicons name="options" size={18} color="#A78BFA" />
            <Text style={s.cardTitle}>Sync plan</Text>
          </View>

          <Text style={s.sectionLabel}>Chapters per item</Text>
          <View style={s.segRow}>
            {([5, 10, 999] as const).map(v => (
              <TouchableOpacity
                key={v}
                style={[s.segBtn, chaptersPerItem === v && s.segBtnActive]}
                onPress={() => setChaptersPerItem(v)}
                activeOpacity={0.7}
              >
                <Text style={[s.segBtnText, chaptersPerItem === v && s.segBtnTextActive]}>
                  {v === 999 ? 'All' : `${v}`}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
          <Text style={s.hint}>
            Tip: 5 chapters per item ≈ light footprint, fast download.
            {'"'}All{'"'} downloads the entire library — may be 100MB+ depending on inventory.
          </Text>

          <Text style={[s.sectionLabel, { marginTop: 18 }]}>Include</Text>
          <ToggleRow icon="book" color="#F97316" label="Books" sub="Open-license texts &amp; companions" value={includeBooks} onValueChange={setIncludeBooks} />
          <ToggleRow icon="library" color="#8B5CF6" label="Bibles" sub="Reference compendia" value={includeBibles} onValueChange={setIncludeBibles} />
          <ToggleRow icon="git-branch" color="#3B82F6" label="Tracks" sub="Multi-chapter learning paths" value={includeTracks} onValueChange={setIncludeTracks} />
        </View>

        {/* Actions */}
        <View style={s.actionsRow}>
          {!isDownloading ? (
            <TouchableOpacity
              style={[s.primaryBtn, busy && s.primaryBtnDisabled]}
              onPress={startSync}
              disabled={busy}
              activeOpacity={0.8}
            >
              {busy ? <ActivityIndicator color="#fff" /> : <Ionicons name="cloud-download" size={18} color="#fff" />}
              <Text style={s.primaryBtnText}>{busy ? 'Starting…' : 'Start Sync'}</Text>
            </TouchableOpacity>
          ) : (
            <TouchableOpacity style={s.warnBtn} onPress={onPause} activeOpacity={0.8}>
              <Ionicons name="pause" size={18} color="#fff" />
              <Text style={s.primaryBtnText}>Pause</Text>
            </TouchableOpacity>
          )}

          <TouchableOpacity style={s.dangerBtn} onPress={onClear} activeOpacity={0.8}>
            <Ionicons name="trash" size={16} color="#EF4444" />
            <Text style={s.dangerBtnText}>Clear cache</Text>
          </TouchableOpacity>
        </View>

        <Text style={s.footerHint}>
          Downloaded chapters are served instantly from local storage by the Reading Visualizer.
          You can browse the Academy normally — cached chapters skip the network entirely.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

function ToggleRow({
  icon, color, label, sub, value, onValueChange,
}: { icon: any; color: string; label: string; sub: string; value: boolean; onValueChange: (v: boolean) => void }) {
  return (
    <View style={s.toggleRow}>
      <View style={[s.toggleIcon, { backgroundColor: color + '22' }]}>
        <Ionicons name={icon} size={18} color={color} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={s.toggleLabel}>{label}</Text>
        <Text style={s.toggleSub}>{sub}</Text>
      </View>
      <Switch
        value={value}
        onValueChange={onValueChange}
        trackColor={{ false: '#404040', true: color + 'AA' }}
        thumbColor={value ? color : '#94A3B8'}
      />
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#141414' },
  header: { flexDirection: 'row', alignItems: 'center', padding: 12, backgroundColor: '#262626', borderBottomWidth: 1, borderBottomColor: '#404040' },
  headerBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  headerTitle: { flex: 1, textAlign: 'center', fontSize: 18, fontWeight: '700', color: '#F8FAFC' },
  intro: { color: '#94A3B8', fontSize: 13, lineHeight: 20, marginBottom: 16 },
  card: { backgroundColor: '#262626', borderRadius: 12, padding: 14, marginBottom: 12, borderWidth: 1, borderColor: '#404040' },
  cardHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: 12 },
  cardTitle: { color: '#F8FAFC', fontSize: 14, fontWeight: '700', marginLeft: 8 },
  statsRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  stat: { flex: 1, alignItems: 'center' },
  statValue: { color: '#F8FAFC', fontSize: 18, fontWeight: '800' },
  statLabel: { color: '#94A3B8', fontSize: 11, marginTop: 2, textTransform: 'uppercase', letterSpacing: 0.5 },
  statDivider: { width: 1, height: 32, backgroundColor: '#404040' },
  progressTrack: { height: 10, backgroundColor: '#141414', borderRadius: 6, overflow: 'hidden', marginBottom: 8, borderWidth: 1, borderColor: '#404040' },
  progressFill: { height: '100%', borderRadius: 6 },
  progressLabel: { color: '#94A3B8', fontSize: 12, fontWeight: '600' },
  errorText: { color: '#FCA5A5', fontSize: 12, marginTop: 6 },
  sectionLabel: { color: '#CBD5E1', fontSize: 12, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 },
  segRow: { flexDirection: 'row', backgroundColor: '#141414', borderRadius: 8, padding: 4, borderWidth: 1, borderColor: '#404040' },
  segBtn: { flex: 1, paddingVertical: 10, alignItems: 'center', borderRadius: 6 },
  segBtnActive: { backgroundColor: '#3B82F6' },
  segBtnText: { color: '#94A3B8', fontWeight: '700', fontSize: 13 },
  segBtnTextActive: { color: '#fff' },
  hint: { color: '#64748B', fontSize: 11, lineHeight: 16, marginTop: 8, fontStyle: 'italic' },
  toggleRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 8, borderTopWidth: 1, borderTopColor: '#404040' },
  toggleIcon: { width: 36, height: 36, borderRadius: 10, justifyContent: 'center', alignItems: 'center', marginRight: 12 },
  toggleLabel: { color: '#F8FAFC', fontSize: 14, fontWeight: '700' },
  toggleSub: { color: '#94A3B8', fontSize: 11, marginTop: 1 },
  actionsRow: { flexDirection: 'row', gap: 10, marginTop: 4 },
  primaryBtn: { flex: 2, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', backgroundColor: '#3B82F6', paddingVertical: 14, borderRadius: 10, gap: 8 },
  primaryBtnDisabled: { opacity: 0.6 },
  primaryBtnText: { color: '#fff', fontWeight: '800', fontSize: 14 },
  warnBtn: { flex: 2, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', backgroundColor: '#F59E0B', paddingVertical: 14, borderRadius: 10, gap: 8 },
  dangerBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#7F1D1D', paddingVertical: 14, borderRadius: 10, gap: 6 },
  dangerBtnText: { color: '#EF4444', fontWeight: '700', fontSize: 12 },
  footerHint: { color: '#64748B', fontSize: 11, lineHeight: 16, marginTop: 18, fontStyle: 'italic', textAlign: 'center' },
});
