import React, { useState, useCallback, useEffect } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator,
  TextInput,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { apiFetch } from '../utils/apiController';

const API = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const C = {
  bg: '#0b0f1a', card: '#141b2e', alt: '#1b2438', border: '#2a3550',
  text: '#eef2fb', muted: '#8a96b2', accent: '#f4a261', good: '#43d39e',
};

export default function EditGamefiles() {
  const router = useRouter();
  const params = useLocalSearchParams<{ build?: string }>();
  const [buildId, setBuildId] = useState<string>((params.build as string) || '');
  const [assets, setAssets] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [removed, setRemoved] = useState<Record<string, boolean>>({});

  const load = useCallback(async (bid: string) => {
    if (!bid.trim()) return;
    setLoading(true); setLoaded(false);
    try {
      const r = await apiFetch(`${API}/api/galaxy-studio/constructs/extract/${encodeURIComponent(bid.trim())}?into_library=false`, { timeoutMs: 15000 });
      const d = await r.json();
      setAssets(Array.isArray(d.assets) ? d.assets : []);
    } catch { setAssets([]); } finally { setLoading(false); setLoaded(true); }
  }, []);

  useEffect(() => { if (params.build) load(params.build as string); }, [params.build, load]);

  const keyFor = (a: any, i: number) => `${a.id || a.preset_id || a.category || 'asset'}:${i}`;
  const kept = assets
    .map((a, i) => ({ a, i }))
    .filter(({ a, i }) => !removed[keyFor(a, i)]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.iconBtn} testID="eg-back">
          <Ionicons name="chevron-back" size={22} color={C.text} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>📝 Edit Gamefiles</Text>
          <Text style={styles.sub}>Review your Vault before the Build phase</Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={{ padding: 14, paddingBottom: 80 }}>
        <View style={styles.row}>
          <TextInput value={buildId} onChangeText={setBuildId} placeholder="Build ID"
            placeholderTextColor={C.muted} style={styles.input} testID="eg-build-input" />
          <TouchableOpacity onPress={() => load(buildId)} style={styles.loadBtn} testID="eg-load">
            <Text style={styles.loadTxt}>Load</Text>
          </TouchableOpacity>
        </View>

        {loading && <View style={styles.center}><ActivityIndicator color={C.accent} /></View>}

        {loaded && !loading && (
          <Text style={styles.count}>{kept.length} gamefile{kept.length === 1 ? '' : 's'} mounted{assets.length !== kept.length ? ` · ${assets.length - kept.length} removed` : ''}</Text>
        )}

        {kept.map(({ a, i }) => {
          const key = keyFor(a, i);
          const pal = a.palette || a.thumb_palette || [];
          return (
            <View key={key} style={styles.assetCard} testID={`eg-asset-${i}`}>
              <View style={styles.assetStrip}>
                {pal.slice(0, 6).map((c: string, j: number) => (
                  <View key={j} style={{ flex: 1, backgroundColor: c }} />
                ))}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.assetName} numberOfLines={1}>{a.name || a.category || a.preset_id || 'Asset'}</Text>
                <Text style={styles.assetMeta} numberOfLines={1}>{a.category || a.family || ''}{a.era ? ` · ${a.era}` : ''}</Text>
              </View>
              <TouchableOpacity onPress={() => setRemoved((p) => ({ ...p, [key]: true }))} style={styles.removeBtn} testID={`eg-remove-${i}`}>
                <Ionicons name="trash-outline" size={18} color="#ff6b6b" />
              </TouchableOpacity>
            </View>
          );
        })}

        {loaded && !loading && assets.length === 0 && (
          <Text style={styles.empty}>No gamefiles yet — forge & mount assets from the AI Game Tools first.</Text>
        )}

        {kept.length > 0 && (
          <TouchableOpacity onPress={() => router.push(`/snowball?game=${encodeURIComponent(buildId.trim())}`)}
            style={styles.buildBtn} testID="eg-continue-build">
            <Text style={styles.buildTxt}>✓ Looks good → Continue to Build</Text>
          </TouchableOpacity>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 12, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.border },
  iconBtn: { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center', backgroundColor: C.card },
  title: { color: C.text, fontSize: 18, fontWeight: '900' },
  sub: { color: C.muted, fontSize: 11, fontWeight: '600' },
  row: { flexDirection: 'row', gap: 8, marginBottom: 12 },
  input: { flex: 1, backgroundColor: C.alt, borderRadius: 10, borderWidth: 1, borderColor: C.border, color: C.text, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14 },
  loadBtn: { backgroundColor: C.accent, borderRadius: 10, paddingHorizontal: 18, justifyContent: 'center' },
  loadTxt: { color: '#1a1004', fontWeight: '900' },
  center: { paddingVertical: 24, alignItems: 'center' },
  count: { color: C.muted, fontSize: 12, fontWeight: '700', marginBottom: 8 },
  assetCard: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, padding: 10, marginBottom: 8 },
  assetStrip: { width: 40, height: 40, borderRadius: 8, overflow: 'hidden', flexDirection: 'row' },
  assetName: { color: C.text, fontSize: 13, fontWeight: '800' },
  assetMeta: { color: C.muted, fontSize: 11, fontWeight: '600', marginTop: 2 },
  removeBtn: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: C.alt },
  empty: { color: C.muted, fontSize: 12, textAlign: 'center', paddingVertical: 24 },
  buildBtn: { backgroundColor: C.good, borderRadius: 12, paddingVertical: 14, alignItems: 'center', marginTop: 16 },
  buildTxt: { color: '#04140d', fontSize: 15, fontWeight: '900' },
});
