import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, StyleSheet, Switch, Text, TouchableOpacity, View } from 'react-native';
import { getAuthToken } from '../../auth/gameforgeAuth';
import { ChatClientError } from '../../product/chatErrors';
import { authorizeRuntimeDatasetDownload, exportRuntimeLearningDataset, MAX_RUNTIME_DATASET_BYTES, type RuntimeControlObservation, type RuntimeLearningDatasetFile, type RuntimeLearningDatasetFilters } from '../../product/runtimeOptimizationClient';
import { saveRuntimeJson } from './runtimeOptimizationFiles';

function Action({ title, disabled, onPress }: { title: string; disabled?: boolean; onPress: () => void }) {
  return <TouchableOpacity accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} onPress={onPress} style={[s.button, disabled && s.disabled]}><Text style={s.buttonText}>{title}</Text></TouchableOpacity>;
}
function compact(value: string): string { return `${value.slice(0, 10)}…${value.slice(-6)}`; }

/** An explicit bounded read/download, without a historical export queue or training authority. */
export default function RuntimeDatasetExportPanel({ observed, partitionId, disabled, foreground }: { observed: RuntimeControlObservation; partitionId?: string; disabled: boolean; foreground: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const [selectedOnly, setSelectedOnly] = useState(false);
  const [includeUntrained, setIncludeUntrained] = useState(false);
  const [page, setPage] = useState<RuntimeLearningDatasetFile | null>(null);
  const [pageNumber, setPageNumber] = useState(0);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const mounted = useRef(true);
  const generation = useRef(0);
  const request = useRef<AbortController | null>(null);
  const locked = useRef(false);
  const active = useRef(foreground);
  active.current = foreground;
  const filterPartition = selectedOnly ? partitionId : undefined;
  const accountToken = observed.scope.token;
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; generation.current += 1; request.current?.abort(); };
  }, []);
  useEffect(() => {
    generation.current += 1; request.current?.abort(); request.current = null; locked.current = false;
    setPage(null); setPageNumber(0); setBusy(''); setError(''); setNotice('');
  }, [accountToken, observed.scope.tenantId, observed.scope.principalId, observed.scope.role, filterPartition, selectedOnly, includeUntrained, foreground]);
  const admin = observed.scope.role === 'admin';
  const blocked = disabled || !foreground || !admin || observed.state.learning.available === false || selectedOnly && !partitionId;
  const filters: RuntimeLearningDatasetFilters = { limit: 128, includeUntrained, partitionId: filterPartition };
  const run = async (operation: 'first' | 'next' | 'download') => {
    if (blocked || locked.current || operation !== 'first' && !page || operation === 'next' && !page?.dataset.next_cursor) return;
    locked.current = true;
    const controller = new AbortController(); request.current = controller;
    const epoch = generation.current;
    const valid = () => mounted.current && active.current && !controller.signal.aborted && epoch === generation.current && getAuthToken() === accountToken;
    setBusy(operation === 'download' ? 'Preparing download' : 'Reading numeric outcomes'); setError(''); setNotice('');
    try {
      if (operation === 'download' && page) {
        await authorizeRuntimeDatasetDownload(observed, page, controller.signal);
        if (!valid()) return;
        await saveRuntimeJson({ content: page.datasetJson, filename: `jeeves-numeric-outcomes-${page.dataset.dataset_digest.slice(0, 12)}-page-${pageNumber}.json`, maximumBytes: MAX_RUNTIME_DATASET_BYTES, dialogTitle: 'Export numeric learning outcomes' }, valid);
        if (valid()) setNotice('The exact canonical dataset page was prepared for your device to save.');
      } else {
        const next = await exportRuntimeLearningDataset(observed, filters, operation === 'next' ? page?.dataset.next_cursor ?? undefined : undefined, controller.signal);
        if (!valid()) return;
        setPage(next); setPageNumber(current => operation === 'first' ? 1 : current + 1);
      }
    } catch (cause) {
      if (valid()) { setError(cause instanceof ChatClientError ? cause.message : 'The numeric dataset page could not be prepared. Refresh the runtime observation before trying again.'); if (cause instanceof ChatClientError && cause.kind === 'authorization') setPage(null); }
    } finally { if (valid()) { setBusy(''); locked.current = false; request.current = null; } }
  };
  const reset = () => { generation.current += 1; request.current?.abort(); request.current = null; locked.current = false; setPage(null); setPageNumber(0); setBusy(''); setError(''); setNotice(''); };
  const dataset = page?.dataset;
  return <View style={s.panel}>
    <TouchableOpacity accessibilityRole="button" accessibilityState={{ expanded }} onPress={() => setExpanded(value => !value)} style={s.header}><View style={s.copy}><Text style={s.title}>Numeric learning dataset</Text><Text style={s.caption}>Scoped canonical outcome features, targets and provenance</Text></View><Text style={s.buttonText}>{expanded ? 'Hide' : 'Export'}</Text></TouchableOpacity>
    {expanded && <>
      <Text style={s.caption}>Read up to 128 retained rows per page, at most 1 MiB. Each page is fetched and downloaded only when requested. Files contain numeric operational telemetry and provenance fingerprints; prompts, replies and transformer weights are excluded.</Text>
      <View style={s.toggle}><View style={s.copy}><Text style={s.title}>Only selected learner</Text><Text style={s.caption}>{partitionId ? `Partition ${compact(partitionId)}` : 'Select a learner above to enable this filter.'}</Text></View><Switch accessibilityLabel="Export only the selected learner" value={selectedOnly} disabled={!!busy || !partitionId || !admin} onValueChange={setSelectedOnly} trackColor={{ false: '#334155', true: '#6d28d9' }} /></View>
      <View style={s.toggle}><View style={s.copy}><Text style={s.title}>Include untrained outcomes</Text><Text style={s.caption}>Retain verified provenance rows that were not used to update the predictor. Eligibility remains explicit in each row.</Text></View><Switch accessibilityLabel="Include untrained numeric outcomes" value={includeUntrained} disabled={!!busy || !admin} onValueChange={setIncludeUntrained} trackColor={{ false: '#334155', true: '#6d28d9' }} /></View>
      <View style={s.actions}><Action title={dataset ? 'Start a new export window' : 'Preview first page'} disabled={blocked || !!busy} onPress={() => { void run('first'); }} /><Action title="Clear preview" disabled={!!busy || !page} onPress={reset} /></View>
      {!!busy && <View style={s.progress}><ActivityIndicator size="small" color="#c4b5fd" /><Text style={s.caption}>{busy}…</Text></View>}
      {!!error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}{!!notice && <Text accessibilityLiveRegion="polite" style={s.notice}>{notice}</Text>}
      {dataset && <View style={s.preview}>
        <Text style={s.title}>Page {pageNumber} · {dataset.row_count} exported rows · {dataset.scanned_rows} scanned</Text>
        <Text style={s.caption}>Digest {compact(dataset.dataset_digest)} · {(new TextEncoder().encode(page!.datasetJson).byteLength / 1024).toFixed(1)} KiB · {dataset.filters.partition_id ? 'Selected learner' : 'All retained tenant learners'}</Text>
        <Text style={s.caption}>Targets: {dataset.target_names.map(name => name.replaceAll('_', ' ')).join(', ')}. These targets describe operational outcomes, not correctness or creative quality.</Text>
        <Text style={s.caption}>Features: {dataset.feature_names.map(name => name.replaceAll('_', ' ')).join(', ')}.</Text>
        <Text style={s.caption}>Retention: {dataset.retention.retained_outcomes ?? 'Unknown'} derived rows · {dataset.retention.outcome_max_age_days ?? 'Unknown'} days. Window watermark: {dataset.watermark?.observed_at ?? 'No retained observation'}.</Text>
        {dataset.omitted_rows.length > 0 && <Text style={s.warning}>{dataset.omitted_rows.length} scanned records were omitted because canonical provenance could not be exported. {Array.from(new Set(dataset.omitted_rows.map(row => row.reason).filter(Boolean))).slice(0, 4).map(reason => reason!.replaceAll('_', ' ')).join(', ')}.</Text>}
        {dataset.row_count === 0 && <Text style={s.caption}>{dataset.has_more ? 'This scanned page contains no exportable rows. The next retained page is still available.' : 'No exportable rows remain in this retained window.'}</Text>}
        {dataset.limitations.map((message, index) => <Text key={index} style={s.caption}>{message}</Text>)}
        <Text style={s.caption}>The first read fixes a chronological watermark. Retention can evict rows between requests, so this is a bounded retained-data export rather than a complete historical snapshot.</Text>
        <View style={s.actions}><Action title="Download this page" disabled={blocked || !!busy} onPress={() => { void run('download'); }} /><Action title="Read next page" disabled={blocked || !!busy || !dataset.has_more} onPress={() => { void run('next'); }} /></View>
      </View>}
      {!admin && <Text style={s.caption}>An administrator account is required to read or download tenant learning data.</Text>}
    </>}
  </View>;
}
const s = StyleSheet.create({ panel: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#334155', paddingTop: 12, gap: 10 }, header: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 44 }, copy: { flex: 1, gap: 3 }, title: { color: '#e2e8f0', fontSize: 12, lineHeight: 19, fontWeight: '600' }, caption: { color: '#94a3b8', fontSize: 11, lineHeight: 17 }, toggle: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 44 }, actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 }, button: { minHeight: 44, paddingHorizontal: 12, justifyContent: 'center', backgroundColor: '#211c38', borderRadius: 8, borderWidth: 1, borderColor: '#4c4274' }, buttonText: { color: '#ddd6fe', fontWeight: '600', fontSize: 11 }, disabled: { opacity: .4 }, preview: { backgroundColor: '#111c30', borderWidth: 1, borderColor: '#334155', borderRadius: 9, padding: 12, gap: 9 }, progress: { flexDirection: 'row', alignItems: 'center', gap: 8 }, error: { color: '#fca5a5', fontSize: 11, lineHeight: 17 }, warning: { color: '#fcd34d', fontSize: 11, lineHeight: 17 }, notice: { color: '#86efac', fontSize: 11, lineHeight: 17 } });
