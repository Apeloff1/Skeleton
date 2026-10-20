import React from 'react';
import { Text, TextInput, TouchableOpacity, View } from 'react-native';
import type { StudioQualityPolicy, StudioQualityProgress, StudioQualityMeasuredProgress, StudioNumericAdaptation } from '../../product/gameStudioAgentClient';
import s, { gameLearningColors as C } from './GameLearningWorkspace.styles';
import v from './GameConsoleStudio.styles';

export type StudioQualityDraft = {
  rounds: string; frames: string; steps: string; errors: string; warnings: string; baseline: string;
  restore: boolean; adaptiveRanking: boolean;
};
export const DEFAULT_QUALITY_DRAFT: StudioQualityDraft = {
  rounds: '2', frames: '2', steps: '64', errors: '0', warnings: '128', baseline: '', restore: true, adaptiveRanking: false,
};

export function studioQualityPolicy(draft: StudioQualityDraft): StudioQualityPolicy {
  const number = (value: string, min: number, max: number, label: string) => {
    if (!/^\d+$/.test(value) || !Number.isSafeInteger(Number(value)) || Number(value) < min || Number(value) > max) throw new Error(`${label} must be between ${min} and ${max}.`);
    return Number(value);
  };
  return {
    schema_version: 'skeleton.game.studio_quality_policy.v1',
    ...(draft.baseline.trim() ? { baseline_review_job_id: draft.baseline.trim() } : {}),
    max_refinement_rounds: number(draft.rounds, 1, 4, 'Refinement rounds'),
    min_available_frames: number(draft.frames, 1, 25, 'Observed frames'),
    min_executed_steps: number(draft.steps, 1, 512, 'Simulation steps'),
    max_error_findings: number(draft.errors, 0, 128, 'Maximum error findings'),
    max_warning_findings: number(draft.warnings, 0, 128, 'Maximum warning findings'),
    require_no_regression: true, restore_on_regression: draft.restore,
    adaptive_ranking: draft.adaptiveRanking,
  };
}

export function StudioQualityForm({ enabled, available, changeEnabled, draft, changeDraft, disabled }: {
  enabled: boolean; available: boolean; changeEnabled: (value: boolean) => void;
  draft: StudioQualityDraft; changeDraft: (value: StudioQualityDraft) => void; disabled?: boolean;
}) {
  const fields: { key: 'rounds' | 'frames' | 'steps' | 'errors' | 'warnings'; label: string; bounds: string }[] = [
    { key: 'rounds', label: 'Refinement rounds', bounds: '1–4' },
    { key: 'frames', label: 'Minimum observed frames', bounds: '1–25' },
    { key: 'steps', label: 'Minimum simulation steps', bounds: '1–512' },
    { key: 'errors', label: 'Maximum error findings', bounds: '0–128' },
    { key: 'warnings', label: 'Maximum warning findings', bounds: '0–128' },
  ];
  return <View style={s.source}>
    <TouchableOpacity accessibilityRole="checkbox" accessibilityState={{ checked: enabled && available, disabled: !available || disabled }}
      disabled={!available || disabled} onPress={() => changeEnabled(!enabled)} style={s.checkbox}>
      <Text style={s.checkboxText}>{enabled && available ? '☑' : '☐'} Require measured acceptance before packaging</Text>
    </TouchableOpacity>
    <Text style={s.dim}>Available for original-game runs with simulation and review. The baseline stays fixed; each new source revision needs its own matched observation. Numerical acceptance describes this workload.</Text>
    {enabled && available && <>
      <View style={v.responsiveCards}>{fields.map(field => <View key={field.key} style={s.fieldGroup}>
        <Text style={s.label}>{field.label} ({field.bounds})</Text>
        <TextInput accessibilityLabel={field.label} value={draft[field.key]} keyboardType="number-pad" maxLength={3}
          editable={!disabled} onChangeText={value => changeDraft({ ...draft, [field.key]: value })} style={s.field} />
      </View>)}</View>
      <Text style={s.label}>Reference review job (optional)</Text>
      <TextInput accessibilityLabel="Reference review job" value={draft.baseline} editable={!disabled} maxLength={128}
        onChangeText={baseline => changeDraft({ ...draft, baseline })} placeholder="Use this goal’s first completed review" placeholderTextColor={C.textDim} style={s.field} />
      <TouchableOpacity accessibilityRole="checkbox" accessibilityState={{ checked: draft.restore, disabled }} disabled={disabled}
        onPress={() => changeDraft({ ...draft, restore: !draft.restore })} style={s.checkbox}>
        <Text style={s.checkboxText}>{draft.restore ? '☑' : '☐'} Restore the pinned source if a candidate is rejected</Text>
      </TouchableOpacity>
      <Text style={s.dim}>Restoration uses this run’s edit grant. Refinement, simulation, review and packaging consume the visible action, model and background-job budgets above.</Text>
      <TouchableOpacity accessibilityRole="checkbox" accessibilityState={{ checked: draft.adaptiveRanking, disabled }} disabled={disabled}
        onPress={() => changeDraft({ ...draft, adaptiveRanking: !draft.adaptiveRanking })} style={s.checkbox}>
        <Text style={s.checkboxText}>{draft.adaptiveRanking ? '☑' : '☐'} Learn numeric control suggestions during this goal</Text>
      </TouchableOpacity>
      <Text style={s.dim}>Allow local learning from this goal’s matched original-game reviews. Jeeves uses the results to suggest mechanics edits; each edit still needs the recorded simulation and review checks.</Text>
    </>}
  </View>;
}

const STATES: Record<StudioQualityMeasuredProgress['status'], string> = {
  baseline_required: 'Waiting for a measured baseline', candidate_required: 'Waiting for the current source review',
  accepted: 'Measured acceptance met', rejected: 'Current candidate rejected',
};
const FAILURE_LABELS: Record<string, string> = {
  insufficient_available_frames: 'Too few actual frames', insufficient_executed_steps: 'Too few actual simulation steps',
  excess_error_findings: 'Error finding limit exceeded', excess_warning_findings: 'Warning finding limit exceeded',
  unmatched_review_protocol: 'The review workload does not match the baseline', measured_regression: 'A measured baseline regression was observed',
};

export function StudioQualityObservation({ value, learning }: { value: StudioQualityProgress; learning?: StudioNumericAdaptation }) {
  if (value.status === 'unavailable') return <View style={s.source}>
    <Text accessibilityRole="header" style={s.projectName}>Measured acceptance unavailable</Text>
    <Text accessibilityRole="alert" style={s.notice}>{value.error.message}</Text>
    <Text style={s.dim}>Current evidence could not be confirmed. A previously accepted candidate does not authorize packaging until the owner can revalidate it.</Text>
  </View>;
  const candidate = value.candidate;
  return <View style={s.source}>
    <Text accessibilityRole="header" style={s.projectName}>Measured acceptance</Text>
    <Text accessibilityLiveRegion="polite" style={value.verified ? s.success : value.status === 'rejected' ? s.error : s.muted}>{STATES[value.status]}</Text>
    <Text style={s.description}>{value.baseline ? `Reference source version ${value.baseline.project_version} is pinned.` : 'The first completed reference review will establish the baseline.'} Current project version: {value.project_version}.</Text>
    {candidate && <>
      <View style={s.metrics}>{[
        ['Simulation steps', candidate.executed_steps?.toLocaleString() ?? 'Unobserved'],
        ['Observed frames', candidate.available_frames?.toLocaleString() ?? 'Unobserved'],
        ['Errors', String(candidate.finding_counts.error)], ['Warnings', String(candidate.finding_counts.warning)],
      ].map(([label, amount]) => <View key={label} style={s.metric}><Text style={s.metricValue}>{amount}</Text><Text style={s.metricLabel}>{label}</Text></View>)}</View>
      {candidate.priority_findings.slice(0, 4).map((finding, index) => <Text key={finding.finding_id || index} style={finding.severity === 'error' ? s.error : s.notice}>{finding.message}</Text>)}
    </>}
    {value.failures.map((failure, index) => <Text key={failure.code + index} style={s.notice}>
      {FAILURE_LABELS[failure.code] || failure.code.replaceAll('_', ' ')}
      {typeof failure.observed === 'number' ? ` · observed ${failure.observed}` : ''}
      {typeof failure.minimum === 'number' ? ` · minimum ${failure.minimum}` : ''}
      {typeof failure.maximum === 'number' ? ` · maximum ${failure.maximum}` : ''}
    </Text>)}
    {!!value.regressions.length && <Text style={s.notice}>Regressed measurements: {value.regressions.map(metric => metric.replaceAll('_', ' ')).join(', ')}</Text>}
    <Text style={s.muted}>{value.refinement_rounds} refinement rounds used · {value.remaining_refinement_rounds} remaining</Text>
    {value.incumbent_source_restored && <Text style={s.success}>The exact pinned source has been restored.</Text>}
    {learning && <View style={s.source}>
      <Text style={s.label}>Learning numeric control suggestions</Text>
      <Text accessibilityLiveRegion="polite" style={s.muted}>{learning.observations_seen ?? 0} matched observations · {learning.training_steps ?? 0} local learning steps · {learning.advice.length} current proposals</Text>
      {learning.status === 'source_shape_changed' && <Text style={s.dim}>The world changed beyond the numeric controls in this reference. Its measurements stay separate.</Text>}
    </View>}
    <Text style={s.dim}>Acceptance is limited to these recorded simulation, review and regression checks. It does not certify overall game quality or an unobserved desktop play session.</Text>
    <Text selectable style={s.dim}>Observation {value.receipt_digest.slice(0, 16)}…</Text>
  </View>;
}
