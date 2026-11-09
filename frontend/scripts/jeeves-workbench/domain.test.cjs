const { test } = require('node:test');
const { assert, load, harness, linkedFixture, assertValid, NOW } = require('./helpers.cjs');
const { applyCommand } = load('domain');
const { LIMITS } = load('types');
const { projectDeletionImpact } = load('integrity');

test('creating a project normalizes tags and chooses it without changing earlier snapshots', () => {
  const h = harness();
  const original = h.state;
  const id = h.project({ title: '  Prototype  ', tags: ['Physics', ' physics ', ''] });
  assert.equal(original.projects.length, 0);
  assert.equal(h.state.activeProjectId, id);
  assert.equal(h.state.projects[0].title, 'Prototype');
  assert.deepEqual(h.state.projects[0].tags, ['physics']);
  assert.equal(h.state.projects[0].revision, 1);
  assert.equal(h.state.events[0].entityId, id);
});

test('a stale editor cannot replace a newer project edit', () => {
  const h = harness();
  const id = h.project();
  const stale = h.record('projects', id).revision;
  h.update('project', id, { goal: 'New goal' });
  assert.throws(() => h.run({ type: 'project.update', id, revision: stale, patch: { goal: 'Stale goal' } }), /changed while/);
  assert.equal(h.record('projects', id).goal, 'New goal');
});

test('task lifecycle records completion once and clears it when reopened', () => {
  const h = harness();
  h.project();
  const id = h.task();
  h.advance(1000);
  h.status(id, 'doing');
  h.advance(1000);
  h.status(id, 'done');
  const completed = h.record('tasks', id).completedAt;
  assert.equal(completed, NOW + 2000);
  h.advance(1000);
  h.status(id, 'done');
  assert.equal(h.record('tasks', id).completedAt, completed);
  h.status(id, 'ready');
  assert.equal(h.record('tasks', id).completedAt, null);
});

test('a checklist must be finished before its task can complete', () => {
  const h = harness();
  h.project();
  const id = h.task({ checklist: [{ id: 'check-one', text: 'Test controls', done: false }] });
  assert.throws(() => h.status(id, 'done'), /checklist/);
  const task = h.record('tasks', id);
  h.run({ type: 'task.check', id, revision: task.revision, itemId: 'check-one', done: true });
  h.status(id, 'done');
  assert.equal(h.record('tasks', id).status, 'done');
});

test('completed prerequisites block reopening until completed dependants reopen', () => {
  const { h, prerequisite, task } = linkedFixture();
  assert.throws(() => h.status(task, 'doing'), /dependencies/);
  h.status(prerequisite, 'done');
  h.status(task, 'done');
  assert.throws(() => h.status(prerequisite, 'ready'), /dependent/);
  assert.throws(() => h.update('task', prerequisite, { status: 'ready' }), /dependent/);
  h.status(task, 'ready');
  h.status(prerequisite, 'ready');
  assert.equal(h.record('tasks', prerequisite).completedAt, null);
});

test('task edits cannot create a dependency cycle', () => {
  const { h, prerequisite, task } = linkedFixture();
  const before = JSON.stringify(h.state);
  assert.throws(() => h.update('task', prerequisite, { dependencies: [task] }), /cycle/i);
  assert.equal(JSON.stringify(h.state), before);
});

test('dependencies cannot point across projects or to missing tasks', () => {
  const h = harness();
  h.project();
  const first = h.task();
  h.project({ title: 'Another project' });
  assert.throws(() => h.task({ dependencies: [first] }), /project/i);
  assert.throws(() => h.task({ dependencies: ['missing-task'] }), /exist|missing/i);
  assert.equal(h.state.tasks.length, 1);
});

test('deleting a referenced prerequisite is blocked instead of dropping its dependency', () => {
  const { h, prerequisite, task } = linkedFixture();
  assert.throws(() => h.remove('task', prerequisite), /depend/i);
  h.remove('task', task);
  h.remove('task', prerequisite);
  assert.equal(h.state.tasks.length, 0);
});

test('task reorder requires exactly the project task set', () => {
  const h = harness();
  const projectId = h.project();
  const first = h.task({ title: 'First' });
  const second = h.task({ title: 'Second' });
  assert.throws(() => h.run({ type: 'task.reorder', projectId, ids: [first] }));
  assert.throws(() => h.run({ type: 'task.reorder', projectId, ids: [first, first] }));
  h.run({ type: 'task.reorder', projectId, ids: [second, first] });
  assert.equal(h.record('tasks', second).order, 0);
  assert.equal(h.record('tasks', first).order, 1);
});

test('batch status changes reject the complete batch when one task is blocked', () => {
  const { h, task } = linkedFixture();
  const independent = h.task({ title: 'Independent' });
  const before = JSON.stringify(h.state);
  assert.throws(() => h.run({ type: 'task.batch-status', ids: [independent, task], status: 'done' }), /dependencies/i);
  assert.equal(JSON.stringify(h.state), before);
});

test('source deletion removes citations from notes and cards and increments affected revisions', () => {
  const { h, source, note, card } = linkedFixture();
  const oldNote = h.record('notes', note);
  const oldCard = h.record('cards', card);
  h.remove('source', source);
  assert.deepEqual(h.record('notes', note).sourceIds, []);
  assert.deepEqual(h.record('cards', card).sourceIds, []);
  assert.ok(h.record('notes', note).revision > oldNote.revision);
  assert.ok(h.record('cards', card).revision > oldCard.revision);
  assert.deepEqual(oldNote.sourceIds, [source]);
});

test('note deletion clears task, card and related-note links', () => {
  const { h, note, task, card, related } = linkedFixture();
  h.remove('note', note);
  assert.deepEqual(h.record('tasks', task).noteIds, []);
  assert.equal(h.record('cards', card).noteId, null);
  assert.deepEqual(h.record('notes', related).relatedNoteIds, []);
  assert.equal(h.state.sources.length, 1);
});

test('self-linked notes and duplicate checklist IDs are rejected', () => {
  const h = harness();
  h.project();
  const id = h.note();
  assert.throws(() => h.update('note', id, { relatedNoteIds: [id] }), /itself/);
  assert.throws(() => h.task({ checklist: [
    { id: 'same', text: 'One', done: false },
    { id: 'same', text: 'Two', done: false },
  ] }), /unique/);
});

test('cards retain content when suspended, resumed and reset', () => {
  const h = harness();
  h.project();
  const id = h.card();
  h.review(id, 'easy');
  let card = h.record('cards', id);
  h.run({ type: 'card.suspend', id, revision: card.revision, suspended: true });
  assert.throws(() => h.review(id), /Resume/);
  card = h.record('cards', id);
  h.run({ type: 'card.suspend', id, revision: card.revision, suspended: false });
  assert.equal(h.record('cards', id).schedule.state, 'review');
  card = h.record('cards', id);
  h.run({ type: 'card.reset', id, revision: card.revision });
  assert.equal(h.record('cards', id).schedule.state, 'new');
  assert.equal(h.record('cards', id).answer, card.answer);
});

test('double grading from the same revision is rejected', () => {
  const h = harness();
  h.project();
  const id = h.card();
  const revision = h.record('cards', id).revision;
  h.run({ type: 'card.review', id, revision, grade: 'good', durationMs: 1000 });
  assert.throws(() => h.run({ type: 'card.review', id, revision, grade: 'good', durationMs: 1000 }), /changed while/);
  assert.equal(h.state.reviews.length, 1);
});

test('undo review restores the exact previous schedule and removes its history row', () => {
  const h = harness();
  h.project();
  const id = h.card();
  const schedule = h.record('cards', id).schedule;
  h.review(id, 'easy');
  const review = h.state.reviews[0];
  h.run({ type: 'card.undo-review', reviewId: review.id });
  assert.deepEqual(h.record('cards', id).schedule, schedule);
  assert.equal(h.state.reviews.length, 0);
});

test('an older review cannot undo a more recent grade', () => {
  const h = harness();
  h.project();
  const id = h.card();
  h.review(id);
  const previous = h.state.reviews[0].id;
  h.advance(600000);
  h.review(id);
  assert.throws(() => h.run({ type: 'card.undo-review', reviewId: previous }), /latest|recent/i);
  assert.equal(h.state.reviews.length, 2);
});

test('deleting a card removes its reviews without removing its source note', () => {
  const { h, card, note } = linkedFixture();
  h.review(card);
  h.remove('card', card);
  assert.equal(h.state.reviews.length, 0);
  assert.ok(h.record('notes', note));
});

test('archived projects allow restoration but reject new and edited records', () => {
  const { h, project, task, note, card, source } = linkedFixture();
  h.update('project', project, { status: 'archived' });
  assert.throws(() => h.task(), /archived/);
  assert.throws(() => h.note(), /archived/);
  assert.throws(() => h.card(), /archived/);
  assert.throws(() => h.update('task', task, { title: 'Changed' }), /archived/);
  assert.throws(() => h.update('note', note, { body: 'Changed' }), /archived/);
  assert.throws(() => h.update('source', source, { title: 'Changed' }), /archived/);
  assert.throws(() => h.review(card), /archived/);
  h.update('project', project, { status: 'active' });
  h.task({ title: 'New task after restoration' });
  assert.equal(h.state.tasks.length, 3);
});

test('project cascade removes owned records and preserves shared prompts and another project', () => {
  const { h, project, card, globalPrompt } = linkedFixture();
  h.review(card);
  const other = h.project({ title: 'Keep me' });
  const otherTask = h.task();
  const impact = projectDeletionImpact(h.state, project);
  assert.equal(impact.tasks, 2);
  assert.equal(impact.reviews, 1);
  h.remove('project', project);
  assert.deepEqual(h.state.projects.map(item => item.id), [other]);
  assert.deepEqual(h.state.tasks.map(item => item.id), [otherTask]);
  assert.deepEqual(h.state.prompts.map(item => item.id), [globalPrompt]);
  assert.equal(h.state.notes.length, 0);
  assert.equal(h.state.reviews.length, 0);
  assert.ok(h.state.events.every(item => item.projectId !== project));
});

test('project limits fail before inserting a record', () => {
  const h = harness();
  for (let index = 0; index < LIMITS.projects; index++) h.project({ title: `Project ${index}` });
  const before = JSON.stringify(h.state);
  assert.throws(() => h.project(), /limit reached/);
  assert.equal(JSON.stringify(h.state), before);
});

test('invalid preferences do not partially apply valid fields', () => {
  const h = harness();
  const original = h.state.preferences;
  assert.throws(() => h.run({ type: 'preferences.update', patch: { focusMinutes: 30, dailyReviewCards: 0 } }));
  assert.deepEqual(h.state.preferences, original);
  h.run({ type: 'preferences.update', patch: { focusMinutes: 30, dailyNewCards: 0 } });
  assert.equal(h.state.preferences.focusMinutes, 30);
  assert.equal(h.state.preferences.dailyNewCards, 0);
});

test('randomized task updates preserve immutable states and graph invariants', () => {
  const h = harness('random');
  h.project();
  let seed = 731;
  const random = max => {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    return (seed >>> 8) % max;
  };
  for (let step = 0; step < 120; step++) {
    if (!h.state.tasks.length || random(4) === 0) {
      h.task({ title: `Task ${step}`, estimateMinutes: random(90) });
    } else {
      const task = h.state.tasks[random(h.state.tasks.length)];
      const operation = random(3);
      if (operation === 0) h.update('task', task.id, { priority: ['low', 'normal', 'high', 'urgent'][random(4)] });
      else if (operation === 1) h.status(task.id, ['inbox', 'ready', 'doing', 'done', 'cancelled'][random(5)]);
      else h.update('task', task.id, { description: `Observation ${step}`, tags: [`tag-${random(5)}`] });
    }
    h.advance(1000);
    assertValid(h.state);
  }
  assert.equal(h.state.revision, 121);
  assert.ok(h.state.tasks.length > 10);
});

test('unrecognized runtime commands cannot silently create revisions', () => {
  const h = harness();
  assert.throws(() => applyCommand(h.state, { type: 'not-a-command' }, h.context()));
});
