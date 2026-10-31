// B040 contract test (QA-owned, draft). Run: node --test artifacts/carrol/b040/
// Dependency-free structural checks mirroring eval_case.schema.json.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const here = new URL('.', import.meta.url);
const schema = JSON.parse(readFileSync(new URL('eval_case.schema.json', here)));
const cases = JSON.parse(readFileSync(new URL('cases.v1.json', here)));
const DIMS = ['correctness', 'editability', 'latency', 'cost', 'safety'];

test('B040-C01 schema requires the five spec dimensions', () => {
  assert.deepEqual(schema.properties.dimensions.required, DIMS);
});
test('B040-C02 golden set is non-empty with unique ids and seeds', () => {
  assert.ok(cases.length > 0);
  assert.equal(new Set(cases.map(c => c.case_id)).size, cases.length);
  assert.equal(new Set(cases.map(c => c.seed)).size, cases.length);
});
for (const c of cases) {
  test(`B040-C03 ${c.case_id} conforms`, () => {
    for (const k of schema.required) assert.ok(k in c, `missing ${k}`);
    for (const k of Object.keys(c)) assert.ok(k in schema.properties, `unknown key ${k}`);
    assert.match(c.case_id, new RegExp(schema.properties.case_id.pattern));
    assert.ok(Number.isInteger(c.version) && c.version >= 1);
    assert.ok(Number.isInteger(c.seed) && c.seed >= 0);
    assert.ok(c.brief.title && c.brief.genre);
    assert.deepEqual(Object.keys(c.dimensions).sort(), [...DIMS].sort());
    const re = new RegExp(schema.$defs.threshold.properties.pass_if.pattern);
    for (const d of DIMS) {
      assert.ok(c.dimensions[d].metric, `${d}.metric`);
      assert.match(c.dimensions[d].pass_if, re);
    }
  });
}
test('B040-C04 every case enforces zero safety violations', () => {
  for (const c of cases) assert.equal(c.dimensions.safety.pass_if, '== 0');
});
