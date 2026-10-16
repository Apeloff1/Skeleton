/** Server-observed model inventory shared with Jeeves chat. No synthetic readiness. */
import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, RefreshControl, SafeAreaView, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useRouter } from 'expo-router';
import StudioLoginGate from '../src/auth/StudioLoginGate';
import { getChatReadiness, chatReadinessMessage, type ChatReadiness } from '../src/product/chatSessionClient';

const WORKFLOWS = [
  { title: 'Talk to Jeeves', href: '/jeeves-chat' },
  { title: 'Governed conversations', href: '/ai-chat' },
  { title: 'Game learning and emulation', href: '/game-learning' },
  { title: 'Mirror room', href: '/mirror-room' },
  { title: 'Jeeves workbench', href: '/jeeves-workbench' },
  { title: 'Jeeves settings', href: '/settings/jeeves' },
  { title: 'Model setup', href: '/setup' },
] as const;

function ModelInventory() {
  const router = useRouter();
  const [readiness, setReadiness] = useState<ChatReadiness | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(true);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    setBusy(true);
    setError('');
    try {
      const value = await getChatReadiness(signal);
      if (!signal?.aborted) setReadiness(value);
    } catch {
      if (!signal?.aborted) {
        setReadiness(null);
        setError('Model readiness could not be verified. Check the authenticated runtime and setup.');
      }
    } finally {
      if (!signal?.aborted) setBusy(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  return <SafeAreaView style={styles.safe}>
    <ScrollView contentContainerStyle={styles.page} refreshControl={<RefreshControl refreshing={busy} onRefresh={() => void refresh()} />}>
      <TouchableOpacity accessibilityRole="button" onPress={() => router.back()}><Text style={styles.back}>‹ Back</Text></TouchableOpacity>
      <Text style={styles.title}>Jeeves · Model inventory</Text>
      <Text style={styles.muted}>Models reported by the authenticated AI chat service. A registered model is not necessarily available, selected or capable of training.</Text>
      {busy && !readiness ? <ActivityIndicator color="#B6A9FF" /> : null}
      {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
      {readiness ? <>
        <View style={styles.card}>
          <Text style={styles.heading}>{readiness.available ? 'Conversation engine ready' : 'AI requires setup'}</Text>
          <Text style={styles.muted}>{chatReadinessMessage(readiness)}</Text>
          {Object.entries(readiness.checks).map(([key, check]) =>
            <Text key={key} style={styles.detail}>{key.replace(/_/g, ' ')}: {check.available ? 'ready' : check.code}</Text>
          )}
        </View>
        {readiness.models.models.length === 0 ? <Text style={styles.muted}>No model has been reported by the service.</Text> : null}
        {readiness.models.models.map(model => <View key={model.id} style={styles.card} testID="ai-model-inventory-row">
          <Text style={styles.heading}>{model.label}</Text>
          <Text style={styles.detail}>Provider: {model.provider_id} · Model: {model.model_id}</Text>
          <Text style={[styles.detail, model.available ? styles.ready : styles.unavailable]}>
            {model.available ? 'Available' : 'Unavailable'} · {model.active ? 'Active' : 'Inactive'} · {model.selectable ? 'Selectable' : 'Not selectable'}
          </Text>
          <Text style={styles.detail}>Context {model.context_window} · Max output {model.max_output_tokens} tokens</Text>
          <Text style={styles.detail}>Credential-free: {model.credential_free ? 'yes' : 'no'} · Capabilities: {model.capabilities.join(', ') || 'not declared'}</Text>
          <Text style={styles.muted}>{model.readiness.message}</Text>
        </View>)}
      </> : null}
      <Text style={styles.section}>Related workspaces</Text>
      <View style={styles.links}>{WORKFLOWS.map(item =>
        <TouchableOpacity key={item.href} accessibilityRole="button" accessibilityLabel={item.title}
          style={styles.link} onPress={() => router.push(item.href as never)}>
          <Text style={styles.linkText}>{item.title} →</Text>
        </TouchableOpacity>
      )}</View>
    </ScrollView>
  </SafeAreaView>;
}

export default function AIModelsRoute() {
  return <StudioLoginGate title="Jeeves model inventory" requireAuthenticated><ModelInventory /></StudioLoginGate>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#0C1120' },
  page: { padding: 18, paddingBottom: 48, gap: 14 },
  back: { color: '#BAB9FF', fontSize: 14, fontWeight: '700' },
  title: { color: '#F8FAFC', fontSize: 24, fontWeight: '800' },
  muted: { color: '#9FAFC6', fontSize: 12, lineHeight: 19 },
  error: { color: '#FCA5A5', fontSize: 13, lineHeight: 20 },
  card: { borderRadius: 14, borderWidth: 1, borderColor: '#2E3853', padding: 15, gap: 7, backgroundColor: '#161E32' },
  heading: { color: '#F8FAFC', fontSize: 16, fontWeight: '800' },
  detail: { color: '#BBC7DB', fontSize: 12, lineHeight: 19 },
  ready: { color: '#8EE5AB' },
  unavailable: { color: '#FBBF24' },
  section: { color: '#F8FAFC', fontSize: 18, fontWeight: '800', marginTop: 6 },
  links: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  link: { backgroundColor: '#293657', borderRadius: 11, minHeight: 42, paddingHorizontal: 13, paddingVertical: 10 },
  linkText: { color: '#E0E5FF', fontSize: 12, fontWeight: '700' },
});
