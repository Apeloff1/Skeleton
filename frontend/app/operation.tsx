import React, { useMemo, useState } from 'react';
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
import { admitProductOperation } from '../src/product/productControlClient';

export default function OperationRoute() {
  const router = useRouter();
  const params = useLocalSearchParams<{ capability?: string | string[]; action?: string | string[] }>();
  const capabilityId = Array.isArray(params.capability) ? params.capability[0] : params.capability;
  const actionId = Array.isArray(params.action) ? params.action[0] : params.action;
  const capability = useMemo(() => capabilityId ? capabilityById(capabilityId) : undefined, [capabilityId]);
  const action = useMemo(() => capabilityId && actionId ? actionById(capabilityId, actionId) : undefined, [capabilityId, actionId]);
  const [principal, setPrincipal] = useState('product-user');
  const [weight, setWeight] = useState('0');
  const [payload, setPayload] = useState('{}');
  const [token, setToken] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  if (!capability || !action) {
    return <SafeAreaView style={styles.safe}><View style={styles.center}><Text style={styles.title}>Unknown operation</Text></View></SafeAreaView>;
  }

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
    setSubmitting(true);
    setResult(null);
    const response = await admitProductOperation({
      capability_id: capability.id,
      domain: capability.id,
      action: action.operation,
      principal: principal.trim() || 'product-user',
      actor_weight: actorWeight,
      payload: decoded,
    }, token.trim());
    setSubmitting(false);
    if (!response.ok || !response.data) {
      setResult(response.error || `Admission failed (${response.status})`);
      return;
    }
    setResult(`Admitted ${response.data.operation_id}\nQueue #${response.data.outbox_seq}\nAudit ${response.data.audit_hash.slice(0, 16)}…`);
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
        </View>
        <Field label="Principal" value={principal} onChangeText={setPrincipal} />
        <Field label="Actor weight" value={weight} onChangeText={setWeight} keyboardType="number-pad" />
        <View style={styles.field}>
          <Text style={styles.label}>Payload JSON</Text>
          <TextInput value={payload} onChangeText={setPayload} multiline autoCapitalize="none" style={[styles.input, styles.payload]} />
        </View>
        <Field label="Ops token (when configured)" value={token} onChangeText={setToken} secureTextEntry />
        <TouchableOpacity style={styles.submit} onPress={submit} disabled={submitting}>
          {submitting ? <ActivityIndicator color="#fff" /> : <Text style={styles.submitText}>Submit governed operation</Text>}
        </TouchableOpacity>
        {result ? <View style={styles.result}><Text style={styles.resultText}>{result}</Text></View> : null}
        <Text style={styles.hint}>Admission is fail-closed. The backend charter must explicitly permit this capability domain and operation.</Text>
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
  field: { gap: 6 },
  label: { color: '#8B96A8', fontSize: 11, fontWeight: '800' },
  input: { color: '#F8FAFC', borderWidth: 1, borderColor: '#283044', borderRadius: 12, backgroundColor: '#0F141F', paddingHorizontal: 12, paddingVertical: 11 },
  payload: { minHeight: 120, textAlignVertical: 'top', fontFamily: 'monospace' },
  submit: { minHeight: 50, borderRadius: 13, backgroundColor: '#6D5CE7', alignItems: 'center', justifyContent: 'center', marginTop: 4 },
  submitText: { color: '#fff', fontWeight: '900' },
  result: { borderWidth: 1, borderColor: '#2A3850', borderRadius: 12, backgroundColor: '#101827', padding: 13 },
  resultText: { color: '#B7C2D5', fontFamily: 'monospace', fontSize: 11, lineHeight: 17 },
  hint: { color: '#69758A', fontSize: 10, lineHeight: 16 },
});
