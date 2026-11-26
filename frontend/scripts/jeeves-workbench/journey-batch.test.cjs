const { test } = require('node:test');
const { assert, load, harness, memoryStorage, assertValid } = require('./helpers.cjs');
const { WorkbenchStore } = load('WorkbenchStore');
const { WORKBENCH_KEY } = load('types');

async function open() {
  const clock = harness('journey').clock;
  const storage = memoryStorage();
  const store = new WorkbenchStore(storage, clock);
  await store.initialize();
  await store.settled();
  const projectId = store.dispatch({ type: 'project.create', input: { title: 'Reviewed plan' } }).createdId;
  await store.settled();
  const task = title => ({ type: 'task.create', input: { projectId, title, status: 'inbox' } });
  return { store, storage, projectId, task };
}

test('forward and backward command references resolve to actual task IDs, not clock positions', async () => {
  const { store, task, projectId } = await open();
  const commands = [
    task('Publish after both checks'),
    { type: 'note.create', input: { projectId, title: 'Acceptance', body: 'Observe the real result.' } },
    task('Build'),
    task('Review the build'),
  ];
  const edges = { 0: [2, 3], 3: [2] };
  const beforeCommands = JSON.stringify(commands);
  const beforeEdges = JSON.stringify(edges);
  assert.equal(store.dispatchBatch(commands, edges), true);
  const state = store.getSnapshot().state;
  const byTitle = title => state.tasks.find(item => item.title === title);
  assert.deepEqual(byTitle('Publish after both checks').dependencies,
    [byTitle('Build').id, byTitle('Review the build').id]);
  assert.deepEqual(byTitle('Review the build').dependencies, [byTitle('Build').id]);
  assert.deepEqual(byTitle('Build').dependencies, []);
  assert.equal(JSON.stringify(commands), beforeCommands);
  assert.equal(JSON.stringify(edges), beforeEdges);
  assertValid(state);
  await store.settled();
});

test('existing prerequisites are retained alongside batch-created prerequisites', async () => {
  const { store, task } = await open();
  const existing = store.dispatch(task('Existing prerequisite')).createdId;
  const target = task('Dependent');
  target.input.dependencies = [existing];
  assert.equal(store.dispatchBatch([target, task('New prerequisite')], { 0: [1] }), true);
  const state = store.getSnapshot().state;
  assert.deepEqual(state.tasks.find(item => item.title === 'Dependent').dependencies,
    [existing, state.tasks.find(item => item.title === 'New prerequisite').id]);
  assertValid(state);
  await store.settled();
});

test('dependency batch publishes and persists only the complete graph and uses one undo entry', async () => {
  const { store, storage, task } = await open();
  const before = store.getSnapshot().state;
  const writes = storage.writes.filter(item => item.key === WORKBENCH_KEY).length;
  const observed = new Set();
  const unsubscribe = store.subscribe(() => observed.add(store.getSnapshot().state));
  assert.equal(store.dispatchBatch([task('Design'), task('Build'), task('Check')], { 1: [0], 2: [1] }), true);
  const applied = store.getSnapshot().state;
  await store.settled();
  unsubscribe();
  assert.deepEqual([...observed], [applied]);
  assert.equal(storage.writes.filter(item => item.key === WORKBENCH_KEY).length, writes + 1);
  assert.deepEqual(JSON.parse(storage.data.get(WORKBENCH_KEY)).tasks, applied.tasks);
  store.undo();
  assert.deepEqual(store.getSnapshot().state.tasks, before.tasks);
  assert.deepEqual(store.getSnapshot().state.notes, before.notes);
  await store.settled();
  assert.deepEqual(JSON.parse(storage.data.get(WORKBENCH_KEY)).tasks, before.tasks);
  store.redo();
  const restored = store.getSnapshot().state;
  assert.deepEqual(restored.tasks.map(item => [item.id, item.dependencies]),
    applied.tasks.map(item => [item.id, item.dependencies]));
  assertValid(restored);
  await store.settled();
});

test('cycles are rejected without publishing, persisting or adding an undo entry', async () => {
  const { store, storage, task } = await open();
  const before = store.getSnapshot().state;
  const writes = storage.writes.length;
  assert.equal(store.dispatchBatch([task('First'), task('Second'), task('Third')],
    { 0: [2], 1: [0], 2: [1] }), false);
  assert.equal(store.getSnapshot().state, before);
  assert.match(store.getSnapshot().notice, /cycle/i);
  await store.settled();
  assert.equal(storage.writes.length, writes);
  store.undo();
  assert.equal(store.getSnapshot().state.projects.length, 0,
    'the previous project creation remains the latest undoable transaction');
  await store.settled();
});

test('invalid, duplicate, self and non-task command references fail atomically', async () => {
  const { store, storage, task, projectId } = await open();
  const commands = [task('First'), task('Second'),
    { type: 'note.create', input: { projectId, title: 'A note' } }];
  const invalid = [
    { 0: [0] }, { 0: [1, 1] }, { 0: [-1] }, { 0: [3] }, { 3: [0] },
    { 0: [1.5] }, { 0: ['1'] }, { 0: [true] }, { 0: [2] }, { 2: [0] },
    { '-1': [0] }, { '01': [0] }, { '1.0': [0] }, { 0: null },
    null, [], Object.create({ 0: [1] }), { [Symbol('index')]: [1] },
  ];
  const accessor = {};
  Object.defineProperty(accessor, '0', { enumerable: true, get() { throw new Error('Getter must remain inert.'); } });
  invalid.push(accessor);
  const before = store.getSnapshot().state;
  const writes = storage.writes.length;
  for (const edges of invalid) {
    assert.equal(store.dispatchBatch(commands, edges), false);
    assert.equal(store.getSnapshot().state, before);
  }
  await store.settled();
  assert.equal(storage.writes.length, writes);
});

test('domain authority rejects cross-project edges and blocked active-task transitions', async () => {
  const { store, task } = await open();
  const otherProject = store.dispatch({ type: 'project.create', input: { title: 'Other project' } }).createdId;
  const before = store.getSnapshot().state;
  const foreign = { type: 'task.create', input: { projectId: otherProject, title: 'Foreign prerequisite' } };
  assert.equal(store.dispatchBatch([task('Local task'), foreign], { 0: [1] }), false);
  assert.equal(store.getSnapshot().state, before);
  assert.match(store.getSnapshot().notice, /same project/i);
  const active = task('Already working');
  active.input.status = 'doing';
  assert.equal(store.dispatchBatch([active, task('Unfinished prerequisite')], { 0: [1] }), false);
  assert.equal(store.getSnapshot().state, before);
  assert.match(store.getSnapshot().notice, /Complete dependencies first/);
  await store.settled();
});

test('legacy batches and empty optional edge maps preserve existing behavior', async () => {
  const { store, task } = await open();
  assert.equal(store.dispatchBatch([task('Legacy task')]), true);
  assert.equal(store.dispatchBatch([task('No links')], {}), true);
  assert.equal(store.dispatchBatch([task('Explicit empty links')], { 0: [] }), true);
  assert.deepEqual(store.getSnapshot().state.tasks.map(item => item.dependencies), [[], [], []]);
  assertValid(store.getSnapshot().state);
  await store.settled();
});

test('storage failure preserves one complete in-memory graph for explicit save retry', async () => {
  const { store, storage, task } = await open();
  const previousDisk = storage.data.get(WORKBENCH_KEY);
  const save = storage.setItem;
  storage.setItem = async (key, value) => {
    if (key === WORKBENCH_KEY) throw new Error('Device full');
    return save(key, value);
  };
  assert.equal(store.dispatchBatch([task('First'), task('Second')], { 1: [0] }), true);
  const applied = store.getSnapshot().state;
  await store.settled();
  assert.equal(store.getSnapshot().saveStatus, 'failed');
  assert.equal(storage.data.get(WORKBENCH_KEY), previousDisk);
  assert.deepEqual(applied.tasks[1].dependencies, [applied.tasks[0].id]);
  storage.setItem = save;
  store.retrySave();
  await store.settled();
  assert.equal(store.getSnapshot().saveStatus, 'saved');
  assert.deepEqual(JSON.parse(storage.data.get(WORKBENCH_KEY)).tasks, applied.tasks);
});
