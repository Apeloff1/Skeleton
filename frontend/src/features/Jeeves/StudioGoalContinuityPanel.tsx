import React, { useEffect, useRef, useState } from 'react';
import { Text, TouchableOpacity, View } from 'react-native';
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
    && (goal.status === 'waiting' || goal.cursor < goal.max_steps)
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
    <Text style={s.description}>Jeeves can continue one confirmed step at a time within this goal’s existing action, model, job and time limits.</Text>
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
