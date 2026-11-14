/**
 * Per-project build status. Stages come from ForgeRunPanel (the same panel
 * the cockpit view renders). Cockpit STATUS is a user action through the
 * existing console hook — this screen does not poll.
 */
import React from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import type { StepAction } from '../../foundation/model';
import type { RunPhase } from '../../hooks';
import { playHandoff } from '../../run';
import type { RunPayload, RunRequest } from '../../types';
import { useStudioA11y } from '../a11yContext';
import { Banner, Button, SectionTitle } from '../primitives';
import ForgeRunPanel from '../ForgeRunPanel';
import { ScaledText as Text } from '../ScaledText';
import { C } from '../theme';
import { PlayHandoffCard } from './PlayHandoffCard';

export function BuildStatusScreen({
  title, phase, payload, error, startedAt, finishedAt, now, onCancel, onRetry,
  onExport, exportBusy, exportError, outdated = false, request = null, live = true,
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
  onExport?: () => void;
  exportBusy?: boolean;
  exportError?: string | null;
  outdated?: boolean;
  /** Request that produced this build (target / playable scene choices). */
  request?: Pick<RunRequest, 'target' | 'playable_content' | 'include_files'> | null;
  /** False when the build record came from an earlier session. */
  live?: boolean;
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
  const a11y = useStudioA11y();
  const handoff = phase === 'done' ? playHandoff(payload, request) : null;
  return (
    <ScrollView contentContainerStyle={st.body} testID="studio-build" keyboardShouldPersistTaps="handled">
      <SectionTitle hint="Forge run">{title}</SectionTitle>
      {outdated ? (
        <Banner tone="warn" testID="studio-build-outdated">
          This build belongs to an earlier version of the questionnaire. Your new design is saved; forge again to update the playable project. Old receipts remain for reference.
        </Banner>
      ) : null}
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
        onExport={onExport}
        exportBusy={exportBusy}
        exportError={exportError}
        reduceMotion={a11y.reduceMotion}
        testID="studio-run-panel"
      />
      {handoff ? (
        <PlayHandoffCard
          handoff={handoff}
          live={live}
          onExport={onExport}
          exportBusy={exportBusy}
          exportError={exportError}
          onBrief={onBrief}
          onRetry={onRetry}
        />
      ) : null}
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
