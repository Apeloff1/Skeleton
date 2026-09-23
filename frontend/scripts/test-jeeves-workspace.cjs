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
async function controller(transport = async () => ({ reply: 'Answer', session_id: 'server-1' }), disk = storage()) {
  const store = new WorkspaceController(disk, transport);
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

test('expired and future session timestamps cannot resume a backend session', () => {
  const now = Date.now();
  for (const time of [now - W.SESSION_TTL - 1, now + 100000]) {
    const workspace = W.createWorkspace();
    Object.assign(workspace.conversations[0], { sessionId: 'stale', sessionUpdatedAt: time });
    assert.equal(W.decodeWorkspace(W.encodeWorkspace(workspace), now).conversations[0].sessionId, null);
    assert.equal(W.buildChatBody(workspace.conversations[0], 'hello', undefined, now).session_id, undefined);
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


function serverThread(patch = {}) {
  return {
    thread_id: 'thread-1',
    title: 'Server conversation',
    created_at: '2026-09-24T00:00:00+00:00',
    updated_at: '2026-09-24T00:01:00+00:00',
    version: 1,
    state: 'active',
    data_class: 'confidential',
    ...patch,
  };
}

function serverMessage(patch = {}) {
  return {
    message_id: 'message-1',
    sequence: 1,
    author_type: 'user',
    created_at: '2026-09-24T00:00:30+00:00',
    idempotency_key: 'client-turn-1',
    content: 'SERVER AUTHORITATIVE MESSAGE',
    artifact_refs: [],
    ...patch,
  };
}

function authorityFixture(input = {}) {
  let threads = input.threads || [serverThread()];
  const messages = new Map(
    input.messages || [['thread-1', [serverMessage()]]],
  );
  const calls = {
    chat: [],
    state: [],
    deletion: [],
    create: [],
    snapshot: [],
  };
  return {
    calls,
    setThreads(next) { threads = next; },
    setMessages(threadId, next) { messages.set(threadId, next); },
    authority: {
      async listThreads() {
        return threads.map(item => ({ ...item }));
      },
      async createThread(title) {
        calls.create.push(title);
        const thread = serverThread({
          thread_id: 'thread-created-' + calls.create.length,
          title,
          version: 1,
        });
        threads = [thread, ...threads];
        messages.set(thread.thread_id, []);
        return { ...thread };
      },
      async listMessages(threadId) {
        return (messages.get(threadId) || []).map(item => ({ ...item }));
      },
      async snapshot(threadId, activeOnly) {
        calls.snapshot.push({ threadId, activeOnly });
        const thread = threads.find(
          item => item.thread_id === threadId,
        );
        if (!thread) throw new Error('conversation not found');
        return {
          thread: { ...thread },
          messages: (messages.get(threadId) || []).map(
            item => ({ ...item }),
          ),
        };
      },
      async chat(request) {
        calls.chat.push({ ...request, signal: undefined });
        if (input.chat) {
          const state = { threads, messages, calls };
          const response = await input.chat(request, state);
          if (state.threads !== threads) threads = state.threads;
          return response;
        }
        throw new Error('chat fixture not configured');
      },
      async setState(request) {
        calls.state.push({ ...request });
        const index = threads.findIndex(item => item.thread_id === request.threadId);
        const current = threads[index];
        const next = {
          ...current,
          state: request.state,
          version: current.version + 1,
          updated_at: '2026-09-24T00:02:00+00:00',
        };
        threads = threads.map((item, i) => i === index ? next : item);
        return { ...next };
      },
      async requestDeletion(request) {
        calls.deletion.push({ ...request });
        const index = threads.findIndex(item => item.thread_id === request.threadId);
        const current = threads[index];
        const next = {
          ...current,
          state: 'deleted',
          version: current.version + 1,
          updated_at: '2026-09-24T00:03:00+00:00',
        };
        threads = threads.map((item, i) => i === index ? next : item);
        return { ...next };
      },
    },
  };
}

async function authorityController(fixture, disk = storage()) {
  let legacyCalls = 0;
  const store = new WorkspaceController(
    disk,
    async () => {
      legacyCalls++;
      throw new Error('legacy transport must not run');
    },
    fixture.authority,
  );
  await store.initialize();
  await tick();
  return { store, disk, legacyCalls: () => legacyCalls };
}

test('server authority overwrites cached transcript while preserving local preferences', async () => {
  const cached = W.createWorkspace();
  cached.conversations[0] = {
    ...cached.conversations[0],
    id: 'thread-1',
    title: 'LOCAL FORGED TITLE',
    draft: 'keep draft',
    context: 'keep context',
    pinned: true,
    messages: [message({ text: 'LOCAL FORGED MESSAGE' })],
  };
  cached.activeId = 'thread-1';
  const disk = storage({ [W.WORKSPACE_KEY]: W.encodeWorkspace(cached) });
  const fixture = authorityFixture();

  const { store, legacyCalls } = await authorityController(fixture, disk);

  assert.equal(store.getSnapshot().serverSynced, true);
  assert.equal(store.active.id, 'thread-1');
  assert.equal(store.active.title, 'Server conversation');
  assert.equal(store.active.draft, 'keep draft');
  assert.equal(store.active.context, 'keep context');
  assert.equal(store.active.pinned, true);
  assert.deepEqual(store.active.messages.map(item => item.text), [
    'SERVER AUTHORITATIVE MESSAGE',
  ]);
  assert.equal(store.active.messages[0].id, 'message-1');
  assert.equal(store.active.messages[0].idempotencyKey, 'client-turn-1');
  assert.equal(store.active.serverVersion, 1);
  assert.equal(legacyCalls(), 0);
});

test('corrupt device transcript cache rebuilds from server authority', async () => {
  const disk = storage({ [W.WORKSPACE_KEY]: '{corrupt' });
  const fixture = authorityFixture();

  const { store } = await authorityController(fixture, disk);

  assert.equal(store.getSnapshot().ready, true);
  assert.equal(store.getSnapshot().serverSynced, true);
  assert.equal(store.active.id, 'thread-1');
  assert.equal(store.active.messages[0].text, 'SERVER AUTHORITATIVE MESSAGE');
});

test('canonical send never sends client transcript and rebuilds from server result', async () => {
  const fixture = authorityFixture({
    chat: async (request, state) => {
      assert.equal(request.threadId, 'thread-1');
      assert.equal(request.expectedThreadVersion, 1);
      assert.equal(request.message, 'new question');
      assert.equal(typeof request.idempotencyKey, 'string');
      assert.ok(!Object.prototype.hasOwnProperty.call(request, 'history'));
      const user = serverMessage({
        message_id: 'server-user-2',
        sequence: 2,
        idempotency_key: request.idempotencyKey,
        content: request.message,
      });
      const assistant = serverMessage({
        message_id: 'server-assistant-3',
        sequence: 3,
        author_type: 'assistant',
        idempotency_key: request.idempotencyKey + ':assistant',
        content: 'server answer',
      });
      state.messages.set('thread-1', [
        serverMessage(),
        user,
        assistant,
      ]);
      const thread = serverThread({ version: 3 });
      state.threads = [thread];
      return {
        success: true,
        response: 'server answer',
        thread,
        user_message: user,
        assistant_message: assistant,
      };
    },
  });
  const { store, legacyCalls } = await authorityController(fixture);
  store.edit({ draft: 'new question', context: 'project context' });

  await store.send();

  assert.equal(fixture.calls.chat.length, 1);
  assert.equal(fixture.calls.chat[0].context, 'project context');
  assert.deepEqual(store.active.messages.map(item => item.text), [
    'SERVER AUTHORITATIVE MESSAGE',
    'new question',
    'server answer',
  ]);
  assert.equal(store.active.serverVersion, 3);
  assert.equal(store.getSnapshot().serverSynced, true);
  assert.equal(legacyCalls(), 0);
});

test('canonical failed turn retries with identical append idempotency and precondition', async () => {
  let attempt = 0;
  const fixture = authorityFixture({
    chat: async (request, state) => {
      attempt++;
      if (attempt === 1) throw new Error('temporary engine outage');
      const user = serverMessage({
        message_id: 'server-retry-user',
        sequence: 2,
        idempotency_key: request.idempotencyKey,
        content: request.message,
      });
      const assistant = serverMessage({
        message_id: 'server-retry-assistant',
        sequence: 3,
        author_type: 'assistant',
        idempotency_key: request.idempotencyKey + ':assistant',
        content: 'recovered',
      });
      state.messages.set('thread-1', [serverMessage(), user, assistant]);
      const thread = serverThread({ version: 3 });
      return {
        success: true,
        response: 'recovered',
        thread,
        user_message: user,
        assistant_message: assistant,
      };
    },
  });
  const { store } = await authorityController(fixture);
  store.edit({ draft: 'retry me' });

  await store.send();
  const failed = store.active.messages.at(-1);
  assert.equal(failed.status, 'failed');
  assert.equal(failed.expectedThreadVersion, 1);
  assert.ok(failed.idempotencyKey);

  await store.retry(failed.id);

  assert.equal(fixture.calls.chat.length, 2);
  assert.equal(
    fixture.calls.chat[0].idempotencyKey,
    fixture.calls.chat[1].idempotencyKey,
  );
  assert.equal(
    fixture.calls.chat[0].expectedThreadVersion,
    fixture.calls.chat[1].expectedThreadVersion,
  );
  assert.deepEqual(store.active.messages.map(item => item.text), [
    'SERVER AUTHORITATIVE MESSAGE',
    'retry me',
    'recovered',
  ]);
});

test('archive and delete mutate server authority before local projection', async () => {
  const fixture = authorityFixture();
  const { store } = await authorityController(fixture);

  store.archive('thread-1', true);
  await tick();
  await tick();

  assert.equal(fixture.calls.state.length, 1);
  assert.equal(fixture.calls.state[0].state, 'archived');
  assert.ok(fixture.calls.create.length >= 1, 'an active replacement is created server-side');

  const created = store.active.id;
  store.remove(created);
  await tick();
  await tick();

  assert.equal(fixture.calls.deletion.length, 1);
  assert.equal(fixture.calls.deletion[0].threadId, created);
});

test('server-authority mode keeps draft when server is unavailable', async () => {
  const fixture = authorityFixture();
  fixture.authority.listThreads = async () => {
    throw new Error('offline');
  };
  const cached = W.createWorkspace();
  cached.conversations[0].draft = 'offline draft';
  const disk = storage({ [W.WORKSPACE_KEY]: W.encodeWorkspace(cached) });

  const { store } = await authorityController(fixture, disk);

  assert.equal(store.getSnapshot().ready, true);
  assert.equal(store.getSnapshot().serverSynced, false);
  assert.equal(store.active.draft, 'offline draft');
  await store.send();
  assert.equal(store.active.draft, 'offline draft');
  assert.match(store.getSnapshot().notice, /Server conversation state is unavailable/);
});


test('product Jeeves screen has no legacy chat endpoint and exports stable server snapshots', () => {
  const source = fs.readFileSync(
    require('node:path').join(
      __dirname,
      '../features/Jeeves/ChatWorkspace.tsx',
    ),
    'utf8',
  );
  assert.ok(!source.includes("'/api/jeeves/chat'"));
  assert.ok(source.includes('sendCanonicalConversationTurn'));
  assert.ok(source.includes('listAllConversationMessages'));
  assert.ok(source.includes('getConversationSnapshot'));
  assert.ok(source.includes('controller.exportAuthoritativeConversation()'));
  assert.ok(!source.includes('.then(() => exportTranscript(controller.active))'));
  assert.ok(source.includes('requestConversationDeletionById'));
});

test('server-authority cache metadata survives local persistence without changing authority', async () => {
  const fixture = authorityFixture();
  const { store, disk } = await authorityController(fixture);
  store.edit({ draft: 'cached draft', context: 'cached context', pinned: true });
  await store.whenSaved();

  const restoredCache = W.decodeWorkspace(disk.data.get(W.WORKSPACE_KEY));
  assert.equal(restoredCache.conversations[0].serverVersion, 1);
  assert.equal(restoredCache.conversations[0].serverState, 'active');
  assert.equal(restoredCache.conversations[0].draft, 'cached draft');

  fixture.setMessages('thread-1', [
    serverMessage({ content: 'NEW SERVER MESSAGE' }),
  ]);
  const rebuilt = new WorkspaceController(
    disk,
    async () => { throw new Error('legacy transport must not run'); },
    fixture.authority,
  );
  await rebuilt.initialize();

  assert.equal(rebuilt.active.draft, 'cached draft');
  assert.equal(rebuilt.active.context, 'cached context');
  assert.equal(rebuilt.active.pinned, true);
  assert.deepEqual(rebuilt.active.messages.map(item => item.text), [
    'NEW SERVER MESSAGE',
  ]);
});



test('authoritative export ignores stale local projection and requests full snapshot', async () => {
  const fixture = authorityFixture();
  const { store } = await authorityController(fixture);

  assert.deepEqual(store.active.messages.map(item => item.text), [
    'SERVER AUTHORITATIVE MESSAGE',
  ]);

  fixture.setMessages('thread-1', [
    serverMessage({ content: 'FRESH EXPORT MESSAGE' }),
    serverMessage({
      message_id: 'assistant-export',
      sequence: 2,
      author_type: 'assistant',
      idempotency_key: 'assistant-export-key',
      content: 'FRESH EXPORT ANSWER',
    }),
  ]);

  const exported = await store.exportAuthoritativeConversation('thread-1');

  assert.deepEqual(exported.messages.map(item => item.text), [
    'FRESH EXPORT MESSAGE',
    'FRESH EXPORT ANSWER',
  ]);
  assert.deepEqual(store.active.messages.map(item => item.text), [
    'SERVER AUTHORITATIVE MESSAGE',
  ]);
  assert.deepEqual(fixture.calls.snapshot.at(-1), {
    threadId: 'thread-1',
    activeOnly: false,
  });
});


test('deleting server conversation is never selected as active and is read-only', async () => {
  const deleting = serverThread({
    thread_id: 'thread-deleting',
    state: 'deleting',
    version: 4,
    title: 'Deleting chat',
  });
  const active = serverThread({
    thread_id: 'thread-active',
    state: 'active',
    version: 2,
    title: 'Active chat',
  });
  const fixture = authorityFixture({
    threads: [deleting, active],
    messages: [
      ['thread-deleting', [serverMessage({
        message_id: 'deleting-message',
        content: 'DELETE ME',
      })]],
      ['thread-active', [serverMessage({
        message_id: 'active-message',
        content: 'KEEP ME',
      })]],
    ],
  });
  const { store } = await authorityController(fixture);

  assert.equal(store.active.id, 'thread-active');
  const deletingProjection = store.getSnapshot().workspace.conversations.find(
    item => item.id === 'thread-deleting',
  );
  assert.equal(deletingProjection.serverState, 'deleting');
  assert.equal(deletingProjection.archived, true);

  store.select('thread-deleting');
  assert.equal(store.active.id, 'thread-active');
  assert.match(
    store.getSnapshot().notice || '',
    /pending deletion/,
  );

  store.archive('thread-deleting', false);
  await tick();
  assert.equal(
    fixture.calls.state.some(call => call.threadId === 'thread-deleting'),
    false,
  );

  store.remove('thread-deleting');
  await tick();
  assert.equal(
    fixture.calls.deletion.some(call => call.threadId === 'thread-deleting'),
    false,
  );
});
