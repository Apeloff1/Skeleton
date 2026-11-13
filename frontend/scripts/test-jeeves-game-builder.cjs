'use strict';
const assert = require('node:assert/strict');
const { test } = require('node:test');
const { execFileSync } = require('node:child_process');
const { resolve } = require('node:path');
const { compileFunction } = require('node:vm');
const ts = require('typescript');

const root = resolve(__dirname, '../..');
const assets = JSON.parse(execFileSync('python', ['-c',
  'import json; from skeleton.app.offline_web import HTML, JAVASCRIPT; print(json.dumps({"html":HTML,"javascript":JAVASCRIPT}))'],
{ cwd: root, encoding: 'utf8', maxBuffer: 2 * 1024 * 1024 }));
const source = ts.createSourceFile('offline-workspace.js', assets.javascript, ts.ScriptTarget.ES2022, true, ts.ScriptKind.JS);
const wanted = ['nativeGameBrief', 'checkedForgeJob', 'forgeArchiveReady', 'readBoundedForgeArchive'];
const declarations = new Map();
function visit(node) {
  if (ts.isFunctionDeclaration(node) && wanted.includes(node.name?.text)) declarations.set(node.name.text, node.getText(source));
  ts.forEachChild(node, visit);
}
visit(source);
assert.equal(declarations.size, wanted.length, 'test the actual embedded production functions');
const helpers = compileFunction([...declarations.values()].join('\n') + `\nreturn {${wanted.join(',')}};`)();
const { nativeGameBrief, checkedForgeJob, forgeArchiveReady, readBoundedForgeArchive } = helpers;
const fields = patch => ({genre: 'shooter', difficulty: 'normal', theme: 'neon', encounter: 'patrol',
  speed: '230', objective: 'Recover the beacon', brief: 'My original idea', ...patch});

function job(patch = {}) {
  return {request_id: 'g_original', state: 'complete', terminal: true, brief_sha256: 'a'.repeat(64),
    result: {ok: true, planning: {status: 'accepted', model_digest: 'b'.repeat(64)},
      build: {ok: true, interactive: {native_boot_verified: true, input_journey_verified: true}}},
    archive: {sha256: 'c'.repeat(64), bytes: 6, file_count: 3}, ...patch};
}
function response(chunks, {type = 'application/zip', length = null, redirected = false, ok = true} = {}) {
  let cancellations = 0;
  const stream = new ReadableStream({
    start(controller) {for (const chunk of chunks) controller.enqueue(chunk); controller.close();},
    cancel() {cancellations++;},
  });
  const result = new Response(stream, {headers: {'Content-Type': type, ...(length === null ? {} : {'Content-Length': length})}});
  Object.defineProperty(result, 'redirected', {value: redirected});
  Object.defineProperty(result, 'ok', {value: ok});
  return {result, cancellations: () => cancellations};
}

test('all genre forms produce actual compiler-compatible locked gameplay and preserve authored text exactly', () => {
  const input = '  A careful authored idea.\nKeep my moonlit 🌙 details and this spacing.  ';
  for (const [genre, expected] of [['shooter', 'top_down_shooter'], ['platformer', 'platformer'], ['roguelike', 'rpg_roguelike']]) {
    const brief = nativeGameBrief(fields({genre, brief: input, difficulty: 'easy', theme: 'frost', encounter: 'ranged', speed: '120', objective: 'Find the café key'}));
    assert.ok(brief.endsWith(input), 'creator input must not be trimmed, rewritten or silently truncated');
    const compiled = JSON.parse(execFileSync('python', ['-c',
      'import json,sys; from skeleton.forge.game_design_spec import compile_brief; print(json.dumps(compile_brief(json.load(sys.stdin))))'],
    {cwd: root, input: JSON.stringify(brief), encoding: 'utf8'}));
    assert.equal(compiled.genre, expected);
    assert.deepEqual(compiled.gameplay, {difficulty: 'easy', theme: 'frost', encounter_style: 'ranged',
      player_speed: 120, objective_label: 'Find the café key'});
  }
});

test('explicit form labels cannot be silently overridden by conflicting creator labels', () => {
  const brief = nativeGameBrief(fields({brief: 'Keep this original requirement. Difficulty: hard.'}));
  const result = execFileSync('python', ['-c',
    'import json,sys; from skeleton.forge.game_design_spec import compile_brief,GameplayValidationError\ntry: compile_brief(json.load(sys.stdin))\nexcept GameplayValidationError as error: print(json.dumps(list(error.violations)))'],
  {cwd: root, input: JSON.stringify(brief), encoding: 'utf8'});
  assert.deepEqual(JSON.parse(result), ['conflicting:gameplay.difficulty']);
});

test('invalid selections, objective delimiters, controls, malformed speeds and UTF-8 overflow refuse submission', () => {
  for (const change of [
    {genre: '__proto__'}, {difficulty: 'automatic'}, {theme: 'unknown'}, {encounter: 'hidden'},
    {speed: '119'}, {speed: '361'}, {speed: '230.0'}, {speed: '+230'}, {speed: '2e2'}, {speed: 230},
    {objective: ''}, {objective: 'x'.repeat(101)}, {objective: 'Hidden. Theme: ember'},
    {objective: 'Hidden; Theme: ember'}, {objective: 'two\nlines'}, {objective: ' padded '},
    {objective: '\ud800'}, {brief: '\u0000private'}, {brief: ' '}, {brief: '🌙'.repeat(1000)},
  ]) assert.throws(() => nativeGameBrief(fields(change)), Error, JSON.stringify(change));
  assert.match(nativeGameBrief(fields({speed: '360', objective: 'Relic 🌙'})), /Player speed: 360\./);
});

test('job identity and terminal-state validation fence malformed or foreign saved results', () => {
  assert.equal(checkedForgeJob(job(), 'g_original').request_id, 'g_original');
  for (const change of [{request_id: '../escape'}, {state: 'succeeded'}, {terminal: false},
    {brief_sha256: 'bad'}, {request_id: 'different'}]) {
    assert.throws(() => checkedForgeJob(job(change), 'g_original'), Error);
  }
  assert.throws(() => checkedForgeJob([]), Error);
});

test('source download requires accepted matching model, successful compilation, actual native input proof and bounded archive', () => {
  assert.equal(forgeArchiveReady(job(), 'b'.repeat(64)), true);
  const rejected = [job({state: 'failed'}), job({terminal: false}),
    job({result: {...job().result, ok: false}}),
    job({result: {...job().result, planning: {status: 'rejected', model_digest: 'b'.repeat(64)}}}),
    job({result: {...job().result, build: {ok: true, interactive: {native_boot_verified: true, input_journey_verified: false}}}}),
    job({result: {...job().result, build: {ok: false, interactive: {native_boot_verified: true, input_journey_verified: true}}}}),
    job({archive: {...job().archive, bytes: 16777217}}), job({archive: {...job().archive, sha256: 'bad'}}),
    job({archive: {...job().archive, file_count: 0}})];
  for (const item of rejected) assert.equal(forgeArchiveReady(item, 'b'.repeat(64)), false);
  assert.equal(forgeArchiveReady(job(), 'd'.repeat(64)), false);
  assert.equal(forgeArchiveReady(null, 'b'.repeat(64)), false);
});

test('ZIP transport reads bounded streamed bytes and checks declared length', async () => {
  const {result} = response([new Uint8Array([80, 75]), new Uint8Array([3, 4, 7, 8])], {length: '6'});
  assert.deepEqual(await readBoundedForgeArchive(result, 6, new AbortController().signal), new Uint8Array([80, 75, 3, 4, 7, 8]));
  const wrong = response([new Uint8Array([1, 2, 3])], {length: '4'});
  await assert.rejects(readBoundedForgeArchive(wrong.result, 8, new AbortController().signal), /length/);
});

test('ZIP transport rejects oversized headers, streamed overflow, redirects, wrong MIME and empty responses', async () => {
  for (const setup of [
    {chunks: [new Uint8Array([1])], options: {length: '16777217'}},
    {chunks: [new Uint8Array(5), new Uint8Array(5)], maximum: 9},
    {chunks: [new Uint8Array([1])], options: {type: 'text/html'}},
    {chunks: [new Uint8Array([1])], options: {redirected: true}},
    {chunks: [new Uint8Array([1])], options: {ok: false}}, {chunks: []},
  ]) {
    const {result} = response(setup.chunks, setup.options);
    await assert.rejects(readBoundedForgeArchive(result, setup.maximum ?? 16777216, new AbortController().signal));
  }
});

test('locking while a source stream is pending cancels the read and exposes no partial bytes', async () => {
  const controller = new AbortController(); let cancelled = false;
  const stream = new ReadableStream({pull() {}, cancel() {cancelled = true;}});
  const result = new Response(stream, {headers: {'Content-Type': 'application/zip'}});
  const pending = readBoundedForgeArchive(result, 100, controller.signal);
  controller.abort();
  await assert.rejects(pending, /cancelled/);
  assert.equal(cancelled, true);
});

test('embedded UI keeps same-origin credentials, lock/epoch fences and source-only semantics', () => {
  for (const id of ['forge-open', 'forge-panel', 'forge-form', 'forge-brief', 'forge-submit', 'forge-status', 'forge-proof', 'forge-download', 'forge-jobs']) {
    assert.ok(assets.html.includes(`id="${id}"`), id);
  }
  assert.match(assets.javascript, /headers: \{Authorization: 'Bearer ' \+ state\.token\}/);
  assert.match(assets.javascript, /epoch !== state\.epoch \|\| !state\.connected \|\| state\.forgeJob\?\.request_id !== id/);
  assert.match(assets.javascript, /content\.byteLength !== job\.archive\.bytes \|\| digest !== job\.archive\.sha256/);
  assert.match(assets.javascript, /redirect: 'error'/);
  assert.match(assets.javascript, /clearForge\(\)/);
  assert.ok(!assets.javascript.includes('innerHTML'));
  assert.ok(!assets.javascript.includes('localStorage'));
  assert.ok(!assets.html.includes('<iframe'));
  assert.ok(assets.html.includes('Download Godot source ZIP'));
});
