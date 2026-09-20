const { test } = require('node:test');
const { assert, load } = require('./helpers.cjs');
const { paginate, pageForRecord } = load('pagination');

test('empty collections have a stable accessible page range', () => {
  const page = paginate([], 0);
  assert.deepEqual(page.items, []);
  assert.equal(page.index, 0);
  assert.equal(page.pages, 1);
  assert.equal(page.first, 0);
  assert.equal(page.last, 0);
  assert.equal(page.hasPrevious, false);
  assert.equal(page.hasNext, false);
});

test('page boundaries partition a collection without overlap or omissions', () => {
  const records = Array.from({ length: 95 }, (_, id) => ({ id: String(id) }));
  const pages = [0, 1, 2, 3].map(index => paginate(records, index));
  assert.deepEqual(pages.map(page => page.items.length), [30, 30, 30, 5]);
  assert.deepEqual(pages.flatMap(page => page.items), records);
  assert.deepEqual(pages.map(page => page.first), [1, 31, 61, 91]);
  assert.deepEqual(pages.map(page => page.last), [30, 60, 90, 95]);
  assert.equal(pages[3].hasNext, false);
  assert.equal(pages[3].hasPrevious, true);
});

test('removing the final page clamps selection to the last existing page', () => {
  const records = Array.from({ length: 61 }, (_, id) => id);
  const before = paginate(records, 2);
  assert.deepEqual(before.items, [60]);
  const after = paginate(records.slice(0, 60), 2);
  assert.equal(after.index, 1);
  assert.equal(after.first, 31);
  assert.equal(after.last, 60);
});

test('untrusted page and size values cannot request unbounded rendering', () => {
  const records = Array.from({ length: 500 }, (_, id) => id);
  assert.equal(paginate(records, -1).index, 0);
  assert.equal(paginate(records, Infinity).index, 0);
  assert.equal(paginate(records, NaN).index, 0);
  assert.equal(paginate(records, 0, 10000).items.length, 100);
  assert.equal(paginate(records, 0, 0).items.length, 1);
  assert.equal(paginate(records, 0, NaN).items.length, 30);
  assert.equal(paginate(records, 1.9, 10.9).index, 1);
  assert.equal(paginate(records, 1.9, 10.9).size, 10);
});

test('record lookup returns the containing page and distinguishes missing IDs', () => {
  const records = Array.from({ length: 95 }, (_, id) => ({ id: `record-${id}` }));
  assert.equal(pageForRecord(records, 'record-0'), 0);
  assert.equal(pageForRecord(records, 'record-29'), 0);
  assert.equal(pageForRecord(records, 'record-30'), 1);
  assert.equal(pageForRecord(records, 'record-94'), 3);
  assert.equal(pageForRecord(records, 'missing'), null);
  assert.equal(pageForRecord([], 'missing'), null);
});

test('pagination never reorders or mutates frozen input arrays', () => {
  const records = Object.freeze([5, 4, 3, 2, 1]);
  const page = paginate(records, 1, 2);
  assert.deepEqual(page.items, [3, 2]);
  page.items.push(99);
  assert.deepEqual(records, [5, 4, 3, 2, 1]);
});

test('all collection sizes through the maximum task count retain complete coverage', () => {
  for (const size of [1, 29, 30, 31, 60, 61, 799, 800, 1499, 1500]) {
    const records = Array.from({ length: size }, (_, id) => id);
    const count = paginate(records, 0).pages;
    const visited = [];
    for (let index = 0; index < count; index++) {
      const page = paginate(records, index);
      assert.ok(page.items.length <= 30);
      assert.equal(page.total, size);
      visited.push(...page.items);
    }
    assert.deepEqual(visited, records);
  }
});
