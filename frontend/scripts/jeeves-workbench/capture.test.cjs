const { test } = require('node:test');
const { assert, load, harness, memoryStorage, assertValid } = require('./helpers.cjs');
const { captureMessage, captureInput } = load('capture');
const { WorkbenchStore } = load('WorkbenchStore');
const { WORKBENCH_KEY } = load('types');
const W = require('../../features/Jeeves/workspace.ts');

function input(projectId, patch = {}) {
  return {
    projectId,
    title: 'Understanding velocity',
    text: 'Velocity describes the rate and direction of position change.',
    kind: 'note',
    conversationId: 'chat-one',
    conversationTitle: 'Physics discussion',
    messageId: 'message-one',
    role: 'assistant',
    model: 'example-model',
    ...patch,
  };
}

test('chat capture creates a linked unverified note and preserves attribution', () => {
  const h = harness();
  const projectId = h.project();
  const result = captureMessage(h.state, input(projectId), h.context());
  assertValid(result.state);
  const note = result.state.notes[0];
  const source = result.state.sources[0];
  assert.equal(note.confidence, 'unverified');
  assert.deepEqual(note.sourceIds, [source.id]);
  assert.equal(source.kind, 'conversation');
  assert.equal(source.author, 'Jeeves (example-model)');
  assert.equal(source.locator, 'jeeves-conversation:chat-one#message-one');
  assert.equal(result.duplicate, false);
  assert.equal(h.state.notes.length, 0);
});

test('capturing the same unchanged message twice is idempotent', () => {
  const h = harness();
  const projectId = h.project();
  const first = captureMessage(h.state, input(projectId), h.context());
  const second = captureMessage(first.state, input(projectId), h.context());
  assert.equal(second.duplicate, true);
  assert.equal(second.state, first.state);
  assert.equal(second.noteId, first.noteId);
  assert.equal(second.sourceId, first.sourceId);
});

test('edited capture text reuses the source and creates a distinct note', () => {
  const h = harness();
  const projectId = h.project();
  const first = captureMessage(h.state, input(projectId), h.context());
  const second = captureMessage(first.state, input(projectId, { text: 'My corrected explanation.' }), h.context());
  assert.equal(second.duplicate, false);
  assert.equal(second.state.notes.length, 2);
  assert.equal(second.state.sources.length, 1);
  assert.equal(second.sourceId, first.sourceId);
  assert.notEqual(second.noteId, first.noteId);
});

test('the same message can be captured independently in different projects', () => {
  const h = harness();
  const firstProject = h.project();
  const secondProject = h.project({ title: 'Second' });
  const first = captureMessage(h.state, input(firstProject), h.context());
  const second = captureMessage(first.state, input(secondProject), h.context());
  assert.equal(second.state.sources.length, 2);
  assert.equal(second.state.notes.length, 2);
  assert.notEqual(second.sourceId, first.sourceId);
  assertValid(second.state);
});

test('user-authored captures identify the user as source author', () => {
  const h = harness();
  const projectId = h.project();
  const result = captureMessage(h.state, input(projectId, { role: 'user', model: null }), h.context());
  assert.equal(result.state.sources[0].author, 'You');
  assert.equal(result.state.notes[0].confidence, 'unverified');
});

test('capture rejects archived projects, missing projects and empty text', () => {
  const h = harness();
  const projectId = h.project();
  assert.throws(() => captureMessage(h.state, input('missing'), h.context()), /existing project/);
  assert.throws(() => captureMessage(h.state, input(projectId, { text: ' ' }), h.context()));
  h.update('project', projectId, { status: 'archived' });
  assert.throws(() => captureMessage(h.state, input(projectId), h.context()), /Restore/);
});

test('source creation is not committed if note validation fails', () => {
  const h = harness();
  const projectId = h.project();
  const before = JSON.stringify(h.state);
  assert.throws(() => captureMessage(h.state, input(projectId, { kind: 'unsupported-kind' }), h.context()));
  assert.equal(JSON.stringify(h.state), before);
  assert.equal(h.state.sources.length, 0);
});

test('capture input maps Jeeves roles and refuses unfinished messages', () => {
  const conversation = W.createConversation();
  const message = { id: 'm', role: 'jeeves', text: '# A heading\nSome explanation', createdAt: Date.now(), status: 'complete' };
  const result = captureInput(conversation, message, 'project');
  assert.equal(result.role, 'assistant');
  assert.equal(result.title, 'A heading');
  assert.equal(result.conversationId, conversation.id);
  assert.throws(() => captureInput(conversation, { ...message, status: 'pending' }, 'project'), /complete message/);
  assert.throws(() => captureInput(conversation, { ...message, text: '' }, 'project'), /no text/);
});

test('captured conversation identifiers are escaped in the stored locator', () => {
  const h = harness();
  const projectId = h.project();
  const result = captureMessage(h.state, input(projectId, { conversationId: 'chat#two', messageId: 'message/three' }), h.context());
  assert.equal(result.state.sources[0].locator, 'jeeves-conversation:chat%23two#message%2Fthree');
});

test('store capture is persisted and undo removes both the note and source together', async () => {
  const h = harness();
  const projectId = h.project();
  const storage = memoryStorage({ [WORKBENCH_KEY]: JSON.stringify(h.state) });
  const store = new WorkbenchStore(storage, h.clock);
  await store.initialize();
  assert.equal(store.capture(input(projectId)), true);
  await store.settled();
  assert.equal(JSON.parse(storage.data.get(WORKBENCH_KEY)).notes.length, 1);
  store.undo();
  assert.equal(store.getSnapshot().state.notes.length, 0);
  assert.equal(store.getSnapshot().state.sources.length, 0);
  store.redo();
  assert.equal(store.getSnapshot().state.notes.length, 1);
  assert.equal(store.getSnapshot().state.sources.length, 1);
  await store.settled();
});
