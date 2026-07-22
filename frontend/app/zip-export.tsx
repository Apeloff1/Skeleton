/**
 * /zip-export — 📦 Zip Export Bay.
 *
 * Packages the current build's gamefiles into a downloadable ZIP and exposes
 * BOTH export routes:
 *   • Raw gamefiles  → /api/galaxy-studio/vault-gdd/{build}/gamefiles.zip
 *   • Packaged build → /api/binary/package (kinds:["zip"]) + /api/binary/download/{build}/zip
 *
 * Reached from the Snowball "Forge & Ship Bay". Reuses the existing binary
 * builder backend — no mock data.
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  StyleSheet, SafeAreaView, RefreshControl, Linking,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../src/utils/apiClient';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

export default function ZipExport() {
  const router = useRouter();
  const params = useLocalSearchParams<{ build?: string; game?: string }>();
  const buildId = String(params?.build || params?.game || 'demo_build');

  const [arts, setArts] = React.useState<any[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [packing, setPacking] = React.useState(false);
  const [status, setStatus] = React.useState<string>('');

  const load = React.useCallback(async () => {
    const r = await api.get<any>(`/api/binary/artifacts/${encodeURIComponent(buildId)}`, { timeoutMs: 12000 });
    if (r.ok && r.data?.artifacts) setArts(r.data.artifacts.filter((a: any) => a.kind === 'zip'));
    setLoading(false);
  }, [buildId]);

  React.useEffect(() => { load(); }, [load]);

  const packageZip = React.useCallback(async () => {
    if (packing) return;
    setPacking(true); setStatus('📦 Packaging gamefiles into a ZIP…');
    const r = await api.post<any>('/api/binary/package', { build_id: buildId, kinds: ['zip'] }, { timeoutMs: 90000 });
    if (r.ok && r.data && !r.data.error) {
      setStatus('✅ ZIP ready — tap Download below.');
      await load();
    } else {
      setStatus(`❌ ${r.data?.error || r.data?.detail || 'Packaging failed — build not found?'}`);
    }
    setPacking(false);
  }, [buildId, packing, load]);

  const downloadPackaged = React.useCallback(() => {
    Linking.openURL(`${BACKEND}/api/binary/download/${encodeURIComponent(buildId)}/zip`);
  }, [buildId]);

  const downloadRaw = React.useCallback(() => {
    Linking.openURL(`${BACKEND}/api/galaxy-studio/vault-gdd/${encodeURIComponent(buildId)}/gamefiles.zip`);
  }, [buildId]);

  const hasZip = arts.length > 0;

  return (
    <SafeAreaView style={s.root}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.back} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
          <Ionicons name="chevron-back" size={22} color="#3B82F6" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={s.title}>📦 Zip Export</Text>
          <Text style={s.sub} numberOfLines={1}>build · {buildId}</Text>
        </View>
        <TouchableOpacity onPress={load} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
          <Ionicons name="refresh" size={18} color="#3B82F6" />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 60 }}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor="#3B82F6" />}>

        {/* Packaged ZIP */}
        <View style={s.card}>
          <Text style={s.cardTitle}>🗜️ Packaged build (ZIP)</Text>
          <Text style={s.cardSub}>Every gamefile bundled for distribution. Generate, then download.</Text>

          <TouchableOpacity testID="zip-package" onPress={packageZip} disabled={packing}
            style={[s.primary, packing && s.off]} activeOpacity={0.9}>
            {packing ? <ActivityIndicator color="#021" size="small" />
              : <Text style={s.primaryTxt}>{hasZip ? '↻ Re-package ZIP' : '📦 Package ZIP'}</Text>}
          </TouchableOpacity>

          {!!status && <Text style={s.status}>{status}</Text>}

          {hasZip && (
            <TouchableOpacity testID="zip-download" onPress={downloadPackaged} style={s.download} activeOpacity={0.9}>
              <Ionicons name="download" size={18} color="#3B82F6" />
              <Text style={s.downloadTxt}>Download galaxy_{buildId}.zip</Text>
            </TouchableOpacity>
          )}

          {loading && !arts.length && <ActivityIndicator color="#3B82F6" style={{ marginTop: 12 }} />}
          {arts.map((a, i) => (
            <View key={i} style={s.artRow}>
              <Ionicons name="archive" size={16} color="#93C5FD" />
              <Text style={s.artName} numberOfLines={1}>{a.artifact_id || a.name || 'artifact'}</Text>
              <Text style={s.artSize}>{a.size_bytes ? `${(a.size_bytes / 1024).toFixed(0)} KB` : ''}</Text>
            </View>
          ))}
        </View>

        {/* Raw gamefiles */}
        <View style={[s.card, { borderColor: '#5a4a1f', backgroundColor: '#1a1608' }]}>
          <Text style={[s.cardTitle, { color: '#ffe9c0' }]}>📄 Raw gamefiles (.zip)</Text>
          <Text style={[s.cardSub, { color: '#b8a482' }]}>The Vault GDD + source gamefiles, exactly as forged.</Text>
          <TouchableOpacity testID="zip-raw" onPress={downloadRaw} style={[s.download, { borderColor: '#f4a261' }]} activeOpacity={0.9}>
            <Ionicons name="download" size={18} color="#f4a261" />
            <Text style={[s.downloadTxt, { color: '#f4a261' }]}>Download {buildId}_gamefiles.zip</Text>
          </TouchableOpacity>
        </View>

        <TouchableOpacity onPress={() => router.push(`/apk-build?build=${encodeURIComponent(buildId)}` as any)}
          style={s.nextLink} activeOpacity={0.85}>
          <Text style={s.nextTxt}>📱 Build an installable APK instead  ›</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#05070d' },
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 12, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#141c2e' },
  back: { width: 30, height: 30, alignItems: 'center', justifyContent: 'center' },
  title: { color: '#F8FAFC', fontSize: 18, fontWeight: '800' },
  sub: { color: '#64748b', fontSize: 11, marginTop: 2 },
  card: { backgroundColor: '#0a1620', borderRadius: 14, borderWidth: 1, borderColor: '#1f3a4a', padding: 16, marginBottom: 14 },
  cardTitle: { color: '#DBEAFE', fontSize: 15, fontWeight: '900' },
  cardSub: { color: '#93A9C9', fontSize: 12, marginTop: 4, lineHeight: 17 },
  primary: { backgroundColor: '#3B82F6', borderRadius: 10, paddingVertical: 13, alignItems: 'center', justifyContent: 'center', marginTop: 14, minHeight: 46 },
  primaryTxt: { color: '#021019', fontSize: 14, fontWeight: '900' },
  off: { opacity: 0.55 },
  status: { color: '#cbd5e1', fontSize: 12, marginTop: 10 },
  download: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderWidth: 1, borderColor: '#3B82F6', borderRadius: 10, paddingVertical: 12, marginTop: 12 },
  downloadTxt: { color: '#3B82F6', fontSize: 13, fontWeight: '800' },
  artRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 10, paddingTop: 10, borderTopWidth: 1, borderTopColor: '#13233c' },
  artName: { color: '#cbd5e1', fontSize: 12, flex: 1 },
  artSize: { color: '#64748b', fontSize: 11, fontWeight: '700' },
  nextLink: { marginTop: 6, padding: 14, alignItems: 'center' },
  nextTxt: { color: '#a78bfa', fontSize: 13, fontWeight: '800' },
});
