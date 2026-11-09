const { test } = require('node:test');
const { assert, load, linkedFixture, harness, NOW } = require('./helpers.cjs');
const C = load('context');

test('default context selects active work and citations from selected notes', () => {
  const { h, project, note, source } = linkedFixture();
  const selection = C.defaultContextSelection(h.state, project);
  assert.equal(selection.projectId, project);
  assert.equal(selection.maxCharacters, 4000);
  assert.ok(selection.noteIds.includes(note));
  assert.ok(selection.sourceIds.includes(source));
  const bundle = C.buildContext(h.state, selection);
  assert.match(bundle.text, /USER PROJECT MATERIAL/);
  assert.match(bundle.text, /confidence: supported/);
  assert.ok(bundle.characters <= 4000);
});

test('context excludes archived notes and completed tasks unless enabled', () => {
  const { h, project, note, prerequisite } = linkedFixture();
  h.update('note', note, { archived: true });
  h.status(prerequisite, 'done');
  let selection = C.defaultContextSelection(h.state, project);
  assert.ok(!selection.noteIds.includes(note));
  assert.ok(!selection.taskIds.includes(prerequisite));
  h.run({ type: 'preferences.update', patch: { includeCompletedTasks: true, includeSourcesInContext: false } });
  selection = C.defaultContextSelection(h.state, project);
  assert.ok(selection.taskIds.includes(prerequisite));
  assert.deepEqual(selection.sourceIds, []);
});

test('foreign and missing IDs are omitted with explicit reasons', () => {
  const { h, project } = linkedFixture();
  h.project({ title: 'Private second project' });
  const foreignNote = h.note({ body: 'Do not include this body.' });
  const selection = { ...C.defaultContextSelection(h.state, project), noteIds: [foreignNote, 'missing'] };
  const bundle = C.buildContext(h.state, selection);
  assert.equal(bundle.omitted.length, 2);
  assert.ok(!bundle.text.includes('Do not include this body'));
});

test('context budget is respected for every allowed budget and long selected content', () => {
  const h = harness();
  const project = h.project({ context: 'Background '.repeat(500) });
  const notes = [];
  for (let index = 0; index < 8; index++) notes.push(h.note({ title: `Note ${index}`, body: 'Evidence '.repeat(1000) }));
  for (const maxCharacters of [200, 201, 300, 1000, 2000, 4000]) {
    const bundle = C.buildContext(h.state, { projectId: project, includeProject: true, taskIds: [], sourceIds: [], noteIds: notes, maxCharacters });
    assert.ok(bundle.characters <= maxCharacters);
    assert.equal(bundle.characters, bundle.text.length);
    assert.ok(bundle.sections.some(section => section.truncated) || bundle.omitted.length);
  }
});

test('empty context selections produce an empty context string', () => {
  const { h, project } = linkedFixture();
  const bundle = C.buildContext(h.state, { projectId: project, includeProject: false, taskIds: [], sourceIds: [], noteIds: [], maxCharacters: 4000 });
  assert.equal(bundle.text, '');
  assert.equal(bundle.characters, 0);
  assert.deepEqual(bundle.sections, []);
});

test('context de-duplicates selected record IDs', () => {
  const { h, project, note } = linkedFixture();
  const selection = { ...C.defaultContextSelection(h.state, project), noteIds: [note, note, note] };
  const bundle = C.buildContext(h.state, selection);
  assert.equal(bundle.sections.filter(section => section.id === note).length, 1);
});

test('handoff round-trips with a bounded draft and explicit source labels', () => {
  const { h, project } = linkedFixture();
  const handoff = C.makeHandoff(h.state, C.defaultContextSelection(h.state, project), 'Help with the next task.', h.context());
  assert.equal(handoff.projectId, project);
  assert.equal(handoff.draft, 'Help with the next task.');
  assert.ok(handoff.sourceLabels.length);
  assert.deepEqual(C.parseHandoff(JSON.stringify(handoff), h.now), handoff);
});

test('expired, future and malformed handoffs are rejected', () => {
  const { h, project } = linkedFixture();
  const value = C.makeHandoff(h.state, C.defaultContextSelection(h.state, project), 'Question', h.context());
  const encode = patch => JSON.stringify({ ...value, ...patch });
  assert.equal(C.parseHandoff(encode({}), NOW + 30 * 60000 + 1), null);
  assert.equal(C.parseHandoff(encode({}), NOW - 1), null);
  assert.equal(C.parseHandoff(encode({ version: 2 }), NOW), null);
  assert.equal(C.parseHandoff(encode({ context: 'x'.repeat(4001) }), NOW), null);
  assert.equal(C.parseHandoff(encode({ draft: '' }), NOW), null);
  assert.equal(C.parseHandoff(encode({ id: '../invalid' }), NOW), null);
  assert.equal(C.parseHandoff(encode({ sourceLabels: [42] }), NOW), null);
  assert.equal(C.parseHandoff('{bad', NOW), null);
});

test('handoff creation rejects missing projects and overlong messages', () => {
  const { h, project } = linkedFixture();
  const selection = C.defaultContextSelection(h.state, project);
  assert.throws(() => C.makeHandoff(h.state, selection, 'x'.repeat(16001), h.context()));
  assert.throws(() => C.makeHandoff(h.state, { ...selection, projectId: 'missing' }, 'Question', h.context()), /exist/);
  assert.throws(() => C.buildContext(h.state, { ...selection, maxCharacters: 4001 }));
});
