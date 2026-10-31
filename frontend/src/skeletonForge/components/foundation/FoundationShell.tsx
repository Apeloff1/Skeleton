/**
 * Studio shell. Owns the screen reducer and renders one step of the path
 * from first-run to a forge brief and its build. Live network hooks stay in
 * FoundationScreen; this component can render from a given state in tests.
 */
import React from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { resolveA11y, type A11yPlatformSnapshot } from '../../foundation/a11y';
import type { AuthPort } from '../../foundation/authPort';
import {
  buildGuidance, canEnter, createId, credentialError, foundationReducer, initialFoundationState,
  openTarget, orderedProjects, persistSnapshot, projectStatus, viewFromMe, bootstrap,
  type BuildPhase, type FoundationState, type LoadResult, type PersistSnapshot, type StepAction, type StudioProject,
} from '../../foundation/model';
import { buildRunRequest, FALLBACK_BEATS, type QuestionnaireAction } from '../../questionnaire';
import { summarizeRun } from '../../run';
import type { Beat, EraRow, GenerationRow, RunPayload, RunRequest } from '../../types';
import { StudioA11yProvider } from '../a11yContext';
import { Banner, Button } from '../primitives';
import { C } from '../theme';
import { AccountScreen } from './AccountScreen';
import { BriefScreen } from './BriefScreen';
import { BuildStatusScreen } from './BuildStatusScreen';
import { DashboardScreen } from './DashboardScreen';
import { OnboardingScreen } from './OnboardingScreen';
import { SettingsScreen } from './SettingsScreen';
import { SignInScreen } from './SignInScreen';

export interface ShellPorts {
  load?: () => Promise<LoadResult>;
  save?: (snap: PersistSnapshot) => Promise<void>;
  auth?: AuthPort;
  platform: A11yPlatformSnapshot;
  catalog: {
    beats: Beat[];
    beatsLive: boolean;
    eras: EraRow[];
    generations: GenerationRow[];
    loading: boolean;
    error: string | null;
    reload: () => void;
  };
  composeSummary: string | null;
  run: {
    phase: BuildPhase;
    payload: RunPayload | null;
    error: string | null;
    startedAt: number | null;
    finishedAt: number | null;
    ownerId: string | null;
    onStart: (projectId: string, req: RunRequest) => void;
    onCancel: () => void;
  };
  now: number;
  console: {
    entries: { ok: boolean; summary: string }[];
    busy: boolean;
    failures: number;
    onStatus: () => void;
  };
  onSetup: () => void;
  onOpenCockpit: () => void;
  onVision?: (vision: string) => void;
  newId?: () => string;
  nowIso?: () => string;
}

function message(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

export default function FoundationShell({ ports, initialState }: { ports: ShellPorts; initialState?: FoundationState }) {
  const [state, dispatch] = React.useReducer(foundationReducer, initialState ?? initialFoundationState());
  const [step, setStep] = React.useState(0);
  const replayKey = state.replaying ? 1 : 0;
  const [seenReplay, setSeenReplay] = React.useState(replayKey);
  if (seenReplay !== replayKey) {
    setSeenReplay(replayKey);
    setStep(0);
  }
  const [busy, setBusy] = React.useState(false);
  const [formError, setFormError] = React.useState<string | null>(null);
  const [pendingForge, setPendingForge] = React.useState<RunRequest | null>(null);
  const seq = React.useRef(0);
  const newId = React.useCallback(() => (ports.newId ? ports.newId() : createId(Date.now(), ++seq.current)), [ports]);
  const iso = React.useCallback(() => (ports.nowIso ? ports.nowIso() : new Date().toISOString()), [ports]);

  React.useEffect(() => {
    if (initialState || !ports.load || !ports.auth) return undefined;
    let cancel = false;
    void bootstrap(ports.load, ports.auth).then((next) => {
      if (!cancel) dispatch({ type: 'replace', state: next });
    });
    return () => { cancel = true; };
  }, [initialState, ports.load, ports.auth]);

  const serial = JSON.stringify(persistSnapshot(state));
  const seen = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!ports.save || !state.hydrated || state.holdSaves) return undefined;
    if (seen.current === null) { seen.current = serial; return undefined; }
    if (seen.current === serial) return undefined;
    seen.current = serial;
    let cancel = false;
    void ports.save(persistSnapshot(state)).then(() => {
      if (!cancel) dispatch({ type: 'persistError', error: null });
    }, (error) => {
      if (!cancel) dispatch({ type: 'persistError', error: message(error, 'Could not save on this device.') });
    });
    return () => { cancel = true; };
  }, [serial, state.hydrated, state.holdSaves, ports.save]);

  React.useEffect(() => {
    if (state.intent !== 'create' || !canEnter(state) || state.holdSaves) return;
    if (state.screen === 'brief' && state.activeId) return;
    dispatch({ type: 'fulfillIntent', id: newId(), at: iso() });
  }, [state, newId, iso]);

  const active = state.projects.find((project) => project.id === state.activeId) ?? null;
  React.useEffect(() => {
    ports.onVision?.(active?.questionnaire.vision ?? '');
  }, [active?.questionnaire.vision, ports]);

  React.useEffect(() => {
    const owner = ports.run.ownerId;
    if (!owner || (ports.run.phase !== 'done' && ports.run.phase !== 'error')) return;
    dispatch({
      type: 'recordRun',
      projectId: owner,
      snapshot: {
        phase: ports.run.phase,
        error: ports.run.error,
        startedAt: ports.run.startedAt,
        finishedAt: ports.run.finishedAt,
        succeeded: ports.run.phase === 'done' ? summarizeRun(ports.run.payload).succeeded : false,
        payload: ports.run.payload,
      },
    });
  }, [ports.run.phase, ports.run.finishedAt, ports.run.ownerId, ports.run.error, ports.run.startedAt, ports.run.payload]);

  const a11y = resolveA11y(state.prefs, ports.platform);
  const other = state.projects.find((project) => project.id === ports.run.ownerId) ?? null;
  const runConflicts = ports.run.phase === 'running' && ports.run.ownerId != null && ports.run.ownerId !== state.activeId;

  const refreshAuth = async () => {
    if (!ports.auth) return;
    setBusy(true);
    setFormError(null);
    try {
      const me = await ports.auth.checkMe();
      dispatch({ type: 'auth', view: viewFromMe(me) });
    } catch (error) {
      dispatch({
        type: 'auth',
        view: { phase: 'unavailable', authenticated: false, enforced: true, role: 'anonymous', email: null, error: message(error, 'The account service did not answer.') },
      });
    } finally {
      setBusy(false);
    }
  };

  const onSubmit = async (email: string, password: string, mode: 'login' | 'register') => {
    if (!ports.auth) return;
    const problem = credentialError(email, password);
    if (problem) { setFormError(problem); return; }
    setBusy(true);
    setFormError(null);
    const result = mode === 'register' ? await ports.auth.registerEmail(email, password) : await ports.auth.loginEmail(email, password);
    if (!result.ok) { setFormError(result.error || 'Sign-in failed'); setBusy(false); return; }
    await refreshAuth();
    dispatch({ type: 'fulfillIntent', id: newId(), at: iso() });
  };

  const onGoogle = async () => {
    if (!ports.auth) return;
    setBusy(true);
    setFormError(null);
    const result = await ports.auth.googleLogin();
    if (result.redirecting) return;
    if (!result.ok) {
      if (result.error && result.error !== 'cancelled') setFormError(result.error);
      setBusy(false);
      return;
    }
    await refreshAuth();
    dispatch({ type: 'fulfillIntent', id: newId(), at: iso() });
  };

  const onSignOut = async () => {
    if (!ports.auth) { dispatch({ type: 'signedOut' }); return; }
    setBusy(true);
    try { await ports.auth.logout(); } catch { /* local sign-out still proceeds */ }
    dispatch({ type: 'signedOut' });
    setBusy(false);
  };

  const startForge = (project: StudioProject, req: RunRequest) => {
    setPendingForge(null);
    ports.run.onStart(project.id, req);
    dispatch({ type: 'openBuild' });
  };

  const onForge = (req: RunRequest) => {
    if (!active) return;
    if (runConflicts) { setPendingForge(req); return; }
    startForge(active, req);
  };

  const visible = visibleRun(active, ports.run);
  const guidance = buildGuidance(visible.phase, visible.error, visible.payload);
  const latest = ports.console.entries[0] ?? null;

  const onGuidance = (action: StepAction) => {
    if (action.id === 'edit-brief') dispatch({ type: 'openBrief' });
    else if (action.id === 'projects') dispatch({ type: 'openDashboard' });
    else if (action.id === 'cockpit') ports.onOpenCockpit();
    else if (action.id === 'retry' && active) startForge(active, buildRunRequest(active.questionnaire));
  };

  let body: React.ReactNode;
  if (state.screen === 'boot') {
    body = (
      <View style={st.center} testID="studio-boot" accessibilityLiveRegion="polite">
        <ActivityIndicator color={C.accent} accessibilityLabel="Opening the studio" />
        <Text style={st.copy}>{state.hydrated ? 'Checking your session…' : 'Opening the studio…'}</Text>
        <Button label="Setup and readiness" tone="ghost" onPress={ports.onSetup} testID="studio-setup" />
      </View>
    );
  } else if (state.screen === 'onboarding') {
    body = (
      <OnboardingScreen
        step={step}
        replaying={state.replaying}
        error={state.persistError}
        onBack={() => setStep((value) => Math.max(0, value - 1))}
        onSkip={() => dispatch({ type: 'skipOnboarding' })}
        onNext={() => {
          if (step >= 2) dispatch({ type: 'finishOnboarding', id: newId(), at: iso() });
          else setStep((value) => value + 1);
        }}
      />
    );
  } else if (state.screen === 'sign-in') {
    body = (
      <SignInScreen
        phase={state.auth.phase === 'loading' ? 'loading' : state.auth.phase === 'unavailable' ? 'unavailable' : 'form'}
        error={formError || state.auth.error}
        enforced={state.auth.enforced}
        busy={busy}
        intentCreate={state.intent === 'create'}
        onSubmit={(email, password, mode) => { void onSubmit(email, password, mode); }}
        onGoogle={() => { void onGoogle(); }}
        onRetry={() => { void refreshAuth(); }}
        onGuest={() => dispatch({ type: 'openDashboard' })}
        onSetup={ports.onSetup}
      />
    );
  } else if (state.screen === 'dashboard') {
    const guestNote = state.auth.phase === 'unavailable' && !state.auth.enforced
      ? 'The account service did not answer. You can keep working on this device, or try signing in again.'
      : state.auth.phase === 'ready' && !state.auth.authenticated && !state.auth.enforced
        ? 'You are on this device without an account. Projects stay here. Sign in when you want the studio account.'
        : null;
    body = (
      <DashboardScreen
        phase={state.reloading ? 'loading' : state.holdSaves ? 'error' : 'ready'}
        error={state.hydrateError}
        holdSaves={state.holdSaves}
        projects={orderedProjects(state.projects).map((project) => ({
          id: project.id,
          title: project.title,
          status: projectStatus(project, ports.run.ownerId, ports.run.phase),
          updated: project.updatedAt.slice(0, 16).replace('T', ' '),
        }))}
        accountLabel={state.auth.email}
        guestNote={guestNote}
        onCreate={() => dispatch({ type: 'createProject', id: newId(), at: iso() })}
        onOpen={(id) => {
          const project = state.projects.find((item) => item.id === id);
          if (!project) return;
          dispatch({ type: 'openProject', id, focus: openTarget(project, ports.run.ownerId, ports.run.phase) });
        }}
        onRetry={() => {
          if (!ports.load) return;
          dispatch({ type: 'retryLoad' });
          void ports.load().then((loaded) => dispatch({ type: 'hydrated', ...loaded }), (error) => dispatch({
            type: 'hydrated',
            onboarded: state.onboarded,
            projects: [],
            prefs: state.prefs,
            projectsCorrupt: false,
            holdSaves: true,
            error: message(error, 'Saved projects could not be read on this device.'),
          }));
        }}
        onStartFresh={() => dispatch({ type: 'startFresh' })}
        onAccount={() => dispatch({ type: 'openAccount' })}
        onSettings={() => dispatch({ type: 'openSettings' })}
        onSignIn={() => dispatch({ type: 'openSignIn' })}
      />
    );
  } else if (state.screen === 'brief' && active) {
    body = (
      <BriefScreen
        title={active.title}
        catalogLoading={ports.catalog.loading}
        catalogError={ports.catalog.error}
        onRetryCatalog={ports.catalog.reload}
        onProjects={() => dispatch({ type: 'openDashboard' })}
        onViewBuild={() => dispatch({ type: 'openBuild' })}
        onOpenCockpit={ports.onOpenCockpit}
        conflict={pendingForge && other ? {
          title: other.title,
          onConfirm: () => startForge(active, pendingForge),
          onKeep: () => setPendingForge(null),
          onView: () => dispatch({ type: 'openProject', id: other.id, focus: 'build' }),
        } : null}
        state={active.questionnaire}
        dispatch={(action: QuestionnaireAction) => dispatch({ type: 'questionnaire', action, at: iso() })}
        beats={ports.catalog.beats.length ? ports.catalog.beats : FALLBACK_BEATS}
        beatsLive={ports.catalog.beatsLive}
        eras={ports.catalog.eras}
        generations={ports.catalog.generations}
        onForge={onForge}
        forging={ports.run.phase === 'running' && ports.run.ownerId === active.id}
        composeSummary={ports.composeSummary}
      />
    );
  } else if (state.screen === 'build' && active) {
    body = (
      <BuildStatusScreen
        title={active.title}
        phase={visible.phase}
        payload={visible.payload}
        error={visible.error}
        startedAt={visible.startedAt}
        finishedAt={visible.finishedAt}
        now={ports.now}
        onCancel={visible.live && visible.phase === 'running' ? ports.run.onCancel : undefined}
        onRetry={visible.phase === 'done' || visible.phase === 'error' ? () => startForge(active, buildRunRequest(active.questionnaire)) : undefined}
        guidance={guidance}
        onGuidance={onGuidance}
        consoleBusy={ports.console.busy}
        consoleSummary={latest?.summary ?? null}
        consoleOk={latest ? latest.ok : null}
        consoleFailures={ports.console.failures}
        onAskCockpit={ports.console.onStatus}
        onBrief={() => dispatch({ type: 'openBrief' })}
        onProjects={() => dispatch({ type: 'openDashboard' })}
        onOpenCockpit={ports.onOpenCockpit}
      />
    );
  } else if (state.screen === 'account') {
    body = (
      <AccountScreen
        phase={state.auth.phase === 'loading' ? 'loading' : state.auth.phase === 'unavailable' ? 'unavailable' : state.auth.authenticated ? 'in' : 'out'}
        email={state.auth.email}
        role={state.auth.role}
        error={state.auth.error}
        busy={busy}
        onSignIn={() => dispatch({ type: 'openSignIn' })}
        onSignOut={() => { void onSignOut(); }}
        onRetry={() => { void refreshAuth(); }}
        onBack={() => dispatch({ type: 'back' })}
        onSetup={ports.onSetup}
      />
    );
  } else if (state.screen === 'settings') {
    body = (
      <SettingsScreen
        prefs={state.prefs}
        platform={ports.platform}
        onChange={(prefs) => dispatch({ type: 'setPrefs', prefs })}
        onReplay={() => dispatch({ type: 'replayOnboarding' })}
        onBack={() => dispatch({ type: 'back' })}
      />
    );
  } else {
    body = (
      <View style={st.center} testID="studio-missing">
        <Text style={st.copy}>This project is no longer on the device.</Text>
        <Button label="All projects" onPress={() => dispatch({ type: 'openDashboard' })} testID="studio-back" />
      </View>
    );
  }

  return (
    <StudioA11yProvider value={a11y}>
      <View style={st.root} testID="studio-shell">
        {state.persistError && state.screen !== 'onboarding' ? (
          <View style={st.persist}>
            <Banner tone="bad" testID="studio-persist-error">{state.persistError}</Banner>
            <Button label="Retry save" tone="secondary" onPress={() => {
              if (!ports.save || state.holdSaves) return;
              void ports.save(persistSnapshot(state)).then(() => dispatch({ type: 'persistError', error: null }), (error) => {
                dispatch({ type: 'persistError', error: message(error, 'Could not save on this device.') });
              });
            }} testID="studio-retry-save" />
          </View>
        ) : null}
        {body}
      </View>
    </StudioA11yProvider>
  );
}

function visibleRun(active: StudioProject | null, run: ShellPorts['run']) {
  if (active && run.ownerId === active.id && run.phase !== 'idle') {
    return { phase: run.phase, payload: run.payload, error: run.error, startedAt: run.startedAt, finishedAt: run.finishedAt, live: true };
  }
  if (active?.lastRun) {
    return {
      phase: active.lastRun.phase,
      payload: active.lastRun.payload,
      error: active.lastRun.error,
      startedAt: active.lastRun.startedAt,
      finishedAt: active.lastRun.finishedAt,
      live: false,
    };
  }
  return { phase: 'idle' as const, payload: null, error: null, startedAt: null, finishedAt: null, live: false };
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12, padding: 24 },
  copy: { color: C.text, fontSize: 15, lineHeight: 22, textAlign: 'center' },
  persist: { paddingHorizontal: 16, paddingTop: 12 },
});
