/**
 * /worldforge-vault — saved Worldforge artifacts.
 * Tabs: Monographs (GET /monograph/saved → /saved/{id}) and Posters (GET /poster/saved).
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  StyleSheet, SafeAreaView, RefreshControl, Modal, Platform, Share, Image,
} from 'react-native';
import { useRouter } from 'expo-router';
import api from '../src/utils/apiClient';
import { useHaptics } from '../src/hooks/useHaptics';
import UnifiedVault from '../src/components/UnifiedVault';

type Mono = { id: string; name: string; scale: string; model: string; chars: number; created_at: string };
type Poster = { id: string; name: string; scale: string; style: string; image: string; created_at: string };

export default function WorldforgeVault() {
  const router = useRouter();
  const haptics = useHaptics();
  const [tab, setTab] = React.useState<'all' | 'monographs' | 'posters'>('all');
  const [monos, setMonos] = React.useState<Mono[]>([]);
  const [posters, setPosters] = React.useState<Poster[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);
  const [open, setOpen] = React.useState<any>(null);
  const [openLoading, setOpenLoading] = React.useState(false);

  const load = React.useCallback(async () => {
    const [m, p] = await Promise.all([
      api.get<any>('/api/worldforge/monograph/saved', { timeoutMs: 15000 }),
      api.get<any>('/api/worldforge/poster/saved', { timeoutMs: 20000 }),
    ]);
    if (m.ok && m.data?.items) setMonos(m.data.items);
    if (p.ok && p.data?.items) setPosters(p.data.items);
    setLoading(false); setRefreshing(false);
  }, []);

  React.useEffect(() => { load(); }, [load]);

  const openMono = async (id: string) => {
    haptics.selection(); setOpen({ loading: true }); setOpenLoading(true);
    const r = await api.get<any>(`/api/worldforge/monograph/saved/${id}`, { timeoutMs: 20000 });
    setOpenLoading(false);
    setOpen(r.ok && r.data ? r.data : { error: 'Could not load monograph' });
  };

  const shareOpen = async () => {
    if (!open?.monograph) return;
    try {
      if (Platform.OS === 'web' && typeof navigator !== 'undefined' && navigator.clipboard) await navigator.clipboard.writeText(open.monograph);
      else await Share.share({ message: open.monograph, title: `${open.name} — monograph` });
    } catch { /* cancelled */ }
  };

  return (
    <SafeAreaView style={styles.root} testID="worldforge-vault-screen">
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} testID="vault-back"><Text style={styles.back}>‹ Back</Text></TouchableOpacity>
        <Text style={styles.title}>📚 Survey Vault</Text>
        <View style={{ width: 48 }} />
      </View>

      <View style={styles.tabs}>
        {(['all', 'monographs', 'posters'] as const).map((t) => (
          <TouchableOpacity key={t} testID={`vault-tab-${t}`} style={[styles.tab, tab === t && styles.tabOn]} onPress={() => { haptics.selection(); setTab(t); }}>
            <Text style={[styles.tabTxt, tab === t && styles.tabTxtOn]}>{t === 'all' ? '🗄️ All Vaults' : t === 'monographs' ? `📖 Monographs (${monos.length})` : `🖼️ Posters (${posters.length})`}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {tab === 'all' ? (
        <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 40 }}>
          <UnifiedVault embedded />
        </ScrollView>
      ) : loading ? <ActivityIndicator color="#60A5FA" style={{ marginTop: 40 }} /> : (
        <ScrollView
          contentContainerStyle={{ padding: 16, paddingBottom: 40 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor="#60A5FA" />}
        >
          {tab === 'monographs' ? (
            monos.length === 0 ? <Text style={styles.empty}>No saved surveys yet.{'\n'}Generate a monograph in Worldforge and tap “Save to Vault”.</Text> :
              monos.map((it) => (
                <TouchableOpacity key={it.id} testID={`vault-item-${it.id}`} style={styles.card} onPress={() => openMono(it.id)}>
                  <Text style={styles.cardName}>📖 {it.name}</Text>
                  <Text style={styles.cardMeta}>{it.scale} · {it.model} · {it.chars.toLocaleString()} chars</Text>
                  <Text style={styles.cardDate}>{(it.created_at || '').slice(0, 16).replace('T', '  ')}</Text>
                </TouchableOpacity>
              ))
          ) : (
            posters.length === 0 ? <Text style={styles.empty}>No saved posters yet.{'\n'}Generate a poster in Worldforge and tap “Save to gallery”.</Text> :
              posters.map((it) => (
                <View key={it.id} testID={`vault-poster-${it.id}`} style={styles.posterCard}>
                  <Image source={{ uri: it.image }} style={styles.posterThumb} resizeMode="cover" />
                  <Text style={styles.cardName}>{it.name}</Text>
                  <Text style={styles.cardMeta}>{it.scale} · {it.style} · {(it.created_at || '').slice(0, 10)}</Text>
                </View>
              ))
          )}
        </ScrollView>
      )}

      <Modal visible={!!open} animationType="slide" transparent onRequestClose={() => setOpen(null)}>
        <View style={styles.backdrop}>
          <View style={styles.sheet}>
            <View style={styles.sheetHead}>
              <Text style={styles.sheetTitle}>{open?.name || 'Monograph'}</Text>
              <View style={{ flexDirection: 'row', gap: 8 }}>
                {open?.monograph ? <TouchableOpacity onPress={shareOpen} style={styles.smallBtn}><Text style={styles.smallTxt}>{Platform.OS === 'web' ? '📋' : '📤'}</Text></TouchableOpacity> : null}
                <TouchableOpacity onPress={() => setOpen(null)} style={styles.smallBtn}><Text style={styles.smallTxt}>Close</Text></TouchableOpacity>
              </View>
            </View>
            {openLoading ? <ActivityIndicator color="#60A5FA" style={{ marginTop: 30 }} /> :
              open?.error ? <Text style={styles.empty}>{open.error}</Text> :
                open?.monograph ? <ScrollView contentContainerStyle={{ paddingBottom: 30 }}><Text style={styles.mono} selectable>{open.monograph}</Text></ScrollView> : null}
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#07080f' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: '#1a1c2a' },
  back: { color: '#93C5FD', fontSize: 15, fontWeight: '700' },
  title: { color: '#f1f5f9', fontSize: 18, fontWeight: '800' },
  tabs: { flexDirection: 'row', gap: 8, paddingHorizontal: 16, paddingVertical: 12 },
  tab: { flex: 1, backgroundColor: '#10131f', borderRadius: 10, paddingVertical: 10, alignItems: 'center', borderWidth: 1, borderColor: '#1e2030' },
  tabOn: { borderColor: '#a855f7', backgroundColor: '#1a1030' },
  tabTxt: { color: '#94a3b8', fontWeight: '800', fontSize: 13 },
  tabTxtOn: { color: '#d8b4fe' },
  empty: { color: '#64748b', fontSize: 14, textAlign: 'center', marginTop: 50, lineHeight: 22 },
  card: { backgroundColor: '#10131f', borderRadius: 12, padding: 14, marginBottom: 12, borderWidth: 1, borderColor: '#1e2030' },
  cardName: { color: '#e2e8f0', fontSize: 16, fontWeight: '800' },
  cardMeta: { color: '#94a3b8', fontSize: 12.5, marginTop: 5 },
  cardDate: { color: '#475569', fontSize: 11, marginTop: 4 },
  posterCard: { backgroundColor: '#10131f', borderRadius: 12, padding: 10, marginBottom: 14, borderWidth: 1, borderColor: '#1e2030' },
  posterThumb: { width: '100%', aspectRatio: 1, borderRadius: 10, backgroundColor: '#000', marginBottom: 8 },
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: '#0c0e18', borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 18, maxHeight: '92%' },
  sheetHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 },
  sheetTitle: { color: '#f1f5f9', fontSize: 18, fontWeight: '800', flex: 1 },
  smallBtn: { backgroundColor: '#1e2030', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 7 },
  smallTxt: { color: '#cbd5e1', fontWeight: '800', fontSize: 13 },
  mono: { color: '#cbd5e1', fontSize: 12.5, lineHeight: 19, fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace', default: 'monospace' }) },
});
