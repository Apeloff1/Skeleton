/**
 * Live forge-operator screen: wires catalog, compose, app/engine/intake run, plan,
 * walk, cockpit, report and recovery into OperatorView.
 */
import React from 'react';
import type { MaterialiseTarget, PlaytestMode, RepairMode } from '../types';
import { useOperatorCatalog, useOperatorCockpit, useOperatorCompose, useOperatorPlan, useOperatorRun, useOperatorWalk, useNow } from '../hooks';
import { type OperatorTab } from '../operatorTabs';
import OperatorView from './OperatorView';

export interface OperatorScreenProps {
  initialTab?: OperatorTab | null;
}

export default function OperatorScreen({ initialTab = null }: OperatorScreenProps) {
  const [tab, setTab] = React.useState<OperatorTab>(initialTab ?? 'compose');
  const [vision, setVision] = React.useState('');
  const [era, setEra] = React.useState('');
  const [target, setTarget] = React.useState<MaterialiseTarget>('godot');
  const [playtest, setPlaytest] = React.useState<PlaytestMode>('auto');
  const [repairMode, setRepairMode] = React.useState<RepairMode>('suggest');
  /** Caller-supplied seal — never hardcoded; lives only in component state. */
  const [seal, setSeal] = React.useState('');
  const [actorWeight, setActorWeight] = React.useState('');
  /** Cleaned beat answers applied from Beats — fuel for GameForge intake. */
  const [answers, setAnswers] = React.useState<Record<string, string>>({});

  const compose = useOperatorCompose(vision);
  const catalog = useOperatorCatalog();
  const run = useOperatorRun();
  const plan = useOperatorPlan();
  const walk = useOperatorWalk();
  const eraIds = React.useMemo(() => catalog.eras.map((e) => e.id), [catalog.eras]);
  const cockpit = useOperatorCockpit(eraIds);
  const now = useNow(run.phase === 'running');

  React.useEffect(() => {
    if (initialTab) setTab(initialTab);
  }, [initialTab]);

  const sealHeaders = React.useMemo(() => {
    const token = seal.trim();
    const weight = actorWeight.trim();
    if (!token && !weight) return null;
    return {
      seal: token || null,
      actorWeight: weight || null,
    };
  }, [seal, actorWeight]);

  const startApp = React.useCallback(() => {
    void run.startApp({
      vision: vision.trim(),
      era: era.trim() || null,
      archetype: 'auto',
      target,
      answers,
    });
  }, [run.startApp, vision, era, target, answers]);

  const startEngine = React.useCallback(() => {
    void run.startEngine({
      vision: vision.trim(),
      era: era.trim() || undefined,
      archetype: 'auto',
      target,
      playtest,
      repair_mode: repairMode,
      answers,
      seal: sealHeaders,
    });
  }, [run.startEngine, vision, era, target, playtest, repairMode, answers, sealHeaders]);

  const startIntake = React.useCallback(() => {
    void run.startIntake({
      answers,
      archetype: 'auto',
      target,
      playtest,
      repair_mode: repairMode,
      seal: sealHeaders,
    });
  }, [run.startIntake, answers, target, playtest, repairMode, sealHeaders]);

  const resultEra = run.enginePayload?.era ?? run.appPayload?.era ?? null;

  return (
    <OperatorView
      testID="forge-operator"
      tab={tab}
      onTab={setTab}
      notice={!catalog.loading && catalog.error ? `Catalog: ${catalog.error}` : null}
      compose={{
        vision,
        onChangeVision: setVision,
        compose,
        run,
        now,
        era,
        onChangeEra: setEra,
        target,
        onChangeTarget: setTarget,
        playtest,
        onChangePlaytest: setPlaytest,
        repairMode,
        onChangeRepairMode: setRepairMode,
        seal,
        onChangeSeal: setSeal,
        actorWeight,
        onChangeActorWeight: setActorWeight,
        onRunApp: startApp,
        onRunEngine: startEngine,
        onOpenReport: () => setTab('report'),
      }}
      plans={{
        vision,
        era,
        plan: plan.plan,
        loading: plan.loading,
        error: plan.error,
        onPlan: () => void plan.run(vision.trim(), era.trim() || null),
      }}
      walk={{
        vision,
        era,
        preview: walk.preview,
        loading: walk.loading,
        error: walk.error,
        onWalk: () => void walk.run(vision.trim(), era.trim() || null),
      }}
      eras={{
        eras: catalog.eras,
        loading: catalog.loading,
        error: catalog.error,
        onReload: catalog.reload,
        resultEra,
        pinnedEra: era.trim() || null,
        onUseInForge: (id) => {
          setEra(id);
          setTab('compose');
        },
      }}
      beats={{
        beats: catalog.beats,
        loading: catalog.loading,
        error: catalog.error,
        onReload: catalog.reload,
        onApplyAnswers: (cleaned) => {
          setAnswers(cleaned);
          const pinned = cleaned.era_explicit;
          if (pinned) setEra(pinned);
          setTab('intake');
        },
      }}
      intake={{
        beats: catalog.beats,
        answers,
        onClearAnswers: () => setAnswers({}),
        onOpenBeats: () => setTab('beats'),
        target,
        onChangeTarget: setTarget,
        playtest,
        onChangePlaytest: setPlaytest,
        repairMode,
        onChangeRepairMode: setRepairMode,
        seal,
        onChangeSeal: setSeal,
        actorWeight,
        onChangeActorWeight: setActorWeight,
        phase: run.phase,
        source: run.source,
        error: run.error,
        operatorError: run.operatorError,
        payload: run.enginePayload,
        onIntake: startIntake,
        onCancel: run.cancel,
        onOpenReport: () => setTab('report'),
      }}
      cockpit={{
        snapshot: cockpit.snapshot,
        entries: cockpit.entries,
        loading: cockpit.loading,
        busy: cockpit.busy,
        error: cockpit.error,
        eraIds,
        onRefresh: () => void cockpit.refresh(),
        onSubmit: (cmd) => void cockpit.submit(cmd),
        onClearHistory: cockpit.clear,
      }}
      report={{
        payload: run.enginePayload,
        request: run.engineRequest,
        sealAttached: !!(sealHeaders?.seal && String(sealHeaders.seal).trim()),
      }}
      recovery={{
        phase: run.phase,
        source: run.source,
        error: run.error,
        operatorError: run.operatorError,
        sealPresent: !!seal.trim(),
        onCancel: run.cancel,
        onClearSeal: () => {
          setSeal('');
          setActorWeight('');
        },
        onResetRun: run.reset,
      }}
    />
  );
}
