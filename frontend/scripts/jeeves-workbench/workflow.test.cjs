const { test } = require('node:test');
const { assert, load, harness, memoryStorage, assertValid } = require('./helpers.cjs');
const { WorkbenchStore } = load('WorkbenchStore');
const { captureMessage } = load('capture');
const { defaultContextSelection, makeHandoff } = load('context');
const { encodeBackup, previewBackup, mergeBackup } = load('backup');
const { weeklyReview, weeklyReviewMarkdown } = load('insights');
const { searchWorkbench } = load('search');
const { planSession } = load('planning');
const { WORKBENCH_KEY } = load('types');
const { MINUTE } = load('review');

test('a project can move from captured learning to planned work, review, backup and chat context', () => {
  const h = harness('workflow');
  const projectId = h.project({ title: 'Movement prototype', engine: 'Godot', weeklyMinutes: 90 });
  const capture = captureMessage(h.state, {
    projectId,
    title: 'Frame-independent movement',
    text: 'Multiply velocity by delta time when integrating position.',
    kind: 'reference',
    conversationId: 'chat-one',
    conversationTitle: 'Movement lesson',
    messageId: 'reply-one',
    role: 'assistant',
    model: null,
  }, h.context());
  h.replace(capture.state);
  const cardId = h.card({
    question: 'Why multiply velocity by delta time?',
    answer: 'To integrate position using elapsed time instead of frame count.',
    noteId: capture.noteId,
    sourceIds: [capture.sourceId],
  });
  const taskId = h.task({ title: 'Implement movement', estimateMinutes: 25, noteIds: [capture.noteId] });
  const testId = h.task({ title: 'Compare two frame rates', dependencies: [taskId], estimateMinutes: 15 });
  const plan = planSession(h.state.tasks, 40, h.now);
  assert.deepEqual(plan.items.map(item => item.task.id), [taskId, testId]);
  const focus = h.run({ type: 'focus.start', projectId, taskId, minutes: 25 });
  h.status(taskId, 'doing');
  h.advance(20 * MINUTE);
  h.run({ type: 'focus.finish', id: focus, outcome: 'completed', reflection: 'Movement implemented; comparison test next.' });
  h.status(taskId, 'done');
  h.review(cardId, 'good');
  const review = weeklyReview(h.state, projectId, h.now);
  assert.equal(review.current.completedTasks.length, 1);
  assert.equal(review.current.focusMinutes, 20);
  assert.equal(review.current.reviewCount, 1);
  assert.ok(review.readyTasks.some(task => task.id === testId));
  assert.ok(weeklyReviewMarkdown(review).includes('Movement implemented'));
  const hits = searchWorkbench(h.state, 'type:note delta');
  assert.equal(hits.hits[0].id, capture.noteId);
  const handoff = makeHandoff(h.state, defaultContextSelection(h.state, projectId), 'Help me compare movement at two frame rates.', h.context());
  assert.ok(handoff.context.includes('Compare two frame rates'));
  assert.ok(handoff.context.includes('Frame-independent movement'));
  assert.ok(handoff.context.includes('unverified'));
  const backup = previewBackup(encodeBackup(h.state, h.now));
  assert.equal(backup.ok, true);
  const otherDevice = harness('other-device');
  const imported = mergeBackup(otherDevice.state, backup.value.imported, otherDevice.context());
  assertValid(imported);
  assert.equal(imported.cards.length, 1);
  assert.equal(imported.reviews.length, 1);
  assert.equal(imported.sessions[0].reflection, 'Movement implemented; comparison test next.');
  assert.notEqual(imported.projects[0].id, projectId);
  const importedCard = imported.cards[0];
  assert.ok(imported.notes.some(note => note.id === importedCard.noteId));
});

test('a persisted workspace reopens with task links, study schedules and focus history intact', async () => {
  const h = harness('persisted');
  const projectId = h.project();
  const noteId = h.note();
  const taskId = h.task({ noteIds: [noteId] });
  const cardId = h.card({ noteId });
  h.review(cardId, 'easy');
  const focus = h.run({ type: 'focus.start', projectId, taskId, minutes: 10 });
  h.advance(10 * MINUTE);
  h.run({ type: 'focus.finish', id: focus, outcome: 'completed', reflection: 'First prototype complete.' });
  const disk = memoryStorage({ [WORKBENCH_KEY]: JSON.stringify(h.state) });
  const first = new WorkbenchStore(disk, h.clock);
  await first.initialize();
  const project = first.getSnapshot().state.projects[0];
  first.dispatch({ type: 'project.update', id: project.id, revision: project.revision, patch: { summary: 'Persist this summary.' } });
  await first.settled();
  const reopened = new WorkbenchStore(disk, h.clock);
  await reopened.initialize();
  const restored = reopened.getSnapshot().state;
  assert.equal(restored.projects[0].summary, 'Persist this summary.');
  assert.deepEqual(restored.tasks[0].noteIds, [noteId]);
  assert.deepEqual(restored.cards[0].schedule, h.state.cards[0].schedule);
  assert.equal(restored.sessions[0].reflection, 'First prototype complete.');
  assert.equal(restored.activeProjectId, projectId);
  assert.equal(reopened.getSnapshot().undoAvailable, false);
  assertValid(restored);
});
