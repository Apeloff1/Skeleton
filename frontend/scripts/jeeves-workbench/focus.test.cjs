const { test } = require('node:test');
const { assert, load, harness, linkedFixture } = require('./helpers.cjs');
const { elapsedFocus, remainingFocus, formatDuration, formatMinutes } = load('selectors');
const { inspectIntegrity } = load('integrity');
const MINUTE = 60000;

test('only one focus session can run across all projects', () => {
  const h = harness();
  const first = h.project();
  h.run({ type: 'focus.start', projectId: first, taskId: null, minutes: 25 });
  const second = h.project({ title: 'Second' });
  assert.throws(() => h.run({ type: 'focus.start', projectId: second, taskId: null, minutes: 25 }), /current focus/i);
  assert.equal(h.state.sessions.length, 1);
});

test('pause and resume exclude paused time from active focus duration', () => {
  const h = harness();
  const projectId = h.project();
  const id = h.run({ type: 'focus.start', projectId, taskId: null, minutes: 25 });
  h.advance(5 * MINUTE);
  h.run({ type: 'focus.pause', id });
  h.advance(10 * MINUTE);
  assert.equal(elapsedFocus(h.record('sessions', id), h.now), 5 * MINUTE);
  h.run({ type: 'focus.resume', id });
  h.advance(2 * MINUTE);
  const session = h.record('sessions', id);
  assert.equal(session.pausedMilliseconds, 10 * MINUTE);
  assert.equal(elapsedFocus(session, h.now), 7 * MINUTE);
  assert.equal(remainingFocus(session, h.now), 18 * MINUTE);
});

test('finishing a paused session accounts for the final pause once', () => {
  const h = harness();
  const projectId = h.project();
  const id = h.run({ type: 'focus.start', projectId, taskId: null, minutes: 10 });
  h.advance(4 * MINUTE);
  h.run({ type: 'focus.pause', id });
  h.advance(3 * MINUTE);
  h.run({ type: 'focus.finish', id, outcome: 'completed', reflection: 'Movement works; camera next.' });
  const session = h.record('sessions', id);
  assert.equal(session.pausedAt, null);
  assert.equal(session.pausedMilliseconds, 3 * MINUTE);
  assert.equal(session.reflection, 'Movement works; camera next.');
  assert.equal(elapsedFocus(session, h.now + 100000), 4 * MINUTE);
  assert.throws(() => h.run({ type: 'focus.finish', id, outcome: 'completed', reflection: 'Again' }));
});

test('ending a timer does not claim its task is completed', () => {
  const h = harness();
  const projectId = h.project();
  const taskId = h.task();
  const id = h.run({ type: 'focus.start', projectId, taskId, minutes: 25 });
  h.advance(25 * MINUTE);
  h.run({ type: 'focus.finish', id, outcome: 'completed', reflection: '' });
  assert.notEqual(h.record('tasks', taskId).status, 'done');
  assert.equal(h.record('sessions', id).outcome, 'completed');
});

test('blocked tasks cannot start focus sessions until prerequisites are completed', () => {
  const { h, project, task, prerequisite } = linkedFixture();
  assert.throws(() => h.run({ type: 'focus.start', projectId: project, taskId: task, minutes: 25 }), /depend|start/i);
  h.status(prerequisite, 'done');
  h.run({ type: 'focus.start', projectId: project, taskId: task, minutes: 25 });
  assert.equal(h.state.sessions[0].taskId, task);
});

test('running sessions protect their project from archive and deletion', () => {
  const h = harness();
  const projectId = h.project();
  const id = h.run({ type: 'focus.start', projectId, taskId: null, minutes: 25 });
  assert.throws(() => h.update('project', projectId, { status: 'archived' }), /running/);
  assert.throws(() => h.remove('project', projectId), /running/);
  h.run({ type: 'focus.finish', id, outcome: 'abandoned', reflection: '' });
  h.update('project', projectId, { status: 'archived' });
  assert.equal(h.state.projects[0].status, 'archived');
});

test('running focus sessions cannot be deleted', () => {
  const h = harness();
  const projectId = h.project();
  const id = h.run({ type: 'focus.start', projectId, taskId: null, minutes: 5 });
  const session = h.record('sessions', id);
  assert.throws(() => h.run({ type: 'focus.delete', id, revision: session.revision }), /End this session/i);
  h.run({ type: 'focus.finish', id, outcome: 'abandoned', reflection: 'Interrupted' });
  h.run({ type: 'focus.delete', id, revision: h.record('sessions', id).revision });
  assert.equal(h.state.sessions.length, 0);
});

test('foreign task links and invalid duration reject a focus start', () => {
  const h = harness();
  h.project();
  const taskId = h.task();
  const projectId = h.project({ title: 'Other' });
  assert.throws(() => h.run({ type: 'focus.start', projectId, taskId, minutes: 25 }));
  for (const minutes of [0, -1, 481, 1.5, NaN]) {
    assert.throws(() => h.run({ type: 'focus.start', projectId, taskId: null, minutes }));
  }
  assert.equal(h.state.sessions.length, 0);
});

test('focus duration clamps at zero and remaining time never becomes negative', () => {
  const h = harness();
  const projectId = h.project();
  const id = h.run({ type: 'focus.start', projectId, taskId: null, minutes: 5 });
  const session = h.record('sessions', id);
  assert.equal(elapsedFocus(session, h.now - MINUTE), 0);
  assert.equal(remainingFocus(session, h.now + 10 * MINUTE), 0);
  assert.equal(formatDuration(65000), '01:05');
  assert.equal(formatMinutes(90), '1h 30m');
});

test('import integrity detects overlapping running timers and impossible paused durations', () => {
  const h = harness();
  const projectId = h.project();
  const id = h.run({ type: 'focus.start', projectId, taskId: null, minutes: 5 });
  const candidate = structuredClone(h.state);
  candidate.sessions.push({ ...candidate.sessions[0], id: 'second-timer' });
  assert.ok(inspectIntegrity(candidate).some(issue => issue.message.includes('Only one')));
  candidate.sessions = [{ ...h.record('sessions', id), outcome: 'completed', endedAt: h.now + 1000, pausedMilliseconds: 2000 }];
  assert.ok(inspectIntegrity(candidate).some(issue => issue.message.includes('Paused time')));
});
