import React, { useEffect, useRef, useState } from 'react';
import { Text, TextInput, TouchableOpacity, View } from 'react-native';
import type { StudioGoal } from '../../product/gameStudioAgentClient';
import { useStudioForeground } from './useStudioForeground';
import s from './GameLearningWorkspace.styles';

type Props = {
  goal: StudioGoal;
  busy: boolean;
  disabled?: boolean;
  error?: string | null;
  advance: () => Promise<boolean>;
};

/** Continues the existing version-fenced owner; never issues a second workflow. */
export default function StudioGoalContinuityPanel({ goal, busy, disabled, error, advance }: Props) {
  const [enabled, setEnabled] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [settlements, setSettlements] = useState(0);
  const active = useStudioForeground();
  const advancing = useRef(false);
  const mounted = useRef(true);
  const currentAdvance = useRef(advance);
  currentAdvance.current = advance;
  const previousGoal = useRef(goal.goal_id);
  const expired = !!goal.expires_at && Date.parse(goal.expires_at) <= Date.now();
  const available = ['ready', 'waiting'].includes(goal.status) && !expired
    && !goal.stop_requested
    && (goal.status === 'waiting' || goal.cursor < goal.max_steps || goal.recovery?.reconciliation_only === true)
    && goal.integrity?.status !== 'legacy_unverified';

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    if (previousGoal.current === goal.goal_id) return;
    previousGoal.current = goal.goal_id;
    setEnabled(false);
    setNotice(null);
  }, [goal.goal_id]);

  useEffect(() => {
    if (!enabled || (active && !disabled && !error && available)) return;
    setEnabled(false);
    setNotice(!active ? 'Continuation paused because the workspace is in the background. Return and continue when ready.'
      : disabled ? 'Continuation paused while project changes are being saved.'
        : error ? 'Continuation stopped after an unconfirmed request. Refresh the saved goal before continuing.'
          : expired ? 'Continuation stopped at the authorization limit. Review the saved goal before renewing its scope.'
            : 'Continuation reached the saved goal’s current boundary.');
  }, [enabled, active, disabled, error, available, expired]);

  useEffect(() => {
    if (!enabled || !active || busy || disabled || !available || error
      || goal.recovery?.next_action !== 'advance'
      || goal.recovery?.automatic_continuation_available !== true
      || advancing.current) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      if (cancelled || advancing.current) return;
      advancing.current = true;
      void currentAdvance.current().then(confirmed => {
        if (!confirmed && !cancelled) {
          setEnabled(false);
          setNotice('Continuation stopped. Inspect the saved goal and its current operation before trying again.');
        }
      }).catch(() => {
        if (!cancelled) { setEnabled(false); setNotice('Continuation stopped because the next step was not confirmed.'); }
      }).finally(() => {
        advancing.current = false;
        // The parent's busy/version updates may commit before this promise
        // settles. Trigger another scheduling pass once the serial slot opens.
        if (mounted.current) setSettlements(value => value + 1);
      });
    }, goal.status === 'waiting' ? 2500 : 1000);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [enabled, active, busy, disabled, available, error, goal.goal_id, goal.version, goal.status,
    goal.recovery?.next_action, goal.recovery?.automatic_continuation_available, settlements]);

  return <View style={s.source}>
    <Text accessibilityRole="header" style={s.projectName}>Continue the saved workflow</Text>
    <Text style={s.description}>Jeeves can continue the bounded slices configured below within this goal’s existing action, model, job and time limits. Every decision uses fresh confirmed source and work receipts.</Text>
    <TouchableOpacity accessibilityRole="switch" accessibilityLabel="Continue within this goal’s granted budget"
      accessibilityState={{ checked: enabled, disabled: !enabled && (!available || !!disabled || busy || !active) }}
      disabled={!enabled && (!available || !!disabled || busy || !active)}
      onPress={() => { setEnabled(value => !value); setNotice(null); }} style={[s.button, enabled && s.primaryButton]}>
      <Text style={s.buttonText}>{enabled ? 'Stop continuing after the current issued step' : 'Continue within this goal’s granted budget'}</Text>
    </TouchableOpacity>
    {enabled && <Text accessibilityLiveRegion="polite" style={s.success}>{busy ? 'Following the currently issued step.'
      : goal.recovery?.next_action === 'wait' ? 'Waiting for the current worker; no duplicate work is being started.'
        : goal.recovery?.automatic_continuation_available ? 'Continuation is active while this workspace stays open.'
          : 'Waiting for the saved goal owner to confirm that another step is available.'}</Text>}
    {notice && <Text accessibilityLiveRegion="polite" style={s.notice}>{notice}</Text>}
    <Text style={s.dim}>Stopping continuation leaves the current issued operation running. Use Pause or Cancel to request a stop at its safe boundary. Retry, fresh model attempts and authorization renewal always require your action.</Text>
  </View>;
}

export function StudioGoalLoopDetails({ goal, busy, disabled, decisions, changeDecisions, waitSeconds, changeWaitSeconds, refreshSource }: {
  goal: StudioGoal; busy: boolean; disabled?: boolean;
  decisions: string; changeDecisions: (value: string) => void;
  waitSeconds: string; changeWaitSeconds: (value: string) => void;
  refreshSource: () => Promise<boolean>;
}) {
  const [acknowledged, setAcknowledged] = useState(false);
  useEffect(() => { setAcknowledged(false); }, [goal.goal_id, goal.version, goal.recovery?.observed_tree_digest]);
  const feedback = goal.candidate_feedback;
  const recovery = goal.recovery;
  const blocked = busy || !!disabled;
  return <View style={s.source}>
    <Text accessibilityRole="header" style={s.projectName}>Bounded planning loop</Text>
    <View style={s.fieldGroup}>
      <Text style={s.label}>Maximum AI decisions per advance (1–4)</Text>
      <TextInput accessibilityLabel="Maximum AI decisions per advance" value={decisions} onChangeText={changeDecisions}
        editable={!blocked} keyboardType="number-pad" maxLength={1} style={s.field} />
    </View>
    <View style={s.fieldGroup}>
      <Text style={s.label}>Wait for issued work (0–10 seconds)</Text>
      <TextInput accessibilityLabel="Wait for issued work seconds" value={waitSeconds} onChangeText={changeWaitSeconds}
        editable={!blocked} keyboardType="number-pad" maxLength={2} style={s.field} />
    </View>
    <Text style={s.dim}>Steps per advance still cap actions. Each request shares a 20-second planning slice and the original total grants. A busy worker or pending AI receipt yields safely for the next request.</Text>
    {goal.last_advance?.yield_reason && <Text accessibilityLiveRegion="polite" style={s.muted}>Last slice: {goal.last_advance.yield_reason.replace(/_/g, ' ')}.</Text>}
    {feedback && <View style={s.source}>
      <Text style={s.projectName}>Measured candidate memory</Text>
      <Text style={s.dim}>These exact edit/review observations guide later proposals. They do not certify creative quality or authorize training and promotion.</Text>
      {!feedback.source_current && <Text style={s.notice}>This projection belongs to an older source. Fresh current-source evidence is required.</Text>}
      {feedback.rounds.map(round => <View key={round.feedback_digest} style={s.checkpoint}>
        <Text style={round.status === 'rejected' ? s.notice : s.success}>Candidate {round.review_job_id.slice(0, 12)} · {round.status}{round.restored ? ' · incumbent restored' : ''}</Text>
        <Text style={s.muted}>{round.edit_step_digests.length} linked edit{round.edit_step_digests.length === 1 ? '' : 's'} · {round.applicable_to_current_tree && feedback.source_current ? 'current source' : 'retained historical observation'}</Text>
        {round.failures.slice(0, 3).map((failure, index) => <Text key={index} style={s.dim}>{failure.code.replace(/_/g, ' ')}</Text>)}
      </View>)}
      {feedback.rounds.length === 0 && <Text style={s.muted}>The baseline is pinned; no matched edited candidate has completed yet.</Text>}
      {!!feedback.excluded_unmatched_reviews && <Text style={s.dim}>{feedback.excluded_unmatched_reviews} unmatched review{feedback.excluded_unmatched_reviews === 1 ? '' : 's'} excluded from candidate memory.</Text>}
    </View>}
    {recovery?.source_refresh_available === true && <View style={s.source}>
      <Text style={s.projectName}>A newer saved source is available</Text>
      <Text style={s.description}>Review and explicitly pin revision {recovery.observed_project_version} to this idle goal. Old queued follow-ups and source-dependent completion are cleared. Original budgets, baseline, history and permissions stay fixed.</Text>
      <Text selectable style={s.dim}>Source {recovery.observed_tree_digest}</Text>
      <TouchableOpacity accessibilityRole="checkbox" accessibilityState={{ checked: acknowledged, disabled: blocked }} disabled={blocked}
        onPress={() => setAcknowledged(value => !value)} style={s.checkbox}>
        <Text style={s.checkboxText}>{acknowledged ? '☑' : '☐'} I reviewed this exact saved source and want this goal to use it.</Text>
      </TouchableOpacity>
      <TouchableOpacity accessibilityRole="button" accessibilityState={{ disabled: blocked || !acknowledged }} disabled={blocked || !acknowledged}
        onPress={() => { void refreshSource(); }} style={[s.button, (blocked || !acknowledged) && s.disabled]}>
        <Text style={s.buttonText}>Pin the reviewed saved source</Text>
      </TouchableOpacity>
      <Text style={s.dim}>This does not run the planner or edit files. Incompatible numeric advice and cross-goal sharing are disabled until a compatible source is explicitly pinned.</Text>
    </View>}
    {!!goal.source_refresh_receipts?.length && <Text style={s.muted}>{goal.source_refresh_receipts.length} exact source refresh receipt{goal.source_refresh_receipts.length === 1 ? '' : 's'} retained; grants and counters were preserved.</Text>}
    {goal.source_refresh_receipts?.at(-1)?.numeric_source_compatible === false && <Text style={s.notice}>The refreshed structure is incompatible with the old numeric ranker. Its evidence remains retained; ranking and cross-goal export are suspended for this source.</Text>}
  </View>;
}
