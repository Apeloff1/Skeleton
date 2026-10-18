'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { h, load, render, text, attrs } = require('./harness.cjs');

const m = load('src/skeletonForge/foundation/model.ts');
const Q = load('src/skeletonForge/questionnaire.ts');
const Shell = load('src/skeletonForge/components/foundation/FoundationShell.tsx').default;
const { OnboardingScreen } = load('src/skeletonForge/components/foundation/OnboardingScreen.tsx');
const { SignInScreen } = load('src/skeletonForge/components/foundation/SignInScreen.tsx');
const { AccountScreen } = load('src/skeletonForge/components/foundation/AccountScreen.tsx');
const { DashboardScreen } = load('src/skeletonForge/components/foundation/DashboardScreen.tsx');
const { SettingsScreen } = load('src/skeletonForge/components/foundation/SettingsScreen.tsx');
const { BriefScreen } = load('src/skeletonForge/components/foundation/BriefScreen.tsx');
const { BuildStatusScreen } = load('src/skeletonForge/components/foundation/BuildStatusScreen.tsx');
const { StudioA11yProvider } = load('src/skeletonForge/components/a11yContext.tsx');

const AT = '2026-10-17T12:00:00.000Z';
const platform = { motionSupported: true, systemReducedMotion: false, systemTextScale: 1 };
const noop = () => {};

function ports(over = {}) {
  return {
    platform,
    catalog: { beats: Q.FALLBACK_BEATS, beatsLive: true, eras: [], generations: [], loading: false, error: null, reload: noop },
    composeSummary: null,
    run: { phase: 'idle', payload: null, error: null, startedAt: null, finishedAt: null, ownerId: null, onStart: noop, onCancel: noop },
    now: 1_700_000_000_000,
    console: { entries: [], busy: false, failures: 0, onStatus: noop },
    onSetup: noop,
    onOpenCockpit: noop,
    ...over,
  };
}
function guest() {
  return { phase: 'ready', authenticated: false, enforced: false, role: 'anonymous', email: null, error: null };
}
function shellState(over = {}) {
  return { ...m.initialFoundationState(), hydrated: true, onboarded: true, auth: guest(), screen: 'dashboard', ...over };
}
function project(id, over = {}) {
  return { id, title: 'Untitled project', createdAt: AT, updatedAt: AT, questionnaire: m.freshQuestionnaire(), lastRun: null, ...over };
}

test('onboarding is skippable and the last step leads into a project', () => {
  const first = render(h(OnboardingScreen, { step: 0, replaying: false, error: null, onNext: noop, onSkip: noop, onBack: noop }));
  assert.match(text(first), /Describe a game/);
  assert.match(first, /data-testid="studio-skip"/);
  assert.match(first, /role="progressbar"/);
  const back = first.match(/<button[^>]*data-testid="studio-onboarding-back"[^>]*>/)[0];
  assert.match(back, /disabled/);
  const last = render(h(OnboardingScreen, { step: 2, replaying: false, error: 'Could not save on this device.', onNext: noop, onSkip: noop, onBack: noop }));
  assert.match(text(last), /Create a project/);
  assert.match(last, /role="alert"/);
  assert.match(text(last), /Could not save/);
  const replay = render(h(OnboardingScreen, { step: 2, replaying: true, error: null, onNext: noop, onSkip: noop, onBack: noop }));
  assert.match(text(replay), /Back to projects/);
  assert.doesNotMatch(text(replay), /Create a project/);
});

test('sign-in covers loading, an unreachable account service, and the form', () => {
  const loading = render(h(SignInScreen, {
    phase: 'loading', error: null, enforced: true, busy: false, intentCreate: false,
    onSubmit: noop, onGoogle: noop, onRetry: noop, onGuest: noop, onSetup: noop,
  }));
  assert.match(text(loading), /Checking your session/);
  assert.match(loading, /data-testid="studio-setup"/);
  assert.doesNotMatch(loading, /data-testid="studio-guest"/);

  const down = render(h(SignInScreen, {
    phase: 'unavailable', error: 'The account service did not answer.', enforced: true, busy: false, intentCreate: true,
    onSubmit: noop, onGoogle: noop, onRetry: noop, onGuest: noop, onSetup: noop,
  }));
  assert.match(down, /role="alert"/);
  assert.match(text(down), /Sign in to start your first project/);
  assert.match(down, /data-testid="studio-retry-auth"/);
  assert.doesNotMatch(down, /data-testid="studio-guest"/);

  const form = render(h(SignInScreen, {
    phase: 'form', error: null, enforced: false, busy: false, intentCreate: false,
    onSubmit: noop, onGoogle: noop, onRetry: noop, onGuest: noop, onSetup: noop,
  }));
  assert.ok(attrs(form, 'aria-label').includes('Email'));
  assert.ok(attrs(form, 'aria-label').includes('Password'));
  assert.match(form, /data-testid="studio-google"/);
  assert.match(form, /data-testid="studio-guest"/);
  assert.match(text(form), /email and password, or Google/);
});

test('account shows loading, failure, signed out, and signed in', () => {
  const loading = render(h(AccountScreen, {
    phase: 'loading', email: null, role: 'anonymous', error: null, busy: false,
    onSignIn: noop, onSignOut: noop, onRetry: noop, onBack: noop, onSetup: noop,
  }));
  assert.match(text(loading), /Checking your session/);
  assert.match(loading, /data-testid="studio-back"/);
  const out = render(h(AccountScreen, {
    phase: 'out', email: null, role: 'anonymous', error: null, busy: false,
    onSignIn: noop, onSignOut: noop, onRetry: noop, onBack: noop, onSetup: noop,
  }));
  assert.match(text(out), /not signed in/);
  assert.match(out, /data-testid="studio-signin-link"/);
  const inn = render(h(AccountScreen, {
    phase: 'in', email: 'ada@studio.test', role: 'viewer', error: null, busy: false,
    onSignIn: noop, onSignOut: noop, onRetry: noop, onBack: noop, onSetup: noop,
  }));
  assert.match(text(inn), /ada@studio.test/);
  assert.match(inn, /data-testid="studio-signout"/);
  const down = render(h(AccountScreen, {
    phase: 'unavailable', email: null, role: 'anonymous', error: 'offline', busy: false,
    onSignIn: noop, onSignOut: noop, onRetry: noop, onBack: noop, onSetup: noop,
  }));
  assert.match(down, /role="alert"/);
  assert.match(down, /data-testid="studio-retry-auth"/);
});

test('dashboard has empty, loading, and unreadable states, each with a way forward', () => {
  const empty = render(h(DashboardScreen, {
    phase: 'ready', error: null, holdSaves: false, projects: [], accountLabel: null,
    guestNote: 'You are on this device without an account.',
    onCreate: noop, onOpen: noop, onRetry: noop, onStartFresh: noop, onAccount: noop, onSettings: noop, onSignIn: noop,
  }));
  assert.match(text(empty), /No projects yet/);
  assert.match(empty, /data-testid="studio-create"/);
  assert.match(empty, /data-testid="studio-settings-link"/);
  assert.match(text(empty), /without an account/);

  const loading = render(h(DashboardScreen, {
    phase: 'loading', error: null, holdSaves: false, projects: [], accountLabel: 'ada@studio.test', guestNote: null,
    onCreate: noop, onOpen: noop, onRetry: noop, onStartFresh: noop, onAccount: noop, onSettings: noop, onSignIn: noop,
  }));
  assert.match(text(loading), /Loading projects/);
  const create = loading.match(/<button[^>]*data-testid="studio-create"[^>]*>/)[0];
  assert.match(create, /disabled/);

  const bad = render(h(DashboardScreen, {
    phase: 'error', error: 'Saved projects could not be read on this device.', holdSaves: true, projects: [],
    accountLabel: null, guestNote: null,
    onCreate: noop, onOpen: noop, onRetry: noop, onStartFresh: noop, onAccount: noop, onSettings: noop, onSignIn: noop,
  }));
  assert.match(bad, /role="alert"/);
  assert.match(bad, /data-testid="studio-retry-projects"/);
  assert.match(bad, /data-testid="studio-start-fresh"/);
  assert.doesNotMatch(bad, /data-testid="studio-create"/);

  const list = render(h(DashboardScreen, {
    phase: 'ready', error: null, holdSaves: false,
    projects: [{ id: 'p1', title: 'A heist', status: 'Needs attention', updated: '2026-10-17 12:00' }],
    accountLabel: null, guestNote: null,
    onCreate: noop, onOpen: noop, onRetry: noop, onStartFresh: noop, onAccount: noop, onSettings: noop, onSignIn: noop,
  }));
  assert.match(text(list), /A heist/);
  assert.match(text(list), /Needs attention/);
  assert.match(list, /data-testid="studio-open-p1"/);
});

test('settings exposes motion and text size, and an explicit size changes the preview', () => {
  const unsupported = { motionSupported: false, systemReducedMotion: false, systemTextScale: null };
  const html = render(h(SettingsScreen, {
    prefs: { reducedMotion: 'system', textSize: 'system' }, platform: unsupported, onChange: noop, onReplay: noop, onBack: noop,
  }));
  assert.equal((html.match(/role="radiogroup"/g) || []).length, 2);
  assert.match(text(html), /does not report a motion setting/);
  assert.match(text(html), /does not report a text size/);
  assert.match(html, /data-testid="studio-replay"/);
  assert.match(text(html), /✓ Match device/);
  assert.match(html, /aria-checked="true"/);

  const sized = render(h(StudioA11yProvider, {
    value: { reduceMotion: true, textScale: 1.2, allowSystemFontScaling: false },
    children: h(SettingsScreen, {
      prefs: { reducedMotion: 'on', textSize: 'large' }, platform, onChange: noop, onReplay: noop, onBack: noop,
    }),
  }));
  assert.match(sized, /font-size:\s*19px/);
  assert.match(sized, /aria-checked="true"/);
});

test('the brief hands off to the forge questionnaire and surfaces catalog failure', () => {
  const html = render(h(BriefScreen, {
    title: 'A heist',
    catalogLoading: false,
    catalogError: 'Backend unreachable',
    onRetryCatalog: noop,
    onProjects: noop,
    onViewBuild: noop,
    onOpenCockpit: noop,
    conflict: { title: 'Other game', onConfirm: noop, onKeep: noop, onView: noop },
    state: { ...Q.INITIAL_STATE, vision: 'a heist with a butler' },
    dispatch: noop,
    beats: Q.FALLBACK_BEATS,
    beatsLive: false,
    onForge: noop,
    forging: false,
    composeSummary: null,
  }));
  assert.match(text(html), /GameForge questionnaire/);
  assert.match(html, /role="alert"/);
  assert.match(html, /data-testid="studio-retry-catalog"/);
  assert.match(html, /data-testid="studio-run-conflict"/);
  assert.match(text(html), /Other game/);
  assert.match(html, /data-testid="studio-view-build"/);
  assert.match(html, /data-testid="q-next"/);
});

test('build status uses the forge run panel and offers a cockpit check without polling', () => {
  const idle = render(h(BuildStatusScreen, {
    title: 'A heist', phase: 'idle', payload: null, error: null, startedAt: null, finishedAt: null, now: 10,
    guidance: { id: 'edit-brief', label: 'Finish the brief', detail: 'Nothing has been built yet.' },
    onGuidance: noop, consoleBusy: false, consoleSummary: null, consoleOk: null, consoleFailures: 0, onAskCockpit: noop,
    onBrief: noop, onProjects: noop, onOpenCockpit: noop,
  }));
  assert.match(text(idle), /No run yet/);
  assert.match(text(idle), /Finish the brief/);
  assert.match(text(idle), /does not keep asking/);
  assert.match(idle, /data-testid="studio-console-status"/);
  assert.match(idle, /data-testid="studio-back-brief"/);

  const failed = render(h(BuildStatusScreen, {
    title: 'A heist', phase: 'error', payload: null, error: 'Backend unreachable', startedAt: 1, finishedAt: 5, now: 5,
    onRetry: noop,
    guidance: { id: 'edit-brief', label: 'Change the brief', detail: 'Backend unreachable' },
    onGuidance: noop, consoleBusy: false, consoleSummary: 'ledger unavailable', consoleOk: false, consoleFailures: 1, onAskCockpit: noop,
    onBrief: noop, onProjects: noop, onOpenCockpit: noop,
  }));
  assert.match(failed, /role="alert"/);
  assert.match(text(failed), /Backend unreachable/);
  assert.match(text(failed), /1 cockpit command failed/);
  assert.match(failed, /data-testid="run-retry"/);
  assert.match(failed, /data-testid="studio-next-action"/);
});

test('the shell renders each gate from state and keeps a save failure actionable', () => {
  const boot = render(h(Shell, { ports: ports(), initialState: m.initialFoundationState() }));
  assert.match(text(boot), /Opening the studio/);
  assert.match(boot, /data-testid="studio-setup"/);

  const projects = [project('p1', { title: 'Garden', questionnaire: { ...m.freshQuestionnaire(), vision: 'a quiet garden' } })];
  const dash = render(h(Shell, { ports: ports(), initialState: shellState({ projects, activeId: null }) }));
  assert.match(text(dash), /Garden/);
  assert.match(text(dash), /without an account/);

  const saved = render(h(Shell, {
    ports: ports(),
    initialState: shellState({ screen: 'settings', prefs: { reducedMotion: 'on', textSize: 'large' }, persistError: 'Could not save on this device.' }),
  }));
  assert.match(saved, /data-testid="studio-persist-error"/);
  assert.match(saved, /data-testid="studio-retry-save"/);
  assert.match(text(saved), /Reduce motion/);
});

test('the live screen reuses the forge run and cockpit console, and auth stays on the existing client', () => {
  const root = path.resolve(__dirname, '..', '..');
  const screen = fs.readFileSync(path.join(root, 'src/skeletonForge/components/foundation/FoundationScreen.tsx'), 'utf8');
  const auth = fs.readFileSync(path.join(root, 'src/skeletonForge/foundation/authPort.ts'), 'utf8');
  assert.match(screen, /useForgeRun/);
  assert.match(screen, /useCockpitConsole/);
  assert.match(screen, /consoleFailures/);
  assert.match(screen, /submit\('STATUS'\)/);
  assert.doesNotMatch(screen, /setInterval|setTimeout/);
  assert.match(auth, /gameforgeAuth/);
  assert.match(auth, /\/api\/auth\/me/);
  assert.doesNotMatch(auth, /fetch\(|axios/);
});
