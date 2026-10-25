import React, { useState, type ReactNode } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import type { RuntimeControlObservation, RuntimeControlState, RuntimeLearningPartition, RuntimeMaintenanceTask, RuntimeServingState } from '../../product/runtimeOptimizationClient';

type Fields = Record<string, unknown>;
const HASH = /^[a-f0-9]{64}$/;
const KINDS = ['cache_cleanup', 'checkpoint_compaction', 'replay_dedup', 'learner_snapshot', 'eligible_augmentation'];
const OUTPUTS = ['operational_completion', 'resource_failure', 'normalized_latency'];
const FEATURES = ['objective_characters_log', 'input_token_budget_log', 'output_token_budget_log', 'model_turn_budget_fraction', 'tool_call_budget_fraction', 'allowed_tool_count_fraction', 'source_snapshot_count_fraction', 'review_rounds_fraction', 'runtime_pressure_fraction', 'wall_time_budget_log', 'tools_available', 'evidence_required'];
function demand(condition: unknown): asserts condition { if (!condition) throw new Error('Read-only diagnostic unavailable'); }
function object(value: unknown): Fields { demand(value !== null && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length <= 64); return value as Fields; }
function text(value: unknown, maximum = 256): string { demand(typeof value === 'string' && value.length > 0 && value.length <= maximum && !/[\u0000-\u001f\u007f]/.test(value)); return value; }
function finite(value: unknown, minimum = 0, maximum = Number.MAX_SAFE_INTEGER): number { demand(typeof value === 'number' && Number.isFinite(value) && value >= minimum && value <= maximum); return value; }
function integer(value: unknown, minimum = 0, maximum = Number.MAX_SAFE_INTEGER): number { const found = finite(value, minimum, maximum); demand(Number.isInteger(found)); return found; }
function hash(value: unknown): string { const found = text(value, 64); demand(HASH.test(found)); return found; }
function nullableHash(value: unknown): void { if (value !== null) hash(value); }
function array(value: unknown, maximum: number): unknown[] { demand(Array.isArray(value) && value.length <= maximum); return value; }
function human(value: string): string { return value.replaceAll('_', ' ').replace(/^./, character => character.toUpperCase()); }
function fingerprint(value: string): string { return `${value.slice(0, 10)}…${value.slice(-6)}`; }
function count(value: number): string { return value.toLocaleString(); }
function seconds(value: unknown): string { if (value === null) return 'Unknown'; const found = integer(value, 0, 9_223_372_036_854_776_000) / 1e9; return found < 1 ? `${Math.round(found * 1000)} ms` : `${found.toFixed(1)} s`; }
function boundedNs(value: unknown): void { if (value !== null) integer(value, 0, 9_223_372_036_854_776_000); }
function Unavailable({ title }: { title: string }) { return <Text style={s.unavailable}>{title} diagnostic unavailable. Current controls retain their own validation.</Text>; }
function Detail({ title, summary, children }: { title: string; summary: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return <View style={s.card}><TouchableOpacity accessibilityRole="button" accessibilityState={{ expanded: open }} onPress={() => setOpen(value => !value)} style={s.heading}><View style={s.copy}><Text style={s.title}>{title}</Text><Text style={s.caption}>{summary}</Text></View><Text style={s.action}>{open ? 'Hide' : 'Inspect'}</Text></TouchableOpacity>{open && <View style={s.body}>{children}</View>}</View>;
}
function Fact({ label, value }: { label: string; value: string }) { return <View style={s.fact}><Text style={s.caption}>{label}</Text><Text style={s.value}>{value}</Text></View>; }

/** Static activated limits; never a capacity reservation or readiness claim. */
export function InferenceExecutionDetails({ model }: { model: RuntimeServingState | undefined }) {
  if (!model || model.execution_contract === undefined && model.execution_contract_error === undefined) return null;
  try {
    const contract = object(model.execution_contract);
    demand(contract.schema_version === 'skeleton.local_inference.execution_contract.v1' && contract.provider_id === 'local');
    demand(hash(contract.model_digest) === hash(model.model_digest));
    text(contract.model_id); const source = text(contract.source_model_id);
    nullableHash(contract.runtime_digest); nullableHash(contract.execution_profile_digest);
    const digest = hash(contract.contract_digest), limits = object(contract.generation_limits), accounting = object(contract.input_accounting), capacity = object(contract.capacity), lifecycle = object(contract.lifecycle);
    const context = integer(limits.context_window, 1), output = integer(limits.max_output_tokens, 1, 8192);
    const total = limits.max_total_tokens === null ? null : integer(limits.max_total_tokens, 1);
    demand(typeof limits.shared_context === 'boolean'); text(limits.tokenizer); text(limits.limits_source);
    for (const key of ['tokenizer_max_chars', 'tokenizer_max_tokens', 'max_output_utf8_bytes']) if (limits[key] !== undefined) integer(limits[key], 1);
    const protocols = array(contract.protocols, 3).map(value => text(value, 32));
    demand(protocols.length > 0 && new Set(protocols).size === protocols.length && protocols.every(value => ['text-generation', 'tool-calls', 'structured-output'].includes(value)));
    const basis = text(accounting.basis, 64);
    demand(['native_tokenizer', 'utf8_byte_tokens', 'reference_tokens', 'conservative_utf8_bytes', 'backend_token_counter'].includes(basis) && (accounting.exact === null || typeof accounting.exact === 'boolean') && typeof accounting.prepared_input === 'boolean');
    demand(basis === 'backend_token_counter' ? accounting.exact === null : accounting.exact === (basis !== 'conservative_utf8_bytes'));
    const active = integer(capacity.max_concurrency, 1, 32), queued = integer(capacity.max_queue_size, 0, 65536), batch = integer(capacity.max_batch_size, 1, 4096);
    const batchTokens = capacity.max_batch_tokens === null ? null : integer(capacity.max_batch_tokens, 1);
    if (model.capacity?.operator_max_concurrency !== undefined) demand(active === model.capacity.operator_max_concurrency);
    if (model.capacity?.operator_max_queue_size !== undefined) demand(queued === model.capacity.operator_max_queue_size);
    for (const key of ['cooperative_cancellation', 'deadline_includes_preparation', 'worker_slot_released_on_physical_drain', 'cache_is_scope_bound']) demand(lifecycle[key] === true);
    return <Detail key={digest} title="Activated local execution limits" summary={`${count(context)} context · ${count(output)} output tokens · ${accounting.exact === true ? 'Exact token accounting' : accounting.exact === false ? 'Conservative token accounting' : 'Backend token accounting'}`}>
      <View style={s.facts}><Fact label="Context window" value={`${count(context)} tokens`} /><Fact label="Output ceiling" value={`${count(output)} tokens`} /><Fact label="Total ceiling" value={total === null ? 'Not separately declared' : `${count(total)} tokens`} /><Fact label="Static workers / queue" value={`${active} / ${queued}`} /><Fact label="Batch items / tokens" value={`${batch} / ${batchTokens === null ? 'Not declared' : count(batchTokens)}`} /></View>
      <Text style={s.caption}>Protocols: {protocols.map(human).join(', ')}. Accounting: {human(basis)}. Prepared native input: {accounting.prepared_input ? 'Available' : 'Not reported'}.</Text>
      <Text style={s.caption}>Source model: {source}. Contract {fingerprint(digest)}. These are activated ceilings; current pressure and normal admission determine whether new work can start.</Text>
      <Text style={s.caption}>Request deadlines include preparation. Cancelled work retains its worker slot until physical drain; derived cache entries remain scope bound.</Text>
    </Detail>;
  } catch { return <Unavailable title="Local execution" />; }
}

/** Inspect one retained numeric input, with the current partition's exact pins. */
export function LearnerReferenceDetails({ partition, observed }: { partition: RuntimeLearningPartition; observed: RuntimeControlObservation }) {
  if (partition.reference_explanation === undefined) return null;
  if (partition.reference_explanation === null) return <Text style={s.caption}>Numeric sensitivity is withheld until this learner has fresh, ready evidence and a retained input.</Text>;
  try {
    demand(partition.readiness === 'ready' && partition.quarantined !== true);
    const explanation = object(partition.reference_explanation), binding = object(explanation.binding), limits = object(explanation.limits);
    demand(explanation.schema_version === 'skeleton.runtime.learning.explanation.v1' && explanation.feature_schema === 'skeleton.runtime.learning.features.v1' && explanation.advisory_only === true && explanation.basis === 'retained_numeric_replay' && explanation.method === 'analytic_local_partial_derivative');
    demand(binding.tenant_id === observed.scope.tenantId && binding.scope_id === observed.state.learning.scope_id && binding.partition_id === partition.partition_id && binding.model_selection_digest === partition.model_selection_digest && binding.state_version === partition.state_version);
    text(binding.tenant_id, 512); text(binding.scope_id, 192); hash(binding.partition_id); hash(binding.model_selection_digest); integer(binding.state_version, 1); nullableHash(binding.stored_state_digest); integer(binding.learning_policy_version, 1);
    demand(hash(binding.learning_policy_digest) === hash(explanation.policy_digest));
    const predictor = hash(explanation.predictor_digest), digest = hash(explanation.explanation_digest), sample = hash(explanation.sample_outcome_id);
    hash(explanation.sample_digest); hash(explanation.input_digest); nullableHash(explanation.state_latest_source_digest);
    demand(explanation.requested_source_snapshot_digest === null && limits.feature_count === 12 && limits.output_count === 3 && limits.top_features_per_output === 4);
    const outputs = array(explanation.outputs, 3).map(value => {
      const row = object(value), name = text(row.output_name, 64), prediction = finite(row.value, 0, 1);
      demand(OUTPUTS.includes(name)); const seen = new Set<number>();
      const features = array(row.top_features, 4).map(item => {
        const feature = object(item), index = integer(feature.feature_index, 0, 11);
        demand(feature.feature_name === FEATURES[index] && !seen.has(index)); seen.add(index);
        return { name: FEATURES[index], value: finite(feature.feature_value, 0, 1), sensitivity: finite(feature.local_sensitivity, -16384, 16384) };
      });
      demand(features.length > 0); return { name, prediction, features };
    });
    demand(outputs.length === 3 && new Set(outputs.map(row => row.name)).size === 3);
    const limitations = array(explanation.limitations, 4).map(value => text(value, 512));
    return <Detail key={digest} title="Operational predictor sensitivity" summary={`Historical numeric input · policy ${binding.learning_policy_version} · predictor ${fingerprint(predictor)}`}>
      <Text style={s.caption}>Each signed value describes this predictor&apos;s local response to a normalized feature. It is not causal importance, an additive explanation, answer correctness or game quality.</Text>
      {outputs.map(row => <View key={row.name} style={s.output}><Text style={s.title}>{human(row.name)} · {row.prediction.toFixed(3)}</Text>{row.features.map(feature => <Text key={feature.name} style={s.caption}>{human(feature.name)}: input {feature.value.toFixed(3)} · local sensitivity {feature.sensitivity >= 0 ? '+' : ''}{feature.sensitivity.toFixed(4)}</Text>)}</View>)}
      <Text style={s.caption}>Retained outcome {fingerprint(sample)} · explanation {fingerprint(digest)}. The latest source pin belongs to the predictor state and does not identify the source of this historical replay input.</Text>
      {limitations.map((value, index) => <Text key={index} style={s.caption}>{value}</Text>)}
    </Detail>;
  } catch { return <Unavailable title="Learner sensitivity" />; }
}

export function MaintenanceQueueDetails({ maintenance }: { maintenance: RuntimeControlState['maintenance'] }) {
  if (maintenance.handler_registry === undefined && maintenance.queue_summary === undefined) return null;
  try {
    const registry = object(maintenance.handler_registry), queue = object(maintenance.queue_summary);
    demand(registry.schema_version === 'jeeves.maintenance_handler_registry.v1' && registry.execution_authority === 'none' && registry.max_local_kinds === 5);
    const kinds = new Set<string>();
    const handlers = array(registry.entries, 5).map(value => {
      const row = object(value), kind = text(row.kind, 64); demand(KINDS.includes(kind) && !kinds.has(kind)); kinds.add(kind);
      for (const key of ['registered', 'retry_safe_declared', 'augmentation_required', 'policy_permits']) demand(typeof row[key] === 'boolean');
      demand(row.registered ? typeof row.handler_version === 'string' && text(row.handler_version, 192) && row.retry_safe_declared : row.handler_version === null && row.retry_safe_declared === false && row.policy_permits === false);
      demand(row.augmentation_required === (kind === 'eligible_augmentation') && row.policy_permits === (row.registered === true && maintenance.policy?.enabled === true && (kind !== 'eligible_augmentation' || maintenance.policy.augmentation_enabled === true)));
      return { kind, registered: row.registered === true, enabled: row.policy_permits === true, version: row.handler_version as string | null };
    });
    demand(handlers.length === 5 && integer(registry.registered_count, 0, 5) === handlers.filter(row => row.registered).length);
    demand(queue.schema_version === 'jeeves.maintenance_queue_summary.v1' && queue.execution_authority === 'none' && queue.host_admission_required === true && typeof queue.available === 'boolean');
    if (queue.scope_id !== null) text(queue.scope_id, 192);
    if (!queue.available) { text(queue.reason, 128); return <Text style={s.caption}>Maintenance queue inspection is unavailable while the controller is closed.</Text>; }
    demand(queue.clock_basis === 'last_persisted_host_logical_clock'); boundedNs(queue.as_of_logical_ns);
    const states = object(queue.state_counts); const stateKeys = ['ready', 'retry_wait', 'running', 'completed', 'failed', 'unknown'];
    const retained = integer(queue.retained_tasks), pending = integer(queue.pending_tasks); demand(pending <= retained && stateKeys.reduce((sum, key) => sum + integer(states[key]), 0) === retained);
    demand(integer(states.ready) + integer(states.retry_wait) + integer(states.running) === pending);
    demand(integer(queue.returned_tasks, 0, 100) <= retained); integer(queue.unknown_kind_tasks);
    for (const key of ['backoff_tasks', 'due_queued_tasks']) if (queue[key] !== null) demand(integer(queue[key]) <= pending);
    for (const key of ['oldest_pending_created_at_ns', 'oldest_pending_age_ns']) boundedNs(queue[key]);
    const counts = array(queue.kind_counts, 5); demand(counts.length === 5);
    const kindCounts = new Set<string>();
    let knownTasks = 0;
    for (const value of counts) { const row = object(value), kind = text(row.kind, 64); demand(KINDS.includes(kind) && !kindCounts.has(kind)); kindCounts.add(kind); const total = integer(row.total); knownTasks += total; for (const key of ['pending', 'running', 'failed']) demand(integer(row[key]) <= total); demand(integer(row.running) <= integer(row.pending)); }
    demand(knownTasks + integer(queue.unknown_kind_tasks) === retained);
    for (const task of maintenance.recent_tasks ?? []) if (task.scope_id !== undefined && queue.scope_id !== null) demand(task.scope_id === queue.scope_id);
    array(queue.limitations, 4).forEach(value => text(value, 512));
    return <Detail title="Maintenance queue and handlers" summary={`${count(pending)} pending · ${count(retained)} retained · ${registry.registered_count} registered local handlers`}>
      <View style={s.facts}><Fact label="Queued / backing off" value={`${queue.due_queued_tasks === null ? 'Unknown' : count(Number(queue.due_queued_tasks))} / ${queue.backoff_tasks === null ? 'Unknown' : count(Number(queue.backoff_tasks))}`} /><Fact label="Running / failed" value={`${states.running} / ${states.failed}`} /><Fact label="Oldest pending age" value={seconds(queue.oldest_pending_age_ns)} /></View>
      {handlers.map(row => <View key={row.kind} style={s.fact}><Text style={s.value}>{human(row.kind)}</Text><Text style={s.caption}>{row.registered ? `Registered · ${row.enabled ? 'Policy enabled' : 'Policy disabled'} · version ${row.version!.slice(0, 32)}` : 'No registered handler'}</Text></View>)}
      <Text style={s.caption}>Counts cover retained tasks in this scope. Timing uses the last saved host clock. Fresh resource observations, quiet time and physical custody are checked again before any work runs.</Text>
    </Detail>;
  } catch { return <Unavailable title="Maintenance queue" />; }
}

const BLOCKERS: Record<string, string> = { maintenance_disabled: 'Maintenance is disabled', coordination_unavailable: 'Coordination is unavailable', host_foreground_pending: 'Foreground work is pending', handler_unavailable: 'No handler is registered', handler_changed: 'The handler version changed', augmentation_disabled: 'Replay adaptation is disabled', logical_clock_unavailable: 'No host clock has been saved', task_timing_unknown: 'The task timing is unavailable', retry_backoff: 'Waiting for retry backoff', circuit_open: 'The scoped circuit is open', host_custody_held: 'Another worker holds host custody', scope_custody_held: 'Another worker holds scope custody', result_backpressure: 'Result receipts have reached capacity', task_observation_changed: 'The task observation changed', physical_drain_required: 'Physical drain proof is required', physical_custody_running: 'The worker still holds physical custody', task_completed: 'The task completed', task_failed: 'The task failed', unknown_task_state: 'The task state is unknown' };
export function MaintenanceTaskScheduling({ task }: { task: RuntimeMaintenanceTask }) {
  if (task.scheduling === undefined) return null;
  try {
    const value = object(task.scheduling), state = text(value.schedule_state, 64);
    demand(value.schema_version === 'jeeves.maintenance_task_scheduling.v1' && value.execution_authority === 'none' && value.host_admission_required === true && ['terminal', 'running', 'blocked', 'awaiting_host_admission', 'unknown'].includes(state));
    demand(state === 'unknown' || state === 'terminal' && ['completed', 'failed'].includes(task.state ?? '') || state === 'running' && task.state === 'running' || ['blocked', 'awaiting_host_admission'].includes(state) && ['ready', 'retry_wait'].includes(task.state ?? ''));
    const blockers = array(value.blockers, 16).map(item => text(item, 96));
    demand(blockers.every(item => /^[a-z_]+$/.test(item)) && new Set(blockers).size === blockers.length && (state !== 'awaiting_host_admission' || blockers.length === 0));
    for (const key of ['as_of_logical_ns', 'remaining_backoff_ns', 'admission_wait_ns', 'work_age_ns']) boundedNs(value[key]);
    if (value.effective_priority !== null) integer(value.effective_priority, 0, 100);
    demand(value.priority_age_basis === 'last_progress_updated_at_ns');
    return <View style={s.schedule}><Text style={s.caption}>{state === 'awaiting_host_admission' ? 'Waiting for fresh host admission' : human(state)}{value.remaining_backoff_ns !== null && Number(value.remaining_backoff_ns) > 0 ? ` · backoff ${seconds(value.remaining_backoff_ns)}` : ''}</Text>{blockers.map(reason => <Text key={reason} style={s.caption}>{BLOCKERS[reason] ?? 'An unrecognized scheduling constraint was reported'}</Text>)}</View>;
  } catch { return <Unavailable title="Task scheduling" />; }
}

const s = StyleSheet.create({
  card: { borderWidth: 1, borderColor: '#334155', borderRadius: 10, padding: 10, gap: 8, backgroundColor: '#101b2d' }, heading: { flexDirection: 'row', gap: 12, alignItems: 'center', minHeight: 42 }, copy: { flex: 1, gap: 4 }, title: { color: '#e2e8f0', fontSize: 12, lineHeight: 19, fontWeight: '600' }, caption: { color: '#94a3b8', fontSize: 11, lineHeight: 17 }, action: { color: '#c4b5fd', fontSize: 11, fontWeight: '600' }, body: { gap: 9 }, facts: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 }, fact: { flexGrow: 1, flexBasis: 140, gap: 3 }, value: { color: '#cbd5e1', fontSize: 11, lineHeight: 18 }, output: { gap: 4, paddingVertical: 7, borderTopColor: '#334155', borderTopWidth: StyleSheet.hairlineWidth }, unavailable: { color: '#d1b98d', fontSize: 11, lineHeight: 17 }, schedule: { width: '100%', gap: 2 },
});
