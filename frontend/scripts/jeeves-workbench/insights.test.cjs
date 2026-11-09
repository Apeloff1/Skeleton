const { test } = require('node:test');
const { assert, load, harness, linkedFixture, NOW } = require('./helpers.cjs');
const I = load('insights');
const { DAY, MINUTE, localDayKey } = load('review');

test('weekly windows honor Monday and Sunday start preferences', () => {
  const monday = I.weekWindow(NOW, 'monday');
  const sunday = I.weekWindow(NOW, 'sunday');
  assert.equal(localDayKey(monday.start), '2026-09-14');
  assert.equal(localDayKey(monday.end), '2026-09-21');
  assert.equal(localDayKey(sunday.start), '2026-09-20');
  assert.equal(localDayKey(sunday.end), '2026-09-27');
  assert.equal(monday.label, '2026-09-14 – 2026-09-20');
});

test('previous week windows are adjacent without overlap', () => {
  const current = I.weekWindow(NOW, 'monday');
  const previous = I.weekWindow(NOW, 'monday', -1);
  assert.equal(previous.end, current.start);
  assert.equal(localDayKey(previous.start), '2026-09-07');
});

test('weekly metrics include only the chosen project and completed session time', () => {
  const h = harness();
  const projectId = h.project();
  h.task({ status: 'done' });
  h.note();
  const completed = h.run({ type: 'focus.start', projectId, taskId: null, minutes: 20 });
  h.advance(20 * MINUTE);
  h.run({ type: 'focus.finish', id: completed, outcome: 'completed', reflection: 'Movement feels better.' });
  const abandoned = h.run({ type: 'focus.start', projectId, taskId: null, minutes: 10 });
  h.advance(5 * MINUTE);
  h.run({ type: 'focus.finish', id: abandoned, outcome: 'abandoned', reflection: 'Interrupted.' });
  h.project({ title: 'Other project' });
  h.task({ status: 'done' });
  const metrics = I.weekMetrics(h.state, projectId, I.weekWindow(h.now, 'monday'), h.now);
  assert.equal(metrics.completedTasks.length, 1);
  assert.equal(metrics.createdNotes.length, 1);
  assert.equal(metrics.focusMinutes, 20);
  assert.equal(metrics.completedSessions, 1);
  assert.equal(metrics.abandonedSessions, 1);
  assert.equal(metrics.reflections.length, 2);
});

test('weekly review counts distinct study cards separately from repeated answers', () => {
  const h = harness();
  const projectId = h.project();
  const first = h.card();
  const second = h.card();
  h.review(first, 'again');
  h.advance(MINUTE);
  h.review(first, 'good');
  h.review(second, 'easy');
  const metrics = I.weekMetrics(h.state, projectId, I.weekWindow(h.now, 'monday'), h.now);
  assert.equal(metrics.reviewCount, 3);
  assert.equal(metrics.reviewedCards, 2);
  assert.deepEqual(metrics.grades, { again: 1, hard: 0, good: 1, easy: 1 });
});

test('weekly metrics exclude future timestamps and use an exclusive end boundary', () => {
  const h = harness();
  const projectId = h.project();
  h.task({ status: 'done' });
  const window = I.weekWindow(h.now, 'monday');
  const candidate = structuredClone(h.state);
  candidate.tasks.push({ ...candidate.tasks[0], id: 'future', completedAt: h.now + MINUTE });
  candidate.tasks.push({ ...candidate.tasks[0], id: 'boundary', completedAt: window.end });
  assert.equal(I.weekMetrics(candidate, projectId, window, h.now).completedTasks.length, 1);
});

test('blocker chains expose unfinished transitive prerequisites', () => {
  const { h, prerequisite, task } = linkedFixture();
  const final = h.task({ title: 'Final integration', dependencies: [task] });
  const chains = I.blockerChains(h.state.tasks);
  const finalChain = chains.find(item => item.taskId === final);
  assert.deepEqual(new Set(finalChain.blockedBy), new Set([task, prerequisite]));
  assert.equal(chains.find(item => item.taskId === task).downstream, 1);
  h.status(prerequisite, 'done');
  const after = I.blockerChains(h.state.tasks).find(item => item.taskId === final);
  assert.deepEqual(after.blockedBy, [task]);
});

test('blocker traversal terminates on a malformed cyclic graph', () => {
  const { h, prerequisite, task } = linkedFixture();
  const tasks = structuredClone(h.state.tasks);
  tasks.find(item => item.id === prerequisite).dependencies = [task];
  const chains = I.blockerChains(tasks);
  assert.equal(chains.length, 2);
  assert.ok(chains.every(item => item.blockedBy.length <= 2));
});

test('blocker reports distinguish missing prerequisites and manual blocks', () => {
  const h = harness();
  h.project();
  const id = h.task({ status: 'blocked' });
  const tasks = structuredClone(h.state.tasks);
  tasks[0].dependencies = ['missing'];
  const report = I.blockerChains(tasks)[0];
  assert.equal(report.taskId, id);
  assert.equal(report.manual, true);
  assert.deepEqual(report.missing, ['missing']);
  assert.deepEqual(report.blockedBy, []);
});

test('evidence gaps distinguish unsupported claims, uncertainty and contradictions', () => {
  const h = harness();
  const projectId = h.project();
  const unsupported = h.note({ title: 'Claim', confidence: 'supported' });
  const unverified = h.note({ title: 'New idea', confidence: 'unverified' });
  const contradicted = h.note({ title: 'Old conclusion', confidence: 'contradicted' });
  const source = h.source();
  const supported = h.note({ title: 'Observed result', confidence: 'supported', sourceIds: [source] });
  const gaps = I.evidenceGaps(h.state, projectId, h.now);
  assert.equal(gaps.find(item => item.noteId === unsupported).reason, 'unsupported');
  assert.equal(gaps.find(item => item.noteId === unverified).reason, 'unverified');
  assert.equal(gaps.find(item => item.noteId === contradicted).reason, 'contradicted');
  assert.ok(!gaps.some(item => item.noteId === supported));
});

test('stale experiments are flagged after thirty days while archived notes stay excluded', () => {
  const h = harness();
  const projectId = h.project();
  const experiment = h.note({ kind: 'experiment', confidence: 'tentative' });
  h.note({ title: 'Archived uncertainty', archived: true, confidence: 'unverified' });
  assert.equal(I.evidenceGaps(h.state, projectId, h.now).length, 0);
  h.advance(31 * DAY);
  const gaps = I.evidenceGaps(h.state, projectId, h.now);
  assert.equal(gaps.length, 1);
  assert.equal(gaps[0].noteId, experiment);
  assert.equal(gaps[0].reason, 'stale');
});

test('weekly review compares prior activity while unresolved work stays current', () => {
  const h = harness();
  const projectId = h.project();
  h.task({ title: 'Last week done', status: 'done' });
  const stale = h.task({ title: 'Still waiting', dueDate: '2026-09-19' });
  h.advance(15 * DAY);
  const review = I.weeklyReview(h.state, projectId, h.now, -3);
  assert.equal(review.current.completedTasks.length, 1);
  assert.ok(review.overdueTasks.some(task => task.id === stale));
  assert.ok(review.staleTasks.some(task => task.id === stale));
  assert.equal(review.openTasks, 1);
  assert.ok(review.prompts.some(prompt => prompt.includes('overdue')));
});

test('uncited source detection includes citations from cards and archived notes', () => {
  const h = harness();
  const projectId = h.project();
  const cardSource = h.source({ title: 'Card source' });
  const noteSource = h.source({ title: 'Note source' });
  const unused = h.source({ title: 'Unused source' });
  h.card({ sourceIds: [cardSource] });
  h.note({ sourceIds: [noteSource], archived: true });
  const review = I.weeklyReview(h.state, projectId, h.now);
  assert.deepEqual(review.uncitedSources, [unused]);
});

test('weekly review rejects missing projects and invalid week offsets', () => {
  const h = harness();
  const projectId = h.project();
  assert.throws(() => I.weeklyReview(h.state, 'missing', h.now), /exist/);
  for (const offset of [1, -53, 1.5, NaN]) assert.throws(() => I.weeklyReview(h.state, projectId, h.now, offset));
});

test('weekly Markdown is self-contained and labels the limits of recorded activity', () => {
  const { h, project } = linkedFixture();
  const report = I.weeklyReviewMarkdown(I.weeklyReview(h.state, project, h.now));
  assert.match(report, /# Weekly review: Orbital garden/);
  assert.match(report, /Recorded activity/);
  assert.match(report, /Reflection questions/);
  assert.match(report, /Current unresolved work/);
  assert.match(report, /not measured retention/);
  assert.match(report, /2026-09-14/);
});
