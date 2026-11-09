/**
 * /collections — Creator Marketplace Collections / Playlists.
 *
 * Curate generated games into named, shareable bundles. Two views in one screen:
 *  • list of all collections (with a 3-cover preview strip)
 *  • a single collection's games (tap to play, swipe-free remove button)
 * No identity layer yet → collections are a shared community shelf.
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  StyleSheet, SafeAreaView, TextInput, Image, RefreshControl, Alert, Platform,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import * as Clipboard from 'expo-clipboard';
import api from '../src/utils/apiClient';
import { useHaptics } from '../src/hooks/useHaptics';
import theme from '../theme/tokens';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const { colors: C, spacing: S, radii: R } = { colors: theme.colors, spacing: theme.spacing, radii: theme.radii };

interface Game { playable_id: string; title: string; genre: string; has_cover?: boolean; plays?: number; overall?: number; }
interface CollectionListItem { collection_id: string; name: string; description: string; count: number; preview: Game[]; updated_at: string; }
interface CollectionDetail { collection_id: string; name: string; description: string; games: Game[]; count: number; }

function Cover({ g, size }: { g: Game; size: number }) {
  const [err, setErr] = React.useState(false);
  if (!g.has_cover || err) {
    return <View style={[styles.coverFallback, { width: size, height: size }]}><Text style={{ fontSize: size * 0.4 }}>🎮</Text></View>;
  }
  return (
    <Image
      source={{ uri: `${BACKEND}/api/playable/${g.playable_id}/cover.png` }}
      style={{ width: size, height: size, borderRadius: 10, backgroundColor: '#141414' }}
      resizeMode="cover"
      onError={() => setErr(true)}
    />
  );
}

export default function CollectionsScreen() {
  const router = useRouter();
  const haptics = useHaptics();
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);
  const [items, setItems] = React.useState<CollectionListItem[]>([]);
  const [open, setOpen] = React.useState<CollectionDetail | null>(null);
  const [newName, setNewName] = React.useState('');
  const [creating, setCreating] = React.useState(false);
  const [shared, setShared] = React.useState(false);
  const params = useLocalSearchParams<{ id?: string }>();

  const loadList = React.useCallback(async () => {
    const r = await api.get<{ collections: CollectionListItem[] }>('/api/collections', { timeoutMs: 12_000 });
    if (r.ok && r.data) setItems(r.data.collections || []);
    setLoading(false); setRefreshing(false);
  }, []);

  React.useEffect(() => { loadList(); }, [loadList]);

  const create = React.useCallback(async () => {
    const name = newName.trim();
    if (!name || creating) return;
    haptics.selection(); setCreating(true);
    const r = await api.post('/api/collections', { name }, { timeoutMs: 12_000 });
    setCreating(false);
    if (r.ok) { setNewName(''); haptics.notify('success'); loadList(); }
    else haptics.notify('error');
  }, [newName, creating, haptics, loadList]);

  const openCollection = React.useCallback(async (cid: string) => {
    haptics.selection();
    const r = await api.get<CollectionDetail>(`/api/collections/${cid}`, { timeoutMs: 12_000 });
    if (r.ok && r.data) setOpen(r.data);
  }, [haptics]);

  // Deep-link: /collections?id=<cid> opens that collection directly (shareable).
  React.useEffect(() => { if (params.id) openCollection(String(params.id)); }, [params.id, openCollection]);

  const shareCollection = React.useCallback(async (cid: string) => {
    haptics.selection();
    const url = Platform.OS === 'web' && typeof window !== 'undefined'
      ? `${window.location.origin}/collections?id=${cid}`
      : `codedock://collections?id=${cid}`;
    try {
      if (Platform.OS === 'web' && typeof navigator !== 'undefined' && (navigator as any).clipboard) {
        await (navigator as any).clipboard.writeText(url);
      } else { await Clipboard.setStringAsync(url); }
      setShared(true); setTimeout(() => setShared(false), 2000);
      haptics.notify('success');
    } catch { /* noop */ }
  }, [haptics]);

  const removeGame = React.useCallback(async (cid: string, pid: string) => {
    haptics.selection();
    const r = await api.del<{ removed: boolean }>(`/api/collections/${cid}/games/${pid}`, { timeoutMs: 12_000 });
    if (r.ok) { openCollection(cid); haptics.notify('success'); }
  }, [haptics, openCollection]);

  const deleteCollection = React.useCallback((cid: string, name: string) => {
    const doDelete = async () => {
      const r = await api.del(`/api/collections/${cid}`, { timeoutMs: 12_000 });
      if (r.ok) { setOpen(null); haptics.notify('success'); loadList(); }
    };
    if (Platform.OS === 'web') { doDelete(); return; }
    Alert.alert('Delete collection?', `"${name}" will be removed.`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: doDelete },
    ]);
  }, [haptics, loadList]);

  // ── Detail view ───────────────────────────────────────────────────────────
  if (open) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.header}>
          <TouchableOpacity testID="col-detail-back" hitSlop={theme.hitSlop.md} onPress={() => { haptics.selection(); setOpen(null); }} style={styles.headerBtn}>
            <Text style={styles.headerBtnTxt}>‹ Collections</Text>
          </TouchableOpacity>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
            <TouchableOpacity testID="col-share" hitSlop={theme.hitSlop.sm} onPress={() => shareCollection(open.collection_id)}>
              <Text style={styles.shareTxt}>{shared ? '✓ Link copied' : '🔗 Share'}</Text>
            </TouchableOpacity>
            <TouchableOpacity testID="col-delete" hitSlop={theme.hitSlop.sm} onPress={() => deleteCollection(open.collection_id, open.name)}>
              <Text style={styles.deleteTxt}>🗑️</Text>
            </TouchableOpacity>
          </View>
        </View>
        <ScrollView contentContainerStyle={styles.body}>
          <Text style={styles.detailTitle}>📚 {open.name}</Text>
          {open.description ? <Text style={styles.detailDesc}>{open.description}</Text> : null}
          <Text style={styles.detailCount}>{open.count} game{open.count === 1 ? '' : 's'}</Text>
          {open.games.length === 0 ? (
            <Text style={styles.empty}>No games yet. Open a game and tap “Save to collection”.</Text>
          ) : open.games.map((g) => (
            <View key={g.playable_id} style={styles.gameRow}>
              <TouchableOpacity testID={`col-game-${g.playable_id}`} style={styles.gameMain} activeOpacity={0.85} onPress={() => { haptics.selection(); router.push(`/playable?id=${g.playable_id}`); }}>
                <Cover g={g} size={48} />
                <View style={styles.gameMeta}>
                  <Text style={styles.gameTitle} numberOfLines={1}>{g.title}</Text>
                  <Text style={styles.gameSub} numberOfLines={1}>{g.genre} · ⭐{g.overall ?? '–'} · ▶{g.plays ?? 0}</Text>
                </View>
              </TouchableOpacity>
              <TouchableOpacity testID={`col-remove-${g.playable_id}`} hitSlop={theme.hitSlop.sm} style={styles.removeBtn} onPress={() => removeGame(open.collection_id, g.playable_id)}>
                <Text style={styles.removeTxt}>✕</Text>
              </TouchableOpacity>
            </View>
          ))}
        </ScrollView>
      </SafeAreaView>
    );
  }

  // ── List view ───────────────────────────────────────────────────────────
  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <TouchableOpacity testID="col-back" hitSlop={theme.hitSlop.md} onPress={() => { try { { if (router.canGoBack()) router.back(); else router.replace('/playable'); } } catch { router.replace('/playable'); } }} style={styles.headerBtn}>
          <Text style={styles.headerBtnTxt}>‹ Back</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>📚 Collections</Text>
        <View style={{ width: 60 }} />
      </View>

      <View style={styles.createRow}>
        <TextInput
          testID="col-new-name"
          style={styles.input}
          placeholder="New collection name…"
          placeholderTextColor={C.textDim}
          value={newName}
          onChangeText={setNewName}
          onSubmitEditing={create}
          returnKeyType="done"
          maxLength={80}
        />
        <TouchableOpacity testID="col-create" style={[styles.createBtn, (!newName.trim() || creating) && styles.createBtnOff]} disabled={!newName.trim() || creating} onPress={create}>
          <Text style={styles.createBtnTxt}>{creating ? '…' : '+ Create'}</Text>
        </TouchableOpacity>
      </View>

      {loading ? (
        <View style={styles.center}><ActivityIndicator color={C.accent} /></View>
      ) : (
        <ScrollView
          contentContainerStyle={styles.body}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); loadList(); }} tintColor={C.accent} />}
        >
          {items.length === 0 ? (
            <Text style={styles.empty}>No collections yet. Create one above, then add games from any game screen.</Text>
          ) : items.map((c) => (
            <TouchableOpacity key={c.collection_id} testID={`col-item-${c.collection_id}`} style={styles.card} activeOpacity={0.85} onPress={() => openCollection(c.collection_id)}>
              <View style={styles.previewStrip}>
                {c.preview.length ? c.preview.map((g) => <Cover key={g.playable_id} g={g} size={44} />) : <View style={[styles.coverFallback, { width: 44, height: 44 }]}><Text style={{ fontSize: 18 }}>📁</Text></View>}
              </View>
              <View style={styles.cardMeta}>
                <Text style={styles.cardTitle} numberOfLines={1}>{c.name}</Text>
                {c.description ? <Text style={styles.cardDesc} numberOfLines={1}>{c.description}</Text> : null}
                <Text style={styles.cardCount}>{c.count} game{c.count === 1 ? '' : 's'}</Text>
              </View>
              <Text style={styles.chev}>›</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: S.base, paddingVertical: S.md, borderBottomWidth: 1, borderBottomColor: C.border },
  headerBtn: { minWidth: 60 },
  headerBtnTxt: { color: C.accent, ...theme.typography.body, fontWeight: '700' },
  headerTitle: { color: C.text, ...theme.typography.h4, fontWeight: '800' },
  deleteTxt: { fontSize: 20 },
  shareTxt: { color: theme.colors.accent, ...theme.typography.body, fontWeight: '700' },
  createRow: { flexDirection: 'row', gap: S.sm, paddingHorizontal: S.base, paddingVertical: S.md },
  input: { flex: 1, backgroundColor: C.surface, borderRadius: R.lg, borderWidth: 1, borderColor: C.border, color: C.text, paddingHorizontal: S.md, paddingVertical: 10, ...theme.typography.body },
  createBtn: { paddingHorizontal: S.md, justifyContent: 'center', borderRadius: R.lg, backgroundColor: C.accent },
  createBtnOff: { opacity: 0.4 },
  createBtnTxt: { color: '#0b1020', fontWeight: '800', ...theme.typography.body },
  body: { padding: S.base, paddingBottom: 48, gap: S.sm },
  empty: { color: C.textDim, ...theme.typography.body, textAlign: 'center', marginTop: 40, paddingHorizontal: S.lg, lineHeight: 22 },
  card: { flexDirection: 'row', alignItems: 'center', gap: S.md, padding: S.md, borderRadius: R.xl, borderWidth: 1, borderColor: C.border, backgroundColor: C.surface },
  previewStrip: { flexDirection: 'row', gap: 3 },
  cardMeta: { flex: 1 },
  cardTitle: { color: C.text, ...theme.typography.body, fontWeight: '800' },
  cardDesc: { color: C.textDim, ...theme.typography.caption, marginTop: 1 },
  cardCount: { color: C.accent, ...theme.typography.micro, fontWeight: '700', marginTop: 3 },
  chev: { color: C.textDim, fontSize: 24 },
  coverFallback: { borderRadius: 10, backgroundColor: '#161b2e', alignItems: 'center', justifyContent: 'center' },
  detailTitle: { color: C.text, ...theme.typography.h3, fontWeight: '800' },
  detailDesc: { color: C.textDim, ...theme.typography.body, marginTop: 4 },
  detailCount: { color: C.accent, ...theme.typography.caption, fontWeight: '700', marginTop: 6, marginBottom: S.sm },
  gameRow: { flexDirection: 'row', alignItems: 'center', borderRadius: R.lg, borderWidth: 1, borderColor: C.border, backgroundColor: C.surface, paddingRight: S.md },
  gameMain: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: S.md, padding: S.sm },
  gameMeta: { flex: 1 },
  gameTitle: { color: C.text, ...theme.typography.body, fontWeight: '700' },
  gameSub: { color: C.textDim, ...theme.typography.caption, marginTop: 1 },
  removeBtn: { width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(239,68,68,0.15)' },
  removeTxt: { color: '#f87171', fontWeight: '800', fontSize: 15 },
});
