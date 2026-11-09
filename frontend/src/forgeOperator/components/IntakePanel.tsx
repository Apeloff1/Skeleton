/**
 * GameForge intake form — POST /api/v1/gameforge/intake from applied beat answers.
 * Seal is caller-supplied; answers come from Beats Apply (OperatorScreen state).
 */
import React from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';
import { Banner, Button, Card, Chip, SectionTitle, StatusPill } from '../../skeletonForge/components/primitives';
import { C } from '../../skeletonForge/components/theme';
import type { OperatorError } from '../errors';
import { isTransient } from '../errors';
import type { RunPhase, RunSource } from '../hooks';
import {
  intakeA11yLabel,
  summarizeIntakeReadiness,
  summarizeIntakeResult,
} from '../intakeSummary';
import type { Beat, EngineRunPayload, MaterialiseTarget, PlaytestMode, RepairMode } from '../types';
import { MATERIALISE_TARGETS, PLAYTEST_MODES, REPAIR_MODES } from '../types';

export interface IntakePanelProps {
  beats: Beat[];
  answers: Record<string, string>;
  onClearAnswers?: () => void;
  onOpenBeats?: () => void;
  target: MaterialiseTarget;
  onChangeTarget: (v: MaterialiseTarget) => void;
  playtest: PlaytestMode;
  onChangePlaytest: (v: PlaytestMode) => void;
  repairMode: RepairMode;
  onChangeRepairMode: (v: RepairMode) => void;
  seal: string;
  onChangeSeal: (v: string) => void;
  actorWeight: string;
  onChangeActorWeight: (v: string) => void;
  phase: RunPhase;
  source: RunSource;
  error: string | null;
  operatorError: OperatorError | null;
  payload: EngineRunPayload | null;
  onIntake: () => void;
  onCancel: () => void;
  onOpenReport?: () => void;
  testID?: string;
}

export default function IntakePanel({
  beats,
  answers,
  onClearAnswers,
  onOpenBeats,
  target,
  onChangeTarget,
  playtest,
  onChangePlaytest,
  repairMode,
  onChangeRepairMode,
  seal,
  onChangeSeal,
  actorWeight,
  onChangeActorWeight,
  phase,
  source,
  error,
  operatorError,
  payload,
  onIntake,
  onCancel,
  onOpenReport,
  testID,
}: IntakePanelProps) {
  const readiness = React.useMemo(() => summarizeIntakeReadiness(beats, answers), [beats, answers]);
  const result = React.useMemo(
    () => (source === 'intake' || payload?.intake ? summarizeIntakeResult(payload) : null),
    [source, payload],
  );
  const busy = phase === 'running' && source === 'intake';
  const canSubmit = readiness.canSubmit && !busy && phase !== 'running';
  const transient = operatorError ? isTransient(operatorError) : false;
  const readinessTone = !readiness.canSubmit ? 'idle' : readiness.complete ? 'ok' : 'warn';

  return (
    <View testID={testID} accessibilityLabel={intakeA11yLabel(readiness)}>
      <SectionTitle hint="Sealed POST /api/v1/gameforge/intake · answers → ballot → forge">
        📥 GameForge intake
      </SectionTitle>

      <Card testID="operator-intake-sheet" label="Applied answers">
        <View style={st.head}>
          <StatusPill
            tone={readinessTone}
            label={readiness.progressLabel}
            testID="operator-intake-progress"
          />
          <StatusPill
            tone={readiness.explicitEra ? 'warn' : 'idle'}
            label={readiness.explicitEra ? `era ${readiness.explicitEra}` : 'ballot vote'}
            testID="operator-intake-era-mode"
          />
        </View>
        <Text style={st.hint}>{readiness.hint}</Text>
        {readiness.answerSheet.length ? (
          <View style={st.sheet} testID="operator-intake-answers">
            {readiness.answerSheet.map((line) => (
              <Text key={line} style={st.sheetLine}>
                {line}
              </Text>
            ))}
          </View>
        ) : (
          <Text style={st.empty} testID="operator-intake-answers-empty">
            No answers applied yet.
          </Text>
        )}
        <View style={st.actions}>
          {onOpenBeats ? (
            <Button
              label="Open Beats"
              tone="secondary"
              compact
              onPress={onOpenBeats}
              testID="operator-intake-open-beats"
            />
          ) : null}
          {onClearAnswers ? (
            <Button
              label="Clear answers"
              tone="ghost"
              compact
              onPress={onClearAnswers}
              disabled={!readiness.answerSheet.length || busy}
              testID="operator-intake-clear-answers"
            />
          ) : null}
        </View>
      </Card>

      <Card testID="operator-intake-controls" label="Intake controls">
        <Text style={st.label}>Target</Text>
        <View style={st.row} accessibilityRole="radiogroup" accessibilityLabel="Intake materialise target">
          {MATERIALISE_TARGETS.map((t) => (
            <Chip
              key={t}
              label={t}
              selected={target === t}
              onPress={() => onChangeTarget(t)}
              disabled={busy}
              testID={`operator-intake-target-${t}`}
            />
          ))}
        </View>

        <Text style={st.label}>Playtest</Text>
        <View style={st.row} accessibilityRole="radiogroup" accessibilityLabel="Intake playtest mode">
          {PLAYTEST_MODES.map((m) => (
            <Chip
              key={m}
              label={m}
              selected={playtest === m}
              onPress={() => onChangePlaytest(m)}
              disabled={busy}
              testID={`operator-intake-playtest-${m}`}
            />
          ))}
        </View>

        <Text style={st.label}>Repair</Text>
        <View style={st.row} accessibilityRole="radiogroup" accessibilityLabel="Intake repair mode">
          {REPAIR_MODES.map((m) => (
            <Chip
              key={m}
              label={m}
              selected={repairMode === m}
              onPress={() => onChangeRepairMode(m)}
              disabled={busy}
              testID={`operator-intake-repair-${m}`}
            />
          ))}
        </View>

        <Text style={st.label} nativeID="operator-intake-seal-label">
          Seal (x-gf-seal · optional)
        </Text>
        <TextInput
          testID="operator-intake-seal-input"
          value={seal}
          onChangeText={onChangeSeal}
          placeholder="Paste minted seal — never stored in source"
          placeholderTextColor={C.dim}
          accessibilityLabel="GameForge seal for intake"
          accessibilityLabelledBy="operator-intake-seal-label"
          autoCapitalize="none"
          autoCorrect={false}
          secureTextEntry
          style={st.input}
          editable={!busy}
        />
        <Text style={st.label} nativeID="operator-intake-weight-label">
          Actor weight (optional)
        </Text>
        <TextInput
          testID="operator-intake-weight-input"
          value={actorWeight}
          onChangeText={onChangeActorWeight}
          placeholder="e.g. 1"
          placeholderTextColor={C.dim}
          accessibilityLabel="Charter actor weight for intake"
          accessibilityLabelledBy="operator-intake-weight-label"
          keyboardType="numeric"
          style={st.input}
          editable={!busy}
        />

        <View style={st.actions}>
          <Button
            label="Forge (intake)"
            tone="primary"
            onPress={onIntake}
            disabled={!canSubmit}
            busy={busy}
            a11yHint="POST /api/v1/gameforge/intake with applied answers"
            testID="operator-run-intake"
          />
          {busy ? (
            <Button label="Cancel" tone="ghost" onPress={onCancel} testID="operator-intake-cancel" />
          ) : null}
          {phase === 'done' && source === 'intake' && onOpenReport ? (
            <Button label="Open report" tone="ghost" onPress={onOpenReport} testID="operator-intake-open-report" />
          ) : null}
        </View>

        {phase === 'error' && source === 'intake' && error ? (
          <Banner tone="bad" testID="operator-intake-error">
            {error}
            {transient ? ' · transient — safe to retry' : ''}
          </Banner>
        ) : null}
        {phase === 'done' && source === 'intake' ? (
          <Banner tone="ok" testID="operator-intake-done">
            Intake forge finished — ballot, tensor and stages are below; open Run report for playtest / repair.
          </Banner>
        ) : null}
      </Card>

      {result ? (
        <Card testID="operator-intake-result" label="Intake result">
          <View style={st.head}>
            <StatusPill
              tone={result.succeeded === false ? 'bad' : result.succeeded ? 'ok' : 'idle'}
              label={result.succeeded === false ? 'failed' : result.succeeded ? 'succeeded' : 'intake'}
              testID="operator-intake-result-status"
            />
            <StatusPill tone="idle" label={`voted ${result.votedEra}`} testID="operator-intake-voted-era" />
          </View>
          <Fact k="Run era" v={result.runEra} />
          <Fact k="Fingerprint" v={result.fingerprint} />
          <Fact k="Dominant" v={result.dominant} />
          <Fact k="Ballots" v={result.ballotLabel} />
          <Fact k="Answers" v={String(result.answerCount)} />
          <Text style={st.visionLabel}>Synthesized vision</Text>
          <Text style={st.vision} testID="operator-intake-vision">
            {result.vision}
          </Text>
          {result.ballotLines.length ? (
            <View style={st.sheet} testID="operator-intake-ballots">
              {result.ballotLines.map((line) => (
                <Text key={line} style={st.sheetLine}>
                  {line}
                </Text>
              ))}
            </View>
          ) : null}
        </Card>
      ) : null}
    </View>
  );
}

function Fact({ k, v }: { k: string; v: string }) {
  return (
    <View style={st.fact}>
      <Text style={st.factK}>{k}</Text>
      <Text style={st.factV} numberOfLines={3}>
        {v}
      </Text>
    </View>
  );
}

const st = StyleSheet.create({
  head: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 10 },
  hint: { color: C.mute, fontSize: 13, lineHeight: 19, marginBottom: 8 },
  empty: { color: C.dim, fontSize: 13, fontStyle: 'italic', marginBottom: 8 },
  sheet: { gap: 4, marginBottom: 8 },
  sheetLine: { color: C.text, fontSize: 12, fontFamily: 'monospace' },
  label: {
    color: C.mute,
    fontSize: 12,
    fontWeight: '700',
    marginBottom: 6,
    marginTop: 8,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  input: {
    minHeight: 44,
    color: C.text,
    fontSize: 14,
    backgroundColor: C.cardAlt,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: C.borderStrong,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  row: { flexDirection: 'row', flexWrap: 'wrap', marginBottom: 4 },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 },
  fact: { flexDirection: 'row', gap: 10, marginBottom: 6 },
  factK: { color: C.mute, fontSize: 12, fontWeight: '700', width: 92 },
  factV: { color: C.text, fontSize: 13, flex: 1 },
  visionLabel: {
    color: C.mute,
    fontSize: 12,
    fontWeight: '700',
    marginTop: 8,
    marginBottom: 4,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  vision: { color: C.text, fontSize: 13, lineHeight: 19 },
});
