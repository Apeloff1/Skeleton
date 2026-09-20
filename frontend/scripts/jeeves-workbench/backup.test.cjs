const { test } = require('node:test');
const { assert, load, harness, linkedFixture, assertValid } = require('./helpers.cjs');
const B = load('backup');
const { LIMITS } = load('types');

test('a full backup round-trips all linked records without changing the original', () => {
  const { h, card } = linkedFixture();
  h.review(card);
  const before = JSON.stringify(h.state);
  const raw = B.encodeBackup(h.state, h.now);
  const preview = B.previewBackup(raw);
  assert.equal(preview.ok, true);
  assert.deepEqual(preview.value.imported, h.state);
  assert.equal(preview.value.counts.review, 1);
  assert.equal(preview.value.counts.task, 2);
  assert.equal(JSON.stringify(h.state), before);
});

test('project backups contain only that project and no shared prompts', () => {
  const { h, project, globalPrompt } = linkedFixture();
  const second = h.project({ title: 'Second' });
  h.task({ title: 'Private to second' });
  const exported = B.projectBackup(h.state, project);
  assertValid(exported);
  assert.deepEqual(exported.projects.map(item => item.id), [project]);
  assert.equal(exported.tasks.length, 2);
  assert.equal(exported.prompts.length, 1);
  assert.ok(exported.prompts.every(item => item.id !== globalPrompt));
  assert.ok(exported.events.every(item => item.projectId !== second));
  assert.equal(exported.activeProjectId, project);
});

test('backup preview rejects invalid envelope, schema and export timestamp', () => {
  const h = harness();
  const envelope = B.backupEnvelope(h.state, h.now);
  for (const candidate of [
    null,
    { ...envelope, format: 'other-app' },
    { ...envelope, version: 2 },
    { ...envelope, exportedAt: -1 },
    { ...envelope, exportedAt: 'yesterday' },
    { ...envelope, workspace: { ...h.state, version: 10 } },
  ]) {
    assert.equal(B.previewBackup(JSON.stringify(candidate)).ok, false);
  }
  assert.equal(B.previewBackup('{bad').ok, false);
});

test('declared record counts are advisory and validated content determines the preview', () => {
  const { h } = linkedFixture();
  const envelope = B.backupEnvelope(h.state, h.now);
  envelope.recordCount = 999;
  const preview = B.previewBackup(JSON.stringify(envelope));
  assert.equal(preview.ok, true);
  assert.equal(preview.value.counts.project, 1);
  assert.ok(preview.value.warnings.some(item => item.includes('record count')));
});

test('broken imported relationships fail before a merge can be offered', () => {
  const { h } = linkedFixture();
  const envelope = B.backupEnvelope(structuredClone(h.state), h.now);
  envelope.workspace.cards[0].noteId = 'missing-note';
  const preview = B.previewBackup(JSON.stringify(envelope));
  assert.equal(preview.ok, false);
  assert.ok(preview.issues.some(issue => issue.message.includes('does not exist')));
});

test('merge remaps every dependency and citation into the imported project', () => {
  const { h: incoming } = linkedFixture('incoming');
  const { h: current } = linkedFixture('current');
  const before = JSON.stringify(current.state);
  const merged = B.mergeBackup(current.state, incoming.state, current.context());
  assertValid(merged);
  const project = merged.projects.find(item => item.id !== current.state.projects[0].id);
  const importedTasks = merged.tasks.filter(item => item.projectId === project.id);
  const movement = importedTasks.find(item => item.title === 'Build movement');
  const prerequisite = importedTasks.find(item => item.title === 'Create scene');
  const note = merged.notes.find(item => item.projectId === project.id && item.title === 'Movement experiment');
  const source = merged.sources.find(item => item.projectId === project.id);
  const card = merged.cards.find(item => item.projectId === project.id);
  assert.deepEqual(movement.dependencies, [prerequisite.id]);
  assert.deepEqual(movement.noteIds, [note.id]);
  assert.deepEqual(note.sourceIds, [source.id]);
  assert.equal(card.noteId, note.id);
  assert.deepEqual(card.sourceIds, [source.id]);
  assert.match(project.title, /imported/);
  assert.equal(merged.activeProjectId, current.state.activeProjectId);
  assert.equal(JSON.stringify(current.state), before);
});

test('merging a backup into its source duplicates records safely without ID collisions', () => {
  const { h, card } = linkedFixture();
  h.review(card);
  const merged = B.mergeBackup(h.state, h.state, h.context());
  assertValid(merged);
  assert.equal(merged.projects.length, 2);
  assert.equal(merged.cards.length, 2);
  assert.equal(merged.reviews.length, 2);
  const ids = ['projects', 'tasks', 'notes', 'sources', 'cards', 'reviews', 'prompts', 'sessions', 'events'].flatMap(key => merged[key].map(item => item.id));
  assert.equal(new Set(ids).size, ids.length);
  const copiedReview = merged.reviews.find(item => item.id !== h.state.reviews[0].id);
  assert.notEqual(copiedReview.cardId, card);
});

test('merged shared prompts remain shared and existing preferences win', () => {
  const { h: incoming } = linkedFixture('incoming');
  const current = harness('current');
  current.run({ type: 'preferences.update', patch: { focusMinutes: 40, dailyNewCards: 3 } });
  const merged = B.mergeBackup(current.state, incoming.state, current.context());
  assert.equal(merged.prompts.filter(item => item.projectId === null).length, 1);
  assert.equal(merged.preferences.focusMinutes, 40);
  assert.equal(merged.preferences.dailyNewCards, 3);
  assert.ok(merged.activeProjectId);
});

test('running imported timers are closed at their last evidenced timestamp', () => {
  const incoming = harness('incoming');
  const projectId = incoming.project();
  const id = incoming.run({ type: 'focus.start', projectId, taskId: null, minutes: 25 });
  incoming.advance(5 * 60000);
  incoming.run({ type: 'focus.pause', id });
  const preview = B.previewBackup(B.encodeBackup(incoming.state, incoming.now));
  assert.equal(preview.ok, true);
  assert.ok(preview.value.warnings.some(item => item.includes('Running focus')));
  const current = harness('current');
  current.advance(600000);
  const merged = B.mergeBackup(current.state, incoming.state, current.context());
  assert.equal(merged.sessions[0].outcome, 'abandoned');
  assert.equal(merged.sessions[0].endedAt, incoming.now);
  assert.equal(merged.sessions[0].pausedAt, null);
  assertValid(merged);
});

test('an existing running timer remains running when importing another device backup', () => {
  const current = harness('current');
  const currentProject = current.project();
  const running = current.run({ type: 'focus.start', projectId: currentProject, taskId: null, minutes: 25 });
  const incoming = harness('incoming');
  const incomingProject = incoming.project();
  incoming.run({ type: 'focus.start', projectId: incomingProject, taskId: null, minutes: 25 });
  const merged = B.mergeBackup(current.state, incoming.state, current.context());
  assert.equal(merged.sessions.find(item => item.id === running).outcome, 'running');
  assert.equal(merged.sessions.filter(item => item.outcome === 'running').length, 1);
  assert.equal(merged.sessions.filter(item => item.outcome === 'abandoned').length, 1);
});

test('replacement keeps the local workspace identity while replacing project contents', () => {
  const current = harness('current');
  current.project({ title: 'Old project' });
  current.advance(10000);
  const { h: incoming } = linkedFixture('incoming');
  const replaced = B.replaceFromBackup(current.state, incoming.state, current.context());
  assert.equal(replaced.id, current.state.id);
  assert.equal(replaced.createdAt, current.state.createdAt);
  assert.equal(replaced.revision, current.state.revision + 1);
  assert.deepEqual(replaced.projects, incoming.state.projects);
  assert.deepEqual(replaced.preferences, incoming.state.preferences);
  assertValid(replaced);
});

test('merge refuses capacity overflow without truncating project records', () => {
  const current = harness('current');
  for (let index = 0; index < LIMITS.projects; index++) current.project({ title: `Project ${index}` });
  const incoming = harness('incoming');
  incoming.project();
  const before = JSON.stringify(current.state);
  assert.throws(() => B.mergeBackup(current.state, incoming.state, current.context()), /projects|limit/i);
  assert.equal(JSON.stringify(current.state), before);
});

test('a broken ID generator is bounded instead of looping forever', () => {
  const current = harness('current');
  const occupied = current.project();
  const incoming = harness('incoming');
  incoming.project();
  let calls = 0;
  assert.throws(() => B.mergeBackup(current.state, incoming.state, {
    now: current.now,
    id: () => { calls++; return occupied; },
  }), /unique import IDs/);
  assert.ok(calls <= 22);
});

test('backup byte limits count UTF-8 bytes instead of JavaScript characters', () => {
  const raw = '🌿'.repeat(Math.ceil(LIMITS.backupBytes / 4) + 1);
  assert.ok(raw.length < LIMITS.backupBytes);
  const result = B.previewBackup(raw);
  assert.equal(result.ok, false);
  assert.match(result.issues[0].message, /12 MB/);
});
