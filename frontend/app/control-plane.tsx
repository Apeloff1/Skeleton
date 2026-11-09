import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, RefreshControl, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { useRouter } from 'expo-router';
import { AuditEntry, ControlPlaneDeploymentPreflight, ControlPlaneStatus, ExecutionReceipt, PendingOperationResponse, PreparedDeployment, executePendingProductOperations, executeProductDeployment, executeProductOperation, getDeploymentPreflight, getExecutionReceipts, getPendingProductOperations, getProductAuditHistory, getProductControlStatus, prepareProductDeployment } from '../src/product/productControlClient';

export default function ControlPlaneRoute() {
  const router = useRouter();
  const [token, setToken] = useState('');
  const [status, setStatus] = useState<ControlPlaneStatus | null>(null);
  const [preflight, setPreflight] = useState<ControlPlaneDeploymentPreflight | null>(null);
  const [pending, setPending] = useState<PendingOperationResponse | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [receipts, setReceipts] = useState<ExecutionReceipt[]>([]);
  const [loading, setLoading] = useState(true);
  const [executing, setExecuting] = useState<number | 'all' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deployTarget, setDeployTarget] = useState('skeleton');
  const [deployEnvironment, setDeployEnvironment] = useState<'development' | 'staging' | 'production'>('staging');
  const [deployArtifact, setDeployArtifact] = useState('');
  const [prepared, setPrepared] = useState<PreparedDeployment | null>(null);
  const [deployBusy, setDeployBusy] = useState<'prepare' | 'execute' | null>(null);
  const [deployResult, setDeployResult] = useState<string>('');

  const refresh = useCallback(async () => {
    setLoading(true); setError(null); const cleanToken = token.trim();
    const [statusResult, preflightResult, pendingResult, auditResult, receiptResult] = await Promise.all([
      getProductControlStatus(cleanToken), getDeploymentPreflight(cleanToken, 3), getPendingProductOperations(cleanToken), getProductAuditHistory(cleanToken, 25), getExecutionReceipts(cleanToken, 25),
    ]);
    const failures = [statusResult, preflightResult, pendingResult, auditResult, receiptResult].filter((item) => !item.ok);
    if (failures.length) setError(failures[0].error || `${failures.length} control-plane source(s) unavailable`);
    if (statusResult.ok && statusResult.data) setStatus(statusResult.data); else setStatus(null);
    if (preflightResult.ok && preflightResult.data) setPreflight(preflightResult.data); else setPreflight(null);
    if (pendingResult.ok && pendingResult.data) setPending(pendingResult.data); else setPending(null);
    if (auditResult.ok && auditResult.data) setAudit(auditResult.data.entries); else setAudit([]);
    if (receiptResult.ok && receiptResult.data) setReceipts(receiptResult.data.receipts); else setReceipts([]);
    setLoading(false);
  }, [token]);
  useEffect(() => { void refresh(); }, []);

  const executeOne = useCallback(async (seq: number) => {
    setExecuting(seq); setError(null); const result = await executeProductOperation(seq, token.trim());
    if (!result.ok) setError(result.error || 'Execution failed'); await refresh(); setExecuting(null);
  }, [refresh, token]);
  const executeAll = useCallback(async () => {
    setExecuting('all'); setError(null); const result = await executePendingProductOperations(token.trim(), 64);
    if (!result.ok) setError(result.error || 'Batch execution failed'); await refresh(); setExecuting(null);
  }, [refresh, token]);
  const prepareDeployment = useCallback(async () => {
    const target = deployTarget.trim(); const artifact = deployArtifact.trim();
    if (!target || !artifact) { setError('Deployment target and immutable artifact reference are required.'); return; }
    setDeployBusy('prepare'); setError(null); setDeployResult(''); setPrepared(null);
    const result = await prepareProductDeployment({ target, environment: deployEnvironment, artifact }, token.trim());
    if (result.ok && result.data) { setPrepared(result.data); setDeployResult('Authorization prepared. Review the bound roots before execution.'); }
    else setError(result.error || 'Deployment preparation was rejected.');
    setDeployBusy(null);
  }, [deployArtifact, deployEnvironment, deployTarget, token]);
  const runDeployment = useCallback(async () => {
    if (!prepared) return;
    setDeployBusy('execute'); setError(null); setDeployResult('');
    const result = await executeProductDeployment(prepared.authorization.id, prepared.plan, token.trim());
    if (result.ok && result.data) {
      setDeployResult(`Release ${result.data.release.release_id} activated at sequence ${result.data.release.sequence}.`);
      setPrepared(null); await refresh();
    } else setError(result.error || 'Deployment execution was rejected.');
    setDeployBusy(null);
  }, [prepared, refresh, token]);
  const blocked = status?.readiness.actions.filter((item) => item.state !== 'native_ready') ?? [];

  return <SafeAreaView style={styles.safe}><ScrollView contentContainerStyle={styles.page} refreshControl={<RefreshControl refreshing={loading} onRefresh={refresh} />}>
    <TouchableOpacity onPress={() => router.back()}><Text style={styles.back}>‹ Product</Text></TouchableOpacity>
    <View style={styles.hero}><Text style={styles.eyebrow}>OPERATE · SELF-VERIFYING CONTROL PLANE</Text><Text style={styles.title}>Governed execution fabric</Text><Text style={styles.description}>Evidence-derived lifecycle, stable-root deployment preflight, quorum finality, replay-safe native executors, immutable receipts and content-addressed provenance.</Text></View>
    <View style={styles.field}><Text style={styles.label}>Ops token (when configured)</Text><TextInput value={token} onChangeText={setToken} secureTextEntry autoCapitalize="none" style={styles.input} /><TouchableOpacity style={styles.refreshButton} onPress={refresh} disabled={loading}>{loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.refreshText}>Re-evaluate evidence</Text>}</TouchableOpacity></View>
    {error ? <View style={styles.errorCard}><Text style={styles.errorText}>{error}</Text></View> : null}

    {status ? <>
      <View style={styles.metrics}><Metric label="Deploy" value={preflight ? (preflight.allowed ? 'READY' : 'BLOCKED') : 'UNKNOWN'} /><Metric label="Posture" value={status.assurance.posture.toUpperCase()} /><Metric label="Ready" value={`${status.readiness.ready_pct}%`} /><Metric label="Evidence gaps" value={String(status.lifecycle.evidence_gaps)} /></View>
      {preflight ? <View style={[styles.card, preflight.allowed ? styles.healthyCard : styles.blockedCard]}>
        <Text style={styles.cardTitle}>Deployment preflight</Text>
        <Text style={styles.muted}>A deployment is authorized only against a stable whole-system root. Trust integrity and required quorum finality fail closed.</Text>
        <View style={styles.row}><View style={{ flex: 1 }}><Text style={preflight.allowed ? styles.good : styles.danger}>{preflight.allowed ? 'DEPLOY READY' : 'DEPLOY BLOCKED'} · {preflight.report.posture}</Text><Text style={styles.muted}>snapshot {preflight.stable ? 'stable' : 'unstable'} · {preflight.attempts} attempt(s) · self-verified {preflight.self_verified ? 'yes' : 'no'}</Text></View></View>
        <View style={styles.row}><View style={{ flex: 1 }}><Text style={styles.rowTitle}>Epistemic finality</Text><Text style={preflight.report.finality_satisfied ? styles.good : preflight.report.finality_required ? styles.danger : styles.warn}>{preflight.report.finality_satisfied ? 'FINALIZED' : preflight.report.finality_required ? 'REQUIRED · MISSING' : 'PROVISIONAL · ALLOWED'}</Text></View></View>
        {preflight.report.blockers.map((item) => <View key={`block-${item.id}`} style={styles.row}><View style={{ flex: 1 }}><Text style={styles.danger}>BLOCK · {item.id}</Text><Text style={styles.muted}>{item.detail}</Text></View></View>)}
        {preflight.report.warnings.map((item) => <View key={`warn-${item.id}`} style={styles.row}><View style={{ flex: 1 }}><Text style={styles.warn}>WARN · {item.id}</Text><Text style={styles.muted}>{item.detail}</Text></View></View>)}
        {preflight.unstable_reason ? <Text style={styles.danger}>{preflight.unstable_reason}</Text> : null}
        <Text style={styles.mono}>system root {preflight.report.system_root_sha256}</Text>
        <Text style={styles.mono}>preflight sha256 {preflight.attestation_sha256}</Text>
      </View> : null}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Governed deployment</Text>
        <Text style={styles.muted}>Prepare creates a short-lived authorization bound to the current whole-system root, plan and preflight. Execution consumes that authorization exactly once.</Text>
        <TextInput value={deployTarget} onChangeText={(value) => { setDeployTarget(value); setPrepared(null); }} placeholder="target" placeholderTextColor="#566176" autoCapitalize="none" style={styles.input} />
        <TextInput value={deployArtifact} onChangeText={(value) => { setDeployArtifact(value); setPrepared(null); }} placeholder="immutable artifact digest or reference" placeholderTextColor="#566176" autoCapitalize="none" style={styles.input} />
        <View style={styles.environmentRow}>{(['development', 'staging', 'production'] as const).map((environment) => <TouchableOpacity key={environment} style={[styles.environmentButton, deployEnvironment === environment && styles.environmentActive]} onPress={() => { setDeployEnvironment(environment); setPrepared(null); }} disabled={deployBusy !== null}><Text style={styles.environmentText}>{environment}</Text></TouchableOpacity>)}</View>
        <TouchableOpacity style={styles.refreshButton} onPress={prepareDeployment} disabled={deployBusy !== null || !preflight?.allowed}>{deployBusy === 'prepare' ? <ActivityIndicator color="#fff" /> : <Text style={styles.refreshText}>{preflight?.allowed ? 'Prepare authorization' : 'Preflight blocks preparation'}</Text>}</TouchableOpacity>
        {prepared ? <View style={styles.authorizationBox}><Text style={styles.good}>AUTHORIZATION READY</Text><Text style={styles.mono}>id {prepared.authorization.id}</Text><Text style={styles.mono}>root {prepared.authorization.system_root_sha256}</Text><Text style={styles.mono}>expires {prepared.authorization.expires_at}</Text><TouchableOpacity style={styles.executeDeployButton} onPress={runDeployment} disabled={deployBusy !== null}>{deployBusy === 'execute' ? <ActivityIndicator color="#fff" /> : <Text style={styles.refreshText}>Execute once</Text>}</TouchableOpacity></View> : null}
        {deployResult ? <Text accessibilityRole="alert" style={styles.good}>{deployResult}</Text> : null}
      </View>
      <View style={[styles.card, status.assurance.posture === 'blocked' ? styles.blockedCard : status.assurance.posture === 'healthy' ? styles.healthyCard : undefined]}>
        <Text style={styles.cardTitle}>System assurance attestation</Text><Text style={styles.muted}>Hard invariants dominate posture. Readiness—not raw binding count—is the convergence signal.</Text>
        {status.assurance.invariants.map((item) => <View key={item.id} style={styles.row}><View style={{ flex: 1 }}><Text style={item.passed ? styles.good : item.severity === 'hard' ? styles.danger : styles.warn}>{item.passed ? 'PASS' : item.severity === 'hard' ? 'HARD FAIL' : 'WARN'} · {item.id}</Text><Text style={styles.muted}>{item.detail}</Text></View></View>)}
        <Text style={styles.mono}>assurance sha256 {status.assurance.attestation_sha256}</Text>
      </View>
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Whole-system root</Text><Text style={styles.muted}>One deploy-comparable identity over independent evidence domains. A changed root can be localized by component digest.</Text>
        <Text style={styles.rootHash}>{status.system_root.root_sha256}</Text>
        {status.system_root.components.map((item) => <View key={item.name} style={styles.row}><View style={{ flex: 1 }}><Text style={styles.rowTitle}>{item.name}</Text><Text style={styles.mono}>{item.sha256}</Text></View></View>)}
      </View>
      <View style={styles.card}><Text style={styles.cardTitle}>Evidence-backed action readiness</Text><Text style={styles.muted}>{status.readiness.ready_actions}/{status.readiness.canonical_actions} native-ready · {status.readiness.governed_unbound} governed/unbound · {status.readiness.unsafe_actions} unsafe · {status.readiness.policy_gaps} policy gaps.</Text><Text style={styles.mono}>readiness sha256 {status.readiness.attestation_sha256}</Text>{blocked.map((item) => <View key={`${item.capability_id}:${item.action}`} style={styles.row}><View style={{ flex: 1 }}><Text style={styles.rowTitle}>{item.action}</Text><Text style={styles.muted}>{item.capability_id} · {item.state}</Text><Text style={item.state === 'governed_unbound' ? styles.warn : styles.danger}>{item.blockers.join(' · ') || 'no blockers'}</Text></View></View>)}</View>
      <View style={styles.card}><Text style={styles.cardTitle}>Native executor contracts</Text><Text style={styles.muted}>{status.executors.bindings.length} exact bindings · raw {status.executors.coverage.coverage_pct}% · ready {status.readiness.ready_pct}%.</Text>{status.executors.bindings.map((binding) => <View key={`${binding.capability_id}:${binding.action}`} style={styles.row}><View style={{ flex: 1 }}><Text style={styles.rowTitle}>{binding.action}</Text><Text style={styles.muted}>{binding.capability_id} · {binding.effect_class} · contract v{binding.version}</Text><Text style={binding.replay_safe ? styles.good : styles.danger}>{binding.replay_safe ? 'replay-safe' : 'non-replay-safe'}</Text></View></View>)}</View>
      <View style={styles.card}><Text style={styles.cardTitle}>Governance</Text><Text style={styles.muted}>{status.governance.charters.length} charters · {status.governance.edicts.length} edicts · policy v{status.policy_version}</Text>{status.governance.charters.map((charter) => <View key={charter.id} style={styles.row}><View style={{ flex: 1 }}><Text style={styles.rowTitle}>{charter.domain}</Text><Text style={styles.muted}>{charter.rules.length} rules · {charter.amendments} amendments</Text></View></View>)}</View>
    </> : null}

    <View style={styles.card}><View style={styles.sectionHead}><View style={{ flex: 1 }}><Text style={styles.cardTitle}>Pending operations</Text><Text style={styles.muted}>{pending?.count ?? 0} durable intents.</Text></View><TouchableOpacity style={styles.smallButton} onPress={executeAll} disabled={executing !== null}><Text style={styles.smallButtonText}>{executing === 'all' ? 'Running…' : 'Run ready'}</Text></TouchableOpacity></View>{(pending?.operations ?? []).map((operation) => <View key={operation.operation_id} style={styles.row}><View style={{ flex: 1 }}><Text style={styles.rowTitle}>{operation.action}</Text><Text style={styles.muted}>{operation.capability_id} · queue #{operation.outbox_seq}</Text><Text style={operation.executor_bound ? styles.good : styles.warn}>{operation.executor_bound ? 'native executor bound' : 'unbound · remains durable'}</Text><Text style={styles.mono}>{operation.operation_id.slice(0, 20)}…</Text></View>{operation.executor_bound ? <TouchableOpacity style={styles.execButton} onPress={() => executeOne(operation.outbox_seq)} disabled={executing !== null}><Text style={styles.smallButtonText}>{executing === operation.outbox_seq ? '…' : 'Execute'}</Text></TouchableOpacity> : null}</View>)}</View>
    <View style={styles.card}><Text style={styles.cardTitle}>Durable execution proofs</Text><Text style={styles.muted}>{receipts.length} newest compact receipts; payloads live in verified CAS.</Text>{receipts.map((receipt) => <View key={receipt.operation_id} style={styles.row}><View style={{ flex: 1 }}><Text style={styles.rowTitle}>{receipt.action}</Text><Text style={styles.muted}>{receipt.executor} v{receipt.executor_version} · {receipt.effect_class} · {receipt.replay_safe ? 'replay-safe' : 'not replay-safe'}</Text><Text style={styles.muted}>result {String(receipt.result_summary.bytes ?? 0)} B · artifact {receipt.result_artifact_id.slice(0, 12)}…</Text><Text style={styles.mono}>sha256 {receipt.result_sha256.slice(0, 24)}…</Text></View></View>)}</View>
    <View style={styles.card}><Text style={styles.cardTitle}>Verified audit history</Text><Text style={styles.muted}>{audit.length} newest entries, re-verified against the append-only hash chain.</Text>{[...audit].reverse().map((entry) => <View key={entry.seq} style={styles.row}><View style={{ flex: 1 }}><Text style={styles.rowTitle}>#{entry.seq} · {entry.kind}</Text><Text style={styles.muted}>{entry.principal} · {entry.route}</Text><Text style={styles.mono}>{entry.hash.slice(0, 24)}…</Text></View></View>)}</View>
  </ScrollView></SafeAreaView>;
}
function Metric({ label, value }: { label: string; value: string }) { return <View style={styles.metric}><Text style={styles.metricValue}>{value}</Text><Text style={styles.metricLabel}>{label}</Text></View>; }
const styles = StyleSheet.create({ safe: { flex: 1, backgroundColor: '#080A0F' }, page: { padding: 18, paddingBottom: 48, gap: 14 }, back: { color: '#99A7FF', fontWeight: '800', paddingVertical: 5 }, hero: { borderWidth: 1, borderColor: '#232838', borderRadius: 22, padding: 20, backgroundColor: '#0D111A' }, eyebrow: { color: '#8BD3A7', fontSize: 10, fontWeight: '900', letterSpacing: 1.8 }, title: { color: '#F8FAFC', fontSize: 28, fontWeight: '900', marginTop: 7 }, description: { color: '#AAB3C5', lineHeight: 20, marginTop: 7 }, field: { gap: 7 }, label: { color: '#8B96A8', fontSize: 11, fontWeight: '800' }, input: { color: '#F8FAFC', borderWidth: 1, borderColor: '#283044', borderRadius: 12, backgroundColor: '#0F141F', paddingHorizontal: 12, paddingVertical: 11 }, refreshButton: { minHeight: 46, borderRadius: 12, backgroundColor: '#5364D8', alignItems: 'center', justifyContent: 'center' }, refreshText: { color: '#fff', fontWeight: '900' }, errorCard: { borderWidth: 1, borderColor: '#5A2D36', borderRadius: 12, backgroundColor: '#241116', padding: 13 }, errorText: { color: '#F3A7B5', fontSize: 12 }, metrics: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 }, metric: { minWidth: '47%', flexGrow: 1, borderRadius: 14, backgroundColor: '#101724', padding: 13 }, metricValue: { color: '#F8FAFC', fontSize: 18, fontWeight: '900' }, metricLabel: { color: '#748096', fontSize: 10, textTransform: 'uppercase', marginTop: 3 }, card: { borderWidth: 1, borderColor: '#202737', borderRadius: 17, backgroundColor: '#0F141F', padding: 15, gap: 9 }, healthyCard: { borderColor: '#274D3A' }, blockedCard: { borderColor: '#65323B' }, cardTitle: { color: '#F1F5F9', fontSize: 15, fontWeight: '900' }, sectionHead: { flexDirection: 'row', gap: 10, alignItems: 'center' }, row: { borderTopWidth: 1, borderTopColor: '#1E2635', paddingTop: 10, flexDirection: 'row', gap: 10, alignItems: 'center' }, rowTitle: { color: '#DDE5F0', fontSize: 12, fontWeight: '800' }, muted: { color: '#77849A', fontSize: 10, lineHeight: 15 }, mono: { color: '#8F9DFF', fontSize: 9, fontFamily: 'monospace', marginTop: 4 }, rootHash: { color: '#B4C0FF', fontSize: 10, fontFamily: 'monospace', lineHeight: 15 }, good: { color: '#7FD9A1', fontSize: 9, fontWeight: '800', marginTop: 3 }, warn: { color: '#E7BA74', fontSize: 9, fontWeight: '800', marginTop: 3 }, danger: { color: '#F08A9A', fontSize: 9, fontWeight: '900', marginTop: 3 }, smallButton: { backgroundColor: '#25325E', borderRadius: 9, paddingHorizontal: 11, paddingVertical: 8 }, execButton: { backgroundColor: '#304B3D', borderRadius: 9, paddingHorizontal: 10, paddingVertical: 8 }, smallButtonText: { color: '#F7FAFC', fontSize: 10, fontWeight: '900' }, environmentRow: { flexDirection: 'row', gap: 6 }, environmentButton: { flex: 1, borderWidth: 1, borderColor: '#283044', borderRadius: 9, paddingVertical: 9, alignItems: 'center' }, environmentActive: { borderColor: '#8F9DFF', backgroundColor: '#202A50' }, environmentText: { color: '#DDE5F0', fontSize: 10, fontWeight: '800' }, authorizationBox: { borderWidth: 1, borderColor: '#274D3A', borderRadius: 12, padding: 12, gap: 3 }, executeDeployButton: { marginTop: 8, minHeight: 44, borderRadius: 10, backgroundColor: '#2D6A49', alignItems: 'center', justifyContent: 'center' } });
