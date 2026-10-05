/**
 * RecentArtifactsStrip — a compact horizontal strip on the Hub showing the
 * last ZIP/APK artifacts the creator shipped, with one-tap re-download.
 * Lets you grab your latest build without reopening Snowball.
 *
 * Data: GET /api/binary/recent?limit=6  → { artifacts: [{build_id, kind, size_bytes, download_url}] }
 * Renders nothing when there are no artifacts yet.
 */
import React from 'react';
import { View, Text, ScrollView, TouchableOpacity, StyleSheet, Linking } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import apiClient from '../src/utils/apiClient';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

type Artifact = { build_id: string; kind: 'zip' | 'apk'; size_bytes: number; download_url: string };

function fmtSize(b: number): string {
  if (b >= 1048576) return `${(b / 1048576).toFixed(1)} MB`;
  if (b >= 1024) return `${(b / 1024).toFixed(0)} KB`;
  return `${b} B`;
}

export const RecentArtifactsStrip: React.FC = () => {
  const [items, setItems] = React.useState<Artifact[]>([]);

  const load = React.useCallback(async () => {
    try {
      const r = await apiClient.get<{ artifacts: Artifact[] }>('/api/binary/recent?limit=6');
      if (r.ok && r.data?.artifacts) setItems(r.data.artifacts);
    } catch { /* non-fatal — strip just stays hidden */ }
  }, []);

  React.useEffect(() => {
    load();
    const iv = setInterval(load, 15000);
    return () => clearInterval(iv);
  }, [load]);

  if (!items.length) return null;

  return (
    <View style={s.wrap} testID="recent-artifacts-strip">
      <View style={s.head}>
        <Ionicons name="download" size={13} color="#60A5FA" />
        <Text style={s.title}>Recent Artifacts</Text>
        <Text style={s.count}>{items.length}</Text>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.row}>
        {items.map((a, i) => {
          const apk = a.kind === 'apk';
          return (
            <TouchableOpacity
              key={`${a.build_id}-${a.kind}-${i}`}
              testID={`recent-artifact-${a.kind}-${i}`}
              activeOpacity={0.85}
              onPress={() => Linking.openURL(`${BACKEND}${a.download_url}`)}
              style={[s.card, { borderColor: apk ? '#7C3AED55' : '#3B82F655' }]}
            >
              <Text style={s.icon}>{apk ? '📱' : '📦'}</Text>
              <View style={{ flex: 1 }}>
                <Text style={s.name} numberOfLines={1}>{a.build_id}</Text>
                <Text style={s.meta}>{a.kind.toUpperCase()} · {fmtSize(a.size_bytes)}</Text>
              </View>
              <Ionicons name="download-outline" size={16} color={apk ? '#A78BFA' : '#60A5FA'} />
            </TouchableOpacity>
          );
        })}
      </ScrollView>
    </View>
  );
};

const s = StyleSheet.create({
  wrap: { marginTop: 8, marginBottom: 2 },
  head: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, marginBottom: 6 },
  title: { color: '#94A3B8', fontSize: 11, fontWeight: '800', letterSpacing: 0.4, textTransform: 'uppercase' },
  count: { color: '#60A5FA', fontSize: 11, fontWeight: '800' },
  row: { paddingHorizontal: 12, gap: 8 },
  card: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: '#0F172A', borderRadius: 10, borderWidth: 1,
    paddingVertical: 8, paddingHorizontal: 10, minWidth: 168, maxWidth: 220,
  },
  icon: { fontSize: 20 },
  name: { color: '#E2E8F0', fontSize: 12, fontWeight: '800' },
  meta: { color: '#64748B', fontSize: 10, fontWeight: '700', marginTop: 1 },
});

export default RecentArtifactsStrip;
