'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('../skeleton-forge/harness.cjs');
const commands = require('./fixtures/commands.json');
const snapshot = require('./fixtures/snapshot.json');

const C = load('src/forgeOperator/commands.ts');

test('tokenize mirrors shlex: quotes, escapes, unbalanced input', () => {
  assert.deepEqual(C.tokenize(`COMPOSE 'a b' "c \\"d\\"" e\\ f`).tokens, ['COMPOSE', 'a b', 'c "d"', 'e f']);
  assert.equal(C.tokenize('BIND ERA "soulslike').error, 'No closing quotation');
  assert.equal(C.tokenize('ROLL \\').error, 'No escaped character');
  assert.equal(C.tokenize('BIND ').trailingSpace, true);
  assert.deepEqual(C.tokenize("''").tokens, ['']);
});

test('quoteArg round-trips through tokenize', () => {
  for (const v of ['plain', 'two words', "it's", '', 'a"b', 'x~y@0.5']) {
    assert.deepEqual(C.tokenize(`X ${C.quoteArg(v)}`).tokens, ['X', v]);
  }
});

test('resolveVerb picks sub-verbs and tolerates optional keywords', () => {
  assert.equal(C.resolveVerb(['bind', 'gen', '16bit']).spec.id, 'bind-generation');
  assert.equal(C.resolveVerb(['BLEND', 'ERA', 'a', 'b']).argStart, 2);
  assert.equal(C.resolveVerb(['BLEND', 'a', 'b']).argStart, 1);
  assert.equal(C.resolveVerb(['BIND', 'NOPE']).spec, null);
  assert.equal(C.resolveVerb(['FLY']).spec, null);
});

test('every captured successful engine command parses as sendable', () => {
  for (const [line, res] of Object.entries(commands)) {
    if (res.status !== 200) continue;
    const parsed = C.parseCommand(line);
    assert.ok(parsed.spec, `${line} resolves`);
    assert.equal(parsed.sendable, true, `${line}: ${JSON.stringify(parsed.diagnostics)}`);
  }
});

test('engine rejections are caught locally with suggestions', () => {
  const unknownVerb = C.parseCommand('FLY away');
  assert.equal(unknownVerb.sendable, false);
  const arche = C.parseCommand('BIND ARCHETYPE dragon');
  assert.equal(arche.sendable, false);
  assert.match(arche.diagnostics[0].message, /unknown archetype/);
  const axis = C.parseCommand('SET AXIS riskk 0.4');
  assert.deepEqual(axis.diagnostics[0].suggestions, ['risk']);
  assert.equal(C.parseCommand('SET AXIS risk high').sendable, false);
  const clamp = C.parseCommand('SET AXIS risk 1.5');
  assert.equal(clamp.sendable, true);
  assert.equal(clamp.diagnostics[0].severity, 'warning');
});

test('unknown eras warn until the live catalogue is loaded, then block', () => {
  assert.equal(C.parseCommand('BIND ERA vaporwave').sendable, true);
  const live = C.mergeCatalog(C.BASE_CATALOG, { eras: ['metroidvania'] });
  assert.equal(C.parseCommand('BIND ERA vaporwave', live).sendable, false);
  assert.equal(C.parseCommand('BIND ERA metroidvania', live).sendable, true);
});

test('defaults are surfaced and self-blends warned', () => {
  const p = C.parseCommand('BIND ERA');
  assert.equal(p.args.era, 'extraction_now');
  assert.ok(p.diagnostics.some((d) => d.severity === 'info'));
  const self = C.parseCommand('BLEND soulslike soulslike');
  assert.ok(self.diagnostics.some((d) => /no-op/.test(d.message)));
  assert.equal(self.args.t, '0.5');
});

test('completion offers verbs, sub-verbs and catalogue values', () => {
  assert.ok(C.complete('BI').some((c) => c.label === 'BIND ERA'));
  assert.deepEqual(C.complete('BIND G').map((c) => c.label), ['GENERATION']);
  assert.ok(C.complete('BIND ERA so').some((c) => c.line === 'BIND ERA soulslike '));
  assert.ok(C.complete('SET AXIS ').some((c) => c.label === 'tempo'));
  assert.deepEqual(C.complete('COMPOSE some'), []);
});

test('builders emit lines the parser accepts', () => {
  const lines = [
    C.build.bindEra('soulslike'),
    C.build.bindGeneration('16bit'),
    C.build.bindArchetype(' Auto '),
    C.build.setAxis('risk', 2),
    C.build.blendEra('soulslike', 'boomer_shooter', 0.33333),
    C.build.compose('craft  gear\nand loot'),
    C.build.train(0),
    C.build.roll(),
  ];
  assert.equal(C.build.setAxis('risk', 2), 'SET AXIS risk 1');
  assert.equal(C.build.bindArchetype(' Auto '), 'BIND ARCHETYPE auto');
  assert.equal(C.build.train(0), 'TRAIN 1');
  for (const line of lines) assert.equal(C.parseCommand(line).sendable, true, line);
});

test('describeResult summarises real envelopes', () => {
  const d = (line) => C.describeResult(commands[line].body, C.parseCommand(line).spec);
  assert.match(d('BLEND ERA arcade_golden_age soulslike 0.35'), /arcade_golden_age → soulslike at t=0.35/);
  assert.equal(d('SET AXIS risk 0.9'), 'risk = 0.90');
  assert.match(d('BIND GENERATION 16bit'), /16-Bit \(320×224\)/);
  assert.match(d('BIND ARCHETYPE auto'), /vision-composed/);
  assert.match(d('ROLL ORACLE'), /^oracle #9/);
});

test('diffSnapshots reports axis, categorical and ledger changes', () => {
  const after = JSON.parse(JSON.stringify(snapshot));
  after.tensor.axes.risk = (after.tensor.axes.risk ?? 0) + 0.2;
  after.generation = after.generation === '8bit' ? '16bit' : '8bit';
  after.ledger.height += 2;
  const changes = C.diffSnapshots(snapshot, after);
  const fields = changes.map((c) => c.field);
  assert.ok(fields.includes('axis.risk'));
  assert.ok(fields.includes('generation'));
  assert.equal(changes.find((c) => c.field === 'ledger.height').delta, 2);
  assert.deepEqual(C.diffSnapshots(snapshot, snapshot), []);
  assert.deepEqual(C.diffSnapshots(null, snapshot), []);
});

test('foreignHistory finds commands issued by other operators', () => {
  assert.deepEqual(C.foreignHistory(['a', 'b', 'c'], ['b', 'c', 'd', 'e']), ['d', 'e']);
  assert.deepEqual(C.foreignHistory(['a', 'b'], ['a', 'b']), []);
  assert.deepEqual(C.foreignHistory([], ['x']), []);
  assert.deepEqual(C.foreignHistory(['z'], ['x', 'y']), ['x', 'y']);
});
