/**
 * /apk-build — 📱 APK Build Bay.
 *
 * Packages the current build into an installable Android APK and tracks its
 * artifacts. Wires the existing binary builder backend:
 *   • POST /api/binary/package      (kinds:["apk"])
 *   • GET  /api/binary/artifacts/{build}
 *   • GET  /api/binary/download/{build}/apk
 *   • Deep bytecode inspection → /apk-inspector
 *
 * Reached from the Snowball "Forge & Ship Bay". No mock data.
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

export default function ApkBuild() {
  const router = useRouter();
  const params = useLocalSearchParams<{ build?: string; game?: string }>();
  const buildId = String(params?.build || params?.game || 'demo_build');

  const [arts, setArts] = React.useState<any[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [building, setBuilding] = React.useState(false);
  const [status, setStatus] = React.useState('');

  const load = React.useCallback(async () => {
    const r = await api.get<any>(`/api/binary/artifacts/${encodeURIComponent(buildId)}`, { timeoutMs: 12000 });
    if (r.ok && r.data?.artifacts) setArts(r.data.artifacts.filter((a: any) => a.kind === 'apk'));
    setLoading(false);
  }, [buildId]);

  React.useEffect(() => { load(); }, [load]);

  const buildApk = React.useCallback(async () => {
    if (building) return;
    setBuilding(true); setStatus('🔨 Compiling & packaging APK… this can take a minute.');
    const r = await api.post<any>('/api/binary/package', { build_id: buildId, kinds: ['apk'] }, { timeoutMs: 120000 });
    if (r.ok && r.data && !r.data.error) {
      setStatus('✅ APK packaged — download or inspect below.');
      await load();
    } else {
      setStatus(`❌ ${r.data?.error || r.data?.detail || 'APK packaging failed — is the build saved?'}`);
    }
    setBuilding(false);
  }, [buildId, building, load]);

  const downloadApk = React.useCallback(() => {
    Linking.openURL(`${BACKEND}/api/binary/download/${encodeURIComponent(buildId)}/apk`);
  }, [buildId]);

  const hasApk = arts.length > 0;

  return (
    <SafeAreaView style={s.root}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.back} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
          <Ionicons name="chevron-back" size={22} color="#A78BFA" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={s.title}>📱 APK Build</Text>
          <Text style={s.sub} numberOfLines={1}>build · {buildId}</Text>
        </View>
        <TouchableOpacity onPress={load} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
          <Ionicons name="refresh" size={18} color="#A78BFA" />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 60 }}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor="#A78BFA" />}>

        <View style={s.card}>
          <Text style={s.cardTitle}>🤖 Android package</Text>
          <Text style={s.cardSub}>Bundle the build into an installable .apk (aapt2 · d8 · zipalign · apksigner).</Text>

          <TouchableOpacity testID="apk-build" onPress={buildApk} disabled={building}
            style={[s.primary, building && s.off]} activeOpacity={0.9}>
            {building ? <ActivityIndicator color="#fff" size="small" />
              : <Text style={s.primaryTxt}>{hasApk ? '↻ Rebuild APK' : '🔨 Build APK'}</Text>}
          </TouchableOpacity>

          {!!status && <Text style={s.status}>{status}</Text>}

          {hasApk && (
            <>
              <TouchableOpacity testID="apk-download" onPress={downloadApk} style={s.download} activeOpacity={0.9}>
                <Ionicons name="download" size={18} color="#A78BFA" />
                <Text style={s.downloadTxt}>Download galaxy_{buildId}.apk</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => router.push(`/apk-inspector?build=${encodeURIComponent(buildId)}` as any)}
                style={[s.download, { borderColor: '#334155' }]} activeOpacity={0.9}>
                <Ionicons name="search" size={18} color="#94a3b8" />
                <Text style={[s.downloadTxt, { color: '#94a3b8' }]}>Inspect bytecode & manifest</Text>
              </TouchableOpacity>
            </>
          )}

          {loading && !arts.length && <ActivityIndicator color="#A78BFA" style={{ marginTop: 12 }} />}
          {arts.map((a, i) => (
            <View key={i} style={s.artRow}>
              <Ionicons name="logo-android" size={16} color="#34D399" />
              <Text style={s.artName} numberOfLines={1}>{a.artifact_id || a.name || 'apk'}</Text>
              <Text style={s.artSize}>{a.size_bytes ? `${(a.size_bytes / 1048576).toFixed(2)} MB` : ''}</Text>
            </View>
          ))}
        </View>

        <View style={s.note}>
          <Ionicons name="information-circle" size={16} color="#64748b" />
          <Text style={s.noteTxt}>For a signed Play-Store build, use the Publish button to generate production iOS/Android binaries.</Text>
        </View>

        <TouchableOpacity onPress={() => router.push(`/zip-export?build=${encodeURIComponent(buildId)}` as any)}
          style={s.nextLink} activeOpacity={0.85}>
          <Text style={s.nextTxt}>📦 Export a ZIP of gamefiles instead  ›</Text>
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
  card: { backgroundColor: '#120e22', borderRadius: 14, borderWidth: 1, borderColor: '#3a2f6e', padding: 16, marginBottom: 14 },
  cardTitle: { color: '#e7ddff', fontSize: 15, fontWeight: '900' },
  cardSub: { color: '#a99cce', fontSize: 12, marginTop: 4, lineHeight: 17 },
  primary: { backgroundColor: '#7C3AED', borderRadius: 10, paddingVertical: 13, alignItems: 'center', justifyContent: 'center', marginTop: 14, minHeight: 46 },
  primaryTxt: { color: '#fff', fontSize: 14, fontWeight: '900' },
  off: { opacity: 0.55 },
  status: { color: '#cbd5e1', fontSize: 12, marginTop: 10 },
  download: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderWidth: 1, borderColor: '#A78BFA', borderRadius: 10, paddingVertical: 12, marginTop: 12 },
  downloadTxt: { color: '#A78BFA', fontSize: 13, fontWeight: '800' },
  artRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 10, paddingTop: 10, borderTopWidth: 1, borderTopColor: '#241c3c' },
  artName: { color: '#cbd5e1', fontSize: 12, flex: 1 },
  artSize: { color: '#64748b', fontSize: 11, fontWeight: '700' },
  note: { flexDirection: 'row', gap: 8, alignItems: 'flex-start', backgroundColor: '#0a1020', borderRadius: 10, padding: 12, marginBottom: 12 },
  noteTxt: { color: '#94a3b8', fontSize: 11, lineHeight: 16, flex: 1 },
  nextLink: { marginTop: 2, padding: 14, alignItems: 'center' },
  nextTxt: { color: '#3B82F6', fontSize: 13, fontWeight: '800' },
});
