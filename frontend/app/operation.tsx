import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';

import { actionById, capabilityById } from '../src/product/productCatalog';
import {
  admitProductOperation,
  executeProductOperation,
  getExecutionResult,
  getOperationLifecycle,
  getPendingProductOperations,
  OperationAdmission,
  OperationLifecycle,
} from '../src/product/productControlClient';
import { resolveCreatorPrincipal } from '../src/product/creatorIdentity';

export default function OperationRoute() {
  const router = useRouter();
  const params = useLocalSearchParams<{ capability?: string | string[]; action?: string | string[] }>();
  const capabilityId = Array.isArray(params.capability) ? params.capability[0] : params.capability;
  const actionId = Array.isArray(params.action) ? params.action[0] : params.action;
  const capability = useMemo(() => capabilityId ? capabilityById(capabilityId) : undefined, [capabilityId]);
  const action = useMemo(() => capabilityId && actionId ? actionById(capabilityId, actionId) : undefined, [capabilityId, actionId]);
  const [principal, setPrincipal] = useState('');
  const [weight, setWeight] = useState('0');
  const [payload, setPayload] = useState('{}');
  const [token, setToken] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [queueCount, setQueueCount] = useState<number | null>(null);
  const [admission, setAdmission] = useState<OperationAdmission | null>(null);
  const [lifecycle, setLifecycle] = useState<OperationLifecycle | null>(null);
  const [executionResult, setExecutionResult] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    let current = true;
    resolveCreatorPrincipal().then(value => { if (current) setPrincipal(value); }).catch(error => {
      if (current) setResult(error instanceof Error ? error.message : 'Sign in before submitting governed work.');
    });
    return () => { current = false; };
  }, []);

  // Deep links are untrusted: navigation-only entries must never be sent to
  // the governed operation admission endpoint.
  if (!capability || !action || typeof action.operation !== 'string') {
    return <SafeAreaView style={styles.safe}><View style={styles.center}><Text style={styles.title}>Unknown operation</Text></View></SafeAreaView>;
  }

  const observe = async (operation: OperationAdmission, cleanToken: string) => {
    const [life, output, pending] = await Promise.all([
      getOperationLifecycle(operation.operation_id, cleanToken),
      getExecutionResult(operation.operation_id, cleanToken),
      getPendingProductOperations(cleanToken),
    ]);
    setLifecycle(life.ok && life.data ? life.data : null);
    setExecutionResult(output.ok && output.data ? output.data : null);
    setQueueCount(pending.ok && pending.data ? pending.data.count : null);
  };

  const execute = async (operation: OperationAdmission, cleanToken: string) => {
    setSubmitting(true); setResult(null);
    const execution = await executeProductOperation(operation.outbox_seq, cleanToken);
    await observe(operation, cleanToken);
    setSubmitting(false);
    if (!execution.ok || !execution.data?.confirmed) {
      setResult(execution.error || 'Execution was not confirmed. The admitted intent remains durable and can be retried.');
      return;
    }
    setResult(`Confirmed ${operation.operation_id}\nQueue #${operation.outbox_seq}\nAudit ${operation.audit_hash.slice(0, 16)}…`);
  };

  const submit = async () => {
    if (submitting) return;
    let decoded: Record<string, unknown>;
    try {
      decoded = JSON.parse(payload);
      if (!decoded || Array.isArray(decoded) || typeof decoded !== 'object') throw new Error('payload');
    } catch {
      setResult('Payload must be a JSON object.');
      return;
    }
    const actorWeight = Number(weight);
    if (!Number.isFinite(actorWeight) || actorWeight < 0) {
      setResult('Actor weight must be a non-negative number.');
      return;
    }
    if (!principal) { setResult('Sign in before submitting governed work.'); return; }
    setSubmitting(true);
    setResult(null);
    const cleanToken = token.trim();
    const response = await admitProductOperation({
      capability_id: capability.id,
      domain: capability.id,
      action: action.operation,
      principal,
      actor_weight: actorWeight,
      payload: decoded,
    }, cleanToken);
    if (!response.ok || !response.data) {
      setSubmitting(false);
      setResult(response.error || `Admission failed (${response.status})`);
      return;
    }
    setAdmission(response.data);
    await execute(response.data, cleanToken);
  };

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
        <TouchableOpacity onPress={() => router.back()}><Text style={styles.back}>‹ {capability.title}</Text></TouchableOpacity>
        <View style={styles.hero}>
          <Text style={styles.eyebrow}>{capability.pillar.toUpperCase()} · GOVERNED</Text>
          <Text style={styles.title}>{action.title}</Text>
          <Text style={styles.description}>{action.description}</Text>
          <Text style={styles.operation}>{action.operation}</Text>
          {queueCount !== null ? <Text style={styles.queue}>Durable queue: {queueCount} pending</Text> : null}
        </View>
        <View style={styles.field}><Text style={styles.label}>Authenticated principal</Text><Text style={styles.identity}>{principal || 'Resolving signed-in account…'}</Text></View>
        <Field label="Actor weight" value={weight} onChangeText={setWeight} keyboardType="number-pad" />
        <View style={styles.field}>
          <Text style={styles.label}>Payload JSON</Text>
          <TextInput value={payload} onChangeText={setPayload} multiline autoCapitalize="none" style={[styles.input, styles.payload]} />
        </View>
        <Field label="Ops token (when configured)" value={token} onChangeText={setToken} secureTextEntry />
        <TouchableOpacity style={styles.submit} onPress={submit} disabled={submitting}>
          {submitting ? <ActivityIndicator color="#fff" /> : <Text style={styles.submitText}>Admit and execute governed operation</Text>}
        </TouchableOpacity>
        {admission && lifecycle?.pending_present ? <TouchableOpacity style={styles.retry} onPress={() => execute(admission, token.trim())} disabled={submitting}><Text style={styles.submitText}>Retry durable execution</Text></TouchableOpacity> : null}
        {result ? <View style={styles.result}><Text style={styles.resultText}>{result}</Text></View> : null}
        {lifecycle ? <View style={styles.result}><Text style={styles.lifecycle}>Lifecycle · {lifecycle.state} · {lifecycle.confidence} confidence</Text><Text style={styles.resultText}>Evidence {lifecycle.evidence_sha256}</Text>{lifecycle.anomalies.length ? <Text style={styles.error}>Anomalies: {lifecycle.anomalies.join(' · ')}</Text> : null}</View> : null}
        {executionResult ? <View style={styles.result}><Text style={styles.lifecycle}>Verified result</Text><Text selectable style={styles.resultText}>{JSON.stringify(executionResult, null, 2)}</Text></View> : null}
        <Text style={styles.hint}>Admission is durably journaled before execution. A failed execution remains recoverable; confirmed output is loaded from its verified result artifact.</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

function Field(props: any) {
  return <View style={styles.field}><Text style={styles.label}>{props.label}</Text><TextInput {...props} style={styles.input} autoCapitalize="none" /></View>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#080A0F' },
  page: { padding: 18, paddingBottom: 48, gap: 14 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  back: { color: '#99A7FF', fontWeight: '800', paddingVertical: 5 },
  hero: { borderWidth: 1, borderColor: '#232838', borderRadius: 22, padding: 20, backgroundColor: '#0D111A' },
  eyebrow: { color: '#8B9AFF', fontSize: 10, fontWeight: '900', letterSpacing: 1.8 },
  title: { color: '#F8FAFC', fontSize: 26, fontWeight: '900', marginTop: 7 },
  description: { color: '#AAB3C5', lineHeight: 20, marginTop: 7 },
  operation: { color: '#8F9DFF', fontFamily: 'monospace', fontSize: 11, marginTop: 14 },
  queue: { color: '#8BD3A7', fontSize: 10, fontWeight: '800', marginTop: 9 },
  field: { gap: 6 },
  label: { color: '#8B96A8', fontSize: 11, fontWeight: '800' },
  input: { color: '#F8FAFC', borderWidth: 1, borderColor: '#283044', borderRadius: 12, backgroundColor: '#0F141F', paddingHorizontal: 12, paddingVertical: 11 },
  identity: { color: '#C8D2E6', borderWidth: 1, borderColor: '#283044', borderRadius: 12, backgroundColor: '#0F141F', paddingHorizontal: 12, paddingVertical: 13 },
  payload: { minHeight: 120, textAlignVertical: 'top', fontFamily: 'monospace' },
  submit: { minHeight: 50, borderRadius: 13, backgroundColor: '#6D5CE7', alignItems: 'center', justifyContent: 'center', marginTop: 4 },
  retry: { minHeight: 46, borderRadius: 13, backgroundColor: '#304B3D', alignItems: 'center', justifyContent: 'center' },
  submitText: { color: '#fff', fontWeight: '900' },
  result: { borderWidth: 1, borderColor: '#2A3850', borderRadius: 12, backgroundColor: '#101827', padding: 13 },
  resultText: { color: '#B7C2D5', fontFamily: 'monospace', fontSize: 11, lineHeight: 17 },
  lifecycle: { color: '#8BD3A7', fontSize: 12, fontWeight: '900', marginBottom: 6 },
  error: { color: '#F3A7B5', fontSize: 11, marginTop: 6 },
  hint: { color: '#69758A', fontSize: 10, lineHeight: 16 },
});
