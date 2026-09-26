/* Hermetic controller/storage tests; no Expo runtime, network or device required. */
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const ts = require('typescript');
require.extensions['.ts'] = (module, filename) => {
  const source = fs.readFileSync(filename, 'utf8');
  const result = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } });
  module._compile(result.outputText, filename);
};
const W = require('../features/Jeeves/workspace.ts');
const { WorkspaceController } = require('../features/Jeeves/WorkspaceController.ts');

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const tick = () => new Promise(resolve => setImmediate(resolve));
function storage(initial = {}) {
  const data = new Map(Object.entries(initial));
  return { data, getItem: async key => data.get(key) ?? null, setItem: async (key, value) => { data.set(key, value); } };
}
async function controller(
  transport = async () => ({ reply: 'Answer', session_id: 'server-1' }),
  disk = storage(),
  historyTransport = undefined,
) {
  const store = new WorkspaceController(disk, transport, historyTransport);
  await store.initialize();
  await tick();
  return store;
}
function message(patch = {}) {
  return { id: W.newId(), role: 'user', text: 'question', createdAt: Date.now(), status: 'complete', ...patch };
}

test('old single transcript migrates without deleting the recovery copy', async () => {
  const legacy = JSON.stringify({ version: 2, messages: [{ role: 'user', text: 'old question' }], draft: 'unfinished', allForms: true });
  const disk = storage({ [W.LEGACY_KEY]: legacy });
  const store = await controller(undefined, disk);
  assert.equal(store.active.messages[0].text, 'old question');
  assert.equal(store.active.draft, 'unfinished');
  assert.equal(store.active.allForms, true);
  assert.equal(disk.data.get(W.LEGACY_KEY), legacy);
  assert.ok(disk.data.has(W.WORKSPACE_KEY));
});

test('corrupt or future workspace stays intact and blocks editing', async () => {
  for (const raw of ['{bad', '{"version":99,"conversations":[]}', '{"version":1,"conversations":[]}']) {
    const disk = storage({ [W.WORKSPACE_KEY]: raw });
    const store = await controller(undefined, disk);
    assert.equal(store.getSnapshot().ready, false);
    assert.ok(store.getSnapshot().loadError);
    store.edit({ draft: 'must not overwrite' });
    store.create();
    await store.send();
    await tick();
    assert.equal(disk.data.get(W.WORKSPACE_KEY), raw);
  }
});

test('pending work is restored as retryable and attachment bytes never persist', () => {
  const workspace = W.createWorkspace();
  workspace.conversations[0].messages = [message({ status: 'pending', attachmentName: 'a.pdf', artifacts: [{ base64: 'SECRET_BYTES', type: 'pdf', mime: 'application/pdf' }], unknown: 'SECRET_FIELD' })];
  const raw = W.encodeWorkspace(workspace);
  assert.ok(!raw.includes('SECRET'));
  const restored = W.decodeWorkspace(raw);
  assert.equal(restored.conversations[0].messages[0].status, 'failed');
  assert.equal(restored.conversations[0].messages[0].attachmentName, 'a.pdf');
  assert.equal(restored.conversations[0].messages[0].artifactCount, 1);
});


test('remount replaces stale device transcript with canonical server history', async () => {
  const workspace = W.createWorkspace();
  Object.assign(workspace.conversations[0], {
    sessionId: 'server-1',
    sessionUpdatedAt: 1,
    messages: [
      message({ id: 'local-user', text: 'stale local question' }),
      message({ id: 'local-ai', role: 'jeeves', text: 'stale local answer' }),
    ],
  });
  const disk = storage({ [W.WORKSPACE_KEY]: W.encodeWorkspace(workspace) });
  let requested = null;

  const store = await controller(
    undefined,
    disk,
    async sessionId => {
      requested = sessionId;
      return {
        ok: true,
        available: true,
        session_id: sessionId,
        history_source: 'canonical',
        turns: [{
          client_message_id: 'client-turn-1',
          role_user: 'canonical question',
          role_jeeves: 'canonical answer',
          user_ts: 100,
          assistant_ts: 101,
          model: 'skeleton-engine',
          tier: 'canonical',
          canonical_user_message_id: 'canonical-user-1',
          canonical_assistant_message_id: 'canonical-assistant-1',
        }],
      };
    },
  );

  assert.equal(requested, 'server-1');
  assert.deepEqual(
    store.active.messages.map(item => item.text),
    ['canonical question', 'canonical answer'],
  );
  assert.deepEqual(
    store.active.messages.map(item => item.id),
    ['client-turn-1', 'canonical-assistant-1'],
  );
  assert.deepEqual(
    store.active.messages.map(item => item.createdAt),
    [100000, 101000],
  );
  assert.equal(store.active.messages[1].model, 'skeleton-engine');
  assert.equal(store.getSnapshot().notice, null);
  const persisted = W.decodeWorkspace(disk.data.get(W.WORKSPACE_KEY));
  assert.deepEqual(
    persisted.conversations[0].messages.map(item => item.text),
    ['canonical question', 'canonical answer'],
  );
});

test('remount keeps device cache with notice when canonical history is unavailable', async () => {
  const workspace = W.createWorkspace();
  Object.assign(workspace.conversations[0], {
    sessionId: 'server-2',
    messages: [message({ text: 'cached question' })],
  });
  const disk = storage({ [W.WORKSPACE_KEY]: W.encodeWorkspace(workspace) });

  const store = await controller(
    undefined,
    disk,
    async () => {
      throw new Error('offline');
    },
  );

  assert.deepEqual(
    store.active.messages.map(item => item.text),
    ['cached question'],
  );
  assert.match(store.getSnapshot().notice, /could not be refreshed/i);
  assert.equal(store.getSnapshot().ready, true);
});

test('durable backend session identity survives timestamp age and skew', () => {
  const now = Date.now();
  for (const time of [now - W.SESSION_TTL - 1, now + 100000]) {
    const workspace = W.createWorkspace();
    Object.assign(workspace.conversations[0], {
      sessionId: 'stable-session',
      sessionUpdatedAt: time,
    });
    const restored = W.decodeWorkspace(W.encodeWorkspace(workspace), now);
    assert.equal(restored.conversations[0].sessionId, 'stable-session');
    assert.equal(
      W.buildChatBody(restored.conversations[0], 'hello', undefined, now).session_id,
      'stable-session',
    );
  }
});

test('restore repairs duplicate ids and rejects malformed message roles', () => {
  const workspace = W.createWorkspace();
  workspace.conversations[0].messages = [message({ id: 'same' }), message({ id: 'same' }), message({ role: 'system' })];
  workspace.conversations.push(workspace.conversations[0]);
  const restored = W.decodeWorkspace(JSON.stringify(workspace));
  assert.equal(restored.conversations.length, 1);
  const messages = restored.conversations[0].messages;
  assert.equal(messages.length, 2);
  assert.notEqual(messages[0].id, messages[1].id);
});

test('new chats retain independent drafts, project context, and form preferences', async () => {
  const store = await controller();
  const first = store.active.id;
  store.edit({ draft: 'first draft', context: 'Godot', allForms: true });
  store.create();
  assert.equal(store.active.draft, '');
  assert.equal(store.active.context, '');
  store.edit({ draft: 'second draft' });
  store.select(first);
  assert.equal(store.active.draft, 'first draft');
  assert.equal(store.active.context, 'Godot');
  assert.equal(store.active.allForms, true);
});

test('search includes transcript/context, pin sorting and archived filter', () => {
  let workspace = W.createWorkspace();
  workspace.conversations[0].messages = [message({ text: 'A dragon boss' })];
  workspace.conversations[0].pinned = true;
  const first = workspace.activeId;
  workspace = W.addConversation(workspace);
  workspace.conversations[0].context = 'Dragon game';
  assert.equal(W.searchConversations(workspace, 'DRAGON')[0].id, first);
  workspace.conversations[0].archived = true;
  assert.equal(W.searchConversations(workspace, 'dragon').length, 1);
  assert.equal(W.searchConversations(workspace, 'dragon', true).length, 1);
});

test('delete active conversation selects another and delete last creates an empty chat', async () => {
  const store = await controller();
  const first = store.active.id;
  store.create();
  store.remove(store.active.id);
  assert.equal(store.active.id, first);
  store.remove(first);
  assert.notEqual(store.active.id, first);
  assert.equal(store.getSnapshot().workspace.conversations.length, 1);
});

test('archive the last active chat creates an open replacement', async () => {
  const store = await controller();
  const original = store.active.id;
  store.archive(original, true);
  assert.notEqual(store.active.id, original);
  assert.equal(store.getSnapshot().workspace.conversations.find(c => c.id === original).archived, true);
});

test('conversation limit never silently evicts an existing transcript', async () => {
  const store = await controller();
  for (let i = 1; i < W.MAX_CONVERSATIONS; i++) store.create();
  const before = store.getSnapshot().workspace.conversations.map(c => c.id);
  store.create();
  assert.deepEqual(store.getSnapshot().workspace.conversations.map(c => c.id), before);
  assert.match(store.getSnapshot().notice, /30 conversations/);
});

test('same-tick double send makes one request and commits one exchange', async () => {
  const pending = deferred();
  let calls = 0;
  const store = await controller(() => { calls++; return pending.promise; });
  store.edit({ draft: 'Hello' });
  const first = store.send();
  await store.send();
  assert.equal(calls, 1);
  pending.resolve({ reply: 'Hi', session_id: 'session' });
  await first;
  assert.equal(store.active.messages.length, 2);
  assert.equal(store.active.messages[0].status, 'complete');
  assert.equal(store.active.sessionId, 'session');
});

test('retry does not duplicate the failed user turn', async () => {
  let calls = 0;
  const store = await controller(async () => { if (!calls++) throw new Error('offline'); return { reply: 'Recovered' }; });
  store.edit({ draft: 'Help' });
  await store.send();
  assert.equal(store.active.messages[0].status, 'failed');
  await store.retry(store.active.messages[0].id);
  assert.deepEqual(store.active.messages.map(m => m.role), ['user', 'jeeves']);
  assert.equal(store.active.messages[0].status, 'complete');
});

test('blank provider reply remains retryable, never invents a success message', async () => {
  const store = await controller(async () => ({ reply: '  ' }));
  store.edit({ draft: 'Hello' });
  await store.send();
  assert.equal(store.active.messages.length, 1);
  assert.equal(store.active.messages[0].status, 'failed');
});

test('switching chats aborts and ignores a late reply even if transport ignores abort', async () => {
  const pending = deferred();
  let signal;
  const store = await controller((_body, requestSignal) => { signal = requestSignal; return pending.promise; });
  const oldId = store.active.id;
  store.edit({ draft: 'Slow question' });
  const request = store.send();
  store.create();
  assert.equal(signal.aborted, true);
  pending.resolve({ reply: 'Too late', session_id: 'wrong-session' });
  await request;
  assert.equal(store.active.messages.length, 0);
  const old = store.getSnapshot().workspace.conversations.find(c => c.id === oldId);
  assert.equal(old.messages.length, 1);
  assert.equal(old.messages[0].status, 'cancelled');
});

test('an old request cannot clear the busy state belonging to its replacement', async () => {
  const old = deferred(), current = deferred();
  let calls = 0;
  const store = await controller(() => calls++ === 0 ? old.promise : current.promise);
  store.edit({ draft: 'one' });
  const first = store.send();
  store.cancel();
  const second = store.retry(store.active.messages[0].id);
  old.resolve({ reply: 'discard' });
  await first;
  assert.equal(store.getSnapshot().busyId, store.active.id);
  current.resolve({ reply: 'keep' });
  await second;
  assert.equal(store.active.messages.at(-1).text, 'keep');
  assert.equal(store.getSnapshot().busyId, null);
});

test('deleting a conversation in flight cannot resurrect it', async () => {
  const pending = deferred();
  const store = await controller(() => pending.promise);
  store.edit({ draft: 'question' });
  const original = store.active.id;
  const request = store.send();
  store.remove(original);
  pending.resolve({ reply: 'late' });
  await request;
  assert.ok(!store.getSnapshot().workspace.conversations.some(c => c.id === original));
});

test('serialized saves coalesce newer drafts while a storage write is pending', async () => {
  const disk = storage();
  const store = await controller(undefined, disk);
  const blocked = deferred();
  let calls = 0;
  let inflight = 0;
  disk.setItem = async (key, value) => {
    assert.equal(inflight++, 0, 'no concurrent storage writes');
    if (calls++ === 0) await blocked.promise;
    disk.data.set(key, value);
    inflight--;
  };
  store.edit({ draft: 'old' });
  store.edit({ draft: 'middle' });
  store.edit({ draft: 'newest' });
  blocked.resolve();
  await tick();
  assert.equal(W.decodeWorkspace(disk.data.get(W.WORKSPACE_KEY)).conversations[0].draft, 'newest');
  assert.equal(calls, 2);
  assert.equal(store.getSnapshot().saveState, 'saved');
});

test('storage quota failure preserves in-memory work and retry saves latest state', async () => {
  const disk = storage();
  const store = await controller(undefined, disk);
  const original = disk.setItem;
  disk.setItem = async () => { throw new Error('quota'); };
  store.edit({ draft: 'precious draft' });
  await tick();
  assert.equal(store.getSnapshot().saveState, 'error');
  assert.equal(store.active.draft, 'precious draft');
  disk.setItem = original;
  store.retrySave();
  await tick();
  assert.equal(store.getSnapshot().saveState, 'saved');
  assert.equal(W.decodeWorkspace(disk.data.get(W.WORKSPACE_KEY)).conversations[0].draft, 'precious draft');
});

test('history excludes failed turns and is bounded by count and characters', () => {
  const conversation = W.createConversation();
  conversation.messages = Array.from({ length: 100 }, (_, i) => message({ text: String(i).padEnd(4000, 'x'), status: i === 99 ? 'failed' : 'complete' }));
  const body = W.buildChatBody(conversation, 'next');
  assert.ok(body.history.length <= 20);
  assert.ok(body.history.reduce((n, m) => n + m.content.length, 0) <= 24000);
  assert.ok(!body.history.some(m => m.content.startsWith('99')));
  assert.ok(body.history.at(-1).content.startsWith('98'));
});

test('retry after remount requires reattaching an unsaved file', async () => {
  const workspace = W.createWorkspace();
  workspace.conversations[0].messages = [message({ status: 'failed', attachmentName: 'report.pdf' })];
  let calls = 0;
  const store = await controller(async () => { calls++; return { reply: 'wrong' }; }, storage({ [W.WORKSPACE_KEY]: W.encodeWorkspace(workspace) }));
  await store.retry(store.active.messages[0].id);
  assert.equal(calls, 0);
  assert.equal(store.active.draft, 'question');
  assert.match(store.getSnapshot().notice, /Reattach/);
});

test('older failed message restores draft instead of inserting a reply out of order', async () => {
  const workspace = W.createWorkspace();
  workspace.conversations[0].messages = [message({ status: 'failed', text: 'older' }), message({ text: 'newer' })];
  const store = await controller(undefined, storage({ [W.WORKSPACE_KEY]: W.encodeWorkspace(workspace) }));
  await store.retry(store.active.messages[0].id);
  assert.equal(store.active.draft, 'older');
  assert.equal(store.active.messages.length, 2);
});

test('message limit preserves the pending draft rather than truncating transcript', async () => {
  const workspace = W.createWorkspace();
  workspace.conversations[0].messages = Array.from({ length: 100 }, () => message());
  const store = await controller(undefined, storage({ [W.WORKSPACE_KEY]: W.encodeWorkspace(workspace) }));
  store.edit({ draft: 'keep this draft' });
  await store.send();
  assert.equal(store.active.messages.length, 100);
  assert.equal(store.active.draft, 'keep this draft');
});

test('transcript export includes context, failure status and honest file omissions', () => {
  const conversation = W.createConversation();
  conversation.context = 'A puzzle game';
  conversation.messages = [message({ status: 'failed', attachmentName: 'scene.png' }), message({ role: 'jeeves', artifactCount: 2 })];
  const output = W.transcript(conversation);
  assert.match(output, /A puzzle game/);
  assert.match(output, /Status: failed/);
  assert.match(output, /file not included/);
  assert.match(output, /Artifacts are not included/);
});
