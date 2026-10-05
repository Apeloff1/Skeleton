/**
 * /health — Live system-health debug panel (developer drawer).
 *
 * Utility-first, terminal-flavoured dashboard (NOT the luxe game styling):
 *   • BACKEND   — /api/health status, uptime, AI availability.
 *   • CIRCUIT BREAKERS — live per-bucket state chips (green/amber/red) from the
 *     apiClient breaker, with cool-off countdowns; reset control.
 *   • STORAGE PRUNER — sidecar-meta stats + a "Run prune now" action.
 * Strict high-contrast red/amber/green signalling per design blueprint.
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet, SafeAreaView, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import api, { _circuitBreakerStats, _circuitBreakerReset } from '../src/utils/apiClient';
import { _safeStorageStats, pruneExpired } from '../utils/safeStorage';
import theme from '../theme/tokens';

const C = theme.colors, S = theme.spacing, R = theme.radii;
const MONO = theme.typography.fontFamily.mono;

const SIGNAL = {
  ok:    { color: '#10b981', bg: 'rgba(16,185,129,0.14)', label: 'HEALTHY' },
  warn:  { color: '#f59e0b', bg: 'rgba(245,158,11,0.14)', label: 'DEGRADED' },
  error: { color: '#ef4444', bg: 'rgba(239,68,68,0.14)', label: 'DOWN' },
};
const CB_SIGNAL: Record<string, keyof typeof SIGNAL> = { closed: 'ok', half_open: 'warn', open: 'error' };

function Chip({ kind, text }: { kind: keyof typeof SIGNAL; text?: string }) {
  const s = SIGNAL[kind];
  return (
    <View style={[styles.chip, { backgroundColor: s.bg, borderColor: s.color }]}>
      <View style={[styles.dot, { backgroundColor: s.color }]} />
      <Text style={[styles.chipTxt, { color: s.color }]}>{text || s.label}</Text>
    </View>
  );
}

export default function HealthScreen() {
  const router = useRouter();
  const [backend, setBackend] = React.useState<any>(null);
  const [backendErr, setBackendErr] = React.useState(false);
  const [cb, setCb] = React.useState<Record<string, any>>({});
  const [store, setStore] = React.useState<{ tracked: number; oldestAgeMs: number | null } | null>(null);
  const [pruneMsg, setPruneMsg] = React.useState<string | null>(null);
  const [tick, setTick] = React.useState(0);

  const refreshBackend = React.useCallback(async () => {
    const r = await api.get('/api/health', { timeoutMs: 8_000, retries: 0 });
    if (r.ok && r.data) { setBackend(r.data); setBackendErr(false); } else { setBackendErr(true); }
  }, []);
  const refreshStore = React.useCallback(async () => { setStore(await _safeStorageStats()); }, []);

  React.useEffect(() => { refreshBackend(); refreshStore(); }, [refreshBackend, refreshStore]);
  // Live breaker poll every 1.5s (breaker stats are in-memory, free to read).
  React.useEffect(() => {
    const id = setInterval(() => { setCb(_circuitBreakerStats()); setTick(t => t + 1); }, 1500);
    setCb(_circuitBreakerStats());
    return () => clearInterval(id);
  }, []);

  const buckets = Object.entries(cb);
  const days = (ms: number | null) => ms == null ? '—' : `${(ms / 86_400_000).toFixed(1)}d`;
  const uptime = backend?.uptime_seconds != null ? `${Math.floor(backend.uptime_seconds / 60)}m ${Math.floor(backend.uptime_seconds % 60)}s` : '—';

  const runPrune = React.useCallback(async () => {
    setPruneMsg('running…');
    const r = await pruneExpired({ ttlMs: 7 * 24 * 60 * 60 * 1000 });
    setPruneMsg(`pruned ${r.pruned}/${r.scanned} in ${r.elapsedMs}ms`);
    refreshStore();
  }, [refreshStore]);

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <TouchableOpacity testID="health-back" hitSlop={theme.hitSlop.md} onPress={() => { try { { if (router.canGoBack()) router.back(); else router.replace('/top'); } } catch { router.replace('/top'); } }}>
          <Text style={styles.backTxt}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.title}>● system.health</Text>
        <View style={{ width: 56 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: S.base, paddingBottom: 48 }}>
        {/* BACKEND */}
        <View style={styles.module}>
          <View style={styles.modHead}>
            <Text style={styles.modTitle}>BACKEND</Text>
            <Chip kind={backendErr ? 'error' : (backend?.status === 'healthy' ? 'ok' : 'warn')}
                  text={backendErr ? 'UNREACHABLE' : (backend?.status || '…').toUpperCase()} />
          </View>
          <Row k="uptime" v={uptime} />
          <Row k="ai_available" v={String(backend?.ai_available ?? '—')} valKind={backend?.ai_available ? 'ok' : 'warn'} />
          <Row k="db" v={String(backend?.db ?? backend?.database ?? 'n/a')} />
          <TouchableOpacity testID="health-refresh" style={styles.actionBtn} onPress={refreshBackend}>
            <Text style={styles.actionTxt}>↻ refresh</Text>
          </TouchableOpacity>
        </View>

        {/* CIRCUIT BREAKERS */}
        <View style={styles.module}>
          <View style={styles.modHead}>
            <Text style={styles.modTitle}>CIRCUIT BREAKERS</Text>
            <Chip kind={buckets.some(([, v]) => v.state === 'open') ? 'error' : buckets.some(([, v]) => v.state === 'half_open') ? 'warn' : 'ok'}
                  text={buckets.length ? `${buckets.length} TRACKED` : 'ALL CLOSED'} />
          </View>
          {buckets.length === 0 ? (
            <Text style={styles.emptyLine}>› all circuits closed — no failures recorded ✓</Text>
          ) : buckets.map(([bucket, v]) => {
            const remain = Math.max(0, Math.round((v.openUntil - Date.now()) / 1000));
            return (
              <View key={bucket} style={styles.cbRow}>
                <Chip kind={CB_SIGNAL[v.state]} text={v.state.toUpperCase()} />
                <Text style={styles.cbBucket} numberOfLines={1}>{bucket}</Text>
                <Text style={styles.cbMeta}>
                  {v.state === 'open' ? `cool ${remain}s` : `fails ${v.failures}`}{v.consecutiveOpens > 1 ? ` ·×${v.consecutiveOpens}` : ''}
                </Text>
              </View>
            );
          })}
          {buckets.length ? (
            <TouchableOpacity testID="health-reset-cb" style={[styles.actionBtn, styles.dangerBtn]} onPress={() => { _circuitBreakerReset(); setCb(_circuitBreakerStats()); }}>
              <Text style={[styles.actionTxt, { color: SIGNAL.error.color }]}>⟲ reset all breakers</Text>
            </TouchableOpacity>
          ) : null}
        </View>

        {/* STORAGE PRUNER */}
        <View style={styles.module}>
          <View style={styles.modHead}>
            <Text style={styles.modTitle}>STORAGE PRUNER</Text>
            <Chip kind="ok" text="7d TTL" />
          </View>
          <Row k="tracked_keys" v={String(store?.tracked ?? '—')} />
          <Row k="oldest_key" v={days(store?.oldestAgeMs ?? null)} />
          {pruneMsg ? <Text style={styles.emptyLine}>› {pruneMsg}</Text> : null}
          <TouchableOpacity testID="health-prune" style={styles.actionBtn} onPress={runPrune}>
            <Text style={styles.actionTxt}>⌫ run prune now</Text>
          </TouchableOpacity>
        </View>

        <Text style={styles.footer}>auto-refresh · breaker poll 1.5s · tick {tick}</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

function Row({ k, v, valKind }: { k: string; v: string; valKind?: keyof typeof SIGNAL }) {
  return (
    <View style={styles.kvRow}>
      <Text style={styles.kvKey}>{k}</Text>
      <Text style={[styles.kvVal, valKind ? { color: SIGNAL[valKind].color } : null]}>{v}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#06070c' },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: S.base, paddingTop: Platform.OS === 'ios' ? S.sm : S.base, paddingBottom: S.md,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.border,
  },
  backTxt: { color: '#10b981', fontFamily: MONO, fontSize: 14, width: 56 },
  title: { color: '#10b981', fontFamily: MONO, fontSize: 15, fontWeight: '700' },
  module: { backgroundColor: '#0b0d14', borderRadius: R.md, borderWidth: 1, borderColor: C.border, padding: S.base, marginBottom: S.md },
  modHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: S.md },
  modTitle: { color: C.textMuted, fontFamily: MONO, fontSize: 12, fontWeight: '700', letterSpacing: 1.5 },
  chip: { flexDirection: 'row', alignItems: 'center', gap: 6, borderRadius: R.sm, borderWidth: 1, paddingHorizontal: S.sm, paddingVertical: 3 },
  dot: { width: 7, height: 7, borderRadius: 4 },
  chipTxt: { fontFamily: MONO, fontSize: 10, fontWeight: '800', letterSpacing: 0.5 },
  kvRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 5, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: 'rgba(255,255,255,0.04)' },
  kvKey: { color: C.textDim, fontFamily: MONO, fontSize: 12 },
  kvVal: { color: C.text, fontFamily: MONO, fontSize: 12, fontWeight: '600' },
  cbRow: { flexDirection: 'row', alignItems: 'center', gap: S.sm, paddingVertical: 6 },
  cbBucket: { flex: 1, color: C.text, fontFamily: MONO, fontSize: 12 },
  cbMeta: { color: C.textDim, fontFamily: MONO, fontSize: 11 },
  emptyLine: { color: C.textDim, fontFamily: MONO, fontSize: 12, marginTop: 2 },
  actionBtn: { marginTop: S.md, backgroundColor: C.surface, borderRadius: R.sm, borderWidth: 1, borderColor: C.border, paddingVertical: 9, alignItems: 'center' },
  dangerBtn: { borderColor: 'rgba(239,68,68,0.4)', backgroundColor: 'rgba(239,68,68,0.06)' },
  actionTxt: { color: C.textMuted, fontFamily: MONO, fontSize: 12, fontWeight: '700' },
  footer: { color: C.textDisabled, fontFamily: MONO, fontSize: 10, textAlign: 'center', marginTop: S.sm },
});
