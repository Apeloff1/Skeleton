/**
 * Per-project build status. Stages come from ForgeRunPanel (the same panel
 * the cockpit view renders). Cockpit STATUS is a user action through the
 * existing console hook — this screen does not poll.
 */
import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import type { StepAction } from '../../foundation/model';
import type { RunPhase } from '../../hooks';
import type { RunPayload } from '../../types';
import { Banner, Button, SectionTitle } from '../primitives';
import ForgeRunPanel from '../ForgeRunPanel';
import { C } from '../theme';

export function BuildStatusScreen({
  title, phase, payload, error, startedAt, finishedAt, now, onCancel, onRetry,
  guidance, onGuidance, consoleBusy, consoleSummary, consoleOk, consoleFailures, onAskCockpit,
  onBrief, onProjects, onOpenCockpit,
}: {
  title: string;
  phase: RunPhase;
  payload: RunPayload | null;
  error: string | null;
  startedAt: number | null;
  finishedAt: number | null;
  now: number;
  onCancel?: () => void;
  onRetry?: () => void;
  guidance: StepAction;
  onGuidance: (action: StepAction) => void;
  consoleBusy: boolean;
  consoleSummary: string | null;
  consoleOk: boolean | null;
  consoleFailures: number;
  onAskCockpit: () => void;
  onBrief: () => void;
  onProjects: () => void;
  onOpenCockpit: () => void;
}) {
  return (
    <ScrollView contentContainerStyle={st.body} testID="studio-build" keyboardShouldPersistTaps="handled">
      <SectionTitle hint="Forge run">{title}</SectionTitle>
      <View style={st.row}>
        <Button label="Back to brief" tone="ghost" compact onPress={onBrief} testID="studio-back-brief" />
        <Button label="All projects" tone="ghost" compact onPress={onProjects} testID="studio-back" />
        <Button label="Forge cockpit" tone="ghost" compact onPress={onOpenCockpit} testID="studio-cockpit" />
      </View>
      <ForgeRunPanel
        phase={phase}
        payload={payload}
        error={error}
        startedAt={startedAt}
        finishedAt={finishedAt}
        now={now}
        onCancel={onCancel}
        onRetry={onRetry}
        testID="studio-run-panel"
      />
      <View testID="studio-next-step">
        <Text style={st.kicker} accessibilityRole="header">Next</Text>
        <Text style={st.copy}>{guidance.detail}</Text>
        {guidance.id === 'wait' ? null : (
          <Button label={guidance.label} onPress={() => onGuidance(guidance)} testID="studio-next-action" />
        )}
      </View>
      <View testID="studio-console">
        <Text style={st.kicker} accessibilityRole="header">Cockpit</Text>
        {consoleSummary ? (
          <Banner tone={consoleOk === false ? 'bad' : 'idle'} testID="studio-console-summary">{consoleSummary}</Banner>
        ) : (
          <Text style={st.copy}>No cockpit check yet. Ask once for STATUS — this does not keep asking.</Text>
        )}
        {consoleFailures > 0 ? <Text style={st.meta}>{consoleFailures} cockpit {consoleFailures === 1 ? 'command' : 'commands'} failed</Text> : null}
        <Button
          label={consoleSummary ? 'Ask the cockpit again' : 'Ask the cockpit for status'}
          tone="secondary"
          onPress={onAskCockpit}
          busy={consoleBusy}
          testID="studio-console-status"
          a11yHint="Sends STATUS once through the forge cockpit"
        />
      </View>
    </ScrollView>
  );
}

const st = StyleSheet.create({
  body: { padding: 16, paddingBottom: 48, gap: 8 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  kicker: { color: C.textStrong, fontSize: 15, fontWeight: '800', marginTop: 8 },
  copy: { color: C.text, fontSize: 15, lineHeight: 22, marginBottom: 8 },
  meta: { color: C.mute, fontSize: 13, marginBottom: 8 },
});
