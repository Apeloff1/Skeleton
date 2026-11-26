/**
 * Live Skeleton Forge cockpit: wires catalog, live compose, forge run and
 * console hooks into ForgeCockpitView, and handles cross-panel handoffs.
 */
import React from 'react';
import { getAuthEpoch } from '../../auth/gameforgeAuth';
import { shareGodotSourceArchive } from '../shareSourceArchive';
import { loadGalaxyProfile } from '../galaxyProfileCustody';
import { consumeGalaxyHandoff } from '../galaxyHandoff';
import { useReduceMotion } from '../../hooks/useReduceMotion';
import { buildRunRequest, INITIAL_STATE, questionnaireReducer, STEPS, stepIndex, type QuestionnaireState } from '../questionnaire';
import { baseEra } from '../eras';
import { planStatus } from '../plan';
import { cockpitScreenReducer, composeSummaryOf, consoleFailures, initialScreenState, tabBadges, type CockpitTab } from '../cockpitScreen';
import { useCockpitConsole } from '../consoleHooks';
import { useForgeCatalog, useForgeRun, useLiveCompose, useNow } from '../hooks';
import type { RunRequest } from '../types';
import ForgeCockpitView from './ForgeCockpitView';

export interface ForgeCockpitScreenProps {
  initialTab?: CockpitTab | null;
  initialQuestionnaire?: QuestionnaireState | null;
  galaxyHandoffId?: string | null;
  onOpenGalaxyStudio?: (draft: QuestionnaireState) => void;
  onReturnToStudio?: (draft: QuestionnaireState) => void;
}

export default function ForgeCockpitScreen({ initialTab = null, initialQuestionnaire = null, galaxyHandoffId = null, onOpenGalaxyStudio, onReturnToStudio }: ForgeCockpitScreenProps) {
  const [screen, dispatchScreen] = React.useReducer(cockpitScreenReducer, initialTab, initialScreenState);
  const [q, dispatchQ] = React.useReducer(questionnaireReducer, initialQuestionnaire ?? INITIAL_STATE);
  React.useEffect(() => {
    if (!galaxyHandoffId) return;
    // The route hint is never an auth credential; require an exact owner epoch
    // and consume only once. Already-scoped restored bridge content wins if
    // both transports are present, preserving Forge beats and quest choices.
    const profile = consumeGalaxyHandoff(galaxyHandoffId, Date.now(), getAuthEpoch());
    if (profile && !initialQuestionnaire?.galaxyProfile) {
      dispatchQ({ type: 'importGalaxy', profile });
    }
  }, [galaxyHandoffId, initialQuestionnaire?.galaxyProfile]);
  const catalog = useForgeCatalog();
  const compose = useLiveCompose(q.vision);
  const run = useForgeRun();
  const consoleState = useCockpitConsole();
  const now = useNow(run.phase === 'running');
  const reduceMotion = useReduceMotion();
  const plan = planStatus(run.payload, run.phase === 'running');
  const openPlan = React.useCallback(() => dispatchScreen({ type: 'tab', tab: 'plan' }), []);
  const hasPlan = Boolean(run.payload?.build_plan);
  const runOwnerEpoch = React.useRef<number | null>(null);
  const runGeneration = React.useRef(0);
  const [exportBusy, setExportBusy] = React.useState(false);
  const [exportError, setExportError] = React.useState<string | null>(null);
  const exportLock = React.useRef(false);

  const startRun = React.useCallback((req: RunRequest) => {
    runOwnerEpoch.current = getAuthEpoch();
    runGeneration.current += 1;
    setExportError(null);
    dispatchScreen({ type: 'runStarted' });
    void run.start(req);
  }, [run.start]);

  const exportGodot = React.useCallback(() => {
    if (exportLock.current || run.phase !== 'done' || run.payload?.succeeded !== true
        || run.payload?.source_export?.status !== 'ready') return;
    const atStart = runGeneration.current;
    const ownerEpoch = runOwnerEpoch.current;
    if (ownerEpoch === null || ownerEpoch !== getAuthEpoch()) {
      setExportError('Account changed since the source project was generated. Forge again to export.');
      return;
    }
    exportLock.current = true;
    setExportBusy(true);
    setExportError(null);
    void shareGodotSourceArchive(run.payload, () =>
      ownerEpoch === getAuthEpoch() && atStart === runGeneration.current
    ).catch((error: unknown) => {
      const message = error instanceof Error ? error.message : '';
      setExportError(message.startsWith('Godot ') || message.startsWith('Device ')
        ? message.slice(0, 180) : 'Could not save or share the source archive on this device.');
    }).finally(() => {
      exportLock.current = false;
      setExportBusy(false);
    });
  }, [run.phase, run.payload]);

  const [galaxyRestoreNotice, setGalaxyRestoreNotice] = React.useState<string | null>(null);
  const restoreGalaxy = React.useCallback(() => {
    const ownerEpoch = getAuthEpoch();
    setGalaxyRestoreNotice(null);
    void loadGalaxyProfile().then(profile => {
      if (getAuthEpoch() !== ownerEpoch) {
        setGalaxyRestoreNotice('Account changed during the design restore; no draft was applied.');
      } else if (profile) {
        dispatchQ({ type: 'importGalaxy', profile });
      } else {
        setGalaxyRestoreNotice('No saved full Galaxy design for this account.');
      }
    }).catch(() => {
      setGalaxyRestoreNotice('Saved Galaxy design could not be validated for this account.');
    });
  }, []);

  const resultEra = run.payload?.era ?? null;
  const composeSystems = Array.isArray(compose.result?.components) ? compose.result!.components.length : 0;

  const badges = tabBadges(screen, {
    runPhase: run.phase,
    composeLoading: compose.loading,
    composeError: compose.error,
    composeSystems,
    erasCount: catalog.eras.length,
    erasError: catalog.error,
    consoleErrors: consoleFailures(consoleState.entries),
    questionnaireStep: stepIndex(q.step),
    questionnaireSteps: STEPS.length,
    planState: plan.state,
  });

  return (
    <ForgeCockpitView
      testID="skeleton-forge-cockpit"
      durableRequest={buildRunRequest(q)}
      tab={screen.tab}
      onTab={(tab) => dispatchScreen({ type: 'tab', tab })}
      onReturnToStudio={onReturnToStudio ? () => onReturnToStudio(q) : undefined}
      badges={badges}
      reduceMotion={reduceMotion}
      notice={galaxyRestoreNotice ?? (!catalog.loading && !catalog.beatsLive ? 'Offline beats in use — the backend catalog is unreachable.' : null)}
      questionnaire={{
        state: q,
        dispatch: dispatchQ,
        beats: catalog.beats,
        beatsLive: catalog.beatsLive,
        eras: catalog.eras,
        generations: catalog.generations,
        onForge: startRun,
        onOpenGalaxyStudio: onOpenGalaxyStudio ? () => onOpenGalaxyStudio(q) : undefined,
        onRestoreGalaxyProfile: restoreGalaxy,
        forging: run.phase === 'running',
        composeSummary: composeSummaryOf(compose.result),
        onViewPlan: hasPlan ? openPlan : undefined,
      }}
      plan={{
        payload: run.payload,
        eras: catalog.eras,
        pinnedEra: q.options.era,
        running: run.phase === 'running',
        error: run.phase === 'error' ? run.error : null,
        onViewEra: (era) => dispatchScreen({ type: 'viewEra', era: baseEra(era) ?? era }),
        onViewRun: () => dispatchScreen({ type: 'tab', tab: 'run' }),
        onBack: () => dispatchScreen({ type: 'tab', tab: 'build' }),
      }}
      compose={{
        vision: q.vision,
        onChangeVision: (vision) => dispatchQ({ type: 'setVision', vision }),
        compose,
      }}
      run={{
        phase: run.phase,
        payload: run.payload,
        error: run.error,
        startedAt: run.startedAt,
        finishedAt: run.finishedAt,
        now,
        onCancel: run.cancel,
        onRetry: () => startRun(run.request ?? buildRunRequest(q)),
        onViewEra: (era) => dispatchScreen({ type: 'viewEra', era: baseEra(era) ?? era }),
        onViewPlan: openPlan,
        onExport: exportGodot,
        exportBusy,
        exportError,
      }}
      eras={{
        eras: catalog.eras,
        loading: catalog.loading,
        error: catalog.error,
        onReload: catalog.reload,
        resultEra,
        pinnedEra: q.options.era,
        selected: screen.selectedEra,
        onSelect: (era) => dispatchScreen({ type: 'selectEra', era }),
        onUseInForge: (era) => {
          dispatchQ({ type: 'setOption', key: 'era', value: era });
          dispatchScreen({ type: 'useEra', era });
        },
        onViewPlan: hasPlan ? openPlan : undefined,
      }}
      console={{
        entries: consoleState.entries,
        busy: consoleState.busy,
        onSubmit: (cmd) => { void consoleState.submit(cmd); },
        onClear: consoleState.clear,
      }}
    />
  );
}
