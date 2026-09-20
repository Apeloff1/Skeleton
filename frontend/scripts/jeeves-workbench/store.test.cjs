const { test } = require('node:test');
const { assert, load, harness, linkedFixture, memoryStorage, deferred, tick, assertValid } = require('./helpers.cjs');
const { WorkbenchStore } = load('WorkbenchStore');
const { WORKBENCH_KEY, RECOVERY_KEY } = load('types');
const { encodeBackup } = load('backup');

async function open(initial = {}, customStorage) {
  const h = harness('clock');
  const storage = customStorage || memoryStorage(initial);
  const store = new WorkbenchStore(storage, h.clock);
  await store.initialize();
  await store.settled();
  return { h, storage, store };
}

function addProject(store, title = 'Prototype') {
  return store.dispatch({ type: 'project.create', input: { title } });
}

test('first open initializes a valid persisted workspace and is idempotent', async () => {
  const { store, storage } = await open();
  assert.equal(store.getSnapshot().ready, true);
  assert.equal(store.getSnapshot().saveStatus, 'saved');
  const writes = storage.writes.length;
  await Promise.all([store.initialize(), store.initialize()]);
  assert.equal(storage.writes.length, writes);
  assertValid(JSON.parse(storage.data.get(WORKBENCH_KEY)));
});

test('concurrent initialization shares one pending read', async () => {
  const storage = memoryStorage();
  const gate = deferred();
  let reads = 0;
  storage.getItem = async key => {
    if (key === WORKBENCH_KEY && reads++ === 0) await gate.promise;
    return null;
  };
  const h = harness();
  const store = new WorkbenchStore(storage, h.clock);
  const first = store.initialize();
  const second = store.initialize();
  assert.equal(first, second);
  assert.equal(store.getSnapshot().loading, true);
  assert.equal(addProject(store), null);
  gate.resolve();
  await first;
  await store.settled();
  assert.equal(store.getSnapshot().state.projects.length, 0);
});

test('corrupt saved data is left untouched and blocks edits', async () => {
  const raw = '{not-json';
  const { store, storage } = await open({ [WORKBENCH_KEY]: raw });
  assert.equal(store.getSnapshot().ready, false);
  assert.match(store.getSnapshot().error, /Existing data has not been changed/);
  assert.equal(addProject(store), null);
  assert.equal(storage.data.get(WORKBENCH_KEY), raw);
  assert.equal(storage.writes.length, 0);
});

test('read failures leave the store retryable after device storage recovers', async () => {
  const storage = memoryStorage();
  const get = storage.getItem;
  storage.getItem = async () => { throw new Error('unavailable'); };
  const { store } = await open({}, storage);
  assert.equal(store.getSnapshot().ready, false);
  storage.getItem = get;
  await store.initialize();
  await store.settled();
  assert.equal(store.getSnapshot().ready, true);
});

test('a failed write retains changes in memory and can retry without losing the edit', async () => {
  const { store, storage } = await open();
  const saved = storage.data.get(WORKBENCH_KEY);
  const set = storage.setItem;
  storage.setItem = async key => { if (key === WORKBENCH_KEY) throw new Error('quota'); };
  addProject(store, 'Unsaved project');
  await store.settled();
  assert.equal(store.getSnapshot().saveStatus, 'failed');
  assert.equal(store.getSnapshot().state.projects[0].title, 'Unsaved project');
  assert.equal(storage.data.get(WORKBENCH_KEY), saved);
  storage.setItem = set;
  store.retrySave();
  await store.settled();
  assert.equal(store.getSnapshot().saveStatus, 'saved');
  assert.equal(JSON.parse(storage.data.get(WORKBENCH_KEY)).projects[0].title, 'Unsaved project');
});

test('rapid edits during a delayed write are persisted in order with the newest state last', async () => {
  const { store, storage } = await open();
  const gate = deferred();
  const set = storage.setItem;
  let blocked = true;
  storage.setItem = async (key, value) => {
    if (key === WORKBENCH_KEY && blocked) { blocked = false; await gate.promise; }
    await set(key, value);
  };
  addProject(store, 'First');
  await tick();
  addProject(store, 'Second');
  addProject(store, 'Third');
  gate.resolve();
  await store.settled();
  const saved = JSON.parse(storage.data.get(WORKBENCH_KEY));
  assert.deepEqual(saved.projects.map(item => item.title), ['First', 'Second', 'Third']);
  const revisions = storage.writes.filter(item => item.key === WORKBENCH_KEY).map(item => JSON.parse(item.value).revision);
  assert.deepEqual(revisions, [...revisions].sort((a, b) => a - b));
});

test('another writer triggers a conflict and its saved value is never overwritten', async () => {
  const { store, storage } = await open();
  const other = harness('other');
  other.project({ title: 'Other tab' });
  const external = JSON.stringify(other.state);
  storage.data.set(WORKBENCH_KEY, external);
  addProject(store, 'My unsaved work');
  await store.settled();
  assert.equal(store.getSnapshot().saveStatus, 'conflict');
  assert.equal(storage.data.get(WORKBENCH_KEY), external);
  assert.equal(addProject(store, 'Blocked'), null);
  store.undo();
  assert.equal(store.getSnapshot().state.projects[0].title, 'My unsaved work');
  await store.reloadSaved();
  assert.equal(store.getSnapshot().state.projects[0].title, 'Other tab');
  assert.equal(store.getSnapshot().undoAvailable, false);
});

test('undo and redo restore complete linked snapshots and persist the result', async () => {
  const { h } = linkedFixture();
  const { store, storage } = await open({ [WORKBENCH_KEY]: JSON.stringify(h.state) });
  const source = store.getSnapshot().state.sources[0];
  store.dispatch({ type: 'source.delete', id: source.id, revision: source.revision });
  assert.equal(store.getSnapshot().state.notes[0].sourceIds.length, 0);
  store.undo();
  assert.equal(store.getSnapshot().state.sources.length, 1);
  assert.deepEqual(store.getSnapshot().state.notes[0].sourceIds, [source.id]);
  assert.equal(store.getSnapshot().redoAvailable, true);
  store.redo();
  assert.equal(store.getSnapshot().state.sources.length, 0);
  await store.settled();
  assertValid(JSON.parse(storage.data.get(WORKBENCH_KEY)));
});

test('a new edit after undo clears the redo branch', async () => {
  const { store } = await open();
  addProject(store, 'First');
  addProject(store, 'Second');
  store.undo();
  addProject(store, 'Replacement');
  assert.equal(store.getSnapshot().redoAvailable, false);
  store.redo();
  assert.deepEqual(store.getSnapshot().state.projects.map(item => item.title), ['First', 'Replacement']);
  await store.settled();
});

test('undo history is bounded to twenty changes', async () => {
  const { store } = await open();
  addProject(store);
  const projectId = store.getSnapshot().state.activeProjectId;
  for (let index = 0; index < 25; index++) store.dispatch({ type: 'task.create', input: { projectId, title: `Task ${index}` } });
  for (let index = 0; index < 30; index++) store.undo();
  assert.equal(store.getSnapshot().state.tasks.length, 5);
  assert.equal(store.getSnapshot().undoAvailable, false);
  await store.settled();
});

test('batch application is atomic and uses a single undo entry', async () => {
  const { store } = await open();
  addProject(store);
  const projectId = store.getSnapshot().state.activeProjectId;
  const valid = { type: 'task.create', input: { projectId, title: 'Valid' } };
  const invalid = { type: 'task.create', input: { projectId, title: '' } };
  assert.equal(store.dispatchBatch([valid, invalid]), false);
  assert.equal(store.getSnapshot().state.tasks.length, 0);
  assert.equal(store.dispatchBatch([valid, valid]), true);
  assert.equal(store.getSnapshot().state.tasks.length, 2);
  store.undo();
  assert.equal(store.getSnapshot().state.tasks.length, 0);
  store.redo();
  assert.equal(store.getSnapshot().state.tasks.length, 2);
  await store.settled();
});

test('empty and oversized batches are rejected without state changes', async () => {
  const { store } = await open();
  const before = store.getSnapshot().state;
  assert.equal(store.dispatchBatch([]), false);
  assert.equal(store.dispatchBatch(Array(501).fill({ type: 'project.select', id: null })), false);
  assert.equal(store.getSnapshot().state, before);
});

test('restoring recovery replaces corrupt main data without destroying the valid recovery copy', async () => {
  const { h } = linkedFixture('recovered');
  const recovery = JSON.stringify(h.state);
  const { store, storage } = await open({ [WORKBENCH_KEY]: '{broken', [RECOVERY_KEY]: recovery });
  assert.equal(store.getSnapshot().ready, false);
  assert.equal(store.getSnapshot().recoveryAvailable, true);
  assert.equal(await store.restoreRecovery(), true);
  assert.equal(store.getSnapshot().ready, true);
  assert.equal(storage.data.get(RECOVERY_KEY), recovery);
  assert.equal(store.getSnapshot().state.projects[0].title, h.state.projects[0].title);
  assertValid(JSON.parse(storage.data.get(WORKBENCH_KEY)));
});

test('invalid recovery never overwrites the main saved version', async () => {
  const { store, storage } = await open({ [RECOVERY_KEY]: '{bad' });
  const saved = storage.data.get(WORKBENCH_KEY);
  assert.equal(await store.restoreRecovery(), false);
  assert.equal(storage.data.get(WORKBENCH_KEY), saved);
});

test('replacement import can be undone to restore previous projects', async () => {
  const { store } = await open();
  addProject(store, 'Original');
  const { h } = linkedFixture('incoming');
  const backup = encodeBackup(h.state, h.now);
  assert.equal(store.importBackup(backup, 'replace'), true);
  assert.equal(store.getSnapshot().state.tasks.length, 2);
  store.undo();
  assert.equal(store.getSnapshot().state.projects[0].title, 'Original');
  assert.equal(store.getSnapshot().state.tasks.length, 0);
  await store.settled();
});

test('subscription cleanup stops notifications without affecting other subscribers', async () => {
  const { store } = await open();
  let first = 0;
  let second = 0;
  const remove = store.subscribe(() => first++);
  const removeSecond = store.subscribe(() => second++);
  store.notify('One');
  remove();
  store.notify('Two');
  removeSecond();
  assert.equal(first, 1);
  assert.equal(second, 2);
});
