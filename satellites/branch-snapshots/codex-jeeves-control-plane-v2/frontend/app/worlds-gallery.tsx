/**
 * /worlds-gallery — a showcase of every world forged from a game and saved (WG).
 * Each card shows a rendered thumbnail (globe / cartographic / cosmic), its name,
 * scale and source game. Tap to open it in Worldforge.
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  StyleSheet, SafeAreaView, Image, RefreshControl, useWindowDimensions,
} from 'react-native';
import { useRouter } from 'expo-router';
import api from '../src/utils/apiClient';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

type World = {
  world_id: string; name: string; scale: string; palette: string; climate: string;
  source_title?: string; config: any; stats?: { land_pct?: number; settlements?: number; biomes?: number };
};

function thumbUrl(w: World) {
  const c = w.config || {};
  const f = Object.keys(c.features || {}).filter((k) => c.features[k]).join(',');
  return `${BACKEND}/api/worldforge/render?scale=${w.scale}&seed=${c.seed || 1337}&size=${c.size || 56}`
    + `&palette=${c.palette || w.palette}&climate=${c.climate || w.climate}`
    + `&sea_level=${c.sea_level ?? 0.3}&mountain_level=${c.mountain_level ?? 0.72}`
    + `&river_density=${c.river_density ?? 0.04}&settlement_density=${c.settlement_density ?? 1}&features=${f}`;
}

export default function WorldsGallery() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const [worlds, setWorlds] = React.useState<World[]>([]);
  const [loading, setLoading] = React.useState(true);

  const load = React.useCallback(async () => {
    setLoading(true);
    const r = await api.get<{ worlds: World[] }>('/api/worldforge/worlds?limit=40', { timeoutMs: 12000 });
    if (r.ok && r.data) setWorlds(r.data.worlds || []);
    setLoading(false);
  }, []);
  React.useEffect(() => { load(); }, [load]);

  const cardW = (Math.min(width, 520) - 16 * 2 - 12) / 2;

  return (
    <SafeAreaView style={styles.safe} testID="worlds-gallery-screen">
      <View style={styles.header}>
        <TouchableOpacity testID="wg-back" onPress={() => router.back()} style={styles.backBtn}><Text style={styles.backTxt}>‹ Back</Text></TouchableOpacity>
        <Text style={styles.title}>🖼 Worlds Gallery</Text>
      </View>
      <ScrollView
        contentContainerStyle={{ padding: 16, paddingBottom: 60 }}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor="#60A5FA" />}
      >
        {loading ? <ActivityIndicator color="#60A5FA" style={{ marginTop: 40 }} /> :
          worlds.length === 0 ? (
            <Text testID="wg-empty" style={styles.empty}>No saved worlds yet. In Worldforge, tap “🎮 From a game” to forge a world from one of your games — it’s saved here tagged (WG).</Text>
          ) : (
            <View style={styles.grid}>
              {worlds.map((w) => (
                <TouchableOpacity key={w.world_id} testID={`wg-world-${w.world_id}`} style={[styles.card, { width: cardW }]}
                  onPress={() => router.push('/worldforge' as any)}>
                  <Image source={{ uri: thumbUrl(w) }} style={{ width: cardW, height: cardW, backgroundColor: '#04040a' }} resizeMode="cover" />
                  <View style={{ padding: 10 }}>
                    <Text style={styles.cardName} numberOfLines={1}>{w.name}</Text>
                    <Text style={styles.cardMeta} numberOfLines={1}>{w.scale} · {w.palette}</Text>
                    {w.source_title ? <Text style={styles.cardSrc} numberOfLines={1}>from {w.source_title}</Text> : null}
                  </View>
                </TouchableOpacity>
              ))}
            </View>
          )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#070710' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#1e2030' },
  backBtn: { paddingVertical: 6, paddingRight: 12 }, backTxt: { color: '#94a3b8', fontSize: 15 },
  title: { flex: 1, color: '#f1f5f9', fontSize: 20, fontWeight: '800' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  card: { backgroundColor: '#10131f', borderRadius: 14, overflow: 'hidden', borderWidth: 1, borderColor: '#1e2030' },
  cardName: { color: '#e2e8f0', fontSize: 14, fontWeight: '800' },
  cardMeta: { color: '#93C5FD', fontSize: 12, marginTop: 2, textTransform: 'capitalize' },
  cardSrc: { color: '#64748b', fontSize: 11, marginTop: 2 },
  empty: { color: '#64748b', fontSize: 14, lineHeight: 22, marginTop: 30, textAlign: 'center' },
});
