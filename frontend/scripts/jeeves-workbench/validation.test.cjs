const { test } = require('node:test');
const { assert, load, harness, linkedFixture } = require('./helpers.cjs');
const V = load('validation');
const { inspectIntegrity } = load('integrity');
const { LIMITS } = load('types');

test('validated workspaces are reconstructed from an explicit field allowlist', () => {
  const { h } = linkedFixture();
  const candidate = structuredClone(h.state);
  candidate.secret = 'not retained';
  candidate.projects[0].unknown = 'not retained';
  candidate.preferences.unknown = true;
  const result = V.validateWorkbench(candidate);
  assert.equal(result.ok, true);
  assert.equal(result.value.secret, undefined);
  assert.equal(result.value.projects[0].unknown, undefined);
  assert.equal(result.value.preferences.unknown, undefined);
  assert.notEqual(result.value.projects[0], candidate.projects[0]);
});

test('unknown schemas and non-object roots are rejected without repair', () => {
  const h = harness();
  for (const input of [null, [], 'hello', 1, { ...h.state, version: 2 }]) {
    const result = V.validateWorkbench(input);
    assert.equal(result.ok, false);
    assert.ok(result.issues.length);
    assert.ok(result.issues.length <= 100);
  }
});

test('numeric strings, booleans and nonfinite values are not accepted as counts', () => {
  const h = harness();
  for (const value of ['10', true, NaN, Infinity, -1, 1.5]) {
    const candidate = structuredClone(h.state);
    candidate.preferences.dailyNewCards = value;
    const result = V.validateWorkbench(candidate);
    assert.equal(result.ok, false, String(value));
    assert.ok(result.issues.some(issue => issue.path.includes('dailyNewCards')));
  }
});

test('boolean flags require actual booleans', () => {
  const h = harness();
  h.project();
  const candidate = structuredClone(h.state);
  candidate.projects[0].pinned = 'false';
  candidate.preferences.includeSourcesInContext = 1;
  const result = V.validateWorkbench(candidate);
  assert.equal(result.ok, false);
  assert.ok(result.issues.some(issue => issue.path.includes('pinned')));
  assert.ok(result.issues.some(issue => issue.path.includes('includeSources')));
});

test('invalid enums fail instead of falling back to a different status', () => {
  const { h } = linkedFixture();
  const candidate = structuredClone(h.state);
  candidate.projects[0].status = 'deleted';
  candidate.tasks[0].priority = 'critical';
  candidate.notes[0].confidence = 'verified-by-ai';
  candidate.cards[0].schedule.state = 'mastered';
  const result = V.validateWorkbench(candidate);
  assert.equal(result.ok, false);
  assert.ok(result.issues.length >= 4);
});

test('IDs must be bounded simple identifiers and globally unique', () => {
  const { h } = linkedFixture();
  for (const id of ['', '../file', 'with space', 'a'.repeat(121), '<script>']) {
    const candidate = structuredClone(h.state);
    candidate.tasks[0].id = id;
    assert.equal(V.validateWorkbench(candidate).ok, false, id);
  }
  const duplicate = structuredClone(h.state);
  duplicate.tasks[0].id = duplicate.notes[0].id;
  const result = V.validateWorkbench(duplicate);
  assert.equal(result.ok, false);
  assert.ok(result.issues.some(issue => issue.message.includes('globally unique')));
});

test('parent and active project references must exist', () => {
  const { h } = linkedFixture();
  const candidate = structuredClone(h.state);
  candidate.activeProjectId = 'missing';
  candidate.tasks[0].projectId = 'missing';
  const result = V.validateWorkbench(candidate);
  assert.equal(result.ok, false);
  assert.ok(result.issues.some(issue => issue.path === 'activeProjectId'));
  assert.ok(result.issues.some(issue => issue.message.includes('parent project')));
});

test('calendar date validation handles leap years and rejects impossible dates', () => {
  for (const value of ['2024-02-29', '2000-02-29', '2026-12-31']) assert.equal(V.validDate(value), true);
  for (const value of ['2026-02-29', '1900-02-29', '2026-04-31', '2026-00-01', '26-01-01', '2026-1-01', '2026-01-01T00:00:00Z']) {
    assert.equal(V.validDate(value), false, value);
  }
  assert.equal(V.assertDate(null, 'Due date'), null);
  assert.throws(() => V.assertDate('2026-02-30', 'Due date'));
});

test('URL validation rejects executable schemes and embedded credentials', () => {
  assert.equal(V.safeUrl('https://example.com/path?q=hello'), 'https://example.com/path?q=hello');
  assert.equal(V.safeUrl('http://localhost:8000/docs'), 'http://localhost:8000/docs');
  for (const value of ['javascript:alert(1)', 'file:///etc/passwd', 'data:text/html,test', 'https://user:pass@example.com', 'not a url']) {
    assert.equal(V.safeUrl(value), null, value);
  }
});

test('tag normalization deduplicates and bounds the resulting vocabulary', () => {
  assert.deepEqual(V.normalizeTags([' UI ', 'ui', '', 'Physics']), ['ui', 'physics']);
  assert.throws(() => V.normalizeTags(['a'.repeat(LIMITS.tag + 1)]));
  assert.throws(() => V.normalizeTags(Array.from({ length: LIMITS.tags + 1 }, (_, index) => `tag-${index}`)));
  assert.deepEqual(V.normalizeIds(['one', 'one', 'two'], 'Links'), ['one', 'two']);
  assert.throws(() => V.normalizeIds(['one', 'two'], 'Links', 1));
});

test('text normalization strips nulls and normalizes Windows newlines', () => {
  assert.equal(V.assertText('a\0b\r\nc', 'Body', 20), 'ab\nc');
  assert.throws(() => V.assertText('   ', 'Title', 20, true));
  assert.throws(() => V.assertText('abc', 'Title', 2));
  assert.throws(() => V.assertText(42, 'Title', 20));
});

test('parseWorkbench enforces serialized storage limits before parsing', () => {
  assert.equal(V.parseWorkbench('{bad').ok, false);
  const over = V.parseWorkbench(' '.repeat(LIMITS.stateCharacters + 1));
  assert.equal(over.ok, false);
  assert.match(over.issues[0].message, /budget/);
  const h = harness();
  assert.equal(V.parseWorkbench(JSON.stringify(h.state)).ok, true);
});

test('collection limits reject oversized arrays rather than silently truncating them', () => {
  const h = harness();
  h.project();
  const candidate = structuredClone(h.state);
  candidate.projects = Array.from({ length: LIMITS.projects + 1 }, (_, index) => ({ ...candidate.projects[0], id: `project-${index}` }));
  candidate.activeProjectId = candidate.projects[0].id;
  const result = V.validateWorkbench(candidate);
  assert.equal(result.ok, false);
  assert.ok(result.issues.some(issue => issue.path === 'projects'));
});

test('integrity detects missing and cross-project citations', () => {
  const { h, note } = linkedFixture();
  h.project({ title: 'Second' });
  const foreign = h.source();
  const candidate = structuredClone(h.state);
  candidate.notes.find(item => item.id === note).sourceIds = [foreign, 'missing'];
  const issues = inspectIntegrity(candidate);
  assert.ok(issues.some(issue => issue.message.includes('another project')));
  assert.ok(issues.some(issue => issue.message.includes('does not exist')));
});

test('integrity catches cycles in imported dependency graphs', () => {
  const { h, prerequisite, task } = linkedFixture();
  const candidate = structuredClone(h.state);
  candidate.tasks.find(item => item.id === prerequisite).dependencies = [task];
  assert.ok(inspectIntegrity(candidate).some(issue => issue.message.includes('cycle')));
});

test('integrity catches completion timestamps and unchecked completed tasks', () => {
  const h = harness();
  h.project();
  h.task();
  const candidate = structuredClone(h.state);
  candidate.tasks[0].status = 'done';
  candidate.tasks[0].checklist = [{ id: 'check', text: 'Still pending', done: false }];
  const issues = inspectIntegrity(candidate);
  assert.ok(issues.some(issue => issue.message.includes('completion timestamp')));
  assert.ok(issues.some(issue => issue.message.includes('unfinished checklist')));
});

test('integrity catches inconsistent suspended schedules and timestamps', () => {
  const h = harness();
  h.project();
  h.card();
  const candidate = structuredClone(h.state);
  candidate.cards[0].schedule.state = 'suspended';
  candidate.cards[0].schedule.repetitions = 5;
  candidate.cards[0].updatedAt = candidate.cards[0].createdAt - 1;
  const issues = inspectIntegrity(candidate);
  assert.ok(issues.some(issue => issue.message.includes('prior state')));
  assert.ok(issues.some(issue => issue.message.includes('last review')));
  assert.ok(issues.some(issue => issue.message.includes('precedes creation')));
});

test('integrity verifies prompt placeholder definitions rather than accepting unresolved variables', () => {
  const h = harness();
  h.project();
  h.prompt();
  const candidate = structuredClone(h.state);
  candidate.prompts[0].template = 'Explain {{concept}}';
  const issues = inspectIntegrity(candidate);
  assert.ok(issues.some(issue => issue.message.includes('concept')));
});
