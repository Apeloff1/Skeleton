/**
 * /storage — Unbulk storage dashboard.
 * Visualizes reclaimed space (compression savings) + lazy-module load status.
 */
import React from 'react';
import {
  View, Text, StyleSheet, SafeAreaView, ScrollView, TouchableOpacity,
  ActivityIndicator, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../src/utils/apiClient';

const GREEN = '#22c55e';
const BLUE = '#3b82f6';
const PURPLE = '#a78bfa';
const AMBER = '#f59e0b';
const CARD = '#111827';
const BG = '#0b1220';
const MUTE = '#94a3b8';

export default function StorageDashboard() {
  const router = useRouter();
  const [savings, setSavings] = React.useState<any>(null);
  const [lazy, setLazy] = React.useState<any>(null);
  const [modules, setModules] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);
  const [sweeping, setSweeping] = React.useState(false);
  const [sweepMsg, setSweepMsg] = React.useState('');

  const load = React.useCallback(async () => {
    const [s, l, m] = await Promise.all([
      api.get<any>('/api/storage/savings', { timeoutMs: 20000 }),
      api.get<any>('/api/storage/lazy', { timeoutMs: 15000 }),
      api.get<any>('/api/storage/modules?top=8', { timeoutMs: 20000 }),
    ]);
    if (s.ok) setSavings(s.data);
    if (l.ok) setLazy(l.data);
    if (m.ok) setModules(m.data);
    setLoading(false);
    setRefreshing(false);
  }, []);

  React.useEffect(() => { load(); }, [load]);

  const runSweep = async () => {
    setSweeping(true); setSweepMsg('Compacting…');
    const r = await api.post<any>('/api/storage/sweep', { freeze_cold: true }, { timeoutMs: 60000 });
    setSweepMsg(r.ok ? 'Sweep complete — storage compacted.' : 'Sweep failed.');
    await load();
    setSweeping(false);
  };

  const fmtBytes = (b: number) => {
    if (!b) return '0 B';
    const u = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.min(Math.floor(Math.log(b) / Math.log(1024)), u.length - 1);
    return `${(b / Math.pow(1024, i)).toFixed(1)} ${u[i]}`;
  };

  const loadedPct = (grp: any) => grp?.total ? Math.round((grp.loaded / grp.total) * 100) : 0;

  return (
    <SafeAreaView style={s.root}>
      <View style={s.header}>
        <TouchableOpacity testID="storage-back" onPress={() => router.back()} style={{ padding: 4 }} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
          <Ionicons name="chevron-back" size={22} color={GREEN} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={s.title}>💾 Storage</Text>
          <Text style={s.sub}>Unbulk reclaimed space · lazy modules</Text>
        </View>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: 16, paddingBottom: 48 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={GREEN} />}
      >
        {loading ? (
          <View style={{ paddingVertical: 60, alignItems: 'center' }}><ActivityIndicator color={GREEN} size="large" /></View>
        ) : (
          <>
            <View style={s.statRow}>
              <Stat label="Saved" value={savings?.human?.saved || '—'} color={GREEN} />
              <Stat label="Reduction" value={`${savings?.saved_pct ?? 0}%`} color={BLUE} />
              <Stat label="Ratio" value={`${savings?.overall_ratio ?? 0}×`} color={PURPLE} />
            </View>

            <Text style={s.h2}>♻️ Reclaimed Space</Text>
            <View style={s.card}>
              <Row label="Raw (uncompressed)" value={savings?.human?.raw || fmtBytes(savings?.total_raw_bytes)} />
              <Row label="Stored (on disk)" value={savings?.human?.stored || fmtBytes(savings?.total_stored_bytes)} />
              <Row label="Reclaimed" value={savings?.human?.saved || fmtBytes(savings?.bytes_saved)} color={GREEN} />
              <View style={s.barTrack}>
                <View style={[s.barFill, { width: `${Math.min(savings?.saved_pct ?? 0, 100)}%` }]} />
              </View>
              <Text style={s.barCap}>{savings?.saved_pct ?? 0}% of raw data reclaimed by Unbulk</Text>
            </View>

            <Text style={s.h2}>🗂️ Compressed Namespaces</Text>
            <View style={s.card}>
              {(savings?.namespaces || []).slice(0, 8).map((n: any, i: number) => (
                <View key={i} style={s.nsRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={s.nsName} numberOfLines={1}>{n.namespace}</Text>
                    <Text style={s.nsMeta}>{fmtBytes(n.raw_bytes)} → {fmtBytes(n.stored_bytes)}{n.shards ? ` · ${n.shards} shards` : ''}</Text>
                  </View>
                  <View style={[s.badge, { borderColor: GREEN, backgroundColor: GREEN + '22' }]}>
                    <Text style={[s.badgeTxt, { color: GREEN }]}>{n.ratio}×</Text>
                  </View>
                </View>
              ))}
              {(savings?.namespaces || []).length === 0 && <Text style={s.empty}>No namespaces reported.</Text>}
            </View>

            <Text style={s.h2}>⚡ Lazy Modules (loaded vs deferred)</Text>
            <View style={s.card}>
              {['core', 'seeds', 'flagged'].map((k) => {
                const grp = lazy?.[k];
                if (!grp) return null;
                return (
                  <View key={k} style={{ paddingVertical: 8, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#1f2937' }}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                      <Text style={s.nsName}>{k}</Text>
                      <Text style={s.nsMeta}>{grp.loaded}/{grp.total} loaded · {grp.deferred} deferred</Text>
                    </View>
                    <View style={s.barTrack}>
                      <View style={[s.barFill, { width: `${loadedPct(grp)}%`, backgroundColor: BLUE }]} />
                    </View>
                  </View>
                );
              })}
              {modules?.module_count != null && (
                <Text style={[s.nsMeta, { marginTop: 8 }]}>
                  Source inventory: {modules.module_count} modules · {fmtBytes(modules.total_bytes)} · {modules.total_lines?.toLocaleString?.() || modules.total_lines} lines
                </Text>
              )}
            </View>

            <TouchableOpacity testID="storage-sweep" style={[s.sweepBtn, sweeping && { opacity: 0.6 }]} onPress={runSweep} disabled={sweeping}>
              {sweeping ? <ActivityIndicator color="#04120a" size="small" /> : <Text style={s.sweepTxt}>🧹 Run compaction sweep</Text>}
            </TouchableOpacity>
            {!!sweepMsg && <Text style={s.reply}>{sweepMsg}</Text>}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <View style={s.stat}>
      <Text style={[s.statVal, { color }]}>{value}</Text>
      <Text style={s.statLbl}>{label}</Text>
    </View>
  );
}

function Row({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={s.row}>
      <Text style={s.rowLbl}>{label}</Text>
      <Text style={[s.rowVal, color ? { color } : null]}>{value}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: BG },
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 14, paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#1f2937' },
  title: { color: '#f1f5f9', fontSize: 17, fontWeight: '700' },
  sub: { color: MUTE, fontSize: 12, marginTop: 1 },
  statRow: { flexDirection: 'row', gap: 8, marginBottom: 6 },
  stat: { flex: 1, backgroundColor: CARD, borderRadius: 12, paddingVertical: 14, alignItems: 'center' },
  statVal: { fontSize: 18, fontWeight: '800' },
  statLbl: { color: MUTE, fontSize: 11, marginTop: 2 },
  h2: { color: '#e2e8f0', fontSize: 14, fontWeight: '700', marginTop: 18, marginBottom: 8 },
  card: { backgroundColor: CARD, borderRadius: 14, padding: 14 },
  row: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 5 },
  rowLbl: { color: MUTE, fontSize: 13 },
  rowVal: { color: '#f1f5f9', fontSize: 13, fontWeight: '700' },
  barTrack: { height: 8, borderRadius: 4, backgroundColor: '#1e293b', marginTop: 10, overflow: 'hidden' },
  barFill: { height: 8, borderRadius: 4, backgroundColor: GREEN },
  barCap: { color: MUTE, fontSize: 11, marginTop: 6 },
  nsRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 7, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#1f2937' },
  nsName: { color: '#f1f5f9', fontSize: 13, fontWeight: '600', textTransform: 'capitalize' },
  nsMeta: { color: MUTE, fontSize: 11, marginTop: 1 },
  badge: { borderRadius: 6, borderWidth: 1, paddingHorizontal: 8, paddingVertical: 3 },
  badgeTxt: { fontSize: 11, fontWeight: '800' },
  empty: { color: MUTE, fontSize: 12, fontStyle: 'italic' },
  sweepBtn: { backgroundColor: AMBER, borderRadius: 12, paddingVertical: 14, alignItems: 'center', marginTop: 20 },
  sweepTxt: { color: '#04120a', fontSize: 14, fontWeight: '800' },
  reply: { color: GREEN, fontSize: 13, marginTop: 12, textAlign: 'center' },
});
