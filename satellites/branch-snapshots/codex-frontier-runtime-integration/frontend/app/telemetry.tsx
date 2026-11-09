/**
 * /telemetry — Live dashboard for the security + modal-log system.
 *
 * Four tabs:
 *   • Live      — most recent events (auto-refreshes every 5s)
 *   • Sessions  — grouped by session_id with duration + modal counts
 *   • Security  — audit ring, rate-limit state, error rate
 *   • Modals    — top modals by event count
 */
import { useCallback, useEffect, useState } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  StyleSheet, SafeAreaView, RefreshControl, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import theme from '../theme/tokens';
import { useModalLogger } from '../utils/modalLogger';
import { useBackendHealth } from '../utils/selfHeal';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const { breathing, palette, radii } = theme;

type Tab = 'live' | 'sessions' | 'security' | 'modals';

export default function TelemetryRoute() {
  const router = useRouter();
  const log = useModalLogger('TelemetryRoute');
  const health = useBackendHealth(10_000);
  const [tab, setTab] = useState<Tab>('live');
  const [data, setData] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [, setFetchErr] = useState<string | null>(null);

  const endpoint = {
    live:     '/api/telemetry/recent?limit=80',
    sessions: '/api/telemetry/sessions?limit=40',
    security: '/api/security/audit-summary',
    modals:   '/api/telemetry/summary',
  }[tab];

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const r = await fetch(`${BACKEND}${endpoint}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      setData(j);
      setFetchErr(null);
    } catch (e: any) {
      log.error(e);
      setFetchErr(String(e?.message || e).slice(0, 100));
    } finally {
      setBusy(false);
    }
  }, [endpoint, log]);

  useEffect(() => { load(); const id = setInterval(load, 5000); return () => clearInterval(id); }, [load]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { log.action('tab_change', { tab }); setData(null); setFetchErr(null); }, [tab]);

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={theme.hitSlop.md} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={palette.ink[100]} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.h1}>Telemetry</Text>
          <Text style={styles.sub}>
            backend: {health.online ? (health.ok ? '✓ healthy' : '⚠ degraded') : '✗ offline'} · err {(health.error_rate * 100).toFixed(1)}%
          </Text>
        </View>
        {busy ? <ActivityIndicator color={palette.ink[200]} /> : null}
      </View>

      <View style={styles.tabRow}>
        {(['live', 'sessions', 'security', 'modals'] as Tab[]).map(t => (
          <TouchableOpacity
            key={t}
            onPress={() => { setTab(t); }}
            style={[styles.tab, tab === t && styles.tabActive]}
          >
            <Text style={[styles.tabText, tab === t && styles.tabTextActive]}>{t}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: breathing.gutter }}
        refreshControl={<RefreshControl refreshing={busy} onRefresh={load} tintColor={palette.ink[200]} />}
      >
        {tab === 'live' && <LiveView data={data} />}
        {tab === 'sessions' && <SessionsView data={data} />}
        {tab === 'security' && <SecurityView data={data} />}
        {tab === 'modals' && <ModalsView data={data} />}
        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

// ─────────────────────────────────────────────────────────────────
function LiveView({ data }: { data: any }) {
  const events = data?.events || [];
  return (
    <View>
      <Text style={styles.muted}>{events.length} most-recent events (auto-refresh 5s)</Text>
      {events.slice().reverse().map((e: any, i: number) => (
        <View key={i} style={[styles.eventRow, sevStyle(e.severity)]}>
          <View style={{ flex: 1 }}>
            <Text style={styles.eventTitle}>
              {e.modal_id} · <Text style={styles.eventName}>{e.event}</Text>
            </Text>
            {e.detail ? <Text style={styles.eventDetail} numberOfLines={2}>{JSON.stringify(e.detail).slice(0, 200)}</Text> : null}
          </View>
          <Text style={styles.eventTs}>{new Date(e.ts * 1000).toLocaleTimeString()}</Text>
        </View>
      ))}
      {events.length === 0 && <Text style={styles.empty}>no events yet — open any modal to start logging</Text>}
    </View>
  );
}

function SessionsView({ data }: { data: any }) {
  const sessions = data?.sessions || [];
  return (
    <View>
      <Text style={styles.muted}>{sessions.length} sessions</Text>
      {sessions.map((s: any) => (
        <View key={s.session_id} style={styles.card}>
          <Text style={styles.eventTitle}>{s.session_id}</Text>
          <View style={styles.metaRow}>
            <Text style={styles.metaItem}>{s.events} events</Text>
            <Text style={styles.metaItem}>{s.modal_count} modals</Text>
            <Text style={styles.metaItem}>{s.duration_s}s</Text>
            {s.errors > 0 && <Text style={[styles.metaItem, { color: '#A78BFA' }]}>{s.errors} errors</Text>}
          </View>
          <Text style={styles.eventDetail} numberOfLines={2}>{s.modals.join(' · ')}</Text>
        </View>
      ))}
      {sessions.length === 0 && <Text style={styles.empty}>no sessions yet</Text>}
    </View>
  );
}

function SecurityView({ data }: { data: any }) {
  if (!data || data.empty) return <Text style={styles.empty}>audit buffer empty</Text>;
  return (
    <View>
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Audit summary</Text>
        <Row label="Total requests" value={String(data.total_requests || 0)} />
        <Row label="Errors" value={`${data.errors || 0} (${((data.error_rate || 0) * 100).toFixed(1)}%)`} ok={(data.error_rate || 0) < 0.05} />
        <Row label="Avg latency" value={`${data.avg_ms || 0} ms`} />
      </View>
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Status codes</Text>
        {Object.entries(data.statuses || {}).map(([code, count]: any) => (
          <Row key={code} label={code} value={String(count)} ok={Number(code) < 400} />
        ))}
      </View>
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Top paths</Text>
        {(data.top_paths || []).map((p: any) => (
          <Row key={p.path} label={p.path} value={`${p.count}×`} mono />
        ))}
      </View>
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Slowest paths</Text>
        {(data.slowest || []).map((p: any) => (
          <Row key={p.path} label={p.path} value={`${p.p_max_ms}ms peak`} mono />
        ))}
      </View>
    </View>
  );
}

function ModalsView({ data }: { data: any }) {
  if (!data || data.empty) return <Text style={styles.empty}>no modal events yet</Text>;
  return (
    <View>
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Overview</Text>
        <Row label="Total events" value={String(data.total_events || 0)} />
        <Row label="Errors" value={`${data.errors || 0} (${((data.error_rate || 0) * 100).toFixed(1)}%)`} ok={(data.error_rate || 0) < 0.05} />
        <Row label="Avg duration" value={data.avg_duration_ms ? `${data.avg_duration_ms} ms` : '—'} />
        <Row label="Ring size" value={`${data.ring_size_now}/${data.ring_capacity}`} mono />
      </View>
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Top modals</Text>
        {(data.top_modals || []).map((m: any) => (
          <Row key={m[0]} label={m[0]} value={`${m[1]} events`} mono />
        ))}
      </View>
      <View style={styles.card}>
        <Text style={styles.cardTitle}>By event type</Text>
        {Object.entries(data.by_event || {}).map(([k, v]: any) => (
          <Row key={k} label={k} value={String(v)} />
        ))}
      </View>
    </View>
  );
}

// ─────────────────────────────────────────────────────────────────
function Row({ label, value, ok, mono }: { label: string; value: string; ok?: boolean; mono?: boolean }) {
  return (
    <View style={styles.kvRow}>
      <Text style={styles.kvLabel} numberOfLines={1}>{label}</Text>
      <Text style={[
        styles.kvValue,
        mono && { fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }) },
        ok === true && { color: '#10B981' },
        ok === false && { color: '#A78BFA' },
      ]}>{value}</Text>
    </View>
  );
}

function sevStyle(sev: string) {
  if (sev === 'error' || sev === 'fatal') return { borderLeftColor: '#A78BFA' };
  if (sev === 'warn') return { borderLeftColor: '#fbbf24' };
  return { borderLeftColor: '#a78bfa' };
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: palette.ink[1000] },
  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: breathing.gutter, paddingVertical: 12, gap: 12,
    borderBottomWidth: 1, borderBottomColor: palette.ink[800],
  },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  h1: { fontSize: 22, fontWeight: '700', color: palette.ink[50] },
  sub: { fontSize: 11, color: palette.ink[400], marginTop: 2 },

  tabRow: { flexDirection: 'row', paddingHorizontal: breathing.gutter, paddingVertical: 10, gap: 6 },
  tab: { flex: 1, height: 36, borderRadius: radii.pill, backgroundColor: palette.ink[800], alignItems: 'center', justifyContent: 'center' },
  tabActive: { backgroundColor: '#a78bfa' },
  tabText: { fontSize: 12, fontWeight: '600', color: palette.ink[300], textTransform: 'capitalize' },
  tabTextActive: { color: palette.ink[1000] },

  card: {
    backgroundColor: palette.ink[900], borderRadius: radii.md,
    padding: breathing.cardPadding, marginBottom: breathing.cardGap,
    borderWidth: 1, borderColor: palette.ink[800],
  },
  cardTitle: { fontSize: 14, fontWeight: '700', color: palette.ink[100], marginBottom: 8 },

  eventRow: {
    flexDirection: 'row', alignItems: 'flex-start',
    paddingVertical: 8, paddingHorizontal: 10,
    borderLeftWidth: 3, borderRadius: 4,
    backgroundColor: palette.ink[900], marginBottom: 6,
  },
  eventTitle: { fontSize: 13, fontWeight: '600', color: palette.ink[100] },
  eventName:  { color: '#a78bfa' },
  eventDetail: { fontSize: 11, color: palette.ink[400], marginTop: 2, fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }) },
  eventTs:    { fontSize: 10, color: palette.ink[500] },

  kvRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4, gap: 12 },
  kvLabel: { color: palette.ink[300], fontSize: 12, flex: 1 },
  kvValue: { color: palette.ink[100], fontSize: 12 },

  metaRow: { flexDirection: 'row', gap: 10, marginVertical: 4 },
  metaItem: { fontSize: 11, color: palette.ink[400] },

  muted: { fontSize: 11, color: palette.ink[500], marginBottom: 8 },
  empty: { color: palette.ink[400], fontSize: 13, textAlign: 'center', paddingVertical: 32 },
});
