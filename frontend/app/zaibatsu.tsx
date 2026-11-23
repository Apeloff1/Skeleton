import { API_BASE as CANONICAL_API_BASE } from '../src/utils/apiBase';
/**
 * /zaibatsu — GameForge CNS "Zaibatsu" Command Center (in-app WebView).
 *
 * Renders the merged CNS cockpit served by the backend at
 * /api/gameforge/cockpit, plus a live header showing mounted subsystems and
 * the 1000-room count. Reachable from Jeeves AI Tutor → "Zaibatsu CNS".
 */
import React from 'react';
import {
  View, Text, StyleSheet, SafeAreaView, TouchableOpacity, ActivityIndicator, Platform,
} from 'react-native';
import { WebView } from 'react-native-webview';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import apiClient from '../src/utils/apiClient';
import { LoadErrorNotice } from '../src/foundation/LoadNotice';
import { failureFromResult, failureFromError, describeLoadFailure, type LoadFailure } from '../src/foundation/loadFailure';

const BACKEND = CANONICAL_API_BASE || '';

export default function Zaibatsu() {
  const router = useRouter();
  const [status, setStatus] = React.useState<any>(null);
  const [rooms, setRooms] = React.useState<number | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [statusFailure, setStatusFailure] = React.useState<LoadFailure | null>(null);
  const [viewFailure, setViewFailure] = React.useState<LoadFailure | null>(null);
  const [viewKey, setViewKey] = React.useState(0);

  const loadStatus = React.useCallback(async () => {
    const [s, r] = await Promise.all([
      apiClient.get<any>('/api/gameforge/status'),
      apiClient.get<any>('/api/gameforge/rooms?limit=1'),
    ]);
    setStatusFailure(failureFromResult(s));
    if (s.ok) setStatus(s.data);
    if (r.ok) setRooms(typeof r.data?.total === 'number' ? r.data.total : null);
  }, []);
  React.useEffect(() => { void loadStatus(); }, [loadStatus]);

  const reloadView = React.useCallback(() => {
    setViewFailure(null); setLoading(true); setViewKey((k) => k + 1); void loadStatus();
  }, [loadStatus]);

  return (
    <SafeAreaView style={s.root}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.back} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
          <Ionicons name="chevron-back" size={22} color="#22c55e" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={s.title}>🧠 Zaibatsu CNS</Text>
          <Text style={s.sub} numberOfLines={1}>
            {status ? `${status.mounted_count}/10 subsystems · ` : ''}{rooms != null ? `${rooms} rooms` : statusFailure ? 'offline' : 'connecting…'}
          </Text>
        </View>
        <View style={[s.dot, { backgroundColor: status ? '#22c55e' : statusFailure ? '#ef4444' : '#f59e0b' }]}
          accessible accessibilityLabel={status ? 'Connected' : statusFailure ? 'Offline' : 'Connecting'} />
      </View>

      <TouchableOpacity
        testID="zaibatsu-governance-btn"
        style={s.govBtn}
        onPress={() => router.push('/gameforge-studio')}
      >
        <Ionicons name="git-branch" size={16} color="#22c55e" />
        <Text style={s.govTxt}>Studio Governance & Jeeves Oversight</Text>
        <Ionicons name="chevron-forward" size={16} color="#64748b" />
      </TouchableOpacity>

      <View style={s.webWrap}>
        {viewFailure ? (
          <LoadErrorNotice failure={viewFailure} what="the command center" onRetry={reloadView} testID="zaibatsu-error" />
        ) : loading && (
          <View style={s.loader} pointerEvents="none" role="progressbar" aria-label="Loading command center…" aria-busy>
            <ActivityIndicator color="#22c55e" size="large" aria-hidden />
            <Text style={s.loaderTxt}>Loading command center…</Text>
          </View>
        )}
        <WebView
          key={viewKey}
          testID="zaibatsu-webview"
          source={{ uri: `${BACKEND}/api/gameforge/cockpit` }}
          onLoadEnd={() => setLoading(false)}
          onError={(e) => { setLoading(false); setViewFailure(failureFromError(new Error(e?.nativeEvent?.description || 'network error'))); }}
          onHttpError={(e) => { setLoading(false); setViewFailure(describeLoadFailure({ status: e?.nativeEvent?.statusCode ?? null })); }}
          style={{ backgroundColor: '#05070d' }}
          originWhitelist={['*']}
          startInLoadingState={false}
          {...(Platform.OS === 'web' ? {} : { domStorageEnabled: true, javaScriptEnabled: true })}
        />
      </View>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#05070d' },
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 12, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#123' },
  back: { width: 30, height: 30, alignItems: 'center', justifyContent: 'center' },
  title: { color: '#F8FAFC', fontSize: 18, fontWeight: '800' },
  sub: { color: '#64748b', fontSize: 11, marginTop: 2 },
  dot: { width: 10, height: 10, borderRadius: 5 },
  webWrap: { flex: 1 },
  govBtn: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 14, paddingVertical: 12, backgroundColor: '#0b1220', borderBottomWidth: 1, borderBottomColor: '#123' },
  govTxt: { flex: 1, color: '#e2e8f0', fontSize: 13, fontWeight: '700' },
  loader: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, alignItems: 'center', justifyContent: 'center', zIndex: 2, backgroundColor: '#05070d' },
  loaderTxt: { color: '#22c55e', fontSize: 12, marginTop: 10, fontWeight: '700' },
});
