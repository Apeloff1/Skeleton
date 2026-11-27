const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const filename = path.resolve(__dirname, '../../src/features/Jeeves/forgeParameters/forgeQueuedSave.ts');
const moduleFixture = { exports: {} };
const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  fileName: filename, compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText;
new Function('module', 'exports', 'require', code)(moduleFixture, moduleFixture.exports,
  () => { throw new Error('The session-only queued save helper acquired a runtime dependency.'); });
const Q = moduleFixture.exports;
const copy = value => JSON.parse(JSON.stringify(value));
const scope = (overrides = {}) => ({ projectId: 'project-one', accountEpoch: 4,
  accountToken: 'fixture-session-one', viewEpoch: 7, ...overrides });
function document(overrides = {}) {
  return { schema: 'skeleton.game.frontier_studio_document.v1', project_id: 'project-one',
    expected_version: 2, source_sha256: 'a'.repeat(64),
    action_catalog: ['tile_set'], layers: [{ id: 'ground', size: [16, 16] }],
    future: { preserve: ['original', 1] }, ...overrides };
}
const tile = (x = 1) => ({ action: 'tile_set', parameters: { layer: 'ground', x, y: 3, tile: 2 } });
const queued = (id = 'step-one', value = tile()) => Q.queueForgeStep(id, value);
const begin = (queue = [queued()], key = 'save-one') => Q.beginForgeSave(scope(), document(), queue, key);

test('save snapshot preserves exact original request after source, parameter, queue and scope edits', () => {
  const currentScope = scope(), currentDoc = document(), input = tile();
  const first = queued('first', input), second = queued('second', tile(2));
  const queue = [first, second];
  const pending = Q.beginForgeSave(currentScope, currentDoc, queue, 'original-save-key');
  input.parameters.x = 99;
  currentDoc.expected_version = 11;
  currentDoc.layers[0].size[0] = 32;
  currentDoc.future.preserve.push('changed');
  currentScope.accountToken = 'fixture-session-two';
  queue.pop(); queue.push(queued('later', tile(9)));
  assert.equal(pending.snapshot.requestId, 'original-save-key');
  assert.equal(pending.snapshot.document.expected_version, 2);
  assert.equal(currentDoc.expected_version, 11, 'Freezing a save must not freeze the current editable source object.');
  assert.deepEqual(pending.snapshot.document.layers[0].size, [16, 16]);
  assert.deepEqual(pending.snapshot.document.future.preserve, ['original', 1]);
  assert.deepEqual(pending.snapshot.steps, [tile(), tile(2)]);
  assert.deepEqual(pending.snapshot.stepIds, ['first', 'second']);
  assert.equal(pending.snapshot.scope.accountToken, 'fixture-session-one');
  assert.ok(Object.isFrozen(pending.snapshot) && Object.isFrozen(pending.snapshot.document.layers[0].size));
  assert.ok(Object.isFrozen(pending.snapshot.steps[0].parameters) && Object.isFrozen(first));
});

test('beginning a save snapshots mutable caller actions without freezing or rewriting their later edits', () => {
  const entry = { localId: 'mutable', action: 'tile_set', parameters: { points: [[1, 2]], title: 'original' } };
  const pending = begin([entry]);
  assert.equal(Object.isFrozen(entry), false);
  assert.equal(Object.isFrozen(entry.parameters), false);
  entry.parameters.points[0][0] = 99;
  entry.parameters.title = 'later draft';
  assert.equal(entry.parameters.points[0][0], 99);
  assert.deepEqual(pending.snapshot.steps[0].parameters, { points: [[1, 2]], title: 'original' });
});

test('wire steps contain only original action and parameters, never local identities', () => {
  const queue = [queued('private-local-one'), queued('private-local-two', tile(2))];
  const wire = Q.forgeQueueWireSteps(queue);
  assert.deepEqual(wire, [tile(), tile(2)]);
  for (const step of wire) assert.deepEqual(Object.keys(step), ['action', 'parameters']);
  assert.equal(JSON.stringify(wire).includes('private-local'), false);
  wire[0].parameters.x = 100;
  assert.equal(queue[0].parameters.x, 1);
});

test('only a proven first pre-dispatch rejection releases the pending save', () => {
  const original = begin();
  assert.equal(original.uncertain, false);
  assert.equal(Q.failForgeSave(original, true), null);
  assert.deepEqual(original.snapshot.steps, [tile()]);
});

test('unknown ACK and every later rejection retain the original immutable save identity', () => {
  const original = begin();
  let pending = Q.failForgeSave(original, false);
  assert.equal(pending.uncertain, true);
  const failures = ['HTTP 400', 'HTTP 401', 'HTTP 403', 'HTTP 404', 'HTTP 409',
    'HTTP 422', 'post-commit mismatch', 'network timeout'];
  for (const failure of failures) {
    pending = Q.failForgeSave(pending, failure.startsWith('HTTP'));
    assert.ok(pending, failure);
    assert.equal(pending.uncertain, true, failure);
    assert.equal(pending.snapshot, original.snapshot, failure);
    assert.equal(pending.snapshot.requestId, 'save-one', failure);
    assert.equal(pending.snapshot.document.expected_version, 2, failure);
  }
});

test('confirmation clears original IDs only and retains later identical content as distinct work', () => {
  const first = queued('first'), second = queued('second', tile(2));
  const pending = Q.failForgeSave(begin([first, second]), false);
  const sameIntentLater = queued('later-identical', tile());
  const another = queued('later-different', tile(9));
  const current = [first, sameIntentLater, second, another];
  const retained = Q.confirmForgeSave(pending, current, scope());
  assert.deepEqual(retained.map(step => step.localId), ['later-identical', 'later-different']);
  assert.equal(retained[0], sameIntentLater);
  assert.equal(retained[1], another);
  assert.deepEqual(current.map(step => step.localId), ['first', 'later-identical', 'second', 'later-different']);
});

test('undoing original actions during uncertainty does not remove later actions on confirmation', () => {
  const first = queued('first'), second = queued('second', tile(2));
  const pending = Q.failForgeSave(begin([first, second]), false);
  const later = queued('later', tile(3));
  assert.deepEqual(Q.confirmForgeSave(pending, [first, later], scope()).map(step => step.localId), ['later']);
  assert.deepEqual(Q.confirmForgeSave(pending, [later], scope()).map(step => step.localId), ['later']);
  assert.deepEqual(Q.confirmForgeSave(pending, [], scope()), []);
});

test('account token, account epoch, project and view changes fence confirmation without touching queued work', () => {
  const pending = begin();
  const queue = [queued(), queued('later', tile(3))];
  for (const changed of [scope({ accountToken: 'fixture-session-two' }), scope({ accountEpoch: 5 }),
    scope({ projectId: 'project-two' }), scope({ viewEpoch: 8 })]) {
    assert.equal(Q.forgeSaveScopeMatches(pending.snapshot, changed), false);
    assert.throws(() => Q.confirmForgeSave(pending, queue, changed), /account or project changed/);
    assert.deepEqual(queue.map(step => step.localId), ['step-one', 'later']);
  }
  assert.equal(Q.forgeSaveScopeMatches(pending.snapshot, scope()), true);
});

test('duplicate or reused local identities cannot clear unrelated authored work', () => {
  assert.throws(() => begin([queued('duplicate'), queued('duplicate', tile(2))]), /unique/);
  const pending = begin([queued('original')]);
  const changed = queued('original', tile(99));
  assert.throws(() => Q.confirmForgeSave(pending, [changed], scope()), /identity changed/);
  assert.equal(changed.parameters.x, 99);
  const reordered = Q.queueForgeStep('original', { action: 'tile_set',
    parameters: { tile: 2, y: 3, x: 1, layer: 'ground' } });
  assert.deepEqual(Q.confirmForgeSave(pending, [reordered], scope()), []);
});

test('current API identity, batch, field and UTF-8 limits remain enforced without number coercion', () => {
  assert.throws(() => begin([]), /1 and 64/);
  const full = Array.from({ length: 64 }, (_, index) => queued('step-' + index, tile(index)));
  assert.equal(begin(full).snapshot.steps.length, 64);
  assert.throws(() => begin([...full, queued('extra')]), /1 and 64/);
  assert.throws(() => Q.beginForgeSave(scope(), document({ project_id: 'foreign' }), [queued()], 'key'), /current project/);
  assert.throws(() => Q.beginForgeSave(scope(), document({ expected_version: 0 }), [queued()], 'key'), /current project/);
  assert.throws(() => Q.beginForgeSave(scope(), document(), [queued()], ' bad-key '), /normalized/);
  const fields = Object.fromEntries(Array.from({ length: 32 }, (_, index) => ['field' + index, index]));
  assert.equal(Q.queueForgeStep('bounded', { action: 'test', parameters: fields }).parameters.field31, 31);
  assert.throws(() => Q.queueForgeStep('over', { action: 'test', parameters: { ...fields, extra: 0 } }), /32 fields/);
  const exact = { title: 'x'.repeat(127988) };
  assert.equal(Buffer.byteLength(JSON.stringify(exact), 'utf8'), 128000);
  assert.equal(Q.queueForgeStep('exact-bytes', { action: 'test', parameters: exact }).parameters.title.length, 127988);
  assert.throws(() => Q.queueForgeStep('one-byte-over', { action: 'test', parameters: { title: exact.title + 'x' } }), /128,000/);
  assert.throws(() => Q.queueForgeStep('large', { action: 'test', parameters: { title: 'é'.repeat(64000) } }), /128,000/);
  const typed = Q.queueForgeStep('typed', { action: 'test', parameters: { number: -0, text: '2', flag: false, empty: null } });
  assert.equal(Object.is(typed.parameters.number, -0), true);
  assert.equal(typeof typed.parameters.text, 'string');
  assert.equal(typed.parameters.flag, false);
  assert.equal(typed.parameters.empty, null);
});

test('freezing JSON cannot invoke mutating accessors or accept hidden executable values', () => {
  let calls = 0;
  const params = Object.defineProperty({}, 'title', { enumerable: true, get() { calls += 1; return 'mutated'; } });
  assert.throws(() => Q.queueForgeStep('getter', { action: 'test', parameters: params }), /ordinary JSON/);
  const toJSON = Object.defineProperty({}, 'toJSON', { enumerable: true, get() { calls += 1; return () => ({}); } });
  assert.throws(() => Q.queueForgeStep('toJSON', { action: 'test', parameters: toJSON }), /ordinary JSON/);
  const queue = [queued()];
  Object.defineProperty(queue, '0', { enumerable: true, get() { calls += 1; return queued(); } });
  assert.throws(() => begin(queue), /ordinary entries/);
  assert.equal(calls, 0);
  const cycle = {}; cycle.self = cycle;
  for (const value of [cycle, { n: NaN }, { n: Infinity }, { n: undefined }, { fn() {} }, { n: 1n }, { [Symbol('hidden')]: 1 }]) {
    assert.throws(() => Q.queueForgeStep('bad', { action: 'test', parameters: value }));
  }
  const sparse = [1, , 3];
  const named = [1]; named.metadata = 2;
  for (const value of [sparse, named]) assert.throws(() => Q.queueForgeStep('array', { action: 'test', parameters: { points: value } }));
  assert.throws(() => begin(new Array(1)), /ordinary entries/);
});

test('snapshot source and scope accessors cannot run during a local save gesture', () => {
  let calls = 0;
  const source = document();
  Object.defineProperty(source, 'source_sha256', { enumerable: true, get() { calls += 1; return 'b'.repeat(64); } });
  assert.throws(() => Q.beginForgeSave(scope(), source, [queued()], 'key'), /ordinary JSON/);
  const identity = scope();
  Object.defineProperty(identity, 'accountToken', { enumerable: true, get() { calls += 1; return 'fixture-other'; } });
  assert.throws(() => Q.beginForgeSave(identity, document(), [queued()], 'key'), /ordinary JSON/);
  assert.equal(calls, 0);
  assert.throws(() => Q.beginForgeSave(scope({ accountEpoch: '4' }), document(), [queued()], 'key'), /scope is invalid/);
});

test('prototype-like own JSON keys survive snapshotting without polluting another object', () => {
  const parameters = JSON.parse('{"__proto__":{"polluted":true},"constructor":"kept","nested":[{"value":3}]}');
  const input = { action: 'test', parameters };
  const entry = queued('prototype', input);
  const pending = begin([entry]);
  assert.deepEqual(copy(pending.snapshot.steps[0].parameters), parameters);
  assert.equal({}.polluted, undefined);
  assert.equal(Object.hasOwn(pending.snapshot.steps[0].parameters, '__proto__'), true);
  parameters.nested[0].value = 100;
  assert.equal(pending.snapshot.steps[0].parameters.nested[0].value, 3);
});

test('standalone client input cloning freezes independent closed data without freezing editable callers', () => {
  const original = document(), steps = [tile()];
  const copied = Q.cloneForgeEditInput('project-one', original, steps);
  original.expected_version = 9;
  original.layers[0].size[0] = 32;
  steps[0].parameters.x = 77;
  assert.equal(copied.document.expected_version, 2);
  assert.deepEqual(copied.document.layers[0].size, [16, 16]);
  assert.deepEqual(copied.steps, [tile()]);
  assert.equal(original.expected_version, 9);
  assert.equal(steps[0].parameters.x, 77);
  assert.ok(Object.isFrozen(copied) && Object.isFrozen(copied.steps[0].parameters));
  assert.deepEqual(Object.keys(copied.steps[0]), ['action', 'parameters']);
});

test('standalone input preflights every array descriptor without invoking getters or custom methods', () => {
  let calls = 0;
  const indexed = [tile()];
  Object.defineProperty(indexed, '0', { enumerable: true, get() { calls += 1; return tile(); } });
  const named = [tile()];
  Object.defineProperty(named, 'metadata', { enumerable: true, get() { calls += 1; return 'hidden'; } });
  const symbolic = [tile()];
  Object.defineProperty(symbolic, Symbol('hidden'), { enumerable: true, get() { calls += 1; return 1; } });
  const nonenumerable = [tile()];
  Object.defineProperty(nonenumerable, '0', { value: tile(), enumerable: false });
  const method = [tile()]; method.map = () => { calls += 1; return [tile(99)]; };
  class UntrustedArray extends Array {}
  for (const array of [indexed, named, symbolic, nonenumerable, method, new Array(1), new UntrustedArray(tile())]) {
    assert.throws(() => Q.cloneForgeEditInput('project-one', document(), array));
  }
  assert.equal(calls, 0);
});

test('standalone document and catalogue accessors are rejected before any source field is read', () => {
  let calls = 0;
  const source = document();
  Object.defineProperty(source, 'source_sha256', { enumerable: true, get() { calls += 1; return 'b'.repeat(64); } });
  const catalogue = document();
  Object.defineProperty(catalogue.action_catalog, '0', { enumerable: true, get() { calls += 1; return 'tile_set'; } });
  assert.throws(() => Q.cloneForgeEditInput('project-one', source, [tile()]));
  assert.throws(() => Q.cloneForgeEditInput('project-one', catalogue, [tile()]));
  assert.equal(calls, 0);
});
