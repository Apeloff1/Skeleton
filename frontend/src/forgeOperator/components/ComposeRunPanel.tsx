/**
 * Compose + run panel for the forge operator.
 * Wires vision → composeVision / runAppForge / engineRun via forgeOperator/client.
 * Reuses skeletonForge ComposePanel + theme primitives; seal is caller-supplied state only.
 */
import React from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';
import ComposePanel from '../../skeletonForge/components/ComposePanel';
import ForgeRunPanel from '../../skeletonForge/components/ForgeRunPanel';
import { Banner, Button, Card, Chip, SectionTitle } from '../../skeletonForge/components/primitives';
import { C } from '../../skeletonForge/components/theme';
import type { ComposeState, OperatorRunState } from '../hooks';
import type { MaterialiseTarget, PlaytestMode, RepairMode } from '../types';
import { MATERIALISE_TARGETS, PLAYTEST_MODES, REPAIR_MODES } from '../types';

export interface ComposeRunPanelProps {
  vision: string;
  onChangeVision: (v: string) => void;
  compose: ComposeState;
  run: OperatorRunState & { cancel: () => void };
  now: number;
  era: string;
  onChangeEra: (v: string) => void;
  target: MaterialiseTarget;
  onChangeTarget: (v: MaterialiseTarget) => void;
  playtest: PlaytestMode;
  onChangePlaytest: (v: PlaytestMode) => void;
  repairMode: RepairMode;
  onChangeRepairMode: (v: RepairMode) => void;
  /** Minted seal from operator state — never hardcoded. */
  seal: string;
  onChangeSeal: (v: string) => void;
  actorWeight: string;
  onChangeActorWeight: (v: string) => void;
  onRunApp: () => void;
  onRunEngine: () => void;
  onOpenReport?: () => void;
  testID?: string;
}

export default function ComposeRunPanel({
  vision,
  onChangeVision,
  compose,
  run,
  now,
  era,
  onChangeEra,
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
  onRunApp,
  onRunEngine,
  onOpenReport,
  testID,
}: ComposeRunPanelProps) {
  const busy = run.phase === 'running';
  const canForge = vision.trim().length > 0 && !busy;

  return (
    <View testID={testID}>
      <ComposePanel
        vision={vision}
        onChangeVision={onChangeVision}
        compose={compose}
        testID="operator-compose"
      />

      <SectionTitle hint="App /api/skeleton/run · sealed /api/v1/gameforge/run">⚒ Run controls</SectionTitle>
      <Card testID="operator-run-controls">
        <Text style={st.label} nativeID="operator-era-label">Era (optional)</Text>
        <TextInput
          testID="operator-era-input"
          value={era}
          onChangeText={onChangeEra}
          placeholder="e.g. thermal_heist or leave blank"
          placeholderTextColor={C.dim}
          accessibilityLabel="Era override"
          accessibilityLabelledBy="operator-era-label"
          style={st.input}
          editable={!busy}
        />

        <Text style={st.label}>Target</Text>
        <View style={st.row} accessibilityRole="radiogroup" accessibilityLabel="Materialise target">
          {MATERIALISE_TARGETS.map((t) => (
            <Chip
              key={t}
              label={t}
              selected={target === t}
              onPress={() => onChangeTarget(t)}
              disabled={busy}
              testID={`operator-target-${t}`}
            />
          ))}
        </View>

        <Text style={st.label}>Playtest</Text>
        <View style={st.row} accessibilityRole="radiogroup" accessibilityLabel="Playtest mode">
          {PLAYTEST_MODES.map((m) => (
            <Chip
              key={m}
              label={m}
              selected={playtest === m}
              onPress={() => onChangePlaytest(m)}
              disabled={busy}
              testID={`operator-playtest-${m}`}
            />
          ))}
        </View>

        <Text style={st.label}>Repair</Text>
        <View style={st.row} accessibilityRole="radiogroup" accessibilityLabel="Repair mode">
          {REPAIR_MODES.map((m) => (
            <Chip
              key={m}
              label={m}
              selected={repairMode === m}
              onPress={() => onChangeRepairMode(m)}
              disabled={busy}
              testID={`operator-repair-${m}`}
            />
          ))}
        </View>

        <Text style={st.label} nativeID="operator-seal-label">Seal (x-gf-seal · optional for engine)</Text>
        <TextInput
          testID="operator-seal-input"
          value={seal}
          onChangeText={onChangeSeal}
          placeholder="Paste minted seal — never stored in source"
          placeholderTextColor={C.dim}
          accessibilityLabel="GameForge seal header"
          accessibilityLabelledBy="operator-seal-label"
          accessibilityHint="Required only for sealed engine runs"
          autoCapitalize="none"
          autoCorrect={false}
          secureTextEntry
          style={st.input}
          editable={!busy}
        />
        <Text style={st.label} nativeID="operator-weight-label">Actor weight (optional)</Text>
        <TextInput
          testID="operator-weight-input"
          value={actorWeight}
          onChangeText={onChangeActorWeight}
          placeholder="e.g. 1"
          placeholderTextColor={C.dim}
          accessibilityLabel="Charter actor weight"
          accessibilityLabelledBy="operator-weight-label"
          keyboardType="numeric"
          style={st.input}
          editable={!busy}
        />

        <View style={st.actions}>
          <Button
            label="Forge (app)"
            tone="primary"
            onPress={onRunApp}
            disabled={!canForge}
            busy={busy && run.source === 'app'}
            a11yHint="POST /api/skeleton/run"
            testID="operator-run-app"
          />
          <Button
            label="Forge (engine)"
            tone="secondary"
            onPress={onRunEngine}
            disabled={!canForge}
            busy={busy && run.source === 'engine'}
            a11yHint="POST /api/v1/gameforge/run with optional seal"
            testID="operator-run-engine"
          />
          {busy ? (
            <Button label="Cancel" tone="ghost" onPress={run.cancel} testID="operator-run-cancel" />
          ) : null}
          {run.phase === 'done' && onOpenReport ? (
            <Button label="Open report" tone="ghost" onPress={onOpenReport} testID="operator-open-report" />
          ) : null}
        </View>
        {run.phase === 'error' && run.error ? (
          <Banner tone="bad" testID="operator-run-error">{run.error}</Banner>
        ) : null}
        {run.phase === 'done' && run.source === 'engine' ? (
          <Banner tone="ok" testID="operator-engine-done">Engine run finished — see Run report for seal / playtest / repair.</Banner>
        ) : null}
      </Card>

      {run.source === 'app' || run.appPayload ? (
        <ForgeRunPanel
          phase={run.source === 'app' ? run.phase : run.appPayload ? 'done' : 'idle'}
          payload={run.appPayload}
          error={run.source === 'app' ? run.error : null}
          startedAt={run.source === 'app' ? run.startedAt : null}
          finishedAt={run.source === 'app' ? run.finishedAt : null}
          now={now}
          onCancel={run.source === 'app' && run.phase === 'running' ? run.cancel : undefined}
          testID="operator-app-run-panel"
        />
      ) : null}
    </View>
  );
}

const st = StyleSheet.create({
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
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 14 },
});
