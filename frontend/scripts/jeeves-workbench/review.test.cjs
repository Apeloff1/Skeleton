const { test } = require('node:test');
const { assert, load, harness, NOW } = require('./helpers.cjs');
const R = load('review');

test('new cards use the documented learning steps for each grade', () => {
  const initial = R.initialSchedule(NOW);
  const again = R.scheduleReview(initial, 'again', NOW);
  const hard = R.scheduleReview(initial, 'hard', NOW);
  const good = R.scheduleReview(initial, 'good', NOW);
  const easy = R.scheduleReview(initial, 'easy', NOW);
  assert.equal(again.dueAt, NOW + R.MINUTE);
  assert.equal(hard.dueAt, NOW + 6 * R.MINUTE);
  assert.equal(good.dueAt, NOW + 10 * R.MINUTE);
  assert.equal(good.learningStep, 1);
  assert.equal(easy.state, 'review');
  assert.equal(easy.intervalDays, 4);
  assert.equal(initial.repetitions, 0);
  assert.equal(initial.state, 'new');
});

test('two good learning answers graduate a new card to one day', () => {
  const first = R.scheduleReview(R.initialSchedule(NOW), 'good', NOW);
  const next = R.scheduleReview(first, 'good', first.dueAt);
  assert.equal(next.state, 'review');
  assert.equal(next.intervalDays, 1);
  assert.equal(next.repetitions, 2);
  assert.equal(next.dueAt, first.dueAt + R.DAY);
});

test('a failed mature review starts relearning and reduces its interval', () => {
  const mature = { ...R.initialSchedule(NOW), state: 'review', intervalDays: 20, repetitions: 5, lastReviewedAt: NOW - 20 * R.DAY };
  const failed = R.scheduleReview(mature, 'again', NOW);
  assert.equal(failed.state, 'relearning');
  assert.equal(failed.intervalDays, 10);
  assert.equal(failed.lapses, 1);
  assert.equal(failed.ease, 2.3);
  assert.equal(failed.dueAt, NOW + R.MINUTE);
  const step = R.scheduleReview(failed, 'good', failed.dueAt);
  const graduated = R.scheduleReview(step, 'good', step.dueAt);
  assert.equal(graduated.state, 'review');
  assert.equal(graduated.intervalDays, 10);
});

test('hard, good and easy mature grades increase intervals in order', () => {
  const mature = { ...R.initialSchedule(NOW), state: 'review', intervalDays: 10, repetitions: 3, lastReviewedAt: NOW - 10 * R.DAY };
  const hard = R.scheduleReview(mature, 'hard', NOW);
  const good = R.scheduleReview(mature, 'good', NOW);
  const easy = R.scheduleReview(mature, 'easy', NOW);
  assert.equal(hard.intervalDays, 12);
  assert.equal(good.intervalDays, 25);
  assert.equal(easy.intervalDays, 33);
  assert.ok(hard.ease < mature.ease);
  assert.equal(good.ease, mature.ease);
  assert.ok(easy.ease > mature.ease);
});

test('overdue reviews receive bounded delay credit', () => {
  const mature = { ...R.initialSchedule(NOW), state: 'review', intervalDays: 10, repetitions: 3, lastReviewedAt: NOW - 20 * R.DAY };
  const next = R.scheduleReview(mature, 'good', NOW);
  assert.equal(next.intervalDays, 38);
  assert.equal(next.dueAt, NOW + 38 * R.DAY);
  assert.equal(next.lastReviewedAt, NOW);
});

test('long repeated review sequences retain finite bounded schedules', () => {
  let schedule = R.initialSchedule(NOW);
  let time = NOW;
  for (let index = 0; index < 300; index++) {
    schedule = R.scheduleReview(schedule, index % 11 === 0 ? 'again' : 'easy', time);
    assert.ok(schedule.ease >= 1.3 && schedule.ease <= 3.5);
    assert.ok(schedule.intervalDays <= 36500);
    assert.ok(Number.isFinite(schedule.dueAt));
    assert.ok(schedule.dueAt > time);
    time = schedule.dueAt;
  }
  assert.equal(schedule.repetitions, 300);
  assert.ok(schedule.lapses > 0);
});

test('suspension is idempotent and resume retains the previous learning state', () => {
  const learning = R.scheduleReview(R.initialSchedule(NOW), 'good', NOW);
  const suspended = R.suspendSchedule(learning);
  assert.deepEqual(R.suspendSchedule(suspended), suspended);
  assert.equal(suspended.suspendedFrom, 'learning');
  assert.throws(() => R.scheduleReview(suspended, 'good', NOW), /Resume/);
  const resumed = R.resumeSchedule(suspended, NOW + R.DAY);
  assert.equal(resumed.state, 'learning');
  assert.equal(resumed.learningStep, 1);
  assert.equal(resumed.dueAt, NOW + R.DAY);
  assert.equal(resumed.suspendedFrom, null);
});

test('invalid grades, future-overflow and backward clocks are rejected', () => {
  const reviewed = R.scheduleReview(R.initialSchedule(NOW), 'good', NOW);
  assert.throws(() => R.scheduleReview(reviewed, 'perfect', NOW));
  assert.throws(() => R.scheduleReview(reviewed, 'good', NOW - 1), /before/);
  assert.throws(() => R.scheduleReview(reviewed, 'good', Infinity));
  assert.throws(() => R.scheduleReview(reviewed, 'good', 8.64e15));
});

test('new-card limits count unique introductions while learning repeats remain available', () => {
  const h = harness();
  const project = h.project();
  h.run({ type: 'preferences.update', patch: { dailyNewCards: 1 } });
  const first = h.card();
  h.card({ question: 'Second question?' });
  assert.equal(R.buildReviewQueue(h.state, project, h.now).cards.length, 1);
  h.review(first, 'again');
  assert.equal(R.buildReviewQueue(h.state, project, h.now).newRemaining, 0);
  h.advance(R.MINUTE);
  const queue = R.buildReviewQueue(h.state, project, h.now);
  assert.equal(queue.learning, 1);
  assert.deepEqual(queue.cards.map(item => item.id), [first]);
  h.review(first, 'again');
  assert.equal(R.buildReviewQueue(h.state, project, h.now).newRemaining, 0);
});

test('learning cards come before mature due cards and new cards', () => {
  const h = harness();
  const project = h.project();
  const fresh = h.card({ question: 'Fresh?' });
  const mature = h.card({ question: 'Mature?' });
  const learning = h.card({ question: 'Learning?' });
  h.review(mature, 'easy');
  h.advance(4 * R.DAY);
  h.review(learning, 'again');
  h.advance(R.MINUTE);
  const queue = R.buildReviewQueue(h.state, project, h.now);
  assert.deepEqual(queue.cards.map(item => item.id), [learning, mature, fresh]);
  assert.equal(queue.due, 1);
  assert.equal(queue.newAvailable, 1);
});

test('daily mature review limits do not hide due relearning cards', () => {
  const h = harness();
  const project = h.project();
  const first = h.card();
  const second = h.card({ question: 'Second?' });
  h.review(first, 'easy');
  h.review(second, 'easy');
  h.advance(4 * R.DAY);
  h.run({ type: 'preferences.update', patch: { dailyReviewCards: 1, dailyNewCards: 0 } });
  h.review(first, 'again');
  h.advance(R.MINUTE);
  const queue = R.buildReviewQueue(h.state, project, h.now);
  assert.equal(queue.reviewRemaining, 0);
  assert.equal(queue.due, 1);
  assert.deepEqual(queue.cards.map(item => item.id), [first]);
});

test('suspended and other-project cards are excluded from a review queue', () => {
  const h = harness();
  const firstProject = h.project();
  const suspended = h.card();
  h.run({ type: 'card.suspend', id: suspended, revision: 1, suspended: true });
  h.project({ title: 'Other' });
  h.card();
  const queue = R.buildReviewQueue(h.state, firstProject, h.now);
  assert.equal(queue.cards.length, 0);
  assert.equal(queue.nextDueAt, null);
});

test('nextDueAt reports the earliest waiting learning or review card', () => {
  const h = harness();
  const project = h.project();
  const first = h.card();
  const second = h.card();
  h.review(first, 'easy');
  h.review(second, 'good');
  assert.equal(R.buildReviewQueue(h.state, project, h.now).nextDueAt, h.now + 10 * R.MINUTE);
});

test('local day helpers preserve local calendar boundaries', () => {
  const evening = new Date(2026, 8, 20, 23, 59).getTime();
  assert.equal(R.localDayKey(evening), '2026-09-20');
  assert.equal(R.localDayKey(R.addCalendarDays(evening, 1)), '2026-09-21');
  assert.equal(new Date(R.dayStart(evening)).getHours(), 0);
  assert.equal(new Date(R.addCalendarDays(evening, 1)).getHours(), 23);
});
