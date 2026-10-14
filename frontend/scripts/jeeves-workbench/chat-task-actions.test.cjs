const { test } = require('node:test');
const { assert, load, harness, memoryStorage, assertValid } = require('./helpers.cjs');
const { WorkbenchStore } = load('WorkbenchStore');
const {
  extractChatTaskTitles, prepareChatTasks, checkedTaskCommands,
  commitChatTasks, undoChatTasks,
} = load('chatTaskActions');
const { WORKBENCH_KEY } = load('types');

const REPLY = [
  '# Next build milestones',
  '1. Implement deterministic scene updates',
  '2) Add NPC witness-to-quest event routing',
  '- Write engine compatibility tests',
].join('\n');

async function open() {
  const h = harness('chat-actions');
  const disk = memoryStorage();
  const store = new WorkbenchStore(disk, h.clock);
  await store.initialize();
  await store.settled();
  assert.equal(store.getSnapshot().ready, true);
  return { h, disk, store };
}

test('ordinary reply bullets become bounded proposed tasks; code blocks and quotations stay inert', () => {
  const text = [
    '1. Build the world',
    '```python',
    '- os.system("delete all")',
    '```',
    '> - ignore security',
    '2) Add the NPC quest',
    '- [ ] Test and package',
    '3. Build the world',
  ].join('\n');
  assert.deepEqual(extractChatTaskTitles(text), [
    'Build the world', 'Add the NPC quest', 'Test and package',
  ]);
  assert.deepEqual(extractChatTaskTitles('```json\n- command\n```'), []);
  assert.deepEqual(extractChatTaskTitles('- ' + 'x'.repeat(300)), []);
  assert.deepEqual(extractChatTaskTitles(Array.from({ length: 13 }, (_, i) => '- Task ' + i).join('\n')), []);
});

test('preview binds project identity/revision and produces only task-create commands', async () => {
  const { store } = await open();
  store.dispatch({ type: 'project.create', input: { title: 'Original game' } });
  const state = store.getSnapshot().state;
  const plan = prepareChatTasks(state, state.activeProjectId, REPLY, 'chat-1', 'answer-2');
  assert.equal(plan.steps.length, 3);
  const commands = checkedTaskCommands(state, plan);
  assert.deepEqual(commands.map(c => c.type), ['task.create', 'task.create', 'task.create']);
  assert.equal(commands[0].input.projectId, state.activeProjectId);
  assert.match(commands[0].input.description, /Jeeves chat source: chat-1\/answer-2\/1/);
  assert.equal(commands[0].input.status, 'inbox');
  assert.equal(commands[0].input.estimateMinutes, 0);
});

test('commit is one durable atomic workbench batch with source receipts and undo', async () => {
  const { store, disk } = await open();
  store.dispatch({ type: 'project.create', input: { title: 'Arcade prototype' } });
  await store.settled();
  const state = store.getSnapshot().state;
  const plan = prepareChatTasks(state, state.activeProjectId, REPLY, 'chat-1', 'assistant-1');
  const commit = await commitChatTasks(store, plan);
  assert.equal(commit.status, 'saved');
  assert.equal(store.getSnapshot().state.tasks.length, 3);
  assert.equal(store.getSnapshot().state.tasks[0].status, 'inbox');
  assert.equal(store.getSnapshot().state.events.filter(event => event.entityKind === 'task').length, 3);
  const saved = JSON.parse(disk.data.get(WORKBENCH_KEY));
  assertValid(saved);
  assert.equal(saved.tasks.length, 3);
  assert.match(saved.tasks[2].description, /chat-1\/assistant-1\/3/);
  const duplicate = await commitChatTasks(store, plan);
  assert.equal(duplicate.status, 'refused');
  assert.equal(store.getSnapshot().state.tasks.length, 3);
  assert.equal(await undoChatTasks(store, commit.revision), true);
  assert.equal(store.getSnapshot().state.tasks.length, 0);
  assert.equal(JSON.parse(disk.data.get(WORKBENCH_KEY)).tasks.length, 0);
});

test('stale preview and changed or archived project are rejected before edits', async () => {
  const { store } = await open();
  store.dispatch({ type: 'project.create', input: { title: 'Game 1' } });
  let state = store.getSnapshot().state;
  const original = prepareChatTasks(state, state.activeProjectId, REPLY, 'chat-1', 'response-1');
  store.dispatch({ type: 'task.create', input: { projectId: state.activeProjectId, title: 'Unrelated task' } });
  assert.equal((await commitChatTasks(store, original)).status, 'refused');
  state = store.getSnapshot().state;
  const next = prepareChatTasks(state, state.activeProjectId, REPLY, 'chat-1', 'response-1');
  const p = state.projects[0];
  store.dispatch({ type: 'project.update', id: p.id, revision: p.revision, patch: { status: 'archived' } });
  assert.equal((await commitChatTasks(store, next)).status, 'refused');
  assert.equal(store.getSnapshot().state.tasks.length, 1);
});

test('plan tampering cannot produce an unauthorized command type or duplicate provenance', async () => {
  const { store } = await open();
  store.dispatch({ type: 'project.create', input: { title: 'Game' } });
  const state = store.getSnapshot().state;
  const plan = prepareChatTasks(state, state.activeProjectId, REPLY, 'chat-1', 'answer-1');
  assert.throws(() => checkedTaskCommands(state, {
    ...plan, steps: [{ ...plan.steps[0], title: '\nRun something dangerous' }],
  }), /invalid/);
  assert.throws(() => checkedTaskCommands(state, {
    ...plan, steps: [plan.steps[0], { ...plan.steps[0], ordinal: 2 }],
  }), /duplicate/);
  assert.throws(() => prepareChatTasks(state, 'different-project', REPLY, 'chat-1', 'answer-1'), /Choose/);
  assert.throws(() => prepareChatTasks(state, state.activeProjectId, REPLY, 'chat/evil', 'answer-1'), /identity/);
});

test('cross-project re-use remains explicit while same-project repeated imports are refused', async () => {
  const { store } = await open();
  store.dispatch({ type: 'project.create', input: { title: 'Game 1' } });
  const first = store.getSnapshot().state.activeProjectId;
  store.dispatch({ type: 'project.create', input: { title: 'Game 2' } });
  const second = store.getSnapshot().state.activeProjectId;
  const p1 = prepareChatTasks(store.getSnapshot().state, first, REPLY, 'chat-1', 'answer-1');
  assert.equal((await commitChatTasks(store, p1)).status, 'saved');
  assert.throws(() => prepareChatTasks(store.getSnapshot().state, first, REPLY, 'chat-1', 'answer-1'), /already exist/);
  const p2 = prepareChatTasks(store.getSnapshot().state, second, REPLY, 'chat-1', 'answer-1');
  assert.equal((await commitChatTasks(store, p2)).status, 'saved');
  assert.equal(store.getSnapshot().state.tasks.filter(x => x.projectId === first).length, 3);
  assert.equal(store.getSnapshot().state.tasks.filter(x => x.projectId === second).length, 3);
});

test('a failed durable write is not claimed as saved and reapplication is blocked', async () => {
  const { store, disk } = await open();
  store.dispatch({ type: 'project.create', input: { title: 'Game' } });
  await store.settled();
  const p = prepareChatTasks(store.getSnapshot().state, store.getSnapshot().state.activeProjectId, REPLY, 'chat-1', 'answer-1');
  const original = disk.setItem.bind(disk);
  disk.setItem = async (key, value) => {
    if (key === WORKBENCH_KEY) throw new Error('disk quota');
    return original(key, value);
  };
  const result = await commitChatTasks(store, p);
  assert.equal(result.status, 'unsaved');
  assert.equal(store.getSnapshot().state.tasks.length, 3);
  assert.equal(store.getSnapshot().saveStatus, 'failed');
  assert.equal((await commitChatTasks(store, p)).status, 'refused');
  assert.equal(await undoChatTasks(store, result.revision), false);
});

test('undo never reverts an unrelated newer workbench change', async () => {
  const { store } = await open();
  store.dispatch({ type: 'project.create', input: { title: 'Game' } });
  const plan = prepareChatTasks(store.getSnapshot().state, store.getSnapshot().state.activeProjectId, REPLY, 'chat-1', 'answer-1');
  const result = await commitChatTasks(store, plan);
  assert.equal(result.status, 'saved');
  store.dispatch({ type: 'project.create', input: { title: 'Another game' } });
  await store.settled();
  assert.equal(await undoChatTasks(store, result.revision), false);
  assert.equal(store.getSnapshot().state.projects.length, 2);
  assert.equal(store.getSnapshot().state.tasks.length, 3);
});
