const { test } = require('node:test');
const { assert, load, harness, linkedFixture } = require('./helpers.cjs');
const I = load('intake');
const E = load('exports');
const P = load('prompts');
const S = load('search');

test('CSV parser handles embedded commas, escaped quotes and multiline fields', () => {
  const input = 'title,description\r\n"Move, jump","Say ""hello""\r\nThen test"\r\nCamera,Follow';
  const table = I.parseDelimited(input);
  assert.deepEqual(table.rows, [
    ['title', 'description'],
    ['Move, jump', 'Say "hello"\nThen test'],
    ['Camera', 'Follow'],
  ]);
  assert.deepEqual(table.rowLines, [1, 2, 4]);
});

test('CSV parser accepts BOM, trailing empty cells and blank lines', () => {
  const table = I.parseDelimited('\uFEFFtitle,description\n\nMove,\n,\nCamera,""');
  assert.deepEqual(table.rows, [
    ['title', 'description'],
    ['Move', ''],
    ['Camera', ''],
  ]);
  assert.deepEqual(table.rowLines, [1, 3, 5]);
});

test('malformed quoting produces line-specific errors', () => {
  assert.throws(() => I.parseDelimited('title\n"unclosed'), /Line 2.*not closed/);
  assert.throws(() => I.parseDelimited('title\n"closed"oops'), /Line 2.*unexpected/);
  assert.throws(() => I.parseDelimited('"' + 'x'.repeat(30001) + '"'), /cell is too long/);
});

test('delimited imports enforce row, column and input limits', () => {
  assert.throws(() => I.parseDelimited(Array(31).fill('column').join(',')), /columns/);
  assert.throws(() => I.parseDelimited(Array(502).fill('row').join('\n')), /500 data rows/);
  assert.throws(() => I.parseDelimited('x'.repeat(500001)), /500,000/);
});

test('task CSV preview reports invalid fields together and imports nothing partially', () => {
  const input = 'title,status,priority,estimate,due_date\nMove,unknown,critical,-2,2026-02-30\nCamera,ready,high,20,2026-10-01';
  const preview = I.previewTaskTable(input, 'project');
  assert.equal(preview.valid, 1);
  assert.equal(preview.invalid, 1);
  assert.equal(preview.rows[0].errors.length, 4);
  assert.throws(() => I.validIntakeValues(preview), /No partial import/);
});

test('task CSV accepts friendly headers and reports duplicate titles and ignored dependencies', () => {
  const input = 'Title,Estimate Minutes,Due Date,Tags,Dependencies\nMove,30,2026-10-01,Physics,Setup\nmove,15,,UI,';
  const preview = I.previewTaskTable(input, 'project');
  assert.equal(preview.invalid, 0);
  assert.equal(preview.rows[0].value.estimateMinutes, 30);
  assert.deepEqual(preview.rows[0].value.tags, ['physics']);
  assert.match(preview.rows[0].warnings[0], /Dependencies/);
  assert.match(preview.rows[1].warnings[0], /same title/);
  assert.equal(I.validIntakeValues(preview).length, 2);
});

test('CSV headers must be unique and contain required columns', () => {
  assert.throws(() => I.previewTaskTable('name\nTask', 'p'), /title/);
  assert.throws(() => I.previewTaskTable('title,Title\nTask,Task', 'p'), /unique/);
  const excess = I.previewTaskTable('title\nTask,extra', 'p');
  assert.equal(excess.invalid, 1);
  assert.match(excess.rows[0].errors[0], /more cells/);
});

test('card TSV preserves multiline answers and starts imported cards without scheduling data', () => {
  const input = 'question\tanswer\thint\tstate\nWhat is velocity?\t"Rate of position change.\nIncludes direction."\tVector\treview';
  const preview = I.previewCardTable(input, 'project');
  assert.equal(preview.invalid, 0);
  const card = preview.rows[0].value;
  assert.match(card.answer, /\nIncludes direction/);
  assert.equal(card.schedule, undefined);
  assert.match(preview.rows[0].warnings[0], /Scheduling fields are ignored/);
});

test('empty answers and oversized questions fail card import validation', () => {
  const empty = I.previewCardTable('question\tanswer\nQuestion?\t', 'p');
  assert.equal(empty.invalid, 1);
  const large = I.previewCardTable(`question\tanswer\n${'q'.repeat(2001)}\tAnswer`, 'p');
  assert.equal(large.invalid, 1);
});

test('Markdown task import recognizes checkboxes and numbered lists', () => {
  const preview = I.previewMarkdownTasks('# Plan\n- [ ] Move\n* [x] Setup\n1. Camera\n2) Test\nPlain paragraph', 'p');
  assert.equal(preview.valid, 4);
  assert.deepEqual(preview.rows.map(row => row.value.status), ['inbox', 'done', 'inbox', 'inbox']);
  assert.deepEqual(preview.rows.map(row => row.line), [2, 3, 4, 5]);
  assert.ok(preview.rows.every(row => row.value.estimateMinutes === 0));
});

test('Markdown note import does not split headings inside fenced code', () => {
  const input = '# First\nDescription\n```python\n# a comment\nprint(1)\n```\n## Second\nMore text';
  const preview = I.previewMarkdownNotes(input, 'p');
  assert.equal(preview.valid, 2);
  assert.equal(preview.rows[0].value.title, 'First');
  assert.match(preview.rows[0].value.body, /# a comment/);
  assert.equal(preview.rows[1].value.title, 'Second');
  assert.ok(preview.rows.every(row => row.value.confidence === 'unverified'));
});

test('heading-free notes get a sensible title and empty sections get warnings', () => {
  const plain = I.previewMarkdownNotes('A useful observation.', 'p');
  assert.equal(plain.rows[0].value.title, 'Imported notes');
  assert.equal(plain.rows[0].value.body, 'A useful observation.');
  const empty = I.previewMarkdownNotes('# Empty\n# Full\nContent', 'p');
  assert.equal(empty.valid, 2);
  assert.equal(empty.rows[0].warnings.length, 1);
});

test('CSV exports neutralize spreadsheet formulas and quote embedded delimiters', () => {
  for (const input of ['=SUM(1,2)', '+cmd', '-1+2', '@formula', '  =formula', '\tformula', '\rformula']) {
    assert.ok(E.csvCell(input).startsWith('"\''), JSON.stringify(input));
  }
  assert.equal(E.csvCell('say "hello", now'), '"say ""hello"", now"');
  assert.equal(E.csvCell(null), '""');
  assert.equal(E.csvCell(25), '"25"');
});

test('task CSV resolves project and dependency names without leaking unrelated data', () => {
  const { h } = linkedFixture();
  const csv = E.tasksCsv(h.state.tasks, h.state.projects);
  const table = I.parseDelimited(csv);
  assert.equal(table.rows.length, 3);
  assert.equal(table.rows[1][0], 'Orbital garden');
  assert.equal(table.rows[2][7], 'Create scene');
  assert.ok(!csv.includes('Shared review'));
});

test('note Markdown includes only selected citations and explicit confidence', () => {
  const { h, note } = linkedFixture();
  h.source({ title: 'Unrelated reference' });
  const markdown = E.noteMarkdown(h.record('notes', note), h.state.sources);
  assert.match(markdown, /Confidence: supported/);
  assert.match(markdown, /Physics reference/);
  assert.ok(!markdown.includes('Unrelated reference'));
});

test('project report excludes archived notes and another project', () => {
  const { h, project, note } = linkedFixture();
  h.update('note', note, { archived: true });
  h.project({ title: 'Other project secret' });
  h.note({ title: 'Secret note' });
  const markdown = E.projectMarkdown(h.state, project, h.now);
  assert.match(markdown, /Orbital garden/);
  assert.ok(!markdown.includes('Secret note'));
  assert.ok(!markdown.includes('## Movement experiment'));
  assert.throws(() => E.projectMarkdown(h.state, 'missing', h.now), /exist/);
});

test('template variables are unique and inferred definitions preserve edited metadata', () => {
  const original = { key: 'concept', label: 'Learning target', description: 'Pick one', defaultValue: 'vectors', required: false };
  const variables = P.inferVariables('{{concept}} then {{engine}} and {{concept}}', [original]);
  assert.equal(variables.length, 2);
  assert.deepEqual(variables[0], original);
  assert.equal(variables[1].key, 'engine');
  assert.equal(variables[1].required, true);
});

test('prompt interpolation uses a single pass and never interprets inserted placeholders', () => {
  const template = 'Explain {{concept}} using {{engine}}.';
  const prompt = { template, variables: P.inferVariables(template) };
  const result = P.renderPrompt(prompt, { concept: '{{engine}}', engine: 'Godot', unused: 'extra' });
  assert.equal(result.text, 'Explain {{engine}} using Godot.');
  assert.deepEqual(result.used, ['concept', 'engine']);
  assert.deepEqual(result.unused, ['unused']);
  assert.deepEqual(result.missing, []);
});

test('required empty values remain visible as unresolved placeholders', () => {
  const template = '{{concept}} and {{concept}}';
  const result = P.renderPrompt({ template, variables: P.inferVariables(template) }, { concept: ' ' });
  assert.deepEqual(result.missing, ['concept']);
  assert.equal(result.text, template);
  assert.equal(result.used.length, 0);
});

test('inherited object properties are never treated as user prompt values', () => {
  const template = '{{constructor}}';
  const variables = P.inferVariables(template);
  variables[0].defaultValue = 'Default constructor';
  const values = Object.create({ constructor: 'Inherited content' });
  const result = P.renderPrompt({ template, variables }, values);
  assert.equal(result.text, 'Default constructor');
});

test('rendered prompt limits account for repeated interpolation expansion', () => {
  const template = Array(10).fill('{{concept}}').join('\n');
  assert.throws(() => P.renderPrompt({ template, variables: P.inferVariables(template) }, { concept: 'x'.repeat(2000) }), /message limit/);
  assert.throws(() => P.renderPrompt({ template: '{{concept}}', variables: P.inferVariables('{{concept}}') }, { concept: 'x'.repeat(2001) }));
});

test('every bundled prompt validates through the same domain rules as user prompts', () => {
  const h = harness();
  h.project();
  const titles = new Set();
  for (const input of P.BUILTIN_PROMPTS) {
    h.prompt(input);
    assert.ok(!titles.has(input.title));
    titles.add(input.title);
    const values = Object.fromEntries(input.variables.map(variable => [variable.key, 'Example input']));
    const result = P.renderPrompt(input, values);
    assert.deepEqual(result.missing, []);
    assert.ok(result.text.length > 50);
  }
  assert.equal(h.state.prompts.length, P.BUILTIN_PROMPTS.length);
});

test('search parses phrases, negative terms and field filters', () => {
  const query = S.parseQuery('"camera follow" -jitter tag:physics type:note -status:archived');
  assert.equal(query.tokens.length, 5);
  assert.equal(query.tokens[0].phrase, true);
  assert.equal(query.tokens[0].value, 'camera follow');
  assert.equal(query.tokens[1].negative, true);
  assert.equal(query.tokens[2].field, 'tag');
  assert.equal(query.tokens[4].negative, true);
});

test('search requires all positive terms and excludes matching negative terms', () => {
  const h = harness();
  h.project();
  const wanted = h.note({ title: 'Camera follow', body: 'Smooth spring behavior', tags: ['camera'] });
  h.note({ title: 'Camera follow jitter', body: 'Investigate noise', tags: ['camera'] });
  h.note({ title: 'Lighting', body: 'Smooth shadows' });
  const result = S.searchWorkbench(h.state, '"camera follow" -jitter type:note tag:camera');
  assert.deepEqual(result.hits.map(hit => hit.id), [wanted]);
  assert.equal(result.byKind.note, 1);
});

test('search normalizes accents and ranks exact titles above body-only matches', () => {
  const h = harness();
  h.project();
  const exact = h.note({ title: 'Café', body: 'A location' });
  h.note({ title: 'Scene notes', body: 'Place the player in a cafe.' });
  const result = S.searchWorkbench(h.state, 'cafe', { kinds: ['note'] });
  assert.equal(result.total, 2);
  assert.equal(result.hits[0].id, exact);
});

test('project-scoped search includes shared prompts but excludes other projects', () => {
  const { h, project, globalPrompt } = linkedFixture();
  const second = h.project({ title: 'Other' });
  h.note({ title: 'Other note' });
  const result = S.searchWorkbench(h.state, '', { projectId: project, limit: 200 });
  assert.ok(result.hits.some(hit => hit.id === globalPrompt));
  assert.ok(result.hits.every(hit => hit.projectId !== second));
});

test('archived project contents and archived notes require explicit search inclusion', () => {
  const { h, project, note } = linkedFixture();
  h.update('note', note, { archived: true });
  assert.ok(!S.searchWorkbench(h.state, '').hits.some(hit => hit.id === note));
  assert.ok(S.searchWorkbench(h.state, '', { includeArchived: true }).hits.some(hit => hit.id === note));
  h.update('project', project, { status: 'archived' });
  assert.ok(S.searchWorkbench(h.state, '').hits.every(hit => hit.projectId !== project));
});

test('search pagination retains total counts and stable title ordering', () => {
  const h = harness();
  h.project();
  for (const title of ['Delta', 'Alpha', 'Charlie', 'Bravo']) h.note({ title });
  const first = S.searchWorkbench(h.state, 'type:note', { limit: 2, sort: 'title' });
  const second = S.searchWorkbench(h.state, 'type:note', { limit: 2, offset: 2, sort: 'title' });
  assert.equal(first.total, 4);
  assert.equal(second.total, 4);
  assert.deepEqual(first.hits.map(hit => hit.title), ['Alpha', 'Bravo']);
  assert.deepEqual(second.hits.map(hit => hit.title), ['Charlie', 'Delta']);
});

test('search query and excerpt budgets remain bounded on large input', () => {
  assert.ok(S.parseQuery('term '.repeat(300)).warnings.length);
  assert.equal(S.parseQuery('term '.repeat(100)).tokens.length, 30);
  const excerpt = S.searchExcerpt('prefix '.repeat(80) + 'needle' + ' suffix'.repeat(80), ['needle'], 120);
  assert.ok(excerpt.includes('needle'));
  assert.ok(excerpt.length <= 122);
  assert.ok(excerpt.startsWith('…'));
});
