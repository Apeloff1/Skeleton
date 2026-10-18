'use strict';
const { compileFunction } = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
function load() {
  const name = path.join(__dirname, '../services/monthCycleLedger.ts');
  const result = ts.transpileModule(fs.readFileSync(name, 'utf8'), {
    fileName: name, compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
      esModuleInterop: true,
    }, reportDiagnostics: true,
  });
  assert.equal(result.diagnostics.length, 0);
  const module = { exports: {} };
  compileFunction(result.outputText, ['require', 'module', 'exports'])(require, module, module.exports);
  return module.exports.MonthCycleLedger;
}
const Ledger = load(), DAY = 86_400_000, START = 1_800_000_000_000;
function store() {
  const items = new Map();
  return { items, getItem: async key => items.get(key) ?? null,
    setItem: async (key, value) => { items.set(key, value); } };
}
const open = (ledger, id='world-1', now=START) => ledger.enroll(id, 'ui', 'studio', now);
test('month-scale receipts survive a fresh app instance', async () => {
  const storage = store(), first = new Ledger(storage, 'alice');
  const receipt = await open(first);
  await first.observe(receipt, { phase: 'observing', cursor: 23,
    now: START + 30 * DAY, nextCheckAt: START + 30 * DAY + 1000 });
  const restarted = new Ledger(storage, 'alice');
  const rows = await restarted.inspect();
  assert.equal(rows.length, 1);
  assert.equal(rows[0].cursor, 23);
  assert.equal(rows[0].status, 'observing');
});
test('both alternating slots are populated over multiple acknowledged writes', async () => {
  const st = store(), ledger = new Ledger(st, 'alice');
  const r = await open(ledger);
  await ledger.observe(r, { phase: 'observing', cursor: 1,
    now: START + 1, nextCheckAt: START + 10 });
  assert.equal(st.items.size, 2);
  assert.equal((await ledger.inspect())[0].cursor, 1);
});
test('corrupt newest slot falls back to last complete receipt', async () => {
  const st = store(), ledger = new Ledger(st, 'alice');
  const r = await open(ledger);
  await ledger.observe(r, { phase: 'observing', cursor: 100,
    now: START + 1, nextCheckAt: START + 10 });
  const key = [...st.items.keys()].find(k => k.endsWith(':b'));
  st.items.set(key, '{"partial":');
  assert.equal((await new Ledger(st, 'alice').inspect())[0].cursor, 0);
});
test('two corrupt slots fail closed rather than silently forgetting running work', async () => {
  const st = store(), ledger = new Ledger(st, 'alice');
  const r = await open(ledger);
  await ledger.observe(r, { phase: 'observing', cursor: 10,
    now: START + 1, nextCheckAt: START + 10 });
  for (const key of st.items.keys()) st.items.set(key, '{bad');
  await assert.rejects(ledger.inspect(), /corrupt/);
  await assert.rejects(open(ledger, 'new'), /corrupt/);
});
test('active jobs remain registered after more than one year', async () => {
  const st = store(), ledger = new Ledger(st, 'alice');
  await open(ledger);
  assert.equal(await ledger.prune(START + 800 * DAY), 0);
  assert.equal((await ledger.inspect()).length, 1);
});
test('terminal receipts are preserved for months before explicit pruning', async () => {
  const ledger = new Ledger(store(), 'alice');
  const r = await open(ledger);
  await ledger.observe(r, { phase: 'terminal_observed', terminalState: 'completed',
    now: START + 10 });
  assert.equal(await ledger.prune(START + 175 * DAY), 0);
  assert.equal(await ledger.prune(START + 181 * DAY), 1);
  assert.equal((await ledger.inspect()).length, 0);
});
test('terminal jobs cannot be revived by duplicate enrollment', async () => {
  const ledger = new Ledger(store(), 'alice');
  const r = await open(ledger);
  await ledger.observe(r, { phase: 'terminal_observed', terminalState: 'failed',
    now: START + 3 });
  const duplicate = await open(ledger);
  assert.equal(duplicate.incarnation, r.incarnation);
  assert.equal(duplicate.status, 'terminal_observed');
  assert.equal((await ledger.inspect()).length, 1);
});
test('a stale callback after dismissal cannot restore a deleted job', async () => {
  const ledger = new Ledger(store(), 'alice');
  const r = await open(ledger);
  assert.equal(await ledger.dismiss(r, START + 30), true);
  assert.equal(await ledger.observe(r, { phase: 'observing', cursor: 999,
    now: START + 50 }), null);
  assert.equal((await ledger.inspect())[0].status, 'dismissed');
});
test('duplicate active enrollment is idempotent', async () => {
  const ledger = new Ledger(store(), 'alice');
  const first = await open(ledger);
  for (let i = 0; i < 40; i++) assert.deepEqual(await open(ledger), first);
  assert.equal((await ledger.inspect()).length, 1);
});
test('cursor confirmations never move backwards', async () => {
  const ledger = new Ledger(store(), 'alice');
  const r = await open(ledger);
  await ledger.observe(r, { phase: 'observing', cursor: 100,
    now: START + 10 });
  await ledger.observe(r, { phase: 'observing', cursor: 50,
    now: START + 20 });
  assert.equal((await ledger.inspect())[0].cursor, 100);
});
test('disconnected status does not falsely report server cancellation', async () => {
  const ledger = new Ledger(store(), 'alice'), r = await open(ledger);
  const row = await ledger.observe(r, { phase: 'disconnected',
    now: START + 10, nextCheckAt: START + 100_000 });
  assert.equal(row.status, 'disconnected');
  assert.equal(row.terminalState, null);
  assert.equal(row.failures, 1);
});
test('terminal status must contain a recognized authoritative outcome', async () => {
  const ledger = new Ledger(store(), 'alice'), r = await open(ledger);
  await assert.rejects(ledger.observe(r, {
    phase: 'terminal_observed', now: START + 10 }), /Terminal observation/);
  assert.equal((await ledger.inspect())[0].status, 'observing');
});
test('due work is sorted by timestamp and excludes terminal/dismissed receipts', async () => {
  const ledger = new Ledger(store(), 'alice');
  const a = await open(ledger, 'A'), b = await open(ledger, 'B'), c = await open(ledger, 'C');
  await ledger.observe(a, { phase: 'observing', now: START + 100, nextCheckAt: START + 500 });
  await ledger.observe(b, { phase: 'observing', now: START + 100, nextCheckAt: START + 200 });
  await ledger.observe(c, { phase: 'terminal_observed', terminalState: 'completed',
    now: START + 100 });
  assert.deepEqual((await ledger.due(START + 400)).map(r => r.operationId), ['B']);
  assert.deepEqual((await ledger.due(START + 600)).map(r => r.operationId), ['B','A']);
});
test('due batch is capped even when hundreds of jobs are retained', async () => {
  const ledger = new Ledger(store(), 'alice');
  for (let i = 0; i < 100; i++) await open(ledger, 'id-'+i);
  assert.equal((await ledger.due(START, 100000)).length, 32);
});
test('saturation refuses new jobs without evicting older active work', async () => {
  const ledger = new Ledger(store(), 'alice');
  for (let i = 0; i < 128; i++) await open(ledger, 'operation-'+i);
  await assert.rejects(open(ledger, 'operation-129'), /saturated/);
  assert.equal((await ledger.inspect()).length, 128);
});
test('parallel same-key writers serialize durable mutations', async () => {
  const ledger = new Ledger(store(), 'alice');
  const jobs = Array.from({ length: 40 }, (_, i) => open(ledger, 'op-'+i));
  const result = await Promise.all(jobs);
  assert.equal(new Set(result.map(r => r.operationId)).size, 40);
  assert.equal((await ledger.inspect()).length, 40);
});
test('writes serialize across two instances sharing a native storage identity', async () => {
  const storage = store();
  const a = new Ledger(storage, 'alice'), b = new Ledger(storage, 'alice');
  await Promise.all([open(a, 'one'), open(b, 'two')]);
  assert.equal((await a.inspect()).length, 2);
});
test('different account namespaces never see each other’s jobs', async () => {
  const storage = store();
  await open(new Ledger(storage, 'alice'), 'private');
  assert.deepEqual(await new Ledger(storage, 'bob').inspect(), []);
});
test('invalid names, future clocks and huge checkpoint cursors fail closed', async () => {
  assert.throws(() => new Ledger(store(), '../bad'), /namespace/);
  const ledger = new Ledger(store(), 'alice');
  await assert.rejects(open(ledger, '../secret'), /identity/);
  const r = await open(ledger);
  await assert.rejects(ledger.observe(r, { phase: 'observing',
    cursor: Number.MAX_SAFE_INTEGER + 1, now: START }), /cursor/);
  await assert.rejects(ledger.observe(r, { phase: 'observing',
    nextCheckAt: START + 9 * DAY, now: START }), /horizon/);
});
test('a rejected native write preserves a previously acknowledged slot', async () => {
  const st = store(), ledger = new Ledger(st, 'alice');
  const r = await open(ledger);
  const oldWrite = st.setItem;
  st.setItem = async () => { throw new Error('locked disk'); };
  await assert.rejects(ledger.observe(r, { phase: 'disconnected', now: START + 100 }), /locked disk/);
  st.setItem = oldWrite;
  assert.equal((await ledger.inspect())[0].status, 'observing');
});
test('storage retry after rejection is never poisoned by previous failure', async () => {
  const st = store(), ledger = new Ledger(st, 'alice');
  const r = await open(ledger);
  const old = st.setItem;
  let failures = 1;
  st.setItem = async (key, value) => {
    if (failures-- > 0) throw new Error('temporary');
    return old(key, value);
  };
  await assert.rejects(ledger.observe(r, { phase: 'disconnected', now: START + 10 }), /temporary/);
  await ledger.observe(r, { phase: 'disconnected', now: START + 20 });
  assert.equal((await ledger.inspect())[0].failures, 1);
});

test('older concurrent status response cannot overwrite newer verified progress', async () => {
  const ledger = new Ledger(store(), 'alice');
  const first = await open(ledger);
  const second = (await ledger.inspect())[0];
  const accepted = await ledger.observe(second, {
    phase: 'observing', cursor: 100, now: START + 30 });
  assert.equal(accepted.observationRevision, 1);
  const outdated = await ledger.observe(first, {
    phase: 'disconnected', cursor: 10, now: START + 31 });
  assert.equal(outdated, null);
  const current = (await ledger.inspect())[0];
  assert.equal(current.cursor, 100);
  assert.equal(current.status, 'observing');
});
test('same-millisecond status collisions are fenced by revision not timestamp', async () => {
  const ledger = new Ledger(store(), 'alice');
  const token = await open(ledger);
  const first = await ledger.observe(token, {
    phase: 'disconnected', now: START, nextCheckAt: START + 300_000 });
  assert.equal(first.observationRevision, 1);
  assert.equal(await ledger.observe(token, {
    phase: 'observing', now: START, nextCheckAt: START + 10 }), null);
  assert.equal((await ledger.inspect())[0].status, 'disconnected');
});
test('fresh receipt version can later record a true terminal response', async () => {
  const ledger = new Ledger(store(), 'alice');
  const first = await open(ledger);
  const accepted = await ledger.observe(first, {
    phase: 'observing', cursor: 10, now: START + 50 });
  const result = await ledger.observe(accepted, {
    phase: 'terminal_observed', terminalState: 'completed',
    cursor: 99, now: START + 60 });
  assert.equal(result.terminalState, 'completed');
  assert.equal(result.cursor, 99);
  assert.equal(result.observationRevision, 2);
});

test('native acknowledgement is not trusted when read-back returns corrupt data', async () => {
  const st = store(), ledger = new Ledger(st, 'alice');
  const receipt = await open(ledger);
  const original = st.setItem;
  st.setItem = async (key, data) => {
    if (key.endsWith(':b')) return original(key, '{"corrupt":true}');
    return original(key, data);
  };
  await assert.rejects(ledger.observe(receipt, {
    phase: 'observing', cursor: 50, now: START + 500,
  }), /verification/);
  assert.equal((await ledger.inspect())[0].cursor, 0);
});
test('newly created slots must be readable before a job is advertised as registered', async () => {
  const st = store(), ledger = new Ledger(st, 'alice');
  st.setItem = async () => {}; // acknowledges but physically does not write
  await assert.rejects(open(ledger), /verification/);
  assert.deepEqual(await ledger.inspect(), []);
});
