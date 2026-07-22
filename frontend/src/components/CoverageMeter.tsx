import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator } from 'react-native';
import { apiFetch } from '../../utils/apiController';

const API = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const C = { card: '#141b2e', border: '#2a3550', text: '#eef2fb', muted: '#8a96b2', accent: '#a78bfa', good: '#43d39e', track: '#22304e' };

const STAGE_ICON: Record<string, string> = { refine: '🔧', polish: '✨', qc: '🛡️' };

export default function CoverageMeter({ build }: { build: string }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!build) { setLoading(false); return; }
    try {
      const r = await apiFetch(`${API}/api/galaxy-studio/gates/build/${encodeURIComponent(build)}/coverage`, { timeoutMs: 10000 });
      setData(await r.json());
    } catch { /* ignore */ } finally { setLoading(false); }
  }, [build]);
  useEffect(() => { load(); }, [load]);

  if (loading) return <View style={styles.card}><ActivityIndicator color={C.accent} /></View>;
  if (!data) return null;

  const mountedRows = (data.systems || []).filter((s: any) => s.mounted);
  return (
    <View style={styles.card} testID="coverage-meter">
      <View style={styles.head}>
        <Text style={styles.title}>📊 Systems Coverage</Text>
        <TouchableOpacity onPress={load} testID="coverage-refresh"><Text style={styles.refresh}>↻</Text></TouchableOpacity>
      </View>
      <Text style={styles.sub}>{data.mounted_count}/{data.total} systems mounted · {data.ship_ready_count} ship-ready</Text>
      <View style={styles.bar}>
        <View style={[styles.fill, { width: `${data.mounted_pct}%` }]} />
      </View>
      {mountedRows.length > 0 && (
        <View style={styles.rows}>
          {mountedRows.map((s: any) => (
            <View key={s.system} style={styles.row}>
              <Text style={styles.rowLabel} numberOfLines={1}>{s.icon} {s.label}</Text>
              <View style={styles.stageDots}>
                {(data.stage_keys || []).map((sk: string) => {
                  const done = (s.stages_passed || []).includes(sk);
                  return (
                    <View key={sk} style={[styles.dot, done && styles.dotOn]}>
                      <Text style={[styles.dotTxt, done && { color: '#04140d' }]}>{STAGE_ICON[sk] || sk[0]}</Text>
                    </View>
                  );
                })}
              </View>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 12, marginBottom: 12 },
  head: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  title: { color: C.text, fontSize: 14, fontWeight: '900' },
  refresh: { color: C.accent, fontSize: 18, fontWeight: '900' },
  sub: { color: C.muted, fontSize: 11, fontWeight: '600', marginTop: 2, marginBottom: 8 },
  bar: { height: 8, borderRadius: 4, backgroundColor: C.track, overflow: 'hidden' },
  fill: { height: 8, backgroundColor: C.accent, borderRadius: 4 },
  rows: { marginTop: 10, gap: 6 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  rowLabel: { color: C.text, fontSize: 12, fontWeight: '700', flex: 1 },
  stageDots: { flexDirection: 'row', gap: 5 },
  dot: { width: 22, height: 22, borderRadius: 11, backgroundColor: C.track, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: C.border },
  dotOn: { backgroundColor: C.good, borderColor: C.good },
  dotTxt: { fontSize: 10, color: C.muted },
});
