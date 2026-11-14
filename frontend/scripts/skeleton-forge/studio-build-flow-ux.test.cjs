'use strict';
/**
 * Studio build-flow UX hardening: bootstrap deadlines, coalesced saves,
 * honest local cancel, the Play handoff, reduced motion on the build
 * screen and questionnaire text scaling.
 */
const test = require('node:test');
const assert = require('node:assert/strict');
const { h, load, render, text, attrs } = require('./harness.cjs');
const runFixture = require('./fixtures/run.json');

const m = load('src/skeletonForge/foundation/model.ts');
const R = load('src/skeletonForge/run.ts');
const Q = load('src/skeletonForge/questionnaire.ts');
const { createSnapshotSaver } = load('src/skeletonForge/foundation/persistQueue.ts');
const { BuildStatusScreen } = load('src/skeletonForge/components/foundation/BuildStatusScreen.tsx');
const { StudioA11yProvider } = load('src/skeletonForge/components/a11yContext.tsx');
const { scaleStyle } = load('src/skeletonForge/components/ScaledText.tsx');
const QuestionnaireFlow = load('src/skeletonForge/components/QuestionnaireFlow.tsx').default;
const Panel = load('src/skeletonForge/components/ForgeRunPanel.tsx').default;

const noop = () => {};
const never = () => new Promise(() => {});
const tick = () => new Promise((resolve) => setImmediate(resolve));
const LOADED = { onboarded: true, projects: [], prefs: m.DEFAULT_PREFS, projectsCorrupt: false, holdSaves: false, error: null };
const GUEST = { authenticated: false, enforced: false, role: 'anonymous', user: null, observed: true };

/** Manual timers so deadline tests are deterministic and instant. */
function manualTimers() {
  const due = [];
  return {
    set(fn, ms) { const h = { fn, ms, live: true }; due.push(h); return h; },
    clear(handle) { handle.live = false; },
    fire(ms) { for (const h of due) if (h.live && h.ms === ms) { h.live = false; h.fn(); } },
    fireAll() { for (const h of due) if (h.live) { h.live = false; h.fn(); } },
  };
}

// ── Bootstrap deadlines ────────────────────────────────────────────────

test('withDeadline resolves early work and rejects hung work with the stage', async () => {
  const timers = manualTimers();
  assert.equal(await m.withDeadline(async () => 7, 50, 'load', 'slow', timers), 7);
  const hung = m.withDeadline(never, 50, 'auth', 'account slow', timers);
  timers.fire(50);
  await assert.rejects(hung, (error) => error instanceof m.DeadlineError && error.stage === 'auth' && /account slow/.test(error.message));
  const thrown = m.withDeadline(() => { throw new Error('sync boom'); }, 50, 'load', 'x', timers);
  await assert.rejects(thrown, /sync boom/);
});

test('a hung device read holds saves with a clear message instead of an empty studio', async () => {
  const timers = manualTimers();
  const pending = m.bootstrap(never, { async completeWebRedirect() {}, async checkMe() { return GUEST; } }, { timers });
  await tick();
  timers.fire(m.BOOTSTRAP_DEADLINES.load);
  const state = await pending;
  assert.equal(state.holdSaves, true);
  assert.match(state.hydrateError, /did not load in time/);
  assert.notEqual(state.screen, 'boot');
});

test('a hung account check fails closed to sign-in with retry and setup exits', async () => {
  const timers = manualTimers();
  const pending = m.bootstrap(async () => LOADED, { async completeWebRedirect() {}, checkMe: never }, { timers });
  await tick(); await tick();
  timers.fire(m.BOOTSTRAP_DEADLINES.auth);
  const state = await pending;
  assert.equal(state.screen, 'sign-in');
  assert.equal(state.auth.phase, 'unavailable');
  assert.match(state.auth.error, /did not answer in time/);
  assert.ok(m.exits(state).includes('retry'));
  assert.ok(m.exits(state).includes('setup'));
});

test('a hung web redirect does not block hydrating or checking the session', async () => {
  const timers = manualTimers();
  let checked = 0;
  const pending = m.bootstrap(async () => LOADED, {
    completeWebRedirect: never,
    async checkMe() { checked += 1; return GUEST; },
  }, { timers });
  await tick();
  timers.fire(m.BOOTSTRAP_DEADLINES.redirect);
  const state = await pending;
  assert.equal(checked, 1);
  assert.equal(state.screen, 'dashboard');
});

test('deadlines are configurable and late results never overwrite a timed-out stage', async () => {
  const timers = manualTimers();
  let release;
  const late = new Promise((resolve) => { release = resolve; });
  const pending = m.bootstrap(() => late, { async completeWebRedirect() {}, async checkMe() { return GUEST; } },
    { timers, deadlines: { load: 25 } });
  await tick();
  timers.fire(25);
  const state = await pending;
  release({ ...LOADED, projects: [{ id: 'late' }] });
  await tick();
  assert.equal(state.holdSaves, true);
  assert.equal(state.projects.length, 0);
});

// ── Coalescing saver ───────────────────────────────────────────────────

function controlledWrites() {
  const calls = [];
  const write = (snap) => new Promise((resolve, reject) => { calls.push({ snap, resolve, reject }); });
  return { calls, write };
}

test('saves coalesce to one in flight plus the newest pending snapshot', async () => {
  const { calls, write } = controlledWrites();
  const outcomes = [];
  const saver = createSnapshotSaver(write, (o) => outcomes.push(o));
  saver.enqueue('a'); saver.enqueue('b'); saver.enqueue('c'); saver.enqueue('d');
  await tick();
  assert.deepEqual(calls.map((c) => c.snap), ['a']);
  calls[0].resolve();
  await tick(); await tick();
  assert.deepEqual(calls.map((c) => c.snap), ['a', 'd'], 'b and c are superseded and never written');
  assert.equal(outcomes.length, 0, 'the superseded write does not report');
  calls[1].resolve();
  await saver.idle();
  assert.deepEqual(outcomes.map((o) => [o.ok, o.generation]), [[true, 4]]);
});

test('an older success never clears a newer failure, and a newer success clears an older failure', async () => {
  const { calls, write } = controlledWrites();
  const outcomes = [];
  const saver = createSnapshotSaver(write, (o) => outcomes.push(o));
  saver.enqueue('old');
  await tick();
  saver.enqueue('new');
  calls[0].resolve();
  await tick(); await tick();
  calls[1].reject(new Error('disk full'));
  await saver.idle();
  assert.equal(outcomes.length, 1);
  assert.equal(outcomes[0].ok, false);
  assert.match(outcomes[0].error.message, /disk full/);

  saver.enqueue('retry');
  await tick();
  calls[2].resolve();
  await saver.idle();
  assert.equal(outcomes.at(-1).ok, true);
});

test('close() still writes the last edit but reports nothing; dispose() drops pending work', async () => {
  const { calls, write } = controlledWrites();
  const outcomes = [];
  const saver = createSnapshotSaver(write, (o) => outcomes.push(o));
  saver.enqueue('first');
  await tick();
  saver.enqueue('last edit');
  saver.close();
  calls[0].resolve();
  await tick(); await tick();
  assert.deepEqual(calls.map((c) => c.snap), ['first', 'last edit']);
  calls[1].resolve();
  await saver.idle();
  assert.equal(outcomes.length, 0);
  assert.equal(saver.enqueue('after close') > 0, true);
  await tick();
  assert.equal(calls.length, 2, 'nothing new is accepted after close');

  const other = controlledWrites();
  const d = createSnapshotSaver(other.write, noop);
  d.enqueue('x'); await tick(); d.enqueue('y'); d.dispose();
  other.calls[0].resolve();
  await tick(); await tick();
  assert.deepEqual(other.calls.map((c) => c.snap), ['x']);
});

// ── Honest local cancel ────────────────────────────────────────────────

test('local cancel is identified, guided as a retry, and never described as a server stop', () => {
  assert.equal(R.isLocallyCancelled('error', R.RUN_CANCELLED_LOCALLY), true);
  assert.equal(R.isLocallyCancelled('error', 'Backend unreachable'), false);
  assert.equal(R.isLocallyCancelled('done', R.RUN_CANCELLED_LOCALLY), false);
  const guide = m.buildGuidance('error', R.RUN_CANCELLED_LOCALLY, null);
  assert.equal(guide.id, 'retry');
  assert.match(guide.detail, /Nothing from it was applied/);
  const running = m.buildGuidance('running', null, null);
  assert.match(running.detail, /one request/);
  assert.match(running.detail, /cannot be told to stop/);
});

test('the run panel labels the button "Stop waiting" and shows a local stop as a warning, not a failure', () => {
  const live = render(h(Panel, { phase: 'running', payload: null, startedAt: 0, now: 4000, onCancel: noop }));
  assert.match(text(live), /Stop waiting/);
  assert.ok(attrs(live, 'aria-label').some((l) => /Stop waiting/.test(l)) || /Stop waiting/.test(live));
  const stopped = render(h(Panel, { phase: 'error', payload: null, error: R.RUN_CANCELLED_LOCALLY, startedAt: 0, finishedAt: 9000, now: 9000, onRetry: noop }));
  assert.match(text(stopped), /Stopped waiting after 9s/);
  assert.match(stopped, /data-testid="run-cancelled"/);
  assert.doesNotMatch(stopped, /data-testid="run-error"/);
  assert.doesNotMatch(stopped, /role="alert"/);
  const failed = render(h(Panel, { phase: 'error', payload: null, error: 'Backend unreachable', startedAt: 0, finishedAt: 1000, now: 1000 }));
  assert.match(text(failed), /Run failed/);
  assert.match(failed, /role="alert"/);
});

// ── Play handoff ───────────────────────────────────────────────────────

function payload(over = {}) {
  return {
    ...runFixture,
    succeeded: true,
    forge: { ...(runFixture.forge || {}), playable_archetype: 'combat_loop' },
    playable_scene_playtest: { status: 'passed', passed: true, verified: true, scene: 'res://playable/combat_loop.tscn' },
    playable_portal: { sealed: true, return_supported: true },
    source_export: { status: 'ready', bytes: 4096, file_count: 12, manifest_sha256: 'ab'.repeat(32) },
    ...over,
  };
}

test('playHandoff: verified scene with exact-run ZIP is ready to play with literal steps', () => {
  const hand = R.playHandoff(payload(), { target: 'godot', playable_content: true, include_files: true });
  assert.equal(hand.state, 'ready');
  assert.equal(hand.tone, 'ok');
  assert.equal(hand.action, 'export');
  assert.match(hand.title, /Ready to play: Combat Loop/);
  assert.equal(hand.steps.length, 4);
  assert.match(hand.steps[1], /project\.godot/);
  assert.match(hand.steps[3], /in-game launch button/);
});

test('playHandoff covers unverified, missing export, failed, no scene, JSON and unsuccessful runs', () => {
  const unverified = R.playHandoff(payload({ playable_scene_playtest: { status: 'unavailable' } }), { target: 'godot' });
  assert.equal(unverified.state, 'ready-unverified');
  assert.match(unverified.detail, /no engine was installed/);
  const unsealed = R.playHandoff(payload({ playable_portal: undefined }), { target: 'godot' });
  assert.match(unsealed.steps[3], /Play Scene \(F6\)/);
  const noExport = R.playHandoff(payload({ source_export: null }), { target: 'godot' });
  assert.equal(noExport.state, 'needs-export');
  assert.equal(noExport.action, 'edit-brief');
  const failed = R.playHandoff(payload({ playable_scene_playtest: { status: 'failed', passed: false, errors: ['player fell through floor'] } }), { target: 'godot' });
  assert.equal(failed.state, 'failed');
  assert.equal(failed.tone, 'bad');
  assert.match(failed.detail, /player fell through floor/);
  assert.equal(failed.steps.length, 0, 'a failed scene never invites play');
  const none = R.playHandoff(payload({ forge: { ...runFixture.forge, playable_archetype: null } }), { target: 'godot' });
  assert.equal(none.state, 'not-requested');
  const json = R.playHandoff(payload({ forge: { ...runFixture.forge, playable_archetype: null } }), { target: 'json' });
  assert.equal(json.state, 'json-target');
  assert.equal(R.playHandoff({ ...payload(), succeeded: false, run: { ...runFixture.run, succeeded: false } }, { target: 'godot' }), null);
  assert.equal(R.playHandoff(null), null);
});

function build(over = {}) {
  return h(BuildStatusScreen, {
    title: 'A heist', phase: 'done', payload: payload(), error: null, startedAt: 0, finishedAt: 2000, now: 2000,
    request: { target: 'godot', playable_content: true, include_files: true }, live: true,
    onExport: noop, onRetry: noop,
    guidance: { id: 'projects', label: 'Back to projects', detail: 'The build finished.' },
    onGuidance: noop, consoleBusy: false, consoleSummary: null, consoleOk: null, consoleFailures: 0, onAskCockpit: noop,
    onBrief: noop, onProjects: noop, onOpenCockpit: noop,
    ...over,
  });
}

test('build screen renders the Play handoff with an accessible ordered step list and export action', () => {
  const html = render(build());
  assert.match(html, /data-testid="studio-play-handoff"/);
  assert.match(text(html), /Ready to play: Combat Loop/);
  assert.match(html, /data-testid="studio-play-export"/);
  assert.match(html, /role="list"/);
  const labels = attrs(html, 'aria-label');
  assert.ok(labels.includes('How to play'));
  assert.ok(labels.some((l) => /^Step 1 of 4\. Save the Godot ZIP/.test(l)));
});

test('a reopened build from an earlier session offers "Forge again to play" instead of a dead export', () => {
  const html = render(build({ live: false, onExport: undefined }));
  assert.doesNotMatch(html, /data-testid="studio-play-export"/);
  assert.match(html, /data-testid="studio-play-retry"/);
  assert.match(text(html), /only kept for the session that forged them/);
});

test('no Play card while running, after a failure, or after a local stop', () => {
  for (const over of [
    { phase: 'running', payload: null, finishedAt: null },
    { phase: 'error', payload: null, error: 'Backend unreachable' },
    { phase: 'error', payload: null, error: R.RUN_CANCELLED_LOCALLY },
  ]) {
    assert.doesNotMatch(render(build(over)), /data-testid="studio-play-handoff"/);
  }
});

// ── Reduced motion and text scaling ────────────────────────────────────

test('the build screen passes the studio reduced-motion preference to the run panel', () => {
  const running = { phase: 'running', payload: null, finishedAt: null, now: 3000 };
  const moving = render(h(StudioA11yProvider, { value: { reduceMotion: false, textScale: 1, allowSystemFontScaling: true }, children: build(running) }));
  assert.ok(attrs(moving, 'aria-label').includes('Forge running'));
  const still = render(h(StudioA11yProvider, { value: { reduceMotion: true, textScale: 1, allowSystemFontScaling: true }, children: build(running) }));
  assert.ok(!attrs(still, 'aria-label').includes('Forge running'));
  assert.match(text(still), /Forging…/);
});

test('scaleStyle scales flattened font metrics and leaves default scale untouched', () => {
  const base = { fontSize: 15, lineHeight: 22, color: 'red' };
  const a = { reduceMotion: false, textScale: 1.4, allowSystemFontScaling: false };
  assert.deepEqual(scaleStyle([base, { fontWeight: '800' }], a), { fontSize: 21, lineHeight: 31, color: 'red', fontWeight: '800' });
  const same = [base];
  assert.equal(scaleStyle(same, { ...a, textScale: 1 }), same);
  assert.equal(scaleStyle(null, a), null);
});

test('questionnaire copy follows the studio text size and disables system double-scaling', () => {
  const props = { state: { ...Q.INITIAL_STATE, vision: 'a heist with a butler' }, dispatch: noop, beats: Q.FALLBACK_BEATS, onForge: noop };
  const plain = render(h(QuestionnaireFlow, props));
  const big = render(h(StudioA11yProvider, { value: { reduceMotion: false, textScale: 1.4, allowSystemFontScaling: false }, children: h(QuestionnaireFlow, props) }));
  const sizes = (html) => (html.match(/font-size:\s*(\d+)px/g) || []).map((s) => Number(s.match(/(\d+)px/)[1]));
  const before = Math.max(...sizes(plain));
  const after = Math.max(...sizes(big));
  assert.ok(after >= Math.round(before * 1.4) - 1, `expected scaled type, got ${before} -> ${after}`);
  assert.match(text(big), /What are you making\?/);
});
