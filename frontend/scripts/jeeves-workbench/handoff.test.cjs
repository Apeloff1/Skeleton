const { test } = require('node:test');
const { assert, load, linkedFixture, memoryStorage, deferred, tick } = require('./helpers.cjs');
const { consumeHandoff } = load('handoff');
const { makeHandoff, defaultContextSelection } = load('context');
const { HANDOFF_KEY } = load('types');
const { WorkspaceController } = require('../../features/Jeeves/WorkspaceController.ts');
const W = require('../../features/Jeeves/workspace.ts');

function pendingDraft() {
  const { h, project } = linkedFixture();
  return { h, value: makeHandoff(h.state, defaultContextSelection(h.state, project), 'Help me build movement.', h.context()) };
}

async function chat(storage = memoryStorage()) {
  let requests = 0;
  const controller = new WorkspaceController(storage, async () => {
    requests++;
    return { reply: 'An answer' };
  });
  await controller.initialize();
  await controller.whenSaved();
  return { controller, storage, requests: () => requests };
}

test('handoff opens a new chat without overwriting an existing unsent draft', async () => {
  const { h, value } = pendingDraft();
  const { controller, storage, requests } = await chat();
  controller.edit({ draft: 'Keep this unfinished question.', context: 'Existing context' });
  const previousId = controller.active.id;
  await controller.whenSaved();
  await storage.setItem(HANDOFF_KEY, JSON.stringify(value));
  assert.equal(await consumeHandoff(storage, controller, h.now), 'opened');
  assert.notEqual(controller.active.id, previousId);
  assert.equal(controller.active.draft, value.draft);
  assert.equal(controller.active.context, value.context);
  const previous = controller.getSnapshot().workspace.conversations.find(item => item.id === previousId);
  assert.equal(previous.draft, 'Keep this unfinished question.');
  assert.equal(previous.context, 'Existing context');
  assert.equal(storage.data.has(HANDOFF_KEY), false);
  assert.equal(requests(), 0, 'handoff must not send an AI request');
});

test('handoff acknowledgement waits until the new conversation is saved', async () => {
  const { h, value } = pendingDraft();
  const { controller, storage } = await chat();
  await storage.setItem(HANDOFF_KEY, JSON.stringify(value));
  const gate = deferred();
  const set = storage.setItem;
  storage.setItem = async (key, raw) => {
    if (key === W.WORKSPACE_KEY) await gate.promise;
    await set(key, raw);
  };
  const pending = consumeHandoff(storage, controller, h.now);
  await tick();
  assert.equal(storage.data.has(HANDOFF_KEY), true);
  assert.equal(controller.getSnapshot().saveState, 'saving');
  gate.resolve();
  assert.equal(await pending, 'opened');
  assert.equal(storage.data.has(HANDOFF_KEY), false);
});

test('failed saves preserve the pending draft and retries do not create duplicates', async () => {
  const { h, value } = pendingDraft();
  const { controller, storage } = await chat();
  await storage.setItem(HANDOFF_KEY, JSON.stringify(value));
  const set = storage.setItem;
  storage.setItem = async (key, raw) => {
    if (key === W.WORKSPACE_KEY) throw new Error('quota');
    await set(key, raw);
  };
  assert.equal(await consumeHandoff(storage, controller, h.now), 'failed');
  const count = controller.getSnapshot().workspace.conversations.length;
  assert.equal(storage.data.has(HANDOFF_KEY), true);
  storage.setItem = set;
  assert.equal(await consumeHandoff(storage, controller, h.now), 'opened');
  assert.equal(controller.getSnapshot().workspace.conversations.length, count);
  assert.equal(storage.data.has(HANDOFF_KEY), false);
});

test('persisted handoff receipts prevent duplication after a restart', async () => {
  const { h, value } = pendingDraft();
  const { controller, storage } = await chat();
  await storage.setItem(HANDOFF_KEY, JSON.stringify(value));
  const remove = storage.removeItem;
  storage.removeItem = async () => { throw new Error('temporary remove failure'); };
  assert.equal(await consumeHandoff(storage, controller, h.now), 'failed');
  const count = controller.getSnapshot().workspace.conversations.length;
  storage.removeItem = remove;
  const restarted = await chat(storage);
  assert.equal(await consumeHandoff(storage, restarted.controller, h.now), 'opened');
  assert.equal(restarted.controller.getSnapshot().workspace.conversations.length, count);
  assert.equal(restarted.controller.active.handoffId, value.id);
});

test('a newer queued handoff is not removed when an older one finishes saving', async () => {
  const { h, value } = pendingDraft();
  const { controller, storage } = await chat();
  const firstRaw = JSON.stringify(value);
  const second = { ...value, id: 'newer-draft', draft: 'Another question' };
  const secondRaw = JSON.stringify(second);
  await storage.setItem(HANDOFF_KEY, firstRaw);
  const gate = deferred();
  const set = storage.setItem;
  storage.setItem = async (key, raw) => {
    if (key === W.WORKSPACE_KEY) await gate.promise;
    await set(key, raw);
  };
  const pending = consumeHandoff(storage, controller, h.now);
  await tick();
  storage.data.set(HANDOFF_KEY, secondRaw);
  gate.resolve();
  assert.equal(await pending, 'opened');
  assert.equal(storage.data.get(HANDOFF_KEY), secondRaw);
});

test('conversation capacity preserves the queued handoff until room is available', async () => {
  const { h, value } = pendingDraft();
  const { controller, storage } = await chat();
  for (let index = 1; index < W.MAX_CONVERSATIONS; index++) controller.create();
  await controller.whenSaved();
  await storage.setItem(HANDOFF_KEY, JSON.stringify(value));
  assert.equal(await consumeHandoff(storage, controller, h.now), 'waiting');
  assert.equal(controller.getSnapshot().workspace.conversations.length, W.MAX_CONVERSATIONS);
  assert.equal(storage.data.has(HANDOFF_KEY), true);
  controller.remove(controller.active.id);
  assert.equal(await consumeHandoff(storage, controller, h.now), 'opened');
  assert.equal(controller.active.handoffId, value.id);
});

test('expired handoffs do not replace active chats or trigger a network request', async () => {
  const { h, value } = pendingDraft();
  const { controller, storage, requests } = await chat();
  const id = controller.active.id;
  await storage.setItem(HANDOFF_KEY, JSON.stringify(value));
  assert.equal(await consumeHandoff(storage, controller, h.now + 31 * 60000), 'invalid');
  assert.equal(controller.active.id, id);
  assert.equal(requests(), 0);
  assert.match(controller.getSnapshot().notice, /expired/);
});

test('an unopened controller defers handoff consumption without reading storage', async () => {
  const storage = memoryStorage();
  let reads = 0;
  storage.getItem = async () => { reads++; return null; };
  const controller = new WorkspaceController(storage, async () => ({ reply: 'unused' }));
  assert.equal(await consumeHandoff(storage, controller), 'waiting');
  assert.equal(reads, 0);
});

test('missing handoffs leave the current conversation unchanged', async () => {
  const { controller, storage } = await chat();
  const id = controller.active.id;
  assert.equal(await consumeHandoff(storage, controller), 'none');
  assert.equal(controller.active.id, id);
});
