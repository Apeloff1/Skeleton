import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';

import {
  AuditEntry,
  ControlPlaneStatus,
  PendingOperationResponse,
  getPendingProductOperations,
  getProductAuditHistory,
  getProductControlStatus,
} from '../src/product/productControlClient';

export default function ControlPlaneRoute() {
  const router = useRouter();
  const [token, setToken] = useState('');
  const [status, setStatus] = useState<ControlPlaneStatus | null>(null);
  const [pending, setPending] = useState<PendingOperationResponse | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    const cleanToken = token.trim();
    const [statusResult, pendingResult, auditResult] = await Promise.all([
      getProductControlStatus(cleanToken),
      getPendingProductOperations(cleanToken),
      getProductAuditHistory(cleanToken, 25),
    ]);
    if (!statusResult.ok || !statusResult.data) {
      setError(statusResult.error || `Status unavailable (${statusResult.status})`);
    } else {
      setStatus(statusResult.data);
    }
    if (pendingResult.ok && pendingResult.data) setPending(pendingResult.data);
    if (auditResult.ok && auditResult.data) setAudit(auditResult.data.entries);
    setLoading(false);
  }, [token]);

  useEffect(() => { void refresh(); }, []); // first load only; token refresh is explicit

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView
        contentContainerStyle={styles.page}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={refresh} />}
      >
        <TouchableOpacity onPress={() => router.back()}><Text style={styles.back}>‹ Product</Text></TouchableOpacity>
        <View style={styles.hero}>
          <Text style={styles.eyebrow}>OPERATE · CONTROL PLANE</Text>
          <Text style={styles.title}>Governed runtime</Text>
          <Text style={styles.description}>Policy, durable admissions, verified audit continuity and queue pressure for the canonical product surface.</Text>
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>Ops token (when configured)</Text>
          <TextInput value={token} onChangeText={setToken} secureTextEntry autoCapitalize="none" style={styles.input} />
          <TouchableOpacity style={styles.refreshButton} onPress={refresh} disabled={loading}>
            {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.refreshText}>Refresh control plane</Text>}
          </TouchableOpacity>
        </View>

        {error ? <View style={styles.errorCard}><Text style={styles.errorText}>{error}</Text></View> : null}

        {status ? (
          <>
            <View style={styles.metrics}>
              <Metric label="Pending" value={String(status.operations.pending_operations)} />
              <Metric label="Capacity" value={String(status.operations.outbox_capacity_remaining)} />
              <Metric label="Audit seq" value={String(status.operations.audit_sequence)} />
              <Metric label="Policy" value={`v${status.policy_version}`} />
            </View>
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Governance</Text>
              <Text style={styles.muted}>{status.governance.charters.length} charters · {status.governance.edicts.length} edicts</Text>
              {status.governance.charters.map((charter) => (
                <View key={charter.id} style={styles.row}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowTitle}>{charter.domain}</Text>
                    <Text style={styles.muted}>{charter.rules.length} rules · {charter.amendments} amendments</Text>
                  </View>
                </View>
              ))}
            </View>
          </>
        ) : null}

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Pending operations</Text>
          <Text style={styles.muted}>{pending?.count ?? 0} durable intents waiting for an exact executor binding.</Text>
          {(pending?.operations ?? []).map((operation) => (
            <View key={operation.operation_id} style={styles.row}>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowTitle}>{operation.action}</Text>
                <Text style={styles.muted}>{operation.capability_id} · queue #{operation.outbox_seq}</Text>
                <Text style={styles.mono}>{operation.operation_id.slice(0, 20)}…</Text>
              </View>
            </View>
          ))}
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Verified audit history</Text>
          <Text style={styles.muted}>{audit.length} newest entries, re-verified against the on-disk hash chain on every read.</Text>
          {[...audit].reverse().map((entry) => (
            <View key={entry.seq} style={styles.row}>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowTitle}>#{entry.seq} · {entry.kind}</Text>
                <Text style={styles.muted}>{entry.principal} · {entry.route}</Text>
                <Text style={styles.mono}>{entry.hash.slice(0, 24)}…</Text>
              </View>
            </View>
          ))}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <View style={styles.metric}><Text style={styles.metricValue}>{value}</Text><Text style={styles.metricLabel}>{label}</Text></View>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#080A0F' },
  page: { padding: 18, paddingBottom: 48, gap: 14 },
  back: { color: '#99A7FF', fontWeight: '800', paddingVertical: 5 },
  hero: { borderWidth: 1, borderColor: '#232838', borderRadius: 22, padding: 20, backgroundColor: '#0D111A' },
  eyebrow: { color: '#8BD3A7', fontSize: 10, fontWeight: '900', letterSpacing: 1.8 },
  title: { color: '#F8FAFC', fontSize: 28, fontWeight: '900', marginTop: 7 },
  description: { color: '#AAB3C5', lineHeight: 20, marginTop: 7 },
  field: { gap: 7 },
  label: { color: '#8B96A8', fontSize: 11, fontWeight: '800' },
  input: { color: '#F8FAFC', borderWidth: 1, borderColor: '#283044', borderRadius: 12, backgroundColor: '#0F141F', paddingHorizontal: 12, paddingVertical: 11 },
  refreshButton: { minHeight: 46, borderRadius: 12, backgroundColor: '#5364D8', alignItems: 'center', justifyContent: 'center' },
  refreshText: { color: '#fff', fontWeight: '900' },
  errorCard: { borderWidth: 1, borderColor: '#5A2D36', borderRadius: 12, backgroundColor: '#241116', padding: 13 },
  errorText: { color: '#F3A7B5', fontSize: 12 },
  metrics: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  metric: { minWidth: '47%', flexGrow: 1, borderRadius: 14, backgroundColor: '#101724', padding: 13 },
  metricValue: { color: '#F8FAFC', fontSize: 18, fontWeight: '900' },
  metricLabel: { color: '#748096', fontSize: 10, textTransform: 'uppercase', marginTop: 3 },
  card: { borderWidth: 1, borderColor: '#202737', borderRadius: 17, backgroundColor: '#0F141F', padding: 15, gap: 9 },
  cardTitle: { color: '#F1F5F9', fontSize: 15, fontWeight: '900' },
  row: { borderTopWidth: 1, borderTopColor: '#1E2635', paddingTop: 10, flexDirection: 'row' },
  rowTitle: { color: '#DDE5F0', fontSize: 12, fontWeight: '850' },
  muted: { color: '#77849A', fontSize: 10, lineHeight: 15 },
  mono: { color: '#8F9DFF', fontSize: 9, fontFamily: 'monospace', marginTop: 4 },
});
