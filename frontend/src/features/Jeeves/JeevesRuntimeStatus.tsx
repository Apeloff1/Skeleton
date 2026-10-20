import React, { useCallback, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { chatReadinessMessage, type ChatReadiness } from '../../product/chatSessionClient';
import { useChatReadiness } from '../../product/useChatReadiness';
import RuntimeOptimizationPanel from './RuntimeOptimizationPanel';

/** Observed prerequisites and authenticated operator controls; never a provider owner. */
export default function JeevesRuntimeStatus({ readiness, refresh, readinessError, observedAt }: { readiness?: ChatReadiness | null; refresh?: () => Promise<void>; readinessError?: string | null; observedAt?: string | null } = {}) {
  const router = useRouter();
  const { height } = useWindowDimensions();
  const local = useChatReadiness(readiness === undefined);
  const [refreshing, setRefreshing] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const check = useCallback(async () => {
    if (!refresh) { await local.refresh(); return; }
    setRefreshing(true);
    try { await refresh(); } finally { setRefreshing(false); }
  }, [refresh, local.refresh]);
  const current = readiness === undefined ? local.readiness : readiness;
  const errorMessage = readinessError ?? local.error?.message;
  const lastObservedAt = observedAt ?? local.observedAt;
  const busy = refreshing || local.busy;
  const checks = { conversation_storage: 'Conversation history', engine: 'AI engine', models: 'Configured models', crawler: 'Captured knowledge' };
  const availableModels = current?.models.models.filter(model => model.available && model.selectable).length ?? 0;
  return <View style={s.container}><View style={s.row}>
    <TouchableOpacity style={s.summary} accessibilityRole="button" accessibilityState={{ expanded }} onPress={() => setExpanded(value => !value)}>
      <Ionicons name={current?.available ? 'checkmark-circle-outline' : 'information-circle-outline'} size={17} color={current?.available ? '#86efac' : '#c4b5fd'} />
      <Text style={s.title}>{busy ? 'Checking AI readiness…' : current?.available ? `AI conversation ready · ${availableModels} available ${availableModels === 1 ? 'model' : 'models'}` : current ? 'AI conversation needs setup' : 'AI readiness not observed'}</Text>
      <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={14} color="#94a3b8" />
    </TouchableOpacity>
    <TouchableOpacity style={s.button} disabled={busy} accessibilityRole="button" accessibilityLabel="Refresh AI readiness" accessibilityState={{ disabled: busy }} onPress={() => { void check().catch(() => {}); }}>
      {busy ? <ActivityIndicator size="small" color="#c4b5fd" /> : <Ionicons name="refresh-outline" size={17} color="#c4b5fd" />}
    </TouchableOpacity>
  </View>{expanded && <ScrollView style={{ maxHeight: Math.max(160, Math.min(520, height * 0.5)) }} contentContainerStyle={s.details} nestedScrollEnabled keyboardShouldPersistTaps="handled">
    <Text style={s.text}>{current ? chatReadinessMessage(current) : 'The app could not confirm its AI prerequisites. Open Setup to read the current service state.'}</Text>
    {!current && errorMessage && <Text accessibilityRole="alert" style={s.error}>{errorMessage}</Text>}
    {current && Object.entries(current.checks).map(([key, value]) => <Text key={key} style={s.text}>{checks[key as keyof typeof checks] || key.replaceAll('_', ' ')}: {value.available ? 'ready' : value.code.replaceAll('_', ' ')}</Text>)}
    {current && !current.checks.models.available && current.models.readiness?.message && <Text style={s.error}>{current.models.readiness.message}</Text>}
    {current && !current.checks.models.available && current.models.readiness?.action && <Text style={s.text}>{current.models.readiness.action}</Text>}
    {current && <Text style={s.text}>{current.capabilities.token_deltas ? 'Live response text is available; the saved answer remains authoritative.' : 'Actual execution states are shown while the final answer is prepared.'} {current.capabilities.resume ? 'Saved turns can be resumed without starting duplicate work.' : 'Turn recovery is unavailable on this connection.'}</Text>}
    {lastObservedAt && <Text style={s.text}>Observed {new Date(lastObservedAt).toLocaleTimeString()}. Readiness is checked again when you return.</Text>}
    <TouchableOpacity accessibilityRole="button" onPress={() => router.push('/setup' as never)} style={s.settings}><Text style={s.link}>Setup & readiness →</Text></TouchableOpacity>
    <TouchableOpacity accessibilityRole="button" onPress={() => router.push('/ai-models' as never)} style={s.settings}><Text style={s.link}>Observed model inventory →</Text></TouchableOpacity>
    <RuntimeOptimizationPanel />
  </ScrollView>}</View>;
}
const s = StyleSheet.create({ container: { borderBottomWidth: 1, borderColor: '#28364e', backgroundColor: '#111a2e' }, row: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14 }, summary: { flex: 1, minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: 8 }, title: { flexShrink: 1, color: '#cbd5e1', fontSize: 12, fontWeight: '600' }, button: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' }, details: { paddingHorizontal: 18, paddingBottom: 12, gap: 6 }, text: { color: '#94a3b8', fontSize: 12, lineHeight: 18 }, error: { color: '#fca5a5', fontSize: 12, lineHeight: 18 }, settings: { alignSelf: 'flex-start', paddingVertical: 8 }, link: { color: '#c4b5fd', fontSize: 12 } });
