/**
 * Live Skeleton Forge cockpit: wires catalog, live compose, forge run and
 * console hooks into ForgeCockpitView, and handles cross-panel handoffs.
 */
import React from 'react';
import { useReduceMotion } from '../../hooks/useReduceMotion';
import { buildRunRequest, INITIAL_STATE, questionnaireReducer, STEPS, stepIndex } from '../questionnaire';
import { baseEra } from '../eras';
import { planStatus } from '../plan';
import { cockpitScreenReducer, composeSummaryOf, consoleFailures, initialScreenState, tabBadges, type CockpitTab } from '../cockpitScreen';
import { useCockpitConsole } from '../consoleHooks';
import { useForgeCatalog, useForgeRun, useLiveCompose, useNow } from '../hooks';
import type { RunRequest } from '../types';
import ForgeCockpitView from './ForgeCockpitView';

export interface ForgeCockpitScreenProps {
  initialTab?: CockpitTab | null;
}

export default function ForgeCockpitScreen({ initialTab = null }: ForgeCockpitScreenProps) {
  const [screen, dispatchScreen] = React.useReducer(cockpitScreenReducer, initialTab, initialScreenState);
  const [q, dispatchQ] = React.useReducer(questionnaireReducer, INITIAL_STATE);
  const catalog = useForgeCatalog();
  const compose = useLiveCompose(q.vision);
  const run = useForgeRun();
  const consoleState = useCockpitConsole();
  const now = useNow(run.phase === 'running');
  const reduceMotion = useReduceMotion();
  const plan = planStatus(run.payload, run.phase === 'running');
  const openPlan = React.useCallback(() => dispatchScreen({ type: 'tab', tab: 'plan' }), []);
  const hasPlan = Boolean(run.payload?.build_plan);

  const startRun = React.useCallback((req: RunRequest) => {
    dispatchScreen({ type: 'runStarted' });
    void run.start(req);
  }, [run.start]);

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
      tab={screen.tab}
      onTab={(tab) => dispatchScreen({ type: 'tab', tab })}
      badges={badges}
      reduceMotion={reduceMotion}
      notice={!catalog.loading && !catalog.beatsLive ? 'Offline beats in use — the backend catalog is unreachable.' : null}
      questionnaire={{
        state: q,
        dispatch: dispatchQ,
        beats: catalog.beats,
        beatsLive: catalog.beatsLive,
        eras: catalog.eras,
        generations: catalog.generations,
        onForge: startRun,
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
