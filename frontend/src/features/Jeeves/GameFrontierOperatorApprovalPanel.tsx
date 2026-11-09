/** GF-P0-58: operator approval gate in front of Game Frontier event actions.
 *
 * Every event action raised by a surfaced RPG-style editor lands here as
 * `pending`. The operator must choose Approve or Reject and then confirm;
 * only a confirmed approval calls the authorized runtime (`runAction`, which
 * defaults to the Forge Studio public client and its authenticated apiClient
 * transport). States: pending / approved / rejected / error.
 */
import React, { useCallback, useEffect, useReducer, useRef } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import theme from '../../theme/tokens';
import {
  approvalReducer, mayCallRuntime, statusLabel, visibleApprovals,
  type ApprovalEntry, type ApprovalEvent, type ApprovalQueue, type FrontierEventAction,
} from './GameFrontierApprovalState';

export type RuntimeRunner = (action: FrontierEventAction) => Promise<{ receipt?: string } | void>;

export default function GameFrontierOperatorApprovalPanel({ actions, runAction, disabled = false }: {
  actions: readonly FrontierEventAction[];
  runAction: RuntimeRunner;
  disabled?: boolean;
}) {
  const [queue, rawDispatch] = useReducer(approvalReducer, [] as ApprovalQueue,
    () => actions.reduce<ApprovalQueue>((q, action) => approvalReducer(q, { type: 'request', action }), []));
  const latest = useRef(queue);
  latest.current = queue;
  const inFlight = useRef(new Set<string>());

  useEffect(() => {
    for (const action of actions.slice(0, 64)) rawDispatch({ type: 'request', action });
  }, [actions]);

  const dispatch = useCallback((event: ApprovalEvent) => rawDispatch(event), []);

  const confirm = useCallback(async (entry: ApprovalEntry) => {
    if (disabled || inFlight.current.has(entry.action.id)) return;
    const before = latest.current.find(e => e.action.id === entry.action.id);
    const after = approvalReducer(latest.current, { type: 'confirm', id: entry.action.id })
      .find(e => e.action.id === entry.action.id);
    if (!before || !after || before.status !== 'confirming'
        || visibleApprovals([before], actions).length !== 1) return;
    if (!mayCallRuntime(before, after)) {
      dispatch({ type: 'confirm', id: entry.action.id });
      return;
    }
    // Synchronous admission lock prevents repeated taps before React rerenders.
    inFlight.current.add(entry.action.id);
    latest.current = latest.current.map(e => e.action.id === entry.action.id ? after : e);
    dispatch({ type: 'confirm', id: entry.action.id });
    try {
      const result = await runAction(before.action);
      if (!result || typeof result.receipt !== 'string'
          || !/^[a-f0-9]{64}$/.test(result.receipt)) {
        throw new Error('Runtime returned no verified source receipt');
      }
      dispatch({ type: 'succeeded', id: entry.action.id, receipt: result.receipt });
    } catch {
      dispatch({ type: 'failed', id: entry.action.id, error: 'Runtime refused or could not verify the action' });
    } finally {
      inFlight.current.delete(entry.action.id);
    }
  }, [dispatch, runAction, disabled, actions]);

  const visible = visibleApprovals(queue, actions);
  return (
    <View style={styles.root} accessibilityLabel="Operator approval queue">
      <Text style={styles.heading} accessibilityRole="header">Operator approval</Text>
      {visible.length === 0 && <Text style={styles.muted}>No event actions are waiting.</Text>}
      {visible.map(entry => {
        const { action, status } = entry;
        return (
          <View key={action.id} style={styles.card} testID={'approval-' + action.id}
                accessibilityLabel={action.label + ': ' + statusLabel[status]}>
            <Text style={styles.title}>{action.label}</Text>
            <Text style={styles.muted}>{action.editor} · {action.action}</Text>
            <Text style={[styles.status, status === 'error' && styles.err,
              status === 'approved' && styles.ok, status === 'rejected' && styles.warn]}
              accessibilityLiveRegion="polite">{statusLabel[status]}</Text>
            {entry.error ? <Text style={styles.err}>{entry.error}</Text> : null}
            {entry.receipt ? <Text style={styles.muted}>Receipt {entry.receipt}</Text> : null}
            <View style={styles.row}>
              {status === 'pending' && <>
                <Btn label="Approve" a11y={'Approve ' + action.label} disabled={disabled}
                     onPress={() => dispatch({ type: 'ask', id: action.id, intent: 'approve' })} />
                <Btn label="Reject" a11y={'Reject ' + action.label} disabled={disabled}
                     onPress={() => dispatch({ type: 'ask', id: action.id, intent: 'reject' })} />
              </>}
              {status === 'confirming' && <>
                <Text style={styles.muted}>
                  {entry.intent === 'approve'
                    ? 'Confirm: send this action to the game runtime?'
                    : 'Confirm: reject this action?'}
                </Text>
                <Btn label="Confirm" a11y={'Confirm ' + entry.intent + ' ' + action.label}
                     disabled={disabled} onPress={() => { void confirm(entry); }} />
                <Btn label="Cancel" a11y={'Cancel ' + action.label}
                     onPress={() => dispatch({ type: 'cancel', id: action.id })} />
              </>}
              {status === 'error' &&
                <Btn label="Retry" a11y={'Retry ' + action.label} disabled={disabled}
                     onPress={() => dispatch({ type: 'retry', id: action.id })} />}
            </View>
          </View>
        );
      })}
    </View>
  );
}

function Btn({ label, a11y, onPress, disabled = false }: {
  label: string; a11y: string; onPress: () => void; disabled?: boolean;
}) {
  return (
    <TouchableOpacity accessibilityRole="button" accessibilityLabel={a11y}
      accessibilityState={{ disabled }} disabled={disabled} onPress={onPress} style={styles.btn}>
      <Text style={styles.btnText}>{label}</Text>
    </TouchableOpacity>
  );
}

const c = theme.colors;
const styles = StyleSheet.create({
  root: { gap: theme.spacing.sm },
  heading: { ...theme.typography.label, color: c.text },
  card: { padding: theme.spacing.md, borderRadius: theme.radii.md, borderWidth: 1,
    borderColor: c.border, backgroundColor: c.surface, gap: theme.spacing.xs },
  title: { ...theme.typography.body, color: c.text, fontWeight: '700' },
  muted: { ...theme.typography.caption, color: c.textMuted },
  status: { ...theme.typography.caption, color: c.text },
  ok: { color: c.success }, warn: { color: c.warning }, err: { color: c.danger },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: theme.spacing.sm, alignItems: 'center' },
  btn: { paddingHorizontal: theme.spacing.md, paddingVertical: theme.spacing.sm, minHeight: 44,
    justifyContent: 'center', borderRadius: theme.radii.sm, backgroundColor: c.surfaceAlt },
  btnText: { ...theme.typography.button, color: c.text },
});
