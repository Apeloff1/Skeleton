import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Platform, StyleSheet, Switch, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import { getAuthToken } from '../../auth/gameforgeAuth';
import { ChatClientError } from '../../product/chatErrors';
import { canManageRuntimePartition, changeRuntimeOptimization, changeRuntimePartition, exportRuntimeCheckpoint, getRuntimeOptimization, MAX_RUNTIME_CHECKPOINT_BYTES, parseRuntimeCheckpoint, retryRuntimeMaintenanceTask, type RuntimeControlChange, type RuntimeControlObservation, type RuntimeLearningAction, type RuntimeLearningCheckpoint, type RuntimeLearningCheckpointFile, type RuntimeLearningPartition, type RuntimeMaintenanceTask } from '../../product/runtimeOptimizationClient';
import { useStudioForeground } from './useStudioForeground';

function number(value: unknown): number | null { return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null; }
function count(value: unknown): string { const found = number(value); return found === null ? 'Unknown' : Math.floor(found).toLocaleString(); }
function label(value: unknown, fallback = 'Unknown'): string { return typeof value === 'string' && value.trim() ? value.slice(0, 100).replaceAll('_', ' ') : fallback; }
function duration(value: unknown): string { const found = number(value); return found === null ? 'Unknown' : found < 1000 ? `${Math.round(found)} ms` : `${(found / 1000).toFixed(1)} s`; }
function bytes(value: unknown): string { const found = number(value); return found === null ? 'Unknown' : found < 1048576 ? `${Math.round(found / 1024)} KB` : `${(found / 1048576).toFixed(1)} MB`; }
function sum(left: unknown, right: unknown): number | null { const first = number(left); const second = number(right); return first === null || second === null ? null : first + second; }
function decimal(value: unknown): string { const found = number(value); return found === null ? 'Unknown' : found.toFixed(3); }
function fingerprint(value: unknown): string { return typeof value === 'string' && /^[a-f0-9]{64}$/.test(value) ? `${value.slice(0, 10)}…${value.slice(-6)}` : 'Unknown'; }
function sourceFingerprint(value: unknown): string { return value === '' ? 'No source observation recorded' : fingerprint(value); }
function checkpointFileError(message: string): never { throw new ChatClientError(message, { kind: 'validation', retryable: false }); }
async function pickCheckpointFile(): Promise<{ name: string; text: string } | null> {
  const picked = await DocumentPicker.getDocumentAsync({ type: ['application/json', 'text/plain'], multiple: false, copyToCacheDirectory: true });
  if (picked.canceled || !picked.assets[0]) return null;
  const asset = picked.assets[0];
  if (typeof asset.size === 'number' && asset.size > MAX_RUNTIME_CHECKPOINT_BYTES) checkpointFileError('Choose a learner checkpoint no larger than 256 KiB.');
  let text: string;
  if (Platform.OS === 'web') {
    if (!asset.file && !asset.uri.startsWith('blob:')) checkpointFileError('Choose a local learner checkpoint file.');
    const file = asset.file || await (await fetch(asset.uri)).blob();
    if (file.size > MAX_RUNTIME_CHECKPOINT_BYTES) checkpointFileError('Choose a learner checkpoint no larger than 256 KiB.');
    text = await file.text();
  } else {
    if (!/^(file|content):\/\//.test(asset.uri)) checkpointFileError('Choose a local learner checkpoint file.');
    const info = await FileSystem.getInfoAsync(asset.uri);
    if (!info.exists || info.isDirectory || info.size > MAX_RUNTIME_CHECKPOINT_BYTES) checkpointFileError('The selected checkpoint is missing, unreadable or larger than 256 KiB.');
    try { text = await FileSystem.readAsStringAsync(asset.uri, { encoding: FileSystem.EncodingType.UTF8 }); }
    finally { if (FileSystem.cacheDirectory && asset.uri.startsWith(FileSystem.cacheDirectory)) await FileSystem.deleteAsync(asset.uri, { idempotent: true }).catch(() => {}); }
  }
  if (new TextEncoder().encode(text).byteLength > MAX_RUNTIME_CHECKPOINT_BYTES) checkpointFileError('Choose a learner checkpoint no larger than 256 KiB.');
  return { name: asset.name.slice(0, 160), text };
}
async function saveCheckpointFile(file: RuntimeLearningCheckpointFile, isCurrent: () => boolean): Promise<void> {
  const { checkpoint, checkpointJson: content } = file;
  if (new TextEncoder().encode(content).byteLength > MAX_RUNTIME_CHECKPOINT_BYTES || !isCurrent()) checkpointFileError('The checkpoint export is stale or exceeds 256 KiB. Refresh and try again.');
  const filename = `jeeves-learner-${checkpoint.partition_id.slice(0, 12)}-v${checkpoint.state_version}.json`;
  if (Platform.OS === 'web') {
    const url = URL.createObjectURL(new Blob([content], { type: 'application/json;charset=utf-8' }));
    const link = document.createElement('a');
    try { if (!isCurrent()) checkpointFileError('Your account changed before the export could be downloaded.'); link.href = url; link.download = filename; document.body.appendChild(link); link.click(); }
    finally { link.remove(); setTimeout(() => URL.revokeObjectURL(url), 5000); }
    return;
  }
  if (!FileSystem.cacheDirectory || !await Sharing.isAvailableAsync()) checkpointFileError('File sharing is unavailable on this device. Open the studio on a device with file export support.');
  if (!isCurrent()) checkpointFileError('Your account changed before the checkpoint could be exported.');
  const uri = `${FileSystem.cacheDirectory}${Date.now()}-${filename}`;
  try {
    await FileSystem.writeAsStringAsync(uri, content, { encoding: FileSystem.EncodingType.UTF8 });
    if (!isCurrent()) checkpointFileError('Your account changed before the checkpoint could be shared.');
    await Sharing.shareAsync(uri, { mimeType: 'application/json', dialogTitle: 'Export operational learner checkpoint' });
  } finally { await FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => {}); }
}
type PendingLearnerChange = { partitionId: string; stateVersion: number; policyVersion: number; action: 'reset' | 'restore_last_healthy' };
type PendingLearnerImport = { partitionId: string; stateVersion: number; policyVersion: number; filename: string; checkpoint: RuntimeLearningCheckpoint; checkpointJson: string };
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
  const [servingRouteId, setServingRouteId] = useState<string | null>(null);
  const [partitionId, setPartitionId] = useState<string | null>(null);
  const [learningOffset, setLearningOffset] = useState(0);
  const learningOffsetRef = useRef(0);
  const [pendingLearnerChange, setPendingLearnerChange] = useState<PendingLearnerChange | null>(null);
  const [pendingImport, setPendingImport] = useState<PendingLearnerImport | null>(null);
  const [pickingFile, setPickingFile] = useState(false);
  const [tasksExpanded, setTasksExpanded] = useState(false);
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
    const requestedOffset = learningOffsetRef.current;
    setLoading(true);
    try {
      const next = await getRuntimeOptimization(request.signal, requestedOffset);
      if (!mounted.current || request.signal.aborted || epoch.current !== generation || getAuthToken() !== requestToken || learningOffsetRef.current !== requestedOffset) return;
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
      learningOffsetRef.current = 0;
      setServingRouteId(null); setPartitionId(null); setLearningOffset(0); setPendingLearnerChange(null); setPendingImport(null); setPickingFile(false);
      setTasksExpanded(false);
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

  const reconcileConfirmed = async (next: RuntimeControlObservation, request: AbortController, generation: number, accountToken: string) => {
    const valid = () => mounted.current && !request.signal.aborted && generation === epoch.current && accountToken === getAuthToken();
    if (!valid()) return;
    const offset = learningOffsetRef.current;
    if (offset === 0) { setObserved(next); setFresh(true); return; }
    setFresh(false);
    try {
      const page = await getRuntimeOptimization(request.signal, offset);
      if (valid() && offset === learningOffsetRef.current) { setObserved(page); setFresh(true); }
    } catch (cause) {
      if (!valid()) return;
      if (cause instanceof ChatClientError && cause.kind === 'authorization') setObserved(null);
      setError('The action was confirmed, but the current learner page could not be refreshed. Refresh to read it; the action will not be repeated.');
    }
  };
  const loadLearnerPage = (offset: number) => {
    if (!Number.isSafeInteger(offset) || offset < 0 || offset > 127 || !foreground || loading || !!command || pickingFile || commandLock.current) return;
    learningOffsetRef.current = offset; setLearningOffset(offset); setFresh(false);
    setPartitionId(null); setPendingLearnerChange(null); setPendingImport(null);
    void refresh();
  };

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
      const routed = serving?.route_id && (change.serving || change.action) ? { ...change, serving_route_id: serving.route_id } : change;
      const next = await changeRuntimeOptimization(observed, routed, request.signal);
      if (!mounted.current || request.signal.aborted || generation !== epoch.current || observed.scope.token !== getAuthToken()) return;
      setNotice(next.state.reconciliation?.state === 'pending' ? `Policy ${next.state.policy_version} saved. The runtime is still applying it; refresh to observe progress.` : `${title} confirmed · policy ${next.state.policy_version}.`);
      await reconcileConfirmed(next, request, generation, observed.scope.token);
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
          const next = await getRuntimeOptimization(request.signal, learningOffsetRef.current);
          if (accept(next)) setError(conflict ? 'Current policy loaded. Review the settings and apply your change again.' : 'The request was not confirmed. Current state is shown; review it before trying again.');
        } catch { /* Retain the useful command error and visibly stale observation. */ }
      }
    } finally {
      requests.current.delete(request);
      if (generation === epoch.current) { commandLock.current = false; if (mounted.current) setCommand(''); }
    }
  };

  const state = observed?.state;
  const servingModels = state?.serving.models ?? [];
  const serving = servingModels.find(row => row.route_id === servingRouteId) ?? servingModels.find(row => row.active) ?? servingModels[0] ?? state?.serving;
  const capacity = serving?.capacity;
  const learning = state?.learning;
  const maintenance = state?.maintenance;
  const partitions = learning?.partitions ?? [];
  const readyPartitions = partitions.filter(row => row.readiness === 'ready' && row.quarantined !== true).length;
  const quarantined = partitions.filter(row => row.quarantined === true || row.readiness === 'quarantined').length;
  const samples = partitions.length ? partitions.reduce<number | null>((total, row) => { const found = number(row.samples); return total === null || found === null ? null : total + found; }, 0) : null;
  const admin = observed?.scope.role === 'admin';
  const disabled = !admin || !fresh || !foreground || loading || !!command || pickingFile;
  const maximum = number(serving?.policy?.max_effective_concurrency);
  const operatorMaximum = number(capacity?.operator_max_concurrency);
  const minimum = Math.max(1, number(serving?.policy?.min_effective_concurrency) ?? 1);
  const pressure = label(serving?.pressure?.level, 'Pressure unknown');
  const learningEnabled = learning?.available === false ? undefined : learning?.policy?.enabled;
  const servingEnabled = serving?.available === false ? undefined : serving?.policy?.enabled;
  const maintenanceEnabled = maintenance?.available === false ? undefined : maintenance?.policy?.enabled;
  const replayEnabled = maintenance?.available === true ? maintenance.policy?.augmentation_enabled : undefined;
  const coordinationUnavailable = maintenance?.coordination?.state === 'degraded' || maintenance?.status?.coordination_state === 'unavailable';
  const maintenanceDisabled = disabled || coordinationUnavailable;
  const maintenanceRetryObserved = maintenance?.available === true && maintenance.coordination?.state === 'observed' && maintenance.status?.coordination_state === 'synchronized';
  const execution = state?.execution;
  const draining = serving?.draining;
  const currentToken = observed?.scope.token === getAuthToken();
  const selectedPartition = partitions.find(row => row.partition_id === partitionId);
  const partitionManageable = !!observed && !!selectedPartition && canManageRuntimePartition(observed, selectedPartition);
  const observedLearningOffset = number(learning?.limits?.partition_offset);
  const totalPartitions = number(learning?.limits?.total_partitions);

  const performLearner = async (action: RuntimeLearningAction | 'export', partition: RuntimeLearningPartition, checkpointJson?: string) => {
    if (!observed || disabled || commandLock.current || !canManageRuntimePartition(observed, partition)) return;
    const pending = action === 'import' ? pendingImport : pendingLearnerChange;
    if (action !== 'export' && (!pending || pending.partitionId !== partition.partition_id || pending.stateVersion !== partition.state_version || pending.policyVersion !== observed.state.policy_version)) {
      setPendingImport(null); setPendingLearnerChange(null); setError('The policy or learner changed since this action was prepared. Review the current state and prepare the action again.'); return;
    }
    commandLock.current = true; refreshRequest.current?.abort();
    const request = new AbortController(); requests.current.add(request);
    const generation = epoch.current;
    const valid = () => mounted.current && !request.signal.aborted && generation === epoch.current && observed.scope.token === getAuthToken();
    setCommand(action === 'export' ? 'Preparing learner checkpoint' : action === 'import' ? 'Importing learner checkpoint' : action === 'reset' ? 'Resetting learner partition' : 'Restoring last healthy learner');
    setLoading(false); setError(''); setNotice('');
    try {
      if (action === 'export') {
        const exported = await exportRuntimeCheckpoint(observed, partition, request.signal);
        if (!valid()) return;
        await saveCheckpointFile(exported, valid);
        if (valid()) setNotice(`Learner checkpoint v${exported.checkpoint.state_version} prepared for export. File saving is handled by your device.`);
      } else {
        const result = await changeRuntimePartition(observed, partition, action, checkpointJson, request.signal);
        if (!valid()) return;
        setPendingLearnerChange(null); setPendingImport(null);
        setNotice(`Learner action confirmed · policy ${count(result.receipt.version)} · receipt ${fingerprint(result.receipt.receipt_digest)}. Fresh canonical outcomes are required before learned guidance resumes.`);
        await reconcileConfirmed(result.observation, request, generation, observed.scope.token);
      }
    } catch (cause) {
      if (!valid()) return;
      setFresh(false); setPendingLearnerChange(null); setPendingImport(null);
      const unauthorized = cause instanceof ChatClientError && cause.kind === 'authorization';
      if (unauthorized) setObserved(null);
      setError(cause instanceof ChatClientError ? cause.message : 'The learner action was not confirmed. Refresh current state before trying again.');
      if (!unauthorized) {
        try { const next = await getRuntimeOptimization(request.signal, learningOffsetRef.current); if (valid()) { setObserved(next); setFresh(true); setError(cause instanceof ChatClientError && cause.kind === 'conflict' ? 'The policy or learner changed. Current state is loaded; review it and prepare the action again.' : 'The learner action was not confirmed. Current state is shown; review it before trying again.'); } }
        catch { /* Keep the first actionable error; never replay a learner mutation. */ }
      }
    } finally { requests.current.delete(request); if (generation === epoch.current) { commandLock.current = false; if (mounted.current) setCommand(''); } }
  };
  const prepareImport = async () => {
    if (!observed || !selectedPartition || disabled || !partitionManageable) return;
    const origin = observed; const partition = selectedPartition;
    setPickingFile(true); setError(''); setNotice(''); setPendingLearnerChange(null); setPendingImport(null);
    try {
      const file = await pickCheckpointFile();
      if (!file || !mounted.current || origin.scope.token !== getAuthToken()) return;
      const checkpoint = parseRuntimeCheckpoint(file.text, origin, partition);
      setPendingImport({ partitionId: partition.partition_id!, stateVersion: partition.state_version!, policyVersion: origin.state.policy_version, filename: file.name, checkpoint, checkpointJson: file.text });
    } catch (cause) { if (mounted.current && origin.scope.token === getAuthToken()) setError(cause instanceof ChatClientError ? cause.message : 'The selected learner checkpoint could not be read. Choose a local JSON export no larger than 256 KiB.'); }
    finally { if (mounted.current) setPickingFile(false); }
  };
  const prepareLearnerChange = (action: 'reset' | 'restore_last_healthy') => {
    if (!observed || !selectedPartition || disabled || !partitionManageable) return;
    setPendingImport(null); setPendingLearnerChange({ partitionId: selectedPartition.partition_id!, stateVersion: selectedPartition.state_version!, policyVersion: observed.state.policy_version, action });
  };
  const retryMaintenance = async (task: RuntimeMaintenanceTask) => {
    if (!observed || disabled || !maintenanceRetryObserved || task.retryable !== true || commandLock.current) return;
    commandLock.current = true; refreshRequest.current?.abort();
    const request = new AbortController(); requests.current.add(request);
    const generation = epoch.current;
    const valid = () => mounted.current && !request.signal.aborted && generation === epoch.current && observed.scope.token === getAuthToken();
    setCommand('Recording failed-task retry'); setLoading(false); setError(''); setNotice('');
    try {
      const result = await retryRuntimeMaintenanceTask(observed, task, request.signal);
      if (!valid()) return;
      setNotice(`${result.result.deduplicated ? 'The same task retry was already recorded' : 'Maintenance task retry recorded'} · ${label(result.result.state)} · attempt ${count(result.result.attempts)}. Work starts only when existing maintenance policy admits it.`);
      await reconcileConfirmed(result.observation, request, generation, observed.scope.token);
    } catch (cause) {
      if (!valid()) return;
      setFresh(false);
      const unauthorized = cause instanceof ChatClientError && cause.kind === 'authorization';
      const message = cause instanceof ChatClientError ? cause.message : 'The maintenance retry was not confirmed.';
      if (unauthorized) setObserved(null);
      setError(message);
      if (!unauthorized) {
        try { const current = await getRuntimeOptimization(request.signal, learningOffsetRef.current); if (valid()) { setObserved(current); setFresh(true); setError(`${message} Current state has been refreshed; the retry was not replayed.`); } }
        catch { /* A read failure cannot authorize another retry or repeat physical work. */ }
      }
    } finally { requests.current.delete(request); if (generation === epoch.current) { commandLock.current = false; if (mounted.current) setCommand(''); } }
  };

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
      <Text style={s.caption}>{admin ? servingModels.length ? 'Administrator controls · serving actions target the selected local model; maintenance affects this host; learning is scoped to your tenant.' : 'Administrator controls · legacy serving actions and maintenance affect this host; learning is scoped to your tenant.' : 'Read-only observation · an administrator can change serving, learning and maintenance policy.'}</Text>
      {!!servingModels.length && <View style={s.modelPicker}><Text style={s.rowTitle}>Local model serving</Text><View style={s.actions}>{servingModels.map(model => <TouchableOpacity key={model.route_id} accessibilityRole="button" accessibilityState={{ selected: model.route_id === serving?.route_id, disabled: !!command || pickingFile }} disabled={!!command || pickingFile} onPress={() => setServingRouteId(model.route_id!)} style={[s.modelChoice, model.route_id === serving?.route_id && s.selectedChoice]}><Text style={s.buttonText}>{label(model.model_id)}{model.active ? ' · primary' : ''}</Text><Text style={s.caption}>{label(model.provider_id)} · {label(model.pressure?.level, 'Pressure unknown')}</Text></TouchableOpacity>)}</View><Text style={s.caption}>Showing {label(serving?.model_id)} · model digest {fingerprint(serving?.model_digest)}. Capacity and queue metrics below belong to this model.</Text></View>}
      <View style={s.metrics}><Metric title="Active / capacity" value={`${count(sum(capacity?.active_interactive, capacity?.active_background))} / ${count(capacity?.effective_concurrency)}`} /><Metric title="Queued requests" value={count(sum(capacity?.queued_interactive, capacity?.queued_background))} /><Metric title="Recent latency" value={duration(serving?.pressure?.latency_ewma_ms)} /><Metric title="Derived cache" value={bytes(serving?.cache?.bytes)} /></View>

      <View style={s.section}>
        <PolicySwitch title="Adaptive serving" description="Adjust capacity inside the configured operator limit" value={servingEnabled} disabled={disabled} onChange={enabled => { void apply(enabled ? 'Adaptive serving enabled' : 'Adaptive serving disabled', { serving: { enabled } }); }} />
        <View style={s.policyRow}><View style={s.policyCopy}><Text style={s.rowTitle}>Concurrency ceiling</Text><Text style={s.caption}>Effective {count(capacity?.effective_concurrency)} · operator maximum {count(operatorMaximum)}</Text></View><View style={s.stepper}><Button title="−" disabled={disabled || maximum === null || maximum <= minimum || operatorMaximum === null} onPress={() => { if (maximum !== null) void apply('Concurrency ceiling updated', { serving: { max_effective_concurrency: maximum - 1 } }); }} /><Text style={s.limit}>{count(maximum)}</Text><Button title="+" disabled={disabled || maximum === null || operatorMaximum === null || maximum >= Math.min(32, operatorMaximum)} onPress={() => { if (maximum !== null) void apply('Concurrency ceiling updated', { serving: { max_effective_concurrency: maximum + 1 } }); }} /></View></View>
        <Text style={s.caption}>Queue wait {duration(serving?.pressure?.queue_wait_ewma_ms)} · cached entries {count(serving?.cache?.entries)} · shared in-flight requests {count(serving?.cache?.singleflight_hits)}</Text>
        <View style={s.metrics}><Metric title="Active tenants" value={count(serving?.fairness?.active_tenants)} /><Metric title="Queued tenants" value={count(serving?.fairness?.queued_tenants)} /><Metric title="Oldest foreground wait" value={duration(serving?.fairness?.oldest_interactive_wait_ms)} /><Metric title="Oldest background wait" value={duration(serving?.fairness?.oldest_background_wait_ms)} /></View>
        <Text style={s.caption}>Tenant active limit {count(capacity?.per_tenant_active_limit)} · tenant queue limit {count(capacity?.per_tenant_queue_limit)} · fairness rotations {count(serving?.fairness?.rotations)} · memory load shedding {count(serving?.fairness?.memory_shed_rejections)}</Text>
      </View>

      <View style={s.section}>
        <PolicySwitch title="Learn from execution outcomes" description="Tenant-scoped numeric learning; no transcript training" value={learningEnabled} disabled={disabled} onChange={enabled => { void apply(enabled ? 'Outcome learning enabled' : 'Outcome learning disabled', { learning: { enabled } }); }} />
        <View style={s.metrics}><Metric title="Recorded outcomes" value={count(learning?.totals?.outcomes)} /><Metric title="Ready partitions shown" value={learning?.partitions ? `${readyPartitions} / ${partitions.length}` : 'Unknown'} /><Metric title="Samples shown" value={count(samples)} /><Metric title="Resource failures" value={count(learning?.totals?.resource_failures)} /></View>
        <Text style={s.caption}>Learned signals estimate completion, latency and resource risk. They do not verify correctness or creative quality. Existing verification and promotion gates remain authoritative.</Text>
        {quarantined > 0 && <Text style={s.warning}>{quarantined} learning {quarantined === 1 ? 'partition is' : 'partitions are'} quarantined and excluded from recommendations.</Text>}
        {(partitions.length > 0 || totalPartitions !== null || learningOffset > 0) && <View style={s.partitionList}>
          <Text style={s.rowTitle}>Inspect an operational learner</Text>
          {partitions.map((row, index) => <TouchableOpacity key={`${row.partition_id ?? index}:${index}`} accessibilityRole="button" accessibilityState={{ selected: row.partition_id === partitionId, disabled: !!command || pickingFile || !row.partition_id }} disabled={!!command || pickingFile || !row.partition_id} onPress={() => { setPartitionId(row.partition_id!); setPendingLearnerChange(null); setPendingImport(null); }} style={[s.partitionChoice, row.partition_id === partitionId && s.selectedChoice]}><View style={s.partition}><Text style={s.partitionName}>{label(row.task_class, 'Task partition')}</Text><Text style={s.caption}>{label(row.readiness, 'Readiness unknown')} · {count(row.samples)} samples</Text></View><Text style={s.caption}>Model {fingerprint(row.model_selection_digest)} · state {count(row.state_version)}{row.drift?.active ? ' · drift detected' : ''}</Text></TouchableOpacity>)}
          {(learningOffset > 0 || learning?.limits?.has_more_partitions === true) && <View style={s.pagination}><Button title="Previous learners" disabled={learningOffset === 0 || loading || !!command || pickingFile || !foreground} onPress={() => loadLearnerPage(Math.max(0, learningOffset - 10))} /><Text style={s.caption}>Page {Math.floor(learningOffset / 10) + 1}{totalPartitions !== null ? ` of ${Math.max(1, Math.ceil(totalPartitions / 10))}` : ''}</Text><Button title="Next learners" disabled={!fresh || learning?.limits?.has_more_partitions !== true || learningOffset >= 120 || loading || !!command || pickingFile || !foreground} onPress={() => loadLearnerPage(Math.min(127, learningOffset + 10))} /></View>}
          <Text style={s.caption}>{count(partitions.length)} returned of {count(totalPartitions)} retained partitions · observed offset {count(observedLearningOffset)}.</Text>{observedLearningOffset !== learningOffset && <Text style={s.warning}>Requested offset {learningOffset} is not loaded yet. The last observed learner page remains visible until a fresh read succeeds.</Text>}{partitions.length === 0 && <Text style={s.caption}>{totalPartitions === 0 ? 'No learner partitions have been recorded for this tenant.' : 'No learners were returned at this offset. Move to the previous page or refresh current state.'}</Text>}
        </View>}
        {selectedPartition && <View style={s.inspector}>
          <View style={s.partition}><Text style={s.rowTitle}>{label(selectedPartition.task_class, 'Selected learner')}</Text><Text style={s.caption}>State {count(selectedPartition.state_version)} · generation {count(selectedPartition.generation)}</Text></View>
          <Text style={s.caption}>Partition {fingerprint(selectedPartition.partition_id)} · model {fingerprint(selectedPartition.model_selection_digest)}</Text>
          <View style={s.metrics}><Metric title="Prequential loss" value={number(selectedPartition.drift?.prequential_count) === 0 ? 'No observations' : decimal(selectedPartition.drift?.last_prequential_loss)} /><Metric title="Prequential observations" value={count(selectedPartition.drift?.prequential_count)} /><Metric title="Drift score" value={decimal(selectedPartition.drift?.score)} /><Metric title="Prediction uncertainty" value={decimal(selectedPartition.uncertainty)} /><Metric title="Fresh observations" value={count(selectedPartition.fresh_samples)} /><Metric title="Learner rollbacks" value={count(selectedPartition.rollback_count)} /></View>
          <Text style={selectedPartition.drift?.active ? s.warning : s.caption}>{selectedPartition.drift?.active === true ? 'Drift is active; confidence is withheld while fresh outcomes are collected.' : selectedPartition.drift?.active === false ? 'No active drift reported by this learner.' : 'Drift state has not been observed.'} Cooldown observations remaining: {count(selectedPartition.drift?.cooldown_remaining)}.</Text>
          {!!selectedPartition.confidence_reasons?.length && <Text style={s.caption}>Confidence constraints: {selectedPartition.confidence_reasons.slice(0, 8).map(reason => label(reason)).join(', ')}.</Text>}
          <Text style={s.caption}>Loss is measured before updating the predictor on each recorded outcome. It describes operational prediction error, not game quality or answer correctness.</Text>
          <View style={s.partition}><Text style={s.rowTitle}>Last healthy predictor</Text><Text style={s.caption}>{selectedPartition.last_healthy?.available === true ? 'Available' : selectedPartition.last_healthy?.available === false ? 'Unavailable' : 'Unknown'}</Text></View>
          <Text style={s.caption}>Healthy observations {count(selectedPartition.last_healthy?.observations)} · optimizer step {count(selectedPartition.last_healthy?.optimizer_step)} · checkpoint {fingerprint(selectedPartition.last_healthy?.checkpoint_digest)}</Text>
          <Text style={s.caption}>Latest source {sourceFingerprint(selectedPartition.source_provenance?.latest_source_digest)} · source changes {count(selectedPartition.source_provenance?.source_switches)} · observations on this source {count(selectedPartition.source_provenance?.latest_source_samples)}</Text>
          <Text style={s.caption}>Optimizer updates: terminal {count(selectedPartition.optimizer_cost?.terminal_updates)}, replay {count(selectedPartition.optimizer_cost?.replay_updates)}, maintenance {count(selectedPartition.optimizer_cost?.maintenance_updates)}.</Text>
          <View style={s.actions}><Button title="Export checkpoint" icon="download-outline" disabled={disabled || !partitionManageable} onPress={() => { void performLearner('export', selectedPartition); }} /><Button title={pickingFile ? 'Choosing file…' : 'Import checkpoint'} icon="cloud-upload-outline" disabled={disabled || !partitionManageable} onPress={() => { void prepareImport(); }} /><Button title="Restore last healthy" icon="refresh-outline" disabled={disabled || !partitionManageable || selectedPartition.last_healthy?.available !== true} onPress={() => prepareLearnerChange('restore_last_healthy')} /><Button title="Reset learner" icon="trash-outline" disabled={disabled || !partitionManageable} onPress={() => prepareLearnerChange('reset')} /></View>
          {!partitionManageable && <Text style={s.warning}>Lifecycle controls require a complete canonical partition identity, model digest and state version. Refresh to observe them.</Text>}
          {pendingLearnerChange && pendingLearnerChange.partitionId === selectedPartition.partition_id && <View style={s.confirmation}><Text style={s.rowTitle}>{pendingLearnerChange.action === 'reset' ? 'Reset this learner partition?' : 'Restore its last healthy predictor?'}</Text><Text style={s.caption}>This replaces the selected operational predictor state and returns learned guidance to a fresh-observation gate. Execution results and independent quality evidence keep their authority. Export a checkpoint first if you need a copy of the current predictor.</Text><View style={s.actions}><Button title={pendingLearnerChange.action === 'reset' ? 'Confirm reset' : 'Confirm restore'} disabled={disabled || !partitionManageable} onPress={() => { void performLearner(pendingLearnerChange.action, selectedPartition); }} /><Button title="Cancel" disabled={!!command} onPress={() => setPendingLearnerChange(null)} /></View></View>}
          {pendingImport && pendingImport.partitionId === selectedPartition.partition_id && <View style={s.confirmation}><Text style={s.rowTitle}>Review checkpoint import</Text><Text style={s.caption}>{pendingImport.filename} · checkpoint state {count(pendingImport.checkpoint.state_version)} · {bytes(new TextEncoder().encode(pendingImport.checkpointJson).byteLength)}</Text><Text style={s.caption}>Model {fingerprint(pendingImport.checkpoint.model_selection_digest)} · source {sourceFingerprint(pendingImport.checkpoint.source_snapshot_digest)} · checkpoint {fingerprint(pendingImport.checkpoint.checkpoint_digest)}</Text><Text style={s.caption}>Tenant, task, model and feature identity match this partition. The engine validates checkpoint integrity on import. Historical source provenance is retained; fresh canonical outcomes are required before confidence resumes.</Text><View style={s.actions}><Button title="Import reviewed checkpoint" disabled={disabled || !partitionManageable} onPress={() => { void performLearner('import', selectedPartition, pendingImport.checkpointJson); }} /><Button title="Cancel" disabled={!!command} onPress={() => setPendingImport(null)} /></View></View>}
          <Text style={s.caption}>Files are limited to 256 KiB and contain numeric predictor/replay state and fingerprints. These actions never import policy, grants, execution results or transformer weights.</Text>
        </View>}
      </View>

      <View style={s.section}>
        <PolicySwitch title="Idle self-maintenance" description="Bounded local housekeeping yields to foreground work" value={maintenanceEnabled} disabled={maintenanceDisabled} onChange={enabled => { void apply(enabled ? 'Idle maintenance enabled' : 'Idle maintenance disabled', { maintenance: { enabled } }); }} />
        <PolicySwitch title="Replay adaptation" description="Update the operational predictor from recorded outcomes during idle time" value={replayEnabled} disabled={maintenanceDisabled || maintenance?.available !== true} onChange={augmentation_enabled => { void apply(augmentation_enabled ? 'Replay adaptation enabled' : 'Replay adaptation disabled', { maintenance: { augmentation_enabled } }); }} />
        {coordinationUnavailable && <Text style={s.warning}>Maintenance coordination is unavailable or degraded. Its controls are read-only until healthy coordination is observed again. Refresh to read current custody and recovery state.</Text>}
        <Text style={s.caption}>Replay adaptation starts off and runs only with idle self-maintenance enabled. It adds bounded local predictor updates; it does not train transformer weights or verify game quality.</Text>
        <Text style={s.caption}>{label(maintenance?.status?.state, 'Maintenance state unknown')} · active tasks {count(maintenance?.status?.active_tasks)} · queued {count(maintenance?.queued_tasks)}</Text>
        <View style={s.metrics}><Metric title="Maintenance owner" value={label(maintenance?.ownership?.state)} /><Metric title="Owner physical tasks" value={count(maintenance?.ownership?.physical_tasks)} /><Metric title="Host foreground work" value={count(maintenance?.quiescence?.host_foreground_requests)} /><Metric title="Registered host owners" value={count(maintenance?.quiescence?.registered_host_owners)} /><Metric title="Blocked recovery tasks" value={count(maintenance?.recovery?.blocked_tasks)} /><Metric title="Clock discontinuities" value={count(maintenance?.recovery?.clock_jump_count)} /></View>
        <View style={s.metrics}><Metric title="Retained chunk receipts" value={count(maintenance?.chunk_results?.retained)} /><Metric title="Pending acknowledgements" value={count(maintenance?.acknowledgements?.pending)} /><Metric title="Acknowledgement failures" value={count(maintenance?.acknowledgements?.failed_attempts)} /><Metric title="Host receipt capacity" value={count(maintenance?.chunk_results?.maximum)} /></View>
        {maintenance?.chunk_results?.backpressure === true && <Text style={s.warning}>Durable chunk results have reached their admission limit. Maintenance waits for receipt capacity before starting more physical work.</Text>}
        {number(maintenance?.acknowledgements?.failed_attempts) !== null && Number(maintenance?.acknowledgements?.failed_attempts) > 0 && <Text style={s.warning}>A receipt acknowledgement is waiting for metadata recovery. Its retry does not repeat the optimizer update.</Text>}
        {number(maintenance?.recovery?.blocked_tasks) !== null && Number(maintenance?.recovery?.blocked_tasks) > 0 && <Text style={s.warning}>Recovery is blocked until the prior physical work is proven drained. Expired leases alone do not authorize takeover.</Text>}
        {!!maintenance?.leases?.length && <View style={s.partitionList}>{maintenance.leases.slice(0, 3).map((lease, index) => <Text key={`${lease.resource_id ?? index}:${index}`} style={s.caption}>Lease fence {count(lease.fencing_token)} · {label(lease.state)}{lease.drained_at_ns != null ? ' · drain recorded' : ''}</Text>)}</View>}
        {!!maintenance?.recent_tasks?.length && <View style={s.partitionList}>{maintenance.recent_tasks.slice(0, tasksExpanded ? maintenance.recent_tasks.length : 3).map((task, index) => <View key={`${task.task_id ?? index}:${index}`} style={s.partitionChoice}><View style={s.partition}><Text style={s.partitionName}>{label(task.kind, 'Maintenance task')}</Text><Text style={s.caption}>{label(task.state)} · {count(task.attempts)} attempts</Text></View>{task.state === 'failed' && task.retryable !== true && task.retry_reason && <Text style={s.caption}>Retry unavailable: {label(task.retry_reason)}</Text>}{task.retryable === true && admin && fresh && foreground && observed && Date.now() - observed.observedAt <= 60000 && maintenanceRetryObserved && <Button title="Retry failed task" icon="refresh-outline" disabled={disabled} onPress={() => { void retryMaintenance(task); }} />}</View>)}{maintenance.recent_tasks.length > 3 && <Button title={tasksExpanded ? 'Show recent three tasks' : `Show ${maintenance.recent_tasks.length} returned tasks`} onPress={() => setTasksExpanded(expanded => !expanded)} />}<Text style={s.caption}>Retry queues the exact observed task and source at its recorded attempt count. It does not enable maintenance, resume other work or force immediate execution.</Text></View>}
      </View>

      {execution && <View style={s.section}><Text style={s.rowTitle}>Execution supervision and recovery</Text>{execution.available !== true ? <Text style={s.caption}>The engine could not observe its execution supervisor. No recovery counters are inferred.</Text> : <><View style={s.metrics}><Metric title="Active executions" value={count(execution.active_executions)} /><Metric title="Lifecycle leases" value={count(execution.active_lifecycle_leases)} /><Metric title="Recovery records scanned" value={count(execution.recovery?.scanned)} /><Metric title="Recovery drivers started" value={count(execution.recovery?.started)} /><Metric title="Driver failures" value={count(execution.recovery?.driver_failures)} /><Metric title="Finalization failures" value={count(execution.recovery?.driver_finalization_failures)} /></View><Text style={s.caption}>{execution.recovery?.scan_in_progress === true ? 'Recovery scan in progress' : execution.recovery?.scan_in_progress === false ? 'Recovery scan idle' : 'Recovery scan state unknown'} · driver ceiling {count(execution.recovery?.maximum_recovery_drivers)} · page limit {count(execution.recovery?.page_limit)}</Text>{execution.faulted === true && <Text style={s.warning}>Execution supervision reports a fault. Inspect the engine before submitting replacement work.</Text>}{typeof execution.recovery?.last_error === 'string' && execution.recovery.last_error && <Text style={s.warning}>Last recovery scan error: {label(execution.recovery.last_error)}</Text>}{typeof execution.recovery?.last_driver_error === 'string' && execution.recovery.last_driver_error && <Text style={s.warning}>Last recovery driver error: {label(execution.recovery.last_driver_error)}</Text>}<Text style={s.caption}>These are aggregate engine observations. A recovery scan or issued lease does not confirm an execution result.</Text></>}</View>}

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
  modelPicker: { gap: 8 },
  modelChoice: { minHeight: 48, flexGrow: 1, flexBasis: 180, paddingHorizontal: 10, paddingVertical: 8, gap: 3, borderRadius: 9, borderWidth: 1, borderColor: '#334155', backgroundColor: '#111c30' },
  selectedChoice: { borderColor: '#a78bfa', backgroundColor: '#251e3d' },
  partitionChoice: { minHeight: 52, paddingHorizontal: 10, paddingVertical: 8, gap: 3, borderRadius: 8, borderWidth: 1, borderColor: '#334155', backgroundColor: '#111c30' },
  pagination: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  inspector: { padding: 12, borderWidth: 1, borderColor: '#514472', borderRadius: 10, backgroundColor: '#131a2c', gap: 10 },
  confirmation: { padding: 12, gap: 10, backgroundColor: '#2b253a', borderRadius: 9, borderWidth: 1, borderColor: '#65538a' },
  partition: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 6 },
  partitionName: { color: '#cbd5e1', fontSize: 11, lineHeight: 17 },
  ratchet: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, paddingTop: 10, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#334155' },
});
