/**
 * Recovery controls — cancel in-flight forge, clear seal from operator state,
 * reset run/report payloads. No secrets are persisted here.
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Banner, Button, Card, SectionTitle, StatusPill } from '../../skeletonForge/components/primitives';
import { C } from '../../skeletonForge/components/theme';
import type { OperatorError } from '../errors';
import { isTransient } from '../errors';
import type { RunPhase, RunSource } from '../hooks';

export interface RecoveryPanelProps {
  phase: RunPhase;
  source: RunSource;
  error: string | null;
  operatorError: OperatorError | null;
  sealPresent: boolean;
  onCancel: () => void;
  onClearSeal: () => void;
  onResetRun: () => void;
  testID?: string;
}

export default function RecoveryPanel({
  phase,
  source,
  error,
  operatorError,
  sealPresent,
  onCancel,
  onClearSeal,
  onResetRun,
  testID,
}: RecoveryPanelProps) {
  const running = phase === 'running';
  const transient = operatorError ? isTransient(operatorError) : false;

  return (
    <View testID={testID}>
      <SectionTitle hint="Cancel · clear seal · reset">🛠 Recovery</SectionTitle>
      <Card testID="operator-recovery-status">
        <View style={st.head}>
          <StatusPill
            tone={running ? 'idle' : phase === 'error' ? 'bad' : phase === 'done' ? 'ok' : 'idle'}
            label={running ? `Running (${source ?? '…'})` : phase}
          />
          <StatusPill tone={sealPresent ? 'warn' : 'idle'} label={sealPresent ? 'Seal in memory' : 'No seal'} />
        </View>
        {error ? <Banner tone="bad">{error}</Banner> : null}
        {operatorError ? (
          <Text style={st.hint}>
            {operatorError.kind}
            {transient ? ' · transient — safe to retry' : ''}
            {operatorError.requestId ? ` · rid ${operatorError.requestId}` : ''}
          </Text>
        ) : (
          <Text style={st.lead}>
            Use these controls when a forge hangs, a seal is rejected, or you need a clean slate before the next run.
          </Text>
        )}
      </Card>
      <Card>
        <View style={st.actions}>
          <Button
            label="Cancel in-flight"
            tone="danger"
            onPress={onCancel}
            disabled={!running}
            testID="operator-recovery-cancel"
          />
          <Button
            label="Clear seal"
            tone="secondary"
            onPress={onClearSeal}
            disabled={!sealPresent}
            testID="operator-recovery-clear-seal"
          />
          <Button
            label="Reset run state"
            tone="ghost"
            onPress={onResetRun}
            disabled={phase === 'idle' && !error}
            testID="operator-recovery-reset"
          />
        </View>
        <Text style={st.note}>
          Seal tokens live only in operator UI state for this session. Clearing them does not revoke a minted seal on the engine.
        </Text>
      </Card>
    </View>
  );
}

const st = StyleSheet.create({
  head: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 10 },
  lead: { color: C.mute, fontSize: 13, lineHeight: 19 },
  hint: { color: C.amber, fontSize: 12, fontWeight: '600', marginTop: 6 },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  note: { color: C.dim, fontSize: 11, marginTop: 12, lineHeight: 16 },
});
