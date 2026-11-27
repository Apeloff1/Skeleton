const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const root = path.resolve(__dirname, '../..');
const helperPath = path.join(root, 'src/features/Jeeves/forgeParameters/forgeParameterEditor.ts');
const helper = { exports: {} };
const compiled = ts.transpileModule(fs.readFileSync(helperPath, 'utf8'), {
  fileName: helperPath, compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText;
new Function('module', 'exports', 'require', compiled)(helper, helper.exports, () => { throw Error('Pure parameter helper acquired a dependency.'); });
const P = helper.exports;
const data = value => JSON.parse(JSON.stringify(value));

test('all 500 actual operation seeds remain typed, complete and losslessly unchanged', () => {
  const filename = path.join(root, 'src/features/Jeeves/GameFrontierAuthoringPanel.tsx');
  const source = fs.readFileSync(filename, 'utf8');
  const tree = ts.createSourceFile(filename, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let choose;
  function visit(node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(tree) === 'choose') choose = node.initializer.getText(tree);
    ts.forEachChild(node, visit);
  }
  visit(tree); assert.ok(choose, 'Use the actual operation-selection implementation.');
  const fixture = `\nexports.__seed = (name, selectedLayer, doc) => {
    let result; const setAction = () => {}; const setParameterIssue = () => {}; const setParameters = value => { result = value; };
    const choose = ${choose}; choose(name); return result;
  }; exports.__groups = GROUPS;`;
  const module = { exports: {} };
  const code = ts.transpileModule(source + fixture, {
    fileName: filename, compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React },
  }).outputText;
  vm.runInNewContext(code, { module, exports: module.exports, require: () => ({}) }, { filename });
  const actions = module.exports.__groups.flatMap(group => group.actions);
  assert.equal(actions.length, 500); assert.equal(new Set(actions).size, 500);
  for (const action of actions) {
    const raw = module.exports.__seed(action, 'test_ground', {
      prefab_catalog: [{ id: 'test_guard' }], actor_catalog: [{ prefab_id: 'test_guard', index: 2 }],
    });
    assert.equal(typeof raw, 'string', action);
    const parsed = P.inspectForgeParameters(raw); assert.equal(parsed.ok, true, `${action}: ${parsed.error}`);
    assert.deepEqual(data(parsed.value), JSON.parse(raw), action);
    for (const field of parsed.root.children) {
      assert.equal(P.replaceForgeParameter(raw, raw, field.path, field.value), raw, `${action}/${field.path.join('/')}`);
    }
  }
});

test('editing a value preserves unrelated whitespace, escapes, numeric spelling and unknown fields', () => {
  const raw = '{ "x" : 1e2, "title": "Keep  spaces", "future": {"escaped":"\\u0061", "flag":true} }';
  const changed = P.replaceForgeParameter(raw, raw, ['title'], 'Lantern route');
  assert.equal(changed, raw.replace('"Keep  spaces"', '"Lantern route"'));
  assert.equal(P.replaceForgeParameter(raw, raw, ['future', 'flag'], false), raw.replace('true', 'false'));
  assert.equal(P.replaceForgeParameter(raw, raw, ['title'], ''), raw.replace('"Keep  spaces"', '""'));
});

test('boolean, null, number and numeric string types remain distinct', () => {
  const raw = '{"enabled":false,"empty":null,"amount":2,"text":"2"}';
  assert.equal(JSON.parse(P.replaceForgeParameter(raw, raw, ['enabled'], true)).enabled, true);
  assert.equal(typeof JSON.parse(P.replaceForgeParameter(raw, raw, ['amount'], 4)).text, 'string');
  assert.equal(P.replaceForgeParameter(raw, raw, ['amount'], -0), raw.replace('"amount":2', '"amount":-0'));
  assert.deepEqual(JSON.parse(P.replaceForgeParameter(raw, raw, ['empty'], [])).empty, []);
});

test('nested point arrays can duplicate, edit, remove and append without replacing neighboring fields', () => {
  const raw = '{ "points": [ [1, 2], [3, 4] ], "other": {"retained":true} }';
  assert.deepEqual(JSON.parse(P.duplicateForgeParameter(raw, raw, ['points', 0])).points, [[1,2], [3,4], [1,2]]);
  assert.deepEqual(JSON.parse(P.replaceForgeParameter(raw, raw, ['points', 1, 0], 9)).points, [[1,2], [9,4]]);
  assert.deepEqual(JSON.parse(P.removeForgeParameter(raw, raw, ['points', 0])).points, [[3,4]]);
  assert.deepEqual(JSON.parse(P.removeForgeParameter(raw, raw, ['points', 1])).points, [[1,2]]);
  const appended = P.appendForgeParameter(raw, raw, ['points'], null, [5,6]);
  assert.deepEqual(JSON.parse(appended).points, [[1,2], [3,4], [5,6]]);
  assert.ok(appended.endsWith(', "other": {"retained":true} }'));
});

test('own-key paths preserve prototype-like, empty and punctuation keys without pollution', () => {
  const raw = '{"__proto__":{"polluted":false},"constructor":2,"a.b":{"a/b~c":3},"":4}';
  assert.equal(JSON.parse(P.replaceForgeParameter(raw, raw, ['__proto__', 'polluted'], true)).__proto__.polluted, true);
  assert.equal({}.polluted, undefined);
  assert.equal(JSON.parse(P.replaceForgeParameter(raw, raw, [''], 5))[''], 5);
  assert.equal(P.parameterPathLabel(['a.b', 'a/b~c']), '/a.b/a~1b~0c');
  assert.throws(() => P.replaceForgeParameter(raw, raw, ['a.b.a/b~c'], 5), /no longer exists/);
});

test('stale drafts, duplicate keys and mismatched array paths cannot apply an edit', () => {
  const raw = '{"x":1,"points":[2]}';
  assert.throws(() => P.replaceForgeParameter(raw + ' ', raw, ['x'], 4), /draft changed/);
  assert.throws(() => P.replaceForgeParameter(raw, raw, ['points', '0'], 4), /no longer exists/);
  for (const broken of ['{"x":', '[1,2]', 'null', '{"x":1,"x":2}', '{"x":1,"\\u0078":2}', '{"x":1,}', '{"x":[1,]}']) {
    assert.equal(P.inspectForgeParameters(broken).ok, false, broken);
  }
  assert.equal(raw, '{"x":1,"points":[2]}');
});

test('backend compact-byte and top-field bounds are separate from visible form limits', () => {
  const fields = Object.fromEntries(Array.from({ length: 32 }, (_, i) => ['field' + i, i]));
  assert.equal(P.inspectForgeParameters(JSON.stringify(fields)).ok, true);
  fields.extra = 0; assert.match(P.inspectForgeParameters(JSON.stringify(fields)).error, /32 top-level/);
  assert.match(P.inspectForgeParameters(JSON.stringify({ text: 'é'.repeat(70000) })).error, /128,000 compact UTF-8/);
  const large = '{"points":[' + Array.from({ length: 2000 }, (_, i) => i).join(',') + ']}';
  const parsed = P.inspectForgeParameters(large); assert.equal(parsed.ok, true); assert.ok(parsed.fieldCount > 96);
});

test('numeric drafts cannot coerce, clamp, round or accept unfinished input', () => {
  for (const text of ['', '-', '1e', '01', 'Infinity', 'NaN', '1e309', '1e-9999', '9007199254740993', '0.10000000000000001']) {
    assert.throws(() => P.parseForgeNumber(text), undefined, text);
  }
  assert.equal(P.parseForgeNumber('-12.5e2'), -1250); assert.equal(P.parseForgeNumber('0.00001'), .00001);
  assert.equal(P.parseForgeNumber('0.100'), .1); assert.equal(P.parseForgeNumber('1e3'), 1000);
  assert.equal(Object.is(P.parseForgeNumber('-0'), -0), true);
  assert.equal(P.inspectForgeParameters('{"unsafe":9007199254740993}').ok, false);
});

test('empty objects and arrays support explicit unknown values and complete removal', () => {
  const raw = '{ "object": {}, "array": [] }';
  assert.deepEqual(JSON.parse(P.appendForgeParameter(raw, raw, ['object'], 'chapter.one', { objective: 'Explore' })).object,
    { 'chapter.one': { objective: 'Explore' } });
  const appended = P.appendForgeParameter(raw, raw, ['array'], null, false);
  assert.deepEqual(JSON.parse(appended).array, [false]);
  assert.deepEqual(JSON.parse(P.removeForgeParameter(appended, appended, ['array', 0])).array, []);
  assert.deepEqual(JSON.parse(P.removeForgeParameter(raw, raw, ['array'])), { object: {} });
  assert.throws(() => P.appendForgeParameter(raw, raw, [], 'array', 0), /unique/);
  assert.throws(() => P.removeForgeParameter(raw, raw, []), /root/);
});

test('new values cannot hide getters, functions, sparse arrays, named array fields or cycles', () => {
  const raw = '{"value":null}'; const accessor = {}; let invoked = false;
  Object.defineProperty(accessor, 'secret', { enumerable: true, get() { invoked = true; return 'leak'; } });
  const cycle = {}; cycle.self = cycle; const named = []; named.extra = 1;
  for (const value of [accessor, cycle, { task: () => 1 }, [undefined], Array(2), named, new Date()]) {
    assert.throws(() => P.replaceForgeParameter(raw, raw, ['value'], value));
  }
  assert.equal(invoked, false);
});

test('inspection bounds stop pathological inputs without changing the draft', () => {
  const deep = '{"a":' + '['.repeat(66) + '0' + ']'.repeat(66) + '}';
  assert.equal(P.inspectForgeParameters(deep).ok, false);
  assert.equal(P.inspectForgeParameters(' '.repeat(P.FORGE_PARAMETER_LIMITS.rawChars + 1)).ok, false);
  const unicode = '{"\\ud800": "\\udc00", "normal":"safe"}';
  assert.equal(P.inspectForgeParameters(unicode).ok, true);
  assert.equal(P.replaceForgeParameter(unicode, unicode, ['normal'], 'retained'), unicode.replace('"safe"', '"retained"'));
});
