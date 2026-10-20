import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, StyleSheet, Switch, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { getAuthToken } from '../../auth/gameforgeAuth';
import { ChatClientError } from '../../product/chatErrors';
import { changeRuntimeOptimization, getRuntimeOptimization, type RuntimeControlChange, type RuntimeControlObservation } from '../../product/runtimeOptimizationClient';
import { useStudioForeground } from './useStudioForeground';

function number(value: unknown): number | null { return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null; }
function count(value: unknown): string { const found = number(value); return found === null ? 'Unknown' : Math.floor(found).toLocaleString(); }
function label(value: unknown, fallback = 'Unknown'): string { return typeof value === 'string' && value.trim() ? value.slice(0, 100).replaceAll('_', ' ') : fallback; }
function duration(value: unknown): string { const found = number(value); return found === null ? 'Unknown' : found < 1000 ? `${Math.round(found)} ms` : `${(found / 1000).toFixed(1)} s`; }
function bytes(value: unknown): string { const found = number(value); return found === null ? 'Unknown' : found < 1048576 ? `${Math.round(found / 1024)} KB` : `${(found / 1048576).toFixed(1)} MB`; }
function sum(left: unknown, right: unknown): number | null { const first = number(left); const second = number(right); return first === null || second === null ? null : first + second; }
function Metric({ title, value }: { title: string; value: string }) {
  return <View style={s.metric}><Text style={s.metricValue}>{value}</Text><Text style={s.caption}>{title}</Text></View>;
}
function Button({ title, onPress, disabled = false, icon }: { title: string; onPress: () => void; disabled?: boolean; icon?: React.ComponentProps<typeof Ionicons>['name'] }) {
  return <TouchableOpacity accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} onPress={onPress} style={[s.button, disabled && s.disabled]}>{icon && <Ionicons name={icon} size={15} color="#c4b5fd" />}<Text style={s.buttonText}>{title}</Text></TouchableOpacity>;
}
function PolicySwitch({ title, description, value, disabled, onChange }: { title: string; description: string; value: boolean | undefined; disabled: boolean; onChange: (value: boolean) => void }) {
  return <View style={s.policyRow}><View style={s.policyCopy}><Text style={s.rowTitle}>{title}</Text><Text style={s.caption}>{description}{value === undefined ? ' · State not observed' : ''}</Text></View><Switch accessibilityLabel={title} accessibilityState={{ disabled: disabled || value === undefined }} value={value === true} disabled={disabled || value === undefined} onValueChange={onChange} trackColor={{ false: '#334155', true: '#6d28d9' }} thumbColor={value ? '#ede9fe' : '#94a3b8'} /></View>;
}

/** An observed projection and explicit operator commands; never an inference owner. */
export default function RuntimeOptimizationPanel() {
  const foreground = useStudioForeground();
  const [observed, setObserved] = useState<RuntimeControlObservation | null>(null);
  const [fresh, setFresh] = useState(false);
  const [loading, setLoading] = useState(false);
  const [command, setCommand] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const epoch = useRef(0);
  const requests = useRef(new Set<AbortController>());
  const refreshRequest = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const token = useRef(getAuthToken());
  const commandLock = useRef(false);
  const active = useRef(foreground);
  active.current = foreground;

  const clearRequests = useCallback(() => {
    epoch.current += 1;
    requests.current.forEach(request => request.abort());
    requests.current.clear();
    refreshRequest.current = null;
  }, []);
  const refresh = useCallback(async () => {
    if (!mounted.current || !active.current || commandLock.current) return;
    refreshRequest.current?.abort();
    const request = new AbortController();
    refreshRequest.current = request;
    requests.current.add(request);
    const generation = epoch.current;
    const requestToken = getAuthToken();
    setLoading(true);
    try {
      const next = await getRuntimeOptimization(request.signal);
      if (!mounted.current || request.signal.aborted || epoch.current !== generation || getAuthToken() !== requestToken) return;
      setObserved(next); setFresh(true); setError('');
    } catch (cause) {
      if (!mounted.current || request.signal.aborted || epoch.current !== generation) return;
      setFresh(false);
      if (cause instanceof ChatClientError && cause.kind === 'authorization') setObserved(null);
      setError(cause instanceof ChatClientError ? cause.message : 'Runtime optimization could not be observed. Refresh to reconnect.');
    } finally {
      requests.current.delete(request);
      if (mounted.current && epoch.current === generation && refreshRequest.current === request) { refreshRequest.current = null; setLoading(false); }
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    // Auth currently exposes a token getter rather than an event subscription.
    // This local check never creates a network request or retains an account cache.
    const accountCheck = setInterval(() => {
      if (token.current === getAuthToken()) return;
      token.current = getAuthToken(); clearRequests();
      setObserved(null); setFresh(false); setLoading(false); setCommand(''); setNotice('');
      setError('Your account changed. Refresh to observe the current account.');
      commandLock.current = false;
    }, 1000);
    return () => { mounted.current = false; clearInterval(accountCheck); clearRequests(); };
  }, [clearRequests]);

  useEffect(() => {
    if (!foreground) { clearRequests(); commandLock.current = false; setCommand(''); setFresh(false); setLoading(false); return; }
    void refresh();
    const timer = setInterval(() => { void refresh(); }, 30000);
    const online = () => { void refresh(); };
    if (typeof window !== 'undefined') window.addEventListener('online', online);
    return () => { clearInterval(timer); clearRequests(); if (typeof window !== 'undefined') window.removeEventListener('online', online); };
  }, [foreground, refresh, clearRequests]);

  const apply = async (title: string, change: RuntimeControlChange) => {
    if (!observed || !fresh || !foreground || commandLock.current || observed.scope.role !== 'admin') return;
    commandLock.current = true;
    refreshRequest.current?.abort();
    const request = new AbortController(); requests.current.add(request);
    const generation = epoch.current;
    setCommand(title); setLoading(false); setError(''); setNotice('');
    const accept = (next: RuntimeControlObservation) => {
      if (!mounted.current || request.signal.aborted || generation !== epoch.current || observed.scope.token !== getAuthToken()) return false;
      setObserved(next); setFresh(true); return true;
    };
    try {
      const next = await changeRuntimeOptimization(observed, change, request.signal);
      if (accept(next)) setNotice(next.state.reconciliation?.state === 'pending' ? `Policy ${next.state.policy_version} saved. The runtime is still applying it; refresh to observe progress.` : `${title} confirmed · policy ${next.state.policy_version}.`);
    } catch (cause) {
      if (!mounted.current || request.signal.aborted || generation !== epoch.current) return;
      setFresh(false);
      const conflict = cause instanceof ChatClientError && cause.kind === 'conflict';
      const unauthorized = cause instanceof ChatClientError && cause.kind === 'authorization';
      if (unauthorized) setObserved(null);
      setError(conflict ? 'The runtime policy changed. Refreshing its current version; review it and apply your change again.' : cause instanceof ChatClientError ? cause.message : 'The change was not confirmed. Refresh current state before trying again.');
      // Reconcile uncertainty with a read; a command is never replayed automatically.
      if (!unauthorized) {
        try {
          const next = await getRuntimeOptimization(request.signal);
          if (accept(next)) setError(conflict ? 'Current policy loaded. Review the settings and apply your change again.' : 'The request was not confirmed. Current state is shown; review it before trying again.');
        } catch { /* Retain the useful command error and visibly stale observation. */ }
      }
    } finally {
      requests.current.delete(request);
      if (generation === epoch.current) { commandLock.current = false; if (mounted.current) setCommand(''); }
    }
  };

  const state = observed?.state;
  const serving = state?.serving;
  const capacity = serving?.capacity;
  const learning = state?.learning;
  const maintenance = state?.maintenance;
  const partitions = learning?.partitions ?? [];
  const readyPartitions = partitions.filter(row => row.readiness === 'ready' && row.quarantined !== true).length;
  const quarantined = partitions.filter(row => row.quarantined === true || row.readiness === 'quarantined').length;
  const samples = partitions.length ? partitions.reduce<number | null>((total, row) => { const found = number(row.samples); return total === null || found === null ? null : total + found; }, 0) : null;
  const admin = observed?.scope.role === 'admin';
  const disabled = !admin || !fresh || !foreground || loading || !!command;
  const maximum = number(serving?.policy?.max_effective_concurrency);
  const operatorMaximum = number(capacity?.operator_max_concurrency);
  const minimum = Math.max(1, number(serving?.policy?.min_effective_concurrency) ?? 1);
  const pressure = label(serving?.pressure?.level, 'Pressure unknown');
  const learningEnabled = learning?.available === false ? undefined : learning?.policy?.enabled;
  const servingEnabled = serving?.available === false ? undefined : serving?.policy?.enabled;
  const maintenanceEnabled = maintenance?.available === false ? undefined : maintenance?.policy?.enabled;
  const replayEnabled = maintenance?.available === true ? maintenance.policy?.augmentation_enabled : undefined;
  const draining = serving?.draining;
  const currentToken = observed?.scope.token === getAuthToken();

  // An account can change between the timer callback and this render.
  if (observed && !currentToken) return <View style={s.panel}><Text style={s.heading}>Runtime optimization</Text><Text style={s.caption}>Account changed. Waiting for a fresh account observation.</Text></View>;
  return <View style={s.panel}>
    <View style={s.header}><View style={s.policyCopy}><Text style={s.heading}>Runtime optimization</Text><Text style={s.caption}>{observed ? `Policy ${state?.policy_version} · ${new Date(observed.observedAt).toLocaleTimeString()}${fresh ? '' : ' · stale'}` : 'No runtime observation yet'}</Text></View><TouchableOpacity style={s.refresh} accessibilityRole="button" accessibilityLabel="Refresh runtime optimization" accessibilityState={{ disabled: loading || !!command || !foreground }} disabled={loading || !!command || !foreground} onPress={() => { void refresh(); }}>{loading ? <ActivityIndicator size="small" color="#c4b5fd" /> : <Ionicons name="refresh-outline" size={18} color="#c4b5fd" />}</TouchableOpacity></View>
    {!!error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}
    {!!notice && <Text accessibilityLiveRegion="polite" style={s.notice}>{notice}</Text>}
    {state?.reconciliation?.state === 'pending' && <Text style={s.warning}>The saved runtime policy is pending. Current observed capacity is shown while the engine retries it.</Text>}
    {learning?.totals_health === 'quarantined' && <Text style={s.warning}>Learning counters are unavailable because their stored integrity check failed. Completed execution results retain their own authority.</Text>}
    {!!command && <View style={s.progress}><ActivityIndicator size="small" color="#c4b5fd" /><Text style={s.caption}>{command}…</Text></View>}
    {!state ? <Text style={s.caption}>Runtime capacity and learning are shown after the authenticated engine reports them.</Text> : <>
      <View style={s.statusRow}><View style={[s.badge, draining === true && s.warningBadge]}><Text style={s.badgeText}>{draining === true ? 'Draining new work' : draining === false ? 'Accepting work' : 'Admission unknown'}</Text></View><Text style={s.caption}>{pressure}</Text></View>
      <Text style={s.caption}>{admin ? 'Administrator controls · serving and maintenance affect this host; learning is scoped to your tenant.' : 'Read-only observation · an administrator can change serving, learning and maintenance policy.'}</Text>
      <View style={s.metrics}><Metric title="Active / capacity" value={`${count(sum(capacity?.active_interactive, capacity?.active_background))} / ${count(capacity?.effective_concurrency)}`} /><Metric title="Queued requests" value={count(sum(capacity?.queued_interactive, capacity?.queued_background))} /><Metric title="Recent latency" value={duration(serving?.pressure?.latency_ewma_ms)} /><Metric title="Derived cache" value={bytes(serving?.cache?.bytes)} /></View>

      <View style={s.section}>
        <PolicySwitch title="Adaptive serving" description="Adjust capacity inside the configured operator limit" value={servingEnabled} disabled={disabled} onChange={enabled => { void apply(enabled ? 'Adaptive serving enabled' : 'Adaptive serving disabled', { serving: { enabled } }); }} />
        <View style={s.policyRow}><View style={s.policyCopy}><Text style={s.rowTitle}>Concurrency ceiling</Text><Text style={s.caption}>Effective {count(capacity?.effective_concurrency)} · operator maximum {count(operatorMaximum)}</Text></View><View style={s.stepper}><Button title="−" disabled={disabled || maximum === null || maximum <= minimum || operatorMaximum === null} onPress={() => { if (maximum !== null) void apply('Concurrency ceiling updated', { serving: { max_effective_concurrency: maximum - 1 } }); }} /><Text style={s.limit}>{count(maximum)}</Text><Button title="+" disabled={disabled || maximum === null || operatorMaximum === null || maximum >= Math.min(32, operatorMaximum)} onPress={() => { if (maximum !== null) void apply('Concurrency ceiling updated', { serving: { max_effective_concurrency: maximum + 1 } }); }} /></View></View>
        <Text style={s.caption}>Queue wait {duration(serving?.pressure?.queue_wait_ewma_ms)} · cached entries {count(serving?.cache?.entries)} · shared in-flight requests {count(serving?.cache?.singleflight_hits)}</Text>
      </View>

      <View style={s.section}>
        <PolicySwitch title="Learn from execution outcomes" description="Tenant-scoped numeric learning; no transcript training" value={learningEnabled} disabled={disabled} onChange={enabled => { void apply(enabled ? 'Outcome learning enabled' : 'Outcome learning disabled', { learning: { enabled } }); }} />
        <View style={s.metrics}><Metric title="Recorded outcomes" value={count(learning?.totals?.outcomes)} /><Metric title="Ready partitions shown" value={learning?.partitions ? `${readyPartitions} / ${partitions.length}` : 'Unknown'} /><Metric title="Samples shown" value={count(samples)} /><Metric title="Resource failures" value={count(learning?.totals?.resource_failures)} /></View>
        <Text style={s.caption}>Learned signals estimate completion, latency and resource risk. They do not verify correctness or creative quality. Existing verification and promotion gates remain authoritative.</Text>
        {quarantined > 0 && <Text style={s.warning}>{quarantined} learning {quarantined === 1 ? 'partition is' : 'partitions are'} quarantined and excluded from recommendations.</Text>}
        {!!partitions.length && <View style={s.partitionList}>{partitions.slice(0, 3).map((row, index) => <View key={`${row.partition_id ?? index}:${index}`} style={s.partition}><Text style={s.partitionName}>{label(row.task_class, 'Task partition')}</Text><Text style={s.caption}>{label(row.readiness, 'Readiness unknown')} · {count(row.samples)} samples</Text></View>)}{partitions.length > 3 && <Text style={s.caption}>Showing 3 of {partitions.length} returned partitions.</Text>}</View>}
      </View>

      <View style={s.section}>
        <PolicySwitch title="Idle self-maintenance" description="Bounded local housekeeping yields to foreground work" value={maintenanceEnabled} disabled={disabled} onChange={enabled => { void apply(enabled ? 'Idle maintenance enabled' : 'Idle maintenance disabled', { maintenance: { enabled } }); }} />
        <PolicySwitch title="Replay adaptation" description="Update the operational predictor from recorded outcomes during idle time" value={replayEnabled} disabled={disabled || maintenance?.available !== true} onChange={augmentation_enabled => { void apply(augmentation_enabled ? 'Replay adaptation enabled' : 'Replay adaptation disabled', { maintenance: { augmentation_enabled } }); }} />
        <Text style={s.caption}>Replay adaptation starts off and runs only with idle self-maintenance enabled. It adds bounded local predictor updates; it does not train transformer weights or verify game quality.</Text>
        <Text style={s.caption}>{label(maintenance?.status?.state, 'Maintenance state unknown')} · active tasks {count(maintenance?.status?.active_tasks)} · queued {count(maintenance?.queued_tasks)}</Text>
        {!!maintenance?.recent_tasks?.length && <View style={s.partitionList}>{maintenance.recent_tasks.slice(0, 3).map((task, index) => <View key={`${task.task_id ?? index}:${index}`} style={s.partition}><Text style={s.partitionName}>{label(task.kind, 'Maintenance task')}</Text><Text style={s.caption}>{label(task.state)} · {count(task.attempts)} attempts</Text></View>)}</View>}
      </View>

      <View style={s.ratchet}><Ionicons name={state.ratchet.available ? 'shield-checkmark-outline' : 'shield-outline'} size={17} color="#a78bfa" /><View style={s.policyCopy}><Text style={s.rowTitle}>Quality ratchet</Text><Text style={s.caption}>{state.ratchet.available ? 'Configured ratchet reported. Learned candidate guidance remains separate from measured promotion evidence.' : 'No configured ratchet reported by this engine. Quality improvement has not been verified here.'}</Text></View></View>
      <View style={s.actions}><Button title="Trim cache" icon="sparkles-outline" disabled={disabled || serving?.available === false} onPress={() => { void apply('Cache trim', { action: 'trim_cache' }); }} /><Button title="Clear cache" icon="trash-outline" disabled={disabled || serving?.available === false} onPress={() => { void apply('Cache cleared', { action: 'clear_cache' }); }} /><Button title={draining === true ? 'Resume admission' : 'Drain new work'} icon={draining === true ? 'play-outline' : 'pause-outline'} disabled={disabled || typeof draining !== 'boolean' || serving?.available === false} onPress={() => { void apply(draining ? 'Admission resumed' : 'New work drained', { action: draining ? 'resume' : 'drain' }); }} /></View>
      <Text style={s.caption}>Commands use the observed policy version. Running work keeps its execution ownership and original budgets.</Text>
    </>}
  </View>;
}

const s = StyleSheet.create({
  panel: { padding: 14, marginTop: 8, borderWidth: 1, borderColor: '#334155', borderRadius: 14, backgroundColor: '#0b1425', gap: 12 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  heading: { fontSize: 14, lineHeight: 21, color: '#f1f5f9', fontWeight: '700' },
  caption: { color: '#94a3b8', fontSize: 11, lineHeight: 17 },
  rowTitle: { color: '#e2e8f0', fontSize: 12, lineHeight: 19, fontWeight: '600' },
  refresh: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  statusRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 10 },
  badge: { borderRadius: 12, backgroundColor: '#16352b', paddingHorizontal: 9, paddingVertical: 4 },
  warningBadge: { backgroundColor: '#422f16' },
  badgeText: { color: '#e2e8f0', fontSize: 11, fontWeight: '600' },
  metrics: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  metric: { flexGrow: 1, flexBasis: 115, minWidth: 100, paddingHorizontal: 10, paddingVertical: 8, borderRadius: 8, backgroundColor: '#152034', gap: 3 },
  metricValue: { color: '#e2e8f0', fontSize: 15, fontWeight: '700' },
  section: { paddingTop: 10, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#334155', gap: 10 },
  policyRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 10, minHeight: 44 },
  policyCopy: { flex: 1, minWidth: 150, gap: 2 },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  limit: { color: '#f1f5f9', fontSize: 14, minWidth: 26, textAlign: 'center', fontWeight: '700' },
  button: { minHeight: 44, minWidth: 44, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 12, gap: 6, borderRadius: 9, borderWidth: 1, borderColor: '#4c4274', backgroundColor: '#211c38' },
  buttonText: { color: '#ddd6fe', fontSize: 11, fontWeight: '600' },
  disabled: { opacity: 0.4 },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  error: { color: '#fca5a5', fontSize: 12, lineHeight: 18 },
  warning: { color: '#fcd34d', fontSize: 11, lineHeight: 17 },
  notice: { color: '#86efac', fontSize: 12, lineHeight: 18 },
  progress: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  partitionList: { gap: 6 },
  partition: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 6 },
  partitionName: { color: '#cbd5e1', fontSize: 11, lineHeight: 17 },
  ratchet: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, paddingTop: 10, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#334155' },
});
