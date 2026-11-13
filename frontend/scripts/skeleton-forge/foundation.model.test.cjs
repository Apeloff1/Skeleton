'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('./harness.cjs');

const m = load('src/skeletonForge/foundation/model.ts');
const storage = load('src/skeletonForge/foundation/storage.ts');
const a11y = load('src/skeletonForge/foundation/a11y.ts');
const Q = load('src/skeletonForge/questionnaire.ts');
const H = load('src/skeletonForge/creatorBridge.ts');

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

test('fresh first-install questionnaires independently allocate all modern Forge controls', () => {
  const a = m.freshQuestionnaire(), b = m.freshQuestionnaire();
  assert.deepEqual(a.instruments, {});
  assert.deepEqual(a.playable, { enabled: false, mode: 'extraction', launch: false });
  assert.deepEqual(a.quest, { enabled: false, length: 3 });
  assert.notStrictEqual(a.instruments, b.instruments);
  assert.notStrictEqual(a.playable, b.playable);
  assert.notStrictEqual(a.options, b.options);
});

test('first-install saved projects preserve full Galaxy matrices, cockpit, eight-mode gameplay and custody', async () => {
  const G = load('src/skeletonForge/galaxyHandoff.ts');
  const config = {
    title: 'Harbor of Glass', genre: 'beat_em_up',
    game_vision: 'Original authored local-first arcade game',
    extra_params: { crowd_density: 71 }, style_params: { visual_style: 'pixel_art' },
    narrative_phases: { prologue: { branching: 2 } },
  };
  for (const field of G.MATRIX_FIELDS) config[field] = { prologue: { complexity: 67 } };
  const q = {
    ...m.freshQuestionnaire(),
    step: 'review', vision: 'Original authored local-first arcade game',
    brief: { genre: 'rpg' }, beats: { pace: 'frantic' },
    instruments: { tempo: 0.75, risk: 0.32 },
    galaxyGenre: 'beat_em_up', galaxyProfile: G.normaliseGalaxyProfile(config),
    quest: { enabled: false, length: 4 },
    playable: { enabled: true, mode: 'stealth', launch: true },
    playtest: 'require', sourceExport: { enabled: true },
  };
  const store = storage.memoryKv({ [storage.KEYS.projects]: JSON.stringify([
    project('harbor', { questionnaire: q }),
  ]) });
  const result = await storage.loadFoundation(store);
  assert.equal(result.projectsCorrupt, false);
  assert.equal(result.holdSaves, false);
  const restored = result.projects[0].questionnaire;
  assert.equal(restored.step, 'review');
  assert.equal(restored.brief.genre, 'rpg');
  assert.equal(restored.beats.pace, 'frantic');
  assert.deepEqual({ ...restored.instruments }, { tempo: 0.75, risk: 0.32 });
  assert.equal(restored.galaxyGenre, 'beat_em_up');
  assert.equal(G.MATRIX_FIELDS.filter(f => restored.galaxyProfile.config[f]).length, 14);
  assert.equal(restored.galaxyProfile.config.extra_params.crowd_density, 71);
  assert.equal(restored.playable.mode, 'stealth');
  assert.equal(restored.playable.launch, true);
  assert.equal(restored.playtest, 'require');
  assert.equal(restored.sourceExport.enabled, true);
  const request = Q.buildRunRequest(restored);
  assert.equal(request.playable_archetype, 'stealth');
  assert.equal(request.playable_main_scene, true);
  assert.equal(request.include_files, true);
});

test('older Studio files receive only missing Forge defaults without dropping authored vision', () => {
  const legacy = project('old', { questionnaire: {
    step: 'brief', vision: 'A careful original mystery',
    brief: { genre: 'puzzle' }, beats: { pace: 'unhurried' },
    options: { archetype: 'auto', target: 'godot', era: null, generation: null },
    playable: { enabled: true },
    quest: { enabled: false },
  } });
  const parsed = m.sanitizeProjects([legacy]);
  assert.equal(parsed.corrupt, false);
  const q = parsed.projects[0].questionnaire;
  assert.equal(q.vision, 'A careful original mystery');
  assert.equal(q.step, 'brief');
  assert.deepEqual({ ...q.instruments }, {});
  assert.deepEqual(q.playable, { enabled: true, mode: 'extraction', launch: false });
  assert.deepEqual(q.quest, { enabled: false, length: 3 });
  assert.equal(q.playtest, 'off');
});

test('forged saved source or unsafe scene controls hold the complete Studio project inventory', () => {
  const G = load('src/skeletonForge/galaxyHandoff.ts');
  const q = { ...m.freshQuestionnaire(), vision: 'An original survival puzzle' };
  for (const mutation of [
    { instruments: { risk: 1.5 } },
    { playable: { enabled: true, mode: 'arbitrary_exec', launch: true } },
    { galaxyProfile: { schema: G.GALAXY_PROFILE_SCHEMA, config: { title: 'incomplete' } } },
    { quest: { enabled: true, length: 100 } },
    { sourceExport: { enabled: 'true' } },
  ]) {
    const checked = m.sanitizeProjects([
      project('good'),
      project('bad', { questionnaire: { ...q, ...mutation } }),
    ]);
    assert.equal(checked.corrupt, true);
    assert.deepEqual(checked.projects, []);
  }
});


// Archived Studio owner-scoped reconciliation, persistence and recovery acceptance.
test('saved first-install projects keep recovered knobs, playable quest, validation and source ZIP preference', async () => {
  const first = m.freshQuestionnaire();
  const second = m.freshQuestionnaire();
  assert.notEqual(first.options, second.options);
  assert.notEqual(first.instruments, second.instruments);
  assert.notEqual(first.sourceExport, second.sourceExport);
  assert.equal(first.playtest, 'off');
  const actions = [
    { type: 'setVision', vision: 'An original offline game' },
    { type: 'setAxis', axis: 'risk', value: 0.63 },
    { type: 'setAxis', axis: 'agency', value: 0.88 },
    { type: 'setPlayableEnabled', value: true },
    { type: 'setQuestEnabled', value: true },
    { type: 'setQuestLength', value: 7 },
    { type: 'setPlaytestMode', value: 'require' },
    { type: 'setSourceExportEnabled', value: true },
    { type: 'goto', step: 'review' },
  ];
  const questionnaire = actions.reduce(Q.questionnaireReducer, first);
  const p = project('recovered_controls', { questionnaire });
  const persisted = m.persistSnapshot(base({ projects: [p] }));
  const store = storage.memoryKv();
  await storage.saveFoundation(store, persisted);
  const reloaded = await storage.loadFoundation(store);
  assert.equal(reloaded.projectsCorrupt, false);
  const restored = reloaded.projects[0].questionnaire;
  assert.equal(restored.step, 'review');
  assert.deepEqual(restored.instruments, { risk: 0.63, agency: 0.88 });
  assert.equal(restored.playable.enabled, true);
  assert.deepEqual(restored.quest, { enabled: true, length: 7 });
  assert.equal(restored.playtest, 'require');
  assert.equal(restored.sourceExport.enabled, true);
  const request = Q.buildRunRequest(restored);
  assert.equal(request.playable_content, true);
  assert.equal(request.quest_length, 7);
  assert.equal(request.playtest, 'require');
  assert.equal(request.include_files, true);
});

test('saved studio receipts are metadata-only and never persist an 8 MiB authored game', async () => {
  const q = m.freshQuestionnaire();
  const runSnapshot = {
    phase: 'done', error: null, startedAt: 1, finishedAt: 2, succeeded: true,
    payload: {
      succeeded: true,
      files: { 'project.godot': 'a'.repeat(1024 * 1024) },
      source_export: { status: 'ready', bytes: 1024 * 1024, file_count: 1, manifest_sha256: 'a'.repeat(64) },
      source_manifest: { schema: 'skeleton.forge.source_manifest.v1', files: { 'project.godot': 'a'.repeat(64) }, file_count: 1, sha256: 'a'.repeat(64) },
      file_names: ['project.godot'],
      forge: { file_count: 1, blueprint_id: 'bp-safe' },
    },
  };
  const stamped = m.applyRecordRun(base({ projects: [project('source', { questionnaire: q })] }), 'source', runSnapshot);
  const receipt = stamped.projects[0].lastRun.payload;
  assert.equal(receipt.files, undefined);
  assert.equal(receipt.source_manifest, undefined);
  assert.equal(receipt.source_export.status, 'unavailable');
  assert.match(receipt.source_export.reason, /original live run/);
  assert.deepEqual(receipt.file_names, ['project.godot']);

  const stored = storage.memoryKv();
  await storage.saveFoundation(stored, m.persistSnapshot(stamped));
  const serialized = stored.dump()[storage.KEYS.projects];
  assert.ok(serialized.length < 10000, 'full source bodies must never land in generic AsyncStorage projects');
  const reloaded = await storage.loadFoundation(stored);
  assert.equal(reloaded.projects[0].lastRun.payload.files, undefined);
  assert.equal(reloaded.projects[0].lastRun.payload.source_export.status, 'unavailable');
  const oldUnsanitized = base({ projects: [project('old', { lastRun: runSnapshot })] });
  assert.equal(m.persistSnapshot(oldUnsanitized).projects[0].lastRun.payload.files, undefined);
});

test('legacy projects without newly recovered controls retain authorship and gain safe defaults', () => {
  const legacy = project('legacy', {
    questionnaire: {
      step: 'beats', vision: 'My old creative game', brief: { genre: 'rpg' },
      beats: { pace: 'unhurried' },
      options: { archetype: 'auto', target: 'godot', era: null, generation: null },
    },
  });
  const saved = m.sanitizeProjects([legacy]);
  assert.equal(saved.corrupt, false);
  assert.equal(saved.projects[0].questionnaire.vision, 'My old creative game');
  assert.equal(saved.projects[0].questionnaire.brief.genre, 'rpg');
  assert.deepEqual({ ...saved.projects[0].questionnaire.instruments }, {});
  assert.equal(saved.projects[0].questionnaire.playable.enabled, false);
  assert.equal(saved.projects[0].questionnaire.playtest, 'off');
  assert.equal(saved.projects[0].questionnaire.sourceExport.enabled, false);
});

test('explicit legacy import cannot overwrite existing account projects and is blocked without access', () => {
  const owned = project('shared-id', {
    title: 'My current account project',
    questionnaire: m.freshQuestionnaire(),
  });
  const legacyDuplicate = project('shared-id', {
    title: 'Older unscoped copy should not overwrite current project',
  });
  const legacyNew = project('old-original', {
    title: 'Original archive recovered by consent',
    questionnaire: {
      step: 'brief', vision: 'A historical original game',
      brief: { genre: 'rpg' }, beats: {},
      options: { target: 'godot', archetype: 'auto', era: null, generation: null },
    },
  });
  const before = base({ projects: [owned] });
  const imported = m.foundationReducer(before, {
    type: 'importLegacy', projects: [legacyDuplicate, legacyNew],
  });
  assert.deepEqual(imported.projects.map(x => x.id), ['old-original', 'shared-id']);
  assert.equal(imported.projects[1].title, owned.title);
  assert.equal(imported.projects[0].questionnaire.vision, 'A historical original game');
  assert.equal(imported.projects[0].questionnaire.sourceExport.enabled, false);
  assert.equal(m.foundationReducer(before, {
    type: 'importLegacy', projects: [legacyNew, { id: null }],
  }), before, 'one corrupt entry must not partially import legacy data');
  assert.equal(m.foundationReducer(
    base({ projects: [owned], auth: signedOutEnforced() }),
    { type: 'importLegacy', projects: [legacyNew] },
  ).projects.length, 1);
  assert.equal(m.foundationReducer(
    base({ projects: [owned], holdSaves: true }),
    { type: 'importLegacy', projects: [legacyNew] },
  ).projects.length, 1);
});

test('overlapping Studio saves cannot revert the newest questionnaire snapshot', async () => {
  const memory = storage.memoryKv();
  let releaseFirstProjectWrite;
  let firstProjectWriteStarted;
  const started = new Promise(resolve => { firstProjectWriteStarted = resolve; });
  const firstSaved = project('serial', { title: 'Earlier genre' });
  const lastSaved = project('serial', { title: 'Latest creator controls' });
  const store = {
    getItem: (key) => memory.getItem(key),
    async setItem(key, value) {
      if (key === storage.KEYS.projects && value.includes('Earlier genre')) {
        firstProjectWriteStarted();
        await new Promise(resolve => { releaseFirstProjectWrite = resolve; });
      }
      await memory.setItem(key, value);
    },
  };
  const first = storage.saveFoundation(store, m.persistSnapshot(
    base({ projects: [firstSaved] }),
  ));
  await started;
  const second = storage.saveFoundation(store, m.persistSnapshot(
    base({ projects: [lastSaved] }),
  ));
  // The later complete snapshot must not overtake a delayed earlier write.
  await Promise.resolve();
  assert.equal(memory.dump()[storage.KEYS.projects], undefined);
  releaseFirstProjectWrite();
  await Promise.all([first, second]);
  assert.equal((await storage.loadFoundation(memory)).projects[0].title, 'Latest creator controls');
});

test('a failed earlier save does not poison a later repair or retry', async () => {
  const memory = storage.memoryKv();
  let failOnce = true;
  const store = {
    getItem: key => memory.getItem(key),
    async setItem(key, value) {
      if (key === storage.KEYS.projects && failOnce) {
        failOnce = false;
        throw new Error('temporary storage pressure');
      }
      await memory.setItem(key, value);
    },
  };
  const first = storage.saveFoundation(store, m.persistSnapshot(
    base({ projects: [project('p1')] }),
  ));
  const second = storage.saveFoundation(store, m.persistSnapshot(
    base({ projects: [project('p2')] }),
  ));
  await assert.rejects(first, /temporary storage pressure/);
  await second;
  const loaded = await storage.loadFoundation(memory);
  assert.deepEqual(loaded.projects.map(p => p.id), ['p2']);
});

test('duplicate historical project IDs are held for recovery, not silently merged', () => {
  const same = project('collision');
  const result = m.sanitizeProjects([same, { ...same, title: 'A second authored world' }]);
  assert.equal(result.corrupt, true);
  assert.deepEqual(result.projects, []);
  const active = base({ projects: [project('existing')] });
  assert.equal(m.foundationReducer(active, {
    type: 'importLegacy',
    projects: [same, { ...same, title: 'A second authored world' }],
  }), active);
});

test('returning cockpit edits respects the exact Studio project revision', () => {
  const original = project('p_origin', { questionnaire: m.freshQuestionnaire() });
  const newState = Q.questionnaireReducer(original.questionnaire, {
    type: 'setVision', vision: 'A new authored game world',
  });
  const nextDate = '2026-11-13T14:00:00.000Z';
  const applied = m.reconcileStudioReturn([original], 'p_origin', AT, newState, nextDate);
  assert.equal(applied.status, 'applied');
  assert.equal(applied.projects[0].id, original.id);
  assert.equal(applied.projects[0].questionnaire.vision, 'A new authored game world');
  assert.equal(applied.projects[0].updatedAt, nextDate);
  const conflict = m.reconcileStudioReturn(applied.projects, 'p_origin', AT, newState, nextDate);
  assert.equal(conflict.status, 'conflict');
  assert.equal(conflict.projects[0].updatedAt, nextDate);
  assert.equal(m.reconcileStudioReturn([original], 'nonexistent', AT, newState, nextDate).status, 'missing');
});

test('a changed Studio project gets a separate copy, never a silent overwrite', () => {
  const prior = project('p_origin', { title: 'My original project' });
  const edited = Q.questionnaireReducer(m.freshQuestionnaire(), {
    type: 'setVision', vision: 'My returned original game',
  });
  const returned = m.recoverStudioReturnAsCopy([prior], edited, '2026-11-13T14:00:00.000Z');
  assert.equal(returned.projects.length, 2);
  assert.equal(returned.projects[1], prior);
  assert.notEqual(returned.project.id, prior.id);
  assert.match(returned.project.title, /Forge copy/);
  assert.equal(returned.project.questionnaire.vision, 'My returned original game');
  const repeated = m.recoverStudioReturnAsCopy(returned.projects, edited, '2026-11-13T14:00:00.000Z');
  assert.equal(new Set(repeated.projects.map(p => p.id)).size, 3);
  assert.notEqual(repeated.project.id, returned.project.id);
});

test('a failed supporting save cannot partially publish a newer authored project', async () => {
  const data = storage.memoryKv();
  let fails = true;
  const seen = [];
  const store = {
    getItem: key => data.getItem(key),
    async setItem(key, value) {
      seen.push(key);
      if (key === storage.KEYS.prefs && fails) {
        fails = false;
        throw new Error('Preferences disk write failed');
      }
      await data.setItem(key, value);
    },
  };
  const current = base({ projects: [project('first')] });
  await assert.rejects(storage.saveFoundation(store, m.persistSnapshot(current)), /disk write/);
  assert.equal(data.dump()[storage.KEYS.projects], undefined);
  await storage.saveFoundation(store, m.persistSnapshot(base({ projects: [project('latest')] })));
  assert.equal((await storage.loadFoundation(data)).projects[0].id, 'latest');
  assert.deepEqual(seen.slice(-3), [
    storage.KEYS.prefs, storage.KEYS.onboarded, storage.KEYS.projects,
  ]);
});

test('source-bound Studio-to-cockpit-to-Studio edits survive a complete device save/reload', async () => {
  const initial = Q.questionnaireReducer(m.freshQuestionnaire(),
    { type: 'setVision', vision: 'A small original local-game world' });
  const original = project('p_roundtrip', { questionnaire: initial });
  const envelope = H.handoffFromStudio(
    initial, original.id, original.updatedAt, 1700000000000,
  );
  assert.equal(envelope.studioProjectUpdatedAt, AT);
  const edited = [
    { type: 'setAxis', axis: 'agency', value: 0.83 },
    { type: 'setPlayableEnabled', value: true },
    { type: 'setPlaytestMode', value: 'require' },
    { type: 'setSourceExportEnabled', value: true },
  ].reduce(Q.questionnaireReducer, initial);
  const fromCockpit = H.handoffToStudio(edited, envelope, 1700000005000);
  const accepted = H.studioStateFromHandoff(fromCockpit, 1700000005001);
  assert.equal(accepted.playtest, 'require');
  const applied = m.reconcileStudioReturn(
    [original], fromCockpit.studioProjectId,
    fromCockpit.studioProjectUpdatedAt, accepted,
    '2026-11-13T16:00:00.000Z',
  );
  assert.equal(applied.status, 'applied');
  const device = storage.memoryKv();
  await storage.saveFoundation(device, m.persistSnapshot(base({ projects: applied.projects })));
  const restarted = await storage.loadFoundation(device);
  assert.equal(restarted.projectsCorrupt, false);
  const saved = restarted.projects[0].questionnaire;
  assert.equal(saved.vision, initial.vision);
  assert.deepEqual(saved.instruments, { agency: 0.83 });
  assert.equal(saved.playable.enabled, true);
  assert.equal(saved.playtest, 'require');
  assert.equal(saved.sourceExport.enabled, true);
  assert.equal(Q.buildRunRequest(saved).include_files, true);
});
