import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { chatReadinessMessage, getChatReadiness, type ChatReadiness } from '../../product/chatSessionClient';

/** Read-only observed prerequisites. A configured URL never becomes a model-ready verdict. */
export default function JeevesRuntimeStatus({ readiness, refresh }: { readiness?: ChatReadiness | null; refresh?: () => Promise<void> } = {}) {
  const router = useRouter(); const [local, setLocal] = useState<ChatReadiness | null>(null); const [busy, setBusy] = useState(false); const [expanded, setExpanded] = useState(false);
  const check = useCallback(async (signal?: AbortSignal) => {
    setBusy(true);
    try { if (refresh) await refresh(); else { const value = await getChatReadiness(signal); if (!signal?.aborted) setLocal(value); } }
    catch { if (!signal?.aborted) setLocal(null); }
    finally { if (!signal?.aborted) setBusy(false); }
  }, [refresh]);
  useEffect(() => { if (readiness !== undefined) return; const request = new AbortController(); void check(request.signal); return () => request.abort(); }, [readiness, check]);
  const current = readiness === undefined ? local : readiness;
  return <View style={s.container}><View style={s.row}>
    <TouchableOpacity style={s.summary} accessibilityRole="button" accessibilityState={{ expanded }} onPress={() => setExpanded(value => !value)}><Ionicons name={current?.available ? 'checkmark-circle-outline' : 'information-circle-outline'} size={17} color={current?.available ? '#86efac' : '#c4b5fd'} /><Text style={s.title}>{busy ? 'Checking AI readiness…' : current?.available ? 'AI conversation ready' : current ? 'AI conversation needs setup' : 'AI readiness not observed'}</Text><Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={14} color="#94a3b8" /></TouchableOpacity>
    <TouchableOpacity style={s.button} disabled={busy} accessibilityRole="button" accessibilityLabel="Refresh AI readiness" onPress={() => void check()}>{busy ? <ActivityIndicator size="small" color="#c4b5fd" /> : <Ionicons name="refresh-outline" size={17} color="#c4b5fd" />}</TouchableOpacity>
  </View>{expanded && <View style={s.details}><Text style={s.text}>{current ? chatReadinessMessage(current) : 'The app could not confirm its AI prerequisites. Saved account cache remains separate from execution readiness.'}</Text>{current && Object.entries(current.checks).map(([key, value]) => <Text key={key} style={s.text}>{key.replaceAll('_', ' ')}: {value.available ? 'ready' : 'unavailable'}</Text>)}<Text style={s.text}>Turn events show actual execution states. Token streaming is not offered by this connection.</Text><TouchableOpacity accessibilityRole="button" onPress={() => router.push('/setup' as never)} style={s.settings}><Text style={s.link}>Setup & readiness →</Text></TouchableOpacity><TouchableOpacity accessibilityRole="button" onPress={() => router.push('/ai-models' as never)} style={s.settings}><Text style={s.link}>Observed model inventory →</Text></TouchableOpacity></View>}</View>;
}
const s = StyleSheet.create({ container: { borderBottomWidth: 1, borderColor: '#28364e', backgroundColor: '#111a2e' }, row: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14 }, summary: { flex: 1, minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: 8 }, title: { flexShrink: 1, color: '#cbd5e1', fontSize: 12, fontWeight: '600' }, button: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' }, details: { paddingHorizontal: 18, paddingBottom: 12, gap: 6 }, text: { color: '#94a3b8', fontSize: 12, lineHeight: 18 }, settings: { alignSelf: 'flex-start', paddingVertical: 8 }, link: { color: '#c4b5fd', fontSize: 12 } });
