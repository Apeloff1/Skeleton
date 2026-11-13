'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('./harness.cjs');

const m = load('src/skeletonForge/foundation/model.ts');
const storage = load('src/skeletonForge/foundation/storage.ts');
const a11y = load('src/skeletonForge/foundation/a11y.ts');
const Q = load('src/skeletonForge/questionnaire.ts');

const AT = '2026-10-17T12:00:00.000Z';

function guest() {
  return { phase: 'ready', authenticated: false, enforced: false, role: 'anonymous', email: null, error: null };
}
function signedOutEnforced() {
  return { phase: 'ready', authenticated: false, enforced: true, role: 'anonymous', email: null, error: null };
}
function authed() {
  return { phase: 'ready', authenticated: true, enforced: true, role: 'viewer', email: 'ada@studio.test', error: null };
}
function base(over = {}) {
  return { ...m.initialFoundationState(), hydrated: true, onboarded: true, auth: guest(), screen: 'dashboard', ...over };
}
function project(id, over = {}) {
  return {
    id,
    title: 'Untitled project',
    createdAt: AT,
    updatedAt: AT,
    questionnaire: m.freshQuestionnaire(),
    lastRun: null,
    ...over,
  };
}

test('bootstrap opens onboarding, then a brief, and always checks the existing session', async () => {
  let redirected = 0;
  const fresh = await m.bootstrap(async () => ({
    onboarded: false, projects: [], prefs: m.DEFAULT_PREFS, projectsCorrupt: false, holdSaves: false, error: null,
  }), {
    async completeWebRedirect() { redirected += 1; },
    async checkMe() { return { authenticated: false, enforced: false, role: 'anonymous', user: null, observed: true }; },
  });
  assert.equal(redirected, 1);
  assert.equal(fresh.screen, 'onboarding');
  const created = m.foundationReducer(fresh, { type: 'finishOnboarding', id: 'p1', at: AT });
  assert.equal(created.screen, 'brief');
  assert.equal(created.projects.length, 1);
  assert.equal(created.intent, null);
  assert.equal(created.onboarded, true);
});

test('enforced sign-in holds the first project until the account is accepted', () => {
  let state = base({ onboarded: false, screen: 'onboarding', auth: signedOutEnforced() });
  state = m.foundationReducer(state, { type: 'finishOnboarding', id: 'p1', at: AT });
  assert.equal(state.screen, 'sign-in');
  assert.equal(state.intent, 'create');
  assert.equal(state.projects.length, 0);
  state = m.foundationReducer(state, { type: 'auth', view: authed() });
  state = m.foundationReducer(state, { type: 'fulfillIntent', id: 'p1', at: AT });
  assert.equal(state.screen, 'brief');
  assert.equal(state.activeId, 'p1');
  assert.equal(state.projects[0].title, 'Untitled project');
});

test('skip remembers first-run is done and lands on projects when the gate is open', () => {
  const state = m.foundationReducer(base({ onboarded: false, screen: 'onboarding' }), { type: 'skipOnboarding' });
  assert.equal(state.onboarded, true);
  assert.equal(state.screen, 'dashboard');
  assert.equal(state.intent, null);
});

test('replaying the introduction does not create another project', () => {
  let state = m.foundationReducer(base(), { type: 'replayOnboarding' });
  assert.equal(state.screen, 'onboarding');
  assert.equal(state.replaying, true);
  state = m.foundationReducer(state, { type: 'finishOnboarding', id: 'extra', at: AT });
  assert.equal(state.screen, 'dashboard');
  assert.equal(state.projects.length, 0);
  assert.equal(state.replaying, false);
});

test('a failed account check fails closed onto sign-in once onboarding is done', async () => {
  const state = await m.bootstrap(async () => ({
    onboarded: true, projects: [], prefs: m.DEFAULT_PREFS, projectsCorrupt: false, holdSaves: false, error: null,
  }), {
    async completeWebRedirect() {},
    async checkMe() { throw new Error('offline'); },
  });
  assert.equal(state.screen, 'sign-in');
  assert.equal(state.auth.phase, 'unavailable');
  assert.equal(state.auth.enforced, true);
  assert.match(state.auth.error, /offline/);
  assert.ok(m.exits(state).includes('retry'));
  assert.ok(m.exits(state).includes('setup'));
  assert.equal(m.exits(state).includes('guest'), false);
});

test('guest continuation stays available when the backend is not enforcing auth', async () => {
  const state = await m.bootstrap(async () => ({
    onboarded: true, projects: [], prefs: m.DEFAULT_PREFS, projectsCorrupt: false, holdSaves: false, error: null,
  }), {
    async completeWebRedirect() {},
    async checkMe() {
      return { authenticated: false, enforced: false, role: 'anonymous', user: null, observed: false, error: 'slow' };
    },
  });
  assert.equal(state.screen, 'dashboard');
  assert.equal(m.canEnter(state), true);
});

test('unreadable projects are held and not overwritten until start fresh', async () => {
  const store = storage.memoryKv({ [storage.KEYS.projects]: '{', [storage.KEYS.onboarded]: '1' });
  const loaded = await storage.loadFoundation(store);
  assert.equal(loaded.projectsCorrupt, true);
  assert.equal(loaded.holdSaves, true);
  assert.equal(loaded.projects.length, 0);
  let state = m.foundationReducer(base({ auth: authed() }), { type: 'hydrated', ...loaded });
  assert.equal(state.screen, 'dashboard');
  assert.equal(m.foundationReducer(state, { type: 'createProject', id: 'p1', at: AT }), state);
  await storage.saveFoundation(store, m.persistSnapshot(state));
  assert.equal(store.dump()[storage.KEYS.projects], '{');
  state = m.foundationReducer(state, { type: 'startFresh' });
  assert.equal(state.holdSaves, false);
  state = m.foundationReducer(state, { type: 'createProject', id: 'p1', at: AT });
  await storage.saveFoundation(store, m.persistSnapshot(state));
  const again = await storage.loadFoundation(store);
  assert.equal(again.projects.length, 1);
  assert.equal(again.projects[0].id, 'p1');
  assert.equal(again.onboarded, true);
});

test('project files round-trip and a broken project fails the whole file', async () => {
  let state = m.foundationReducer(base(), { type: 'createProject', id: 'p1', at: AT });
  state = m.foundationReducer(state, { type: 'questionnaire', action: { type: 'setVision', vision: 'a heist with a butler' }, at: '2026-10-17T12:05:00.000Z' });
  const store = storage.memoryKv();
  await storage.saveFoundation(store, m.persistSnapshot(state));
  const loaded = await storage.loadFoundation(store);
  assert.equal(loaded.projects[0].title, 'a heist with a butler');
  assert.equal(loaded.projects[0].questionnaire.vision, 'a heist with a butler');
  const bad = storage.memoryKv({ [storage.KEYS.projects]: JSON.stringify([{ id: 'ok' }, { nope: true }]) });
  const corrupt = await storage.loadFoundation(bad);
  assert.equal(corrupt.projectsCorrupt, true);
  assert.deepEqual(m.sanitizeProjects([{ id: 1 }]).projects, []);
});

test('opening, backing out, and signing out never drop the only exit', () => {
  let state = m.foundationReducer(base(), { type: 'createProject', id: 'p1', at: AT });
  state = m.foundationReducer(state, { type: 'questionnaire', action: { type: 'setVision', vision: 'garden' }, at: AT });
  state = m.foundationReducer(state, { type: 'recordRun', projectId: 'p1', snapshot: {
    phase: 'error', error: 'Backend unreachable', startedAt: 1, finishedAt: 2, succeeded: false, payload: null,
  } });
  assert.equal(state.projects[0].title, 'garden');
  assert.equal(m.projectStatus(state.projects[0], null, 'idle'), 'Needs attention');
  assert.equal(m.openTarget(state.projects[0], null, 'idle'), 'build');
  state = m.foundationReducer(state, { type: 'openProject', id: 'p1', focus: 'build' });
  assert.equal(state.screen, 'build');
  state = m.foundationReducer(state, { type: 'back' });
  assert.equal(state.screen, 'brief');
  state = m.foundationReducer(state, { type: 'back' });
  assert.equal(state.screen, 'dashboard');
  state = m.foundationReducer(state, { type: 'openSettings' });
  state = m.foundationReducer(state, { type: 'setPrefs', prefs: { reducedMotion: 'on', textSize: 'large', extra: 'no' } });
  assert.deepEqual(state.prefs, { reducedMotion: 'on', textSize: 'large' });
  state = m.foundationReducer(state, { type: 'back' });
  const signedOut = m.foundationReducer({ ...state, auth: authed() }, { type: 'signedOut' });
  assert.equal(signedOut.screen, 'sign-in');
  assert.equal(signedOut.auth.authenticated, false);
  const guestOut = m.foundationReducer({ ...state, auth: guest(), screen: 'account' }, { type: 'signedOut' });
  assert.equal(guestOut.screen, 'account');
  for (const screen of m.SCREENS) {
    const sample = screen === 'boot'
      ? m.initialFoundationState()
      : { ...base(), screen, activeId: 'p1', projects: [project('p1')] };
    assert.ok(m.exits(sample).length > 0, screen);
  }
});

test('build guidance names a next step for idle, running, transport errors, and stage failure', () => {
  assert.equal(m.buildGuidance('idle', null, null).id, 'edit-brief');
  assert.match(m.buildGuidance('running', null, null).detail, /one request/);
  assert.match(m.buildGuidance('error', 'Backend unreachable', null).detail, /Backend unreachable/);
  const failed = m.buildGuidance('done', null, {
    succeeded: false,
    era: 'soulslike',
    run: { run_id: 'r1', succeeded: false, stages: [{ name: 'forge', status: 'FAILED', error: 'verification blocked' }] },
    jeeves: { next: { text: 'Name the place before forging again.' } },
  });
  assert.equal(failed.id, 'edit-brief');
  assert.match(failed.detail, /Name the place/);
  const ok = m.buildGuidance('done', null, { succeeded: true, era: 'jrpg', run: { run_id: 'r2', succeeded: true, stages: [] } });
  assert.equal(ok.id, 'projects');
  assert.match(ok.detail, /jrpg/);
});

test('credential checks reject a blank password and accept a normal email', () => {
  assert.match(m.credentialError('not-an-email', 'x'), /email/);
  assert.match(m.credentialError('ada@studio.test', ''), /password/);
  assert.equal(m.credentialError('ada@studio.test', 'secret'), null);
});

test('text size and reduced motion resolve only what the platform reports', () => {
  const platform = { motionSupported: true, systemReducedMotion: true, systemTextScale: 1.3 };
  assert.equal(a11y.resolveA11y(m.DEFAULT_PREFS, platform).reduceMotion, true);
  assert.equal(a11y.resolveA11y(m.DEFAULT_PREFS, platform).allowSystemFontScaling, true);
  assert.equal(a11y.resolveA11y(m.DEFAULT_PREFS, platform).textScale, 1);
  const large = a11y.resolveA11y({ reducedMotion: 'off', textSize: 'large' }, platform);
  assert.equal(large.reduceMotion, false);
  assert.equal(large.textScale, 1.2);
  assert.equal(large.allowSystemFontScaling, false);
  const unsupported = { motionSupported: false, systemReducedMotion: true, systemTextScale: null };
  assert.match(a11y.motionHint(m.DEFAULT_PREFS, unsupported), /does not report a motion setting/);
  assert.match(a11y.textHint(m.DEFAULT_PREFS, unsupported), /does not report a text size/);
  assert.equal(a11y.resolveA11y({ reducedMotion: 'on', textSize: 'xlarge' }, unsupported).textScale, 1.4);
});

test('questionnaire answers and a missing run record stay inside the project', () => {
  let state = m.foundationReducer(base(), { type: 'createProject', id: 'p1', at: AT });
  state = m.foundationReducer(state, { type: 'questionnaire', action: { type: 'setBrief', facet: 'genre', value: 'rpg' }, at: AT });
  assert.equal(state.projects[0].questionnaire.brief.genre, 'rpg');
  assert.equal(Q.INITIAL_STATE.brief.genre, undefined);
  const untouched = m.foundationReducer(state, { type: 'recordRun', projectId: 'missing', snapshot: {
    phase: 'done', error: null, startedAt: 1, finishedAt: 2, succeeded: true, payload: null,
  } });
  assert.equal(untouched.projects[0].lastRun, null);
});

test('a thrown device read holds saves instead of inventing an empty studio', async () => {
  const state = await m.bootstrap(async () => { throw new Error('disk locked'); }, {
    async completeWebRedirect() {},
    async checkMe() { return { authenticated: false, enforced: false, role: 'anonymous', user: null, observed: true }; },
  });
  assert.equal(state.holdSaves, true);
  assert.match(state.hydrateError, /disk locked/);
  assert.equal(state.screen, 'onboarding');
});
