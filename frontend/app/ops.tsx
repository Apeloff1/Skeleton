/**
 * /ops — Admin / Ops observability (DELUXE, read-only).
 * At-a-glance platform health: headline KPIs (GMV, paid txns, active listings,
 * live tournaments, creators, games), recent transactions, and collection counts.
 * Backed by GET /api/admin/ops/overview. If OPS_TOKEN is set server-side, append ?token=.
 */
import { useState, useEffect, useCallback } from 'react';
import {
  View, Text, ScrollView, ActivityIndicator, TouchableOpacity,
  StyleSheet, SafeAreaView, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import api from '../src/utils/apiClient';
import { C, S, R } from '../src/theme/deluxe';

type Overview = {
  generated_at: string;
  kpis: { gmv_usd: number; paid_transactions: number; active_listings: number; live_tournaments: number; creators: number; games: number };
  counts: Record<string, number>;
  recent_transactions: any[];
  recent_listings: any[];
};

function KpiTile({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <View style={styles.kpi} testID={`ops-kpi-${label.toLowerCase().replace(/\s/g, '-')}`}>
      <Text style={[styles.kpiValue, accent ? { color: accent } : null]}>{value}</Text>
      <Text style={styles.kpiLabel}>{label}</Text>
    </View>
  );
}

export default function Ops() {
  const router = useRouter();
  const [data, setData] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    const r = await api.get<Overview>('/api/admin/ops/overview', { timeoutMs: 12000 });
    if (r.ok && r.data) setData(r.data);
    setLoading(false); setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <SafeAreaView style={styles.safe} testID="ops-screen">
      <View style={styles.header}>
        <TouchableOpacity testID="ops-back" onPress={() => router.back()} style={styles.backBtn}><Text style={styles.backTxt}>‹ Back</Text></TouchableOpacity>
        <Text style={styles.title}>🛰️ Ops Console</Text>
      </View>
      {loading ? <ActivityIndicator color={C.brand} style={{ marginTop: S.xxl }} /> : (
        <ScrollView
          contentContainerStyle={{ padding: S.lg, paddingBottom: S.xxxl }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={C.brand} />}
        >
          {data ? (
            <>
              <View style={styles.kpiGrid}>
                <KpiTile label="GMV" value={`$${(data.kpis.gmv_usd || 0).toFixed(2)}`} accent={C.success} />
                <KpiTile label="Paid Txns" value={`${data.kpis.paid_transactions}`} accent={C.brand2} />
                <KpiTile label="Active Listings" value={`${data.kpis.active_listings}`} accent={C.info} />
                <KpiTile label="Live Cups" value={`${data.kpis.live_tournaments}`} accent={C.gold} />
                <KpiTile label="Creators" value={`${data.kpis.creators}`} accent={C.brand2} />
                <KpiTile label="Games" value={`${data.kpis.games}`} accent={C.warning} />
              </View>

              <Text style={styles.section}>RECENT TRANSACTIONS</Text>
              {data.recent_transactions.length === 0 ? (
                <Text style={styles.empty}>No transactions yet.</Text>
              ) : data.recent_transactions.map((t, i) => (
                <View key={i} testID={`ops-tx-${i}`} style={styles.row}>
                  <View style={[styles.dot, { backgroundColor: t.payment_status === 'paid' ? C.success : t.payment_status === 'initiated' ? C.warning : C.textMute }]} />
                  <View style={{ flex: 1, marginLeft: S.md, minWidth: 0 }}>
                    <Text style={styles.rowTitle} numberOfLines={1}>${(t.amount || 0).toFixed(2)} · {t.payment_status}</Text>
                    <Text style={styles.rowSub} numberOfLines={1}>{t.session_id || '—'}</Text>
                  </View>
                </View>
              ))}

              <Text style={styles.section}>COLLECTION COUNTS</Text>
              <View style={styles.countGrid}>
                {Object.entries(data.counts).map(([k, v]) => (
                  <View key={k} style={styles.countTile} testID={`ops-count-${k}`}>
                    <Text style={styles.countVal}>{v}</Text>
                    <Text style={styles.countKey} numberOfLines={1}>{k.replace(/_/g, ' ')}</Text>
                  </View>
                ))}
              </View>
              <Text style={styles.ts}>updated {new Date(data.generated_at).toLocaleTimeString()}</Text>
            </>
          ) : <Text style={styles.empty}>Couldn’t load ops data.</Text>}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: S.lg, paddingVertical: S.md, borderBottomWidth: 1, borderBottomColor: C.border },
  backBtn: { paddingVertical: 6, paddingRight: S.md }, backTxt: { color: C.textMute, fontSize: 15, fontWeight: '600' },
  title: { flex: 1, color: C.text, fontSize: 20, fontWeight: '800', letterSpacing: 0.3 },
  kpiGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: S.md },
  kpi: { width: '47%', flexGrow: 1, backgroundColor: C.surface, borderRadius: R.lg, borderWidth: 1, borderColor: C.border, paddingVertical: S.lg, paddingHorizontal: S.lg },
  kpiValue: { color: C.text, fontSize: 22, fontWeight: '800', letterSpacing: 0.5 },
  kpiLabel: { color: C.textMute, fontSize: 11, fontWeight: '700', letterSpacing: 1.1, marginTop: 4, textTransform: 'uppercase' },
  section: { color: C.textDim, fontSize: 13, fontWeight: '800', letterSpacing: 1.5, marginTop: S.xl, marginBottom: S.md },
  empty: { color: C.textMute, textAlign: 'center', marginVertical: S.lg },
  row: { flexDirection: 'row', alignItems: 'center', backgroundColor: C.surface, borderRadius: R.md, padding: S.md, marginBottom: S.sm, borderWidth: 1, borderColor: C.border },
  dot: { width: 10, height: 10, borderRadius: 5 },
  rowTitle: { color: C.text, fontSize: 14, fontWeight: '700' }, rowSub: { color: C.textMute, fontSize: 11, marginTop: 2 },
  countGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: S.sm },
  countTile: { width: '31%', flexGrow: 1, backgroundColor: C.surface2, borderRadius: R.md, padding: S.md, borderWidth: 1, borderColor: C.border },
  countVal: { color: C.brand2, fontSize: 18, fontWeight: '800' },
  countKey: { color: C.textMute, fontSize: 10, marginTop: 2, textTransform: 'capitalize' },
  ts: { color: C.textMute, fontSize: 11, textAlign: 'center', marginTop: S.lg },
});
