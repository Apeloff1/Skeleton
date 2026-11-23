const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const { assert, load, harness, memoryStorage, deferred, tick } = require('./helpers.cjs');
const { makeHandoff, defaultContextSelection } = load('context');
const { consumeHandoff } = load('handoff');
const { HANDOFF_KEY } = load('types');
const { WorkspaceController } = require('../../src/features/Jeeves/WorkspaceController.ts');
const { WORKSPACE_KEY } = require('../../src/features/Jeeves/workspace.ts');
const draft = load('../journeys/journeyDraft');

const KEY_A = 'a'.repeat(64);
const KEY_B = 'b'.repeat(64);
function handoff() {
  const h = harness('handoff-journey'); const projectId = h.project();
  return makeHandoff(h.state, { ...defaultContextSelection(h.state, projectId), includeProject: false },
    'Reviewed guided request', { now: Date.now(), id: () => 'reviewed-handoff' });
}
function adapter(storage, auth) {
  const filename = path.resolve(__dirname, '../../src/features/Jeeves/journeys/journeyHandoff.ts');
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, fileName: filename,
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(code, { module, exports: module.exports, require(name) {
    if (name === '@react-native-async-storage/async-storage') return { default: storage };
    if (name === '../../../auth/gameforgeAuth') return { getAuthEpoch: () => auth.epoch, getAuthToken: () => auth.token };
    if (name === '../workbench/handoff') return { consumeHandoff };
    if (name === './journeyDraft') return draft;
    throw new Error('Unexpected handoff dependency: ' + name);
  } }, { filename });
  return module.exports;
}
async function open() {
  const storage = memoryStorage(); const auth = { token: 'account-A', epoch: 1 }; let generations = 0;
  const controller = new WorkspaceController(storage, async () => { generations++; return { reply: 'No automatic generation expected' }; });
  await controller.initialize(); await controller.whenSaved();
  return { storage, auth, controller, generations: () => generations, api: adapter(storage, auth), scope: { key: KEY_A, token: auth.token } };
}

test('account handoff accepts the existing hash scope and refuses invalid scope identities', () => {
  const h = adapter(memoryStorage(), { token: 'A', epoch: 1 });
  const original = handoff();
  const scoped = h.accountBoundHandoff(original, KEY_A);
  assert.equal(scoped.account_scope_key, KEY_A);
  assert.equal(original.account_scope_key, undefined);
  for (const value of ['', 'account-email@example.test', 'x'.repeat(64), 'a'.repeat(63), KEY_A.toUpperCase()]) {
    assert.throws(() => h.accountBoundHandoff(original, value), /account scope is invalid/);
  }
});

test('legacy, foreign-account and malformed handoffs remain untouched and never open a conversation', async () => {
  const h = await open(); const original = h.controller.active.id;
  const values = [JSON.stringify(handoff()), JSON.stringify(h.api.accountBoundHandoff(handoff(), KEY_B)), '{invalid'];
  for (const raw of values) {
    h.storage.data.set(HANDOFF_KEY, raw);
    assert.equal(await h.api.consumeAccountWorkbenchHandoff(h.scope, h.controller), 'none');
    assert.equal(h.storage.data.get(HANDOFF_KEY), raw);
    assert.equal(h.controller.active.id, original);
  }
  assert.equal(h.generations(), 0);
});

test('matching handoff preserves the authored chat draft and acknowledges only after durable save', async () => {
  const h = await open();
  h.controller.edit({ draft: 'Keep my earlier question' }); await h.controller.whenSaved();
  const previousId = h.controller.active.id;
  const value = h.api.accountBoundHandoff(handoff(), KEY_A);
  h.storage.data.set(HANDOFF_KEY, JSON.stringify(value));
  const gate = deferred(); const save = h.storage.setItem;
  h.storage.setItem = async (key, text) => { if (key === WORKSPACE_KEY) await gate.promise; return save(key, text); };
  const pending = h.api.consumeAccountWorkbenchHandoff(h.scope, h.controller);
  await tick();
  assert.equal(h.storage.data.has(HANDOFF_KEY), true);
  assert.equal(h.controller.getSnapshot().saveState, 'saving');
  assert.equal(h.controller.active.draft, value.draft);
  assert.equal(h.controller.getSnapshot().workspace.conversations.find(item => item.id === previousId).draft, 'Keep my earlier question');
  gate.resolve();
  assert.equal(await pending, 'opened');
  assert.equal(h.storage.data.has(HANDOFF_KEY), false);
  assert.equal(h.controller.active.handoffId, value.id);
  assert.equal(h.generations(), 0);
});

test('failed chat persistence retains the bound handoff and safe retry opens no duplicate conversation', async () => {
  const h = await open(); const value = h.api.accountBoundHandoff(handoff(), KEY_A);
  h.storage.data.set(HANDOFF_KEY, JSON.stringify(value)); const save = h.storage.setItem;
  h.storage.setItem = async (key, text) => { if (key === WORKSPACE_KEY) throw new Error('Full device'); return save(key, text); };
  assert.equal(await h.api.consumeAccountWorkbenchHandoff(h.scope, h.controller), 'failed');
  const count = h.controller.getSnapshot().workspace.conversations.length;
  assert.equal(h.storage.data.has(HANDOFF_KEY), true);
  h.storage.setItem = save;
  assert.equal(await h.api.consumeAccountWorkbenchHandoff(h.scope, h.controller), 'opened');
  assert.equal(h.controller.getSnapshot().workspace.conversations.length, count);
  assert.equal(h.generations(), 0);
});

test('account and same-token epoch changes during reads fail before a handoff is opened', async () => {
  for (const field of ['token', 'epoch']) {
    const h = await open(); const raw = JSON.stringify(h.api.accountBoundHandoff(handoff(), KEY_A));
    h.storage.data.set(HANDOFF_KEY, raw); const before = h.controller.active.id;
    const gate = deferred(); const get = h.storage.getItem;
    h.storage.getItem = async key => { if (key === HANDOFF_KEY) await gate.promise; return get(key); };
    const pending = h.api.consumeAccountWorkbenchHandoff(h.scope, h.controller);
    await tick(); h.auth[field] = field === 'token' ? 'account-B' : 2; gate.resolve();
    assert.equal(await pending, 'failed');
    assert.equal(h.controller.active.id, before);
    assert.equal(h.storage.data.get(HANDOFF_KEY), raw);
    assert.equal(h.generations(), 0);
  }
});

test('account rotation during durable chat save never acknowledges the old account handoff', async () => {
  const h = await open(); const raw = JSON.stringify(h.api.accountBoundHandoff(handoff(), KEY_A));
  h.storage.data.set(HANDOFF_KEY, raw);
  const gate = deferred(); const save = h.storage.setItem;
  h.storage.setItem = async (key, value) => { if (key === WORKSPACE_KEY) await gate.promise; return save(key, value); };
  const pending = h.api.consumeAccountWorkbenchHandoff(h.scope, h.controller);
  await tick(); h.auth.token = 'account-B'; h.auth.epoch++; gate.resolve();
  assert.equal(await pending, 'failed');
  assert.equal(h.storage.data.get(HANDOFF_KEY), raw);
  assert.equal(h.generations(), 0);
});
