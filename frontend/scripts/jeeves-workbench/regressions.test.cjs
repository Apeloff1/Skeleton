const { test } = require('node:test');
const { assert, load, harness, linkedFixture, memoryStorage, assertValid } = require('./helpers.cjs');
const { WorkbenchStore } = load('WorkbenchStore');
const { WORKBENCH_KEY } = load('types');
const { inspectIntegrity } = load('integrity');
const { previewBackup, backupEnvelope } = load('backup');
const { previewTaskTable, validIntakeValues } = load('intake');
const { taskDiscussionPrompt } = load('context');
const { MINUTE } = load('review');

async function openFixture() {
  const fixture = linkedFixture();
  const storage = memoryStorage({ [WORKBENCH_KEY]: JSON.stringify(fixture.h.state) });
  const store = new WorkbenchStore(storage, fixture.h.clock);
  await store.initialize();
  return { ...fixture, store, storage };
}

test('undo never reuses a revision held by an old task editor', async () => {
  const { store, task } = await openFixture();
  const original = store.getSnapshot().state.tasks.find(item => item.id === task);
  store.dispatch({ type: 'task.update', id: task, revision: original.revision, patch: { title: 'Edited title' } });
  store.undo();
  const restored = store.getSnapshot().state.tasks.find(item => item.id === task);
  assert.equal(restored.title, original.title);
  assert.ok(restored.revision > original.revision);
  assert.equal(store.dispatch({ type: 'task.update', id: task, revision: original.revision, patch: { title: 'Stale overwrite' } }), null);
  assert.equal(store.getSnapshot().state.tasks.find(item => item.id === task).title, original.title);
  await store.settled();
});

test('delete and undo resurrection invalidates the deleted record’s old editor', async () => {
  const { store, note } = await openFixture();
  const original = store.getSnapshot().state.notes.find(item => item.id === note);
  store.dispatch({ type: 'note.delete', id: note, revision: original.revision });
  store.undo();
  const restored = store.getSnapshot().state.notes.find(item => item.id === note);
  assert.ok(restored.revision > original.revision);
  assert.equal(store.dispatch({ type: 'note.update', id: note, revision: original.revision, patch: { body: 'Old editor' } }), null);
  assert.equal(restored.body, original.body);
  await store.settled();
});

test('redo increases record revisions again while restoring the intended content', async () => {
  const { store, note } = await openFixture();
  const original = store.getSnapshot().state.notes.find(item => item.id === note);
  store.dispatch({ type: 'note.update', id: note, revision: original.revision, patch: { body: 'New content' } });
  const editedRevision = store.getSnapshot().state.notes.find(item => item.id === note).revision;
  store.undo();
  const undoRevision = store.getSnapshot().state.notes.find(item => item.id === note).revision;
  store.redo();
  const redone = store.getSnapshot().state.notes.find(item => item.id === note);
  assert.ok(undoRevision > editedRevision);
  assert.ok(redone.revision > undoRevision);
  assert.equal(redone.body, 'New content');
  await store.settled();
});

test('ordinary edits preserve monotonic update timestamps when the device clock moves backward', () => {
  const h = harness();
  const projectId = h.project();
  h.advance(10 * MINUTE);
  h.update('project', projectId, { title: 'New title' });
  const updatedAt = h.record('projects', projectId).updatedAt;
  h.advance(-5 * MINUTE);
  h.update('project', projectId, { summary: 'Still useful' });
  assert.equal(h.record('projects', projectId).updatedAt, updatedAt);
  assertValid(h.state);
});

test('focus finish rejects a clock rollback after a completed pause-resume cycle', () => {
  const h = harness();
  const projectId = h.project();
  const id = h.run({ type: 'focus.start', projectId, taskId: null, minutes: 25 });
  h.advance(5 * MINUTE);
  h.run({ type: 'focus.pause', id });
  h.advance(10 * MINUTE);
  h.run({ type: 'focus.resume', id });
  h.advance(-5 * MINUTE);
  assert.throws(() => h.run({ type: 'focus.finish', id, outcome: 'completed', reflection: '' }), /clock moved backwards/);
  assert.equal(h.record('sessions', id).outcome, 'running');
});

test('an imported completed task cannot depend on unfinished work', () => {
  const { h, task } = linkedFixture();
  const candidate = structuredClone(h.state);
  const completed = candidate.tasks.find(item => item.id === task);
  completed.status = 'done';
  completed.completedAt = h.now;
  const issues = inspectIntegrity(candidate);
  assert.ok(issues.some(issue => issue.message.includes('unfinished dependencies')));
  const preview = previewBackup(JSON.stringify(backupEnvelope(candidate, h.now)));
  assert.equal(preview.ok, false);
});

test('minimal title-only CSV works without optional status and priority headers', () => {
  const preview = previewTaskTable('title\nCreate scene\nBuild movement', 'project');
  assert.equal(preview.invalid, 0);
  const values = validIntakeValues(preview);
  assert.equal(values.length, 2);
  assert.ok(values.every(value => value.status === 'inbox'));
  assert.ok(values.every(value => value.priority === 'normal'));
  assert.ok(values.every(value => value.estimateMinutes === 25));
});

test('very long task descriptions produce a usable bounded chat draft', () => {
  const prompt = taskDiscussionPrompt('Complex task', 'x'.repeat(30000));
  assert.ok(prompt.length < 16000);
  assert.match(prompt, /Description shortened for chat/);
  assert.match(prompt, /verify the result/);
  const short = taskDiscussionPrompt('Small task', 'Short description');
  assert.ok(!short.includes('shortened'));
});

test('source links restored by undo still point to the restored source IDs', async () => {
  const { store, source, card, note } = await openFixture();
  const record = store.getSnapshot().state.sources.find(item => item.id === source);
  store.dispatch({ type: 'source.delete', id: source, revision: record.revision });
  store.undo();
  const state = store.getSnapshot().state;
  assert.deepEqual(state.cards.find(item => item.id === card).sourceIds, [source]);
  assert.deepEqual(state.notes.find(item => item.id === note).sourceIds, [source]);
  assertValid(state);
  await store.settled();
});

test('CSV batch import with done and ready tasks retains completion semantics', async () => {
  const { store, project } = await openFixture();
  const preview = previewTaskTable('title,status\nImported done,done\nImported ready,ready', project);
  const commands = validIntakeValues(preview).map(input => ({ type: 'task.create', input }));
  assert.equal(store.dispatchBatch(commands), true);
  const tasks = store.getSnapshot().state.tasks;
  assert.ok(tasks.find(task => task.title === 'Imported done').completedAt);
  assert.equal(tasks.find(task => task.title === 'Imported ready').completedAt, null);
  store.undo();
  assert.ok(!store.getSnapshot().state.tasks.some(task => task.title.startsWith('Imported')));
  await store.settled();
});
