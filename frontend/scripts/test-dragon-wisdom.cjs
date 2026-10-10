const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const root = path.resolve(__dirname, '../features/Jeeves/companion');
const source = fs.readFileSync(path.join(root, 'dragonWisdomReview.ts'), 'utf8');
const result = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
}, reportDiagnostics: true });
assert.equal((result.diagnostics || []).filter(x => x.category === ts.DiagnosticCategory.Error).length, 0);
const mod = { exports: {} };
vm.runInNewContext(result.outputText, { module: mod, exports: mod.exports }, { timeout: 1000 });
const normalize = mod.exports.normalizeDragonWisdomReview;
const good = {
  schema: 'skeleton.dragon.square_review.v1', terminal: true, release_authority: false,
  candidate_digest: 'a'.repeat(64), artifact_digest: 'b'.repeat(64), review_digest: 'c'.repeat(64),
  reviewed_at: 20, valid_until: 100, completed_rounds: 100, planned_rounds: 100, blockers: [], improvements: [],
  squares: ['play', 'craft', 'delivery', 'trust'].map(id => ({ id, label: id, score: 70,
    industry_score: null, industry_delta: null, comparison_state: 'unknown', status: 'improve' })),
};
assert.ok(normalize(good));
for (const bad of [null, {}, { ...good, terminal: false }, { ...good, completed_rounds: 99 },
  { ...good, release_authority: true }, { ...good, squares: null }, { ...good, squares: [null] },
  { ...good, squares: good.squares.map(x => ({ ...x, score: NaN })) },
  { ...good, squares: good.squares.map(x => ({ ...x, industry_score: 80 })) },
  { ...good, squares: good.squares.map(x => ({ ...x, comparison_state: 'matched_measurements', industry_score: 80, industry_delta: 20 })) },
  { ...good, reviewed_at: -1 }, { ...good, valid_until: 321 },
  { ...good, blockers: [1] }, { ...good, improvements: [{ target: 'untrusted' }] },
]) assert.equal(normalize(bad), null);
assert.ok(normalize({ ...good, squares: good.squares.map(x => ({ ...x,
  comparison_state: 'matched_measurements', industry_score: 80, industry_delta: -10 })) }));
const normalizeSnapshot = mod.exports.normalizeDragonWisdomSnapshot;
const snapshot = { review: good, issued_at: 20, expires_at: 40 };
assert.ok(normalizeSnapshot(snapshot, 21));
for (const [value, now] of [[snapshot, 19], [snapshot, 40], [snapshot, NaN],
  [{...snapshot, expires_at: 101}, 21], [{...snapshot, issued_at: 51, expires_at: 70}, 52],
  [null, 21], [{...snapshot, review: {...good, terminal: false}}, 21]]) {
  assert.equal(normalizeSnapshot(value, now), null);
}
for (const name of ['DragonWisdomSquares.tsx', 'DragonCompanionPanel.tsx', 'useDragonAcademy.ts']) {
  const output = ts.transpileModule(fs.readFileSync(path.join(root, name), 'utf8'), {
    fileName: name, reportDiagnostics: true, compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
    },
  });
  assert.equal((output.diagnostics || []).filter(x => x.category === ts.DiagnosticCategory.Error).length, 0);
}
console.log('Dragon wisdom display: valid terminal cards and malformed-input rejection passed');
