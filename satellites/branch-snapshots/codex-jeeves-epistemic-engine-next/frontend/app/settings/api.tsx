/**
 * Settings → API Controller
 * Live observability + control surface for the SOTA API layer.
 *   • Live request counters, cache hits, retries, rate-limited hits
 *   • Latency p50/p95/max
 *   • Per-tag breakdown
 *   • Last error
 *   • Clear cache, toggle controller passthrough
 *   • Pulls /api/_telemetry for server-side counterpart
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, SafeAreaView, Switch,
  RefreshControl,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { api, TelemetrySnapshot } from '../../utils/apiController';
import { toast } from '../../components/Toast';
import { actionSheet } from '../../components/ActionSheet';

interface ServerStats {
  uptime_seconds: number;
  requests_total: number;
  requests_2xx: number;
  requests_4xx: number;
  requests_5xx: number;
  rate_limited_total: number;
  samples: number;
  latency_ms: { p50: number; p95: number; p99: number; max: number };
  rate_limit: { per_minute: number; burst: number; exempt_ips: string[] };
}

export default function ApiSettings() {
  const router = useRouter();
  const [client, setClient] = useState<TelemetrySnapshot>(api.getTelemetry());
  const [server, setServer] = useState<ServerStats | null>(null);
  const [inspect, setInspect] = useState(api.inspect());
  const [refreshing, setRefreshing] = useState(false);
  const [serverErr, setServerErr] = useState<string | null>(null);
  const [passthrough, setPassthrough] = useState(false);

  const reload = useCallback(async () => {
    setRefreshing(true);
    setServerErr(null);
    setClient(api.getTelemetry());
    setInspect(api.inspect());
    try {
      const data = await api.get<ServerStats>('/api/_telemetry', { tag: 'telemetry', timeoutMs: 5000, retry: { max: 1 } });
      setServer(data);
    } catch (e: any) {
      setServerErr(e?.message || 'Failed to fetch /api/_telemetry');
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    reload();
    const t = setInterval(reload, 5000);
    return () => clearInterval(t);
  }, [reload]);

  const togglePassthrough = (v: boolean) => {
    setPassthrough(v);
    api.configure({ enabled: !v });
  };

  const clearCache = () => {
    actionSheet.show({
      title: 'Clear API cache?',
      message: 'Drops all in-memory + persisted cached responses.',
      options: [
        { label: 'Cancel', kind: 'cancel' },
        { label: 'Clear cache', kind: 'destructive', onPress: () => {
          const n = api.clearCache();
          setInspect(api.inspect());
          toast.success(`Cleared ${n} cache entries`);
        }},
      ],
    });
  };

  const successRate = client.totalRequests
    ? Math.round((client.successes / client.totalRequests) * 100)
    : 100;

  const tagEntries = Object.entries(client.byTag)
    .sort((a, b) => b[1].count - a[1].count)
    .slice(0, 8);

  return (
    <SafeAreaView style={s.container}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.hdrBtn} hitSlop={{ top: 8, left: 8, right: 8, bottom: 8 }}>
          <Ionicons name="arrow-back" size={24} color="#F8FAFC" />
        </TouchableOpacity>
        <Text style={s.hdrTitle}>API Controller</Text>
        <TouchableOpacity onPress={reload} style={s.hdrBtn} hitSlop={{ top: 8, left: 8, right: 8, bottom: 8 }}>
          <Ionicons name="refresh" size={20} color="#3B82F6" />
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: 14, paddingBottom: 60 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={reload} tintColor="#3B82F6" />}
      >
        {/* ── Status pill ── */}
        <View style={[s.statusPill, { backgroundColor: inspect.isOnline ? '#10B98122' : '#EF444422', borderColor: inspect.isOnline ? '#10B981' : '#EF4444' }]}>
          <Ionicons name={inspect.isOnline ? 'wifi' : 'wifi-outline'} size={14} color={inspect.isOnline ? '#10B981' : '#EF4444'} />
          <Text style={[s.statusText, { color: inspect.isOnline ? '#10B981' : '#EF4444' }]}>
            {inspect.isOnline ? 'ONLINE' : 'OFFLINE'} · {inspect.inflight} in-flight · {inspect.cacheSize} cached
          </Text>
          {inspect.offlineQueueDepth > 0 && <Text style={[s.statusText, { color: '#F59E0B' }]}>· {inspect.offlineQueueDepth} queued</Text>}
        </View>

        {/* ── Client telemetry ── */}
        <Section title="Client" icon="phone-portrait" color="#3B82F6">
          <Grid items={[
            { label: 'Requests', value: client.totalRequests, accent: '#3B82F6' },
            { label: 'Success', value: client.successes, accent: '#10B981' },
            { label: 'Failures', value: client.failures, accent: client.failures > 0 ? '#EF4444' : '#94A3B8' },
            { label: 'Retries', value: client.retries, accent: '#F59E0B' },
            { label: 'Rate-limited', value: client.rateLimitedHits, accent: client.rateLimitedHits > 0 ? '#EF4444' : '#94A3B8' },
            { label: 'Cache hits', value: client.cacheHits, accent: '#A78BFA' },
            { label: 'p50 / p95', value: `${client.latency.p50}/${client.latency.p95}ms`, accent: '#F8FAFC' },
            { label: 'Success %', value: `${successRate}%`, accent: successRate >= 95 ? '#10B981' : successRate >= 80 ? '#F59E0B' : '#EF4444' },
          ]} />
          {client.lastError && (
            <View style={s.errorBox}>
              <Ionicons name="alert-circle" size={14} color="#EF4444" />
              <Text style={s.errorText} numberOfLines={3}>
                {client.lastError.tag}: {client.lastError.message}
              </Text>
            </View>
          )}
        </Section>

        {/* ── Per-tag breakdown ── */}
        {tagEntries.length > 0 && (
          <Section title="Top routes (client)" icon="list" color="#A78BFA">
            {tagEntries.map(([tag, m]) => (
              <View key={tag} style={s.tagRow}>
                <Text style={s.tagPath} numberOfLines={1}>{tag}</Text>
                <Text style={s.tagCount}>{m.count}</Text>
                <Text style={s.tagLatency}>{m.lastLatencyMs}ms</Text>
                {m.errors > 0 && <Text style={s.tagErrors}>{m.errors}✗</Text>}
              </View>
            ))}
          </Section>
        )}

        {/* ── Server telemetry ── */}
        <Section title="Server" icon="server" color="#10B981">
          {serverErr ? (
            <View style={s.errorBox}>
              <Ionicons name="alert-circle" size={14} color="#EF4444" />
              <Text style={s.errorText}>{serverErr}</Text>
            </View>
          ) : !server ? (
            <Text style={s.dim}>Loading…</Text>
          ) : (
            <>
              <Grid items={[
                { label: 'Uptime', value: `${Math.round(server.uptime_seconds / 60)}m`, accent: '#3B82F6' },
                { label: 'Requests', value: server.requests_total, accent: '#3B82F6' },
                { label: '2xx', value: server.requests_2xx, accent: '#10B981' },
                { label: '4xx', value: server.requests_4xx, accent: server.requests_4xx > 0 ? '#F59E0B' : '#94A3B8' },
                { label: '5xx', value: server.requests_5xx, accent: server.requests_5xx > 0 ? '#EF4444' : '#94A3B8' },
                { label: 'Rate-limited', value: server.rate_limited_total, accent: server.rate_limited_total > 0 ? '#EF4444' : '#94A3B8' },
                { label: 'p50/p95', value: `${server.latency_ms.p50}/${server.latency_ms.p95}ms`, accent: '#F8FAFC' },
                { label: 'Limit', value: `${server.rate_limit.per_minute}/min`, accent: '#3B82F6' },
              ]} />
            </>
          )}
        </Section>

        {/* ── Controls ── */}
        <Section title="Controls" icon="settings" color="#F59E0B">
          <View style={s.row}>
            <View style={{ flex: 1 }}>
              <Text style={s.rowLabel}>Passthrough mode</Text>
              <Text style={s.rowHint}>Disable controller features. Vanilla fetch, no retries, no cache.</Text>
            </View>
            <Switch
              value={passthrough}
              onValueChange={togglePassthrough}
              trackColor={{ false: '#404040', true: '#F59E0B' }}
              thumbColor={passthrough ? '#D97706' : '#94A3B8'}
            />
          </View>
          <TouchableOpacity style={s.clearBtn} onPress={clearCache} activeOpacity={0.85}>
            <Ionicons name="trash-outline" size={16} color="#fff" />
            <Text style={s.clearBtnText}>Clear cache ({inspect.cacheSize})</Text>
          </TouchableOpacity>
        </Section>

        {/* ── Config inspect ── */}
        <Section title="Configuration" icon="information-circle" color="#94A3B8">
          <KV k="API base" v={inspect.base} />
          <KV k="Default timeout" v={`${inspect.defaultTimeoutMs}ms`} />
          <KV k="Retries" v={`max=${inspect.defaultRetry.max} base=${inspect.defaultRetry.baseMs}ms cap=${inspect.defaultRetry.capMs}ms`} />
          <KV k="Cache TTL (default)" v={`${inspect.defaultCacheTtlMs}ms`} />
          <KV k="Enabled" v={inspect.enabled ? 'yes' : 'no (passthrough)'} />
        </Section>

        <Text style={s.footer}>Polling every 5s. Pull down to refresh.</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const Section: React.FC<{ title: string; icon: any; color: string; children: React.ReactNode }> = ({ title, icon, color, children }) => (
  <View style={s.section}>
    <View style={s.sectionHead}>
      <Ionicons name={icon} size={16} color={color} />
      <Text style={[s.sectionTitle, { color }]}>{title}</Text>
    </View>
    {children}
  </View>
);

const Grid: React.FC<{ items: { label: string; value: any; accent: string }[] }> = ({ items }) => (
  <View style={s.grid}>
    {items.map((it, i) => (
      <View key={i} style={s.gridCell}>
        <Text style={[s.gridValue, { color: it.accent }]}>{it.value}</Text>
        <Text style={s.gridLabel}>{it.label}</Text>
      </View>
    ))}
  </View>
);

const KV: React.FC<{ k: string; v: any }> = ({ k, v }) => (
  <View style={s.kvRow}>
    <Text style={s.kvKey}>{k}</Text>
    <Text style={s.kvVal} numberOfLines={1}>{String(v)}</Text>
  </View>
);

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#141414' },
  header: { flexDirection: 'row', alignItems: 'center', padding: 12, backgroundColor: '#262626', borderBottomWidth: 1, borderBottomColor: '#404040' },
  hdrBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  hdrTitle: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '700', color: '#F8FAFC' },
  statusPill: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, borderWidth: 1, marginBottom: 12, alignSelf: 'flex-start' },
  statusText: { fontSize: 11, fontWeight: '800', letterSpacing: 0.5 },
  section: { backgroundColor: '#262626', borderRadius: 12, padding: 12, marginBottom: 12, borderWidth: 1, borderColor: '#404040' },
  sectionHead: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 10 },
  sectionTitle: { fontSize: 12, fontWeight: '800', letterSpacing: 0.5, textTransform: 'uppercase' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 4 },
  gridCell: { width: '24%', backgroundColor: '#141414', borderRadius: 8, padding: 8, alignItems: 'center', borderWidth: 1, borderColor: '#404040', marginBottom: 4 },
  gridValue: { fontSize: 14, fontWeight: '800' },
  gridLabel: { color: '#94A3B8', fontSize: 9, fontWeight: '700', marginTop: 2, textTransform: 'uppercase' },
  tagRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6, borderTopWidth: 1, borderTopColor: '#404040' },
  tagPath: { color: '#CBD5E1', fontSize: 11, fontFamily: 'monospace', flex: 1 },
  tagCount: { color: '#3B82F6', fontSize: 11, fontWeight: '800', minWidth: 36, textAlign: 'right' },
  tagLatency: { color: '#94A3B8', fontSize: 11, minWidth: 50, textAlign: 'right' },
  tagErrors: { color: '#EF4444', fontSize: 11, fontWeight: '800', minWidth: 30, textAlign: 'right' },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, paddingVertical: 8 },
  rowLabel: { color: '#F8FAFC', fontSize: 13, fontWeight: '700' },
  rowHint: { color: '#94A3B8', fontSize: 11, marginTop: 2 },
  clearBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: '#EF4444', borderRadius: 8, paddingVertical: 10, marginTop: 6 },
  clearBtnText: { color: '#fff', fontSize: 13, fontWeight: '800' },
  kvRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 },
  kvKey: { color: '#94A3B8', fontSize: 11, fontWeight: '600' },
  kvVal: { color: '#CBD5E1', fontSize: 11, fontFamily: 'monospace', maxWidth: '60%' },
  errorBox: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#EF444411', borderRadius: 6, padding: 8, marginTop: 8, borderWidth: 1, borderColor: '#EF444444' },
  errorText: { color: '#EF4444', fontSize: 11, flex: 1 },
  dim: { color: '#94A3B8', fontSize: 12, fontStyle: 'italic' },
  footer: { color: '#64748B', fontSize: 10, textAlign: 'center', marginTop: 6, fontStyle: 'italic' },
});
