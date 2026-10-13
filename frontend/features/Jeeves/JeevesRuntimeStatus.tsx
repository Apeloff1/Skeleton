import React, { useCallback, useRef, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, useRouter } from 'expo-router';
import api from '../../src/utils/apiClient';

type Provider = {
  id: string;
  model?: string;
  available: boolean;
  execution_mode?: string;
  network_policy?: string;
};
type Runtime = { providers?: Provider[]; active?: string | null; llm_available?: boolean };
type Budget = { free_remaining?: number };
type Status = { title: string; detail: string; model: string; state: 'local' | 'configured' | 'limited' | 'unknown' };

const UNKNOWN: Status = {
  title: 'AI status unavailable', model: '', state: 'unknown',
  detail: 'The engine connection could not be confirmed. Saved conversations remain available; use Refresh to check again.',
};

/** Read-only projection of the engine-owned provider, never a routing authority. */
export default function JeevesRuntimeStatus() {
  const router = useRouter();
  const [status, setStatus] = useState<Status>(UNKNOWN);
  const [busy, setBusy] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const request = useRef<AbortController | null>(null);
  const active = useRef(false);

  const refresh = useCallback(async () => {
    request.current?.abort();
    const current = new AbortController();
    request.current = current;
    setBusy(true);
    try {
      const [runtime, budget] = await Promise.all([
        api.get<Runtime>('/api/ai/providers', { signal: current.signal, timeoutMs: 10000, retries: 0 }),
        api.get<Budget>('/api/jeeves/free-tier', { signal: current.signal, timeoutMs: 10000, retries: 0 }),
      ]);
      if (!active.current || request.current !== current || current.signal.aborted) return;
      if (!runtime.ok || !runtime.data || !Array.isArray(runtime.data.providers)) {
        setStatus(UNKNOWN);
        return;
      }
      const selected = runtime.data.providers.find(provider => provider?.id === runtime.data?.active);
      const available = runtime.data.llm_available === true && selected?.available === true;
      const local = available && selected.id === 'local' && selected.execution_mode === 'local'
        && selected.network_policy === 'none';
      const remaining = budget.ok && typeof budget.data?.free_remaining === 'number'
        ? Math.max(0, Math.floor(budget.data.free_remaining)) : null;
      if (local) {
        setStatus({ title: 'Local model connected', state: 'local', model: selected.model || 'Local model',
          detail: 'Jeeves can generate through the configured local engine. Model quality depends on the supplied trained weights. The label on each reply records the route actually used.' });
      } else if (available) {
        setStatus({ title: 'Engine provider connected', state: 'configured', model: selected.model || selected.id,
          detail: 'A generative provider is available. Jeeves still applies its cost policy: free requests can return knowledge extracts before paid generation.'
            + (remaining === null ? '' : ` ${remaining} free requests remain in the current window.`) });
      } else {
        setStatus({ title: 'Knowledge extraction mode', state: 'limited', model: '',
          detail: 'No available generative provider is reported by the engine. Replies may contain knowledge excerpts, and requests requiring generation may fail. Configure a trained local model or an approved engine provider for generative chat.' });
      }
    } catch {
      if (active.current && request.current === current && !current.signal.aborted) setStatus(UNKNOWN);
    } finally {
      if (active.current && request.current === current) setBusy(false);
    }
  }, []);

  useFocusEffect(useCallback(() => {
    active.current = true;
    void refresh();
    return () => { active.current = false; request.current?.abort(); };
  }, [refresh]));

  return <View style={s.container}>
    <View style={s.row}>
      <TouchableOpacity style={s.summary} accessibilityRole="button"
        accessibilityLabel="AI runtime details" accessibilityState={{ expanded }}
        onPress={() => setExpanded(value => !value)}>
        <Ionicons name={status.state === 'local' ? 'hardware-chip-outline' : 'information-circle-outline'}
          size={17} color={status.state === 'local' ? '#86efac' : '#c4b5fd'} />
        <Text style={s.title}>{busy ? 'Checking AI connection…' : status.title}</Text>
        <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={14} color="#94a3b8" />
      </TouchableOpacity>
      <TouchableOpacity style={s.button} disabled={busy} accessibilityRole="button"
        accessibilityLabel="Refresh AI runtime status" accessibilityState={{ disabled: busy }}
        onPress={() => { void refresh(); }}>
        {busy ? <ActivityIndicator size="small" color="#c4b5fd" /> : <Ionicons name="refresh-outline" size={17} color="#c4b5fd" />}
      </TouchableOpacity>
    </View>
    {expanded && <View style={s.details}>
      {!!status.model && <Text style={s.model}>{status.model}</Text>}
      <Text style={s.text}>{status.detail}</Text>
      <TouchableOpacity style={s.settings} accessibilityRole="button" accessibilityLabel="Open connection settings"
        onPress={() => router.push('/settings/api')}><Text style={s.link}>Connection settings</Text></TouchableOpacity>
    </View>}
  </View>;
}

const s = StyleSheet.create({
  container: { borderBottomWidth: 1, borderColor: '#28364e', backgroundColor: '#111a2e' },
  row: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14 },
  summary: { flex: 1, minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { flexShrink: 1, color: '#cbd5e1', fontSize: 12, fontWeight: '600' },
  button: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  details: { paddingHorizontal: 18, paddingBottom: 12, gap: 6 },
  model: { color: '#e2e8f0', fontSize: 12, fontWeight: '600' },
  text: { color: '#94a3b8', fontSize: 12, lineHeight: 18 },
  settings: { alignSelf: 'flex-start', paddingVertical: 8 },
  link: { color: '#c4b5fd', fontSize: 12 },
});
