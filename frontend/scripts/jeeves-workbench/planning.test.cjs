const { test } = require('node:test');
const { assert, load, harness, linkedFixture } = require('./helpers.cjs');
const P = load('planning');
const S = load('selectors');
const { localDayKey } = load('review');

test('topological ordering places prerequisites before their dependants regardless of priority', () => {
  const { h, prerequisite, task } = linkedFixture();
  h.update('task', task, { priority: 'urgent' });
  const ordered = P.topologicalTasks([...h.state.tasks].reverse());
  assert.deepEqual(ordered.map(item => item.id), [prerequisite, task]);
  assert.equal(P.dependencyCycle(h.state.tasks), null);
});

test('cycle detection handles a long graph without recursive stack growth', () => {
  const h = harness();
  h.project();
  h.task();
  const template = h.state.tasks[0];
  const tasks = Array.from({ length: 1500 }, (_, index) => ({
    ...template, id: `task-${index}`, dependencies: index ? [`task-${index - 1}`] : [],
  }));
  assert.equal(P.dependencyCycle(tasks), null);
  tasks[0].dependencies = ['task-1499'];
  const cycle = P.dependencyCycle(tasks);
  assert.ok(cycle);
  assert.equal(cycle[0], cycle.at(-1));
  assert.throws(() => P.topologicalTasks(tasks), /cycle/);
});

test('critical path takes the longest branch rather than summing parallel work', () => {
  const h = harness();
  h.project();
  const root = h.task({ title: 'Setup', estimateMinutes: 10 });
  const short = h.task({ title: 'UI', estimateMinutes: 20, dependencies: [root] });
  const long = h.task({ title: 'Physics', estimateMinutes: 40, dependencies: [root] });
  const finish = h.task({ title: 'Integrate', estimateMinutes: 5, dependencies: [short, long] });
  const path = P.criticalPath(h.state.tasks);
  assert.equal(path.estimatedMinutes, 55);
  assert.deepEqual(path.taskIds, [root, long, finish]);
  assert.equal(path.earliestFinish[short], 30);
});

test('critical path excludes completed effort and exposes missing estimates', () => {
  const { h, prerequisite, task } = linkedFixture();
  h.status(prerequisite, 'done');
  h.task({ title: 'Unestimated', estimateMinutes: 0 });
  const path = P.criticalPath(h.state.tasks);
  assert.equal(path.estimatedMinutes, 30);
  assert.equal(path.unestimatedTasks, 1);
  assert.equal(path.earliestFinish[task], 30);
});

test('session planning can unlock dependants earlier in the same plan', () => {
  const { h, prerequisite, task } = linkedFixture();
  const plan = P.planSession(h.state.tasks, 40, h.now);
  assert.deepEqual(plan.items.map(item => item.task.id), [prerequisite, task]);
  assert.equal(plan.items[0].startMinute, 0);
  assert.equal(plan.items[1].startMinute, 10);
  assert.equal(plan.plannedMinutes, 40);
  assert.equal(plan.remainingMinutes, 0);
  assert.equal(plan.excluded.length, 0);
});

test('time budgets exclude oversized tasks without blocking smaller independent tasks', () => {
  const h = harness();
  h.project();
  const large = h.task({ title: 'Large', priority: 'urgent', estimateMinutes: 100 });
  const small = h.task({ title: 'Small', estimateMinutes: 20 });
  const plan = P.planSession(h.state.tasks, 25, h.now);
  assert.deepEqual(plan.items.map(item => item.task.id), [small]);
  assert.equal(plan.remainingMinutes, 5);
  assert.ok(plan.excluded.some(item => item.taskId === large && item.reason.includes('fit')));
});

test('manually blocked and cancelled prerequisites never unlock their dependants', () => {
  const { h, prerequisite, task } = linkedFixture();
  h.status(prerequisite, 'cancelled');
  const blocked = h.task({ title: 'Waiting for assets', status: 'blocked' });
  const plan = P.planSession(h.state.tasks, 120, h.now);
  assert.equal(plan.items.length, 0);
  assert.ok(plan.excluded.some(item => item.taskId === task));
  assert.ok(plan.excluded.some(item => item.taskId === blocked));
  assert.equal(P.canStart(h.record('tasks', task), h.state.tasks), false);
});

test('unknown estimates receive an explicit provisional allocation', () => {
  const h = harness();
  h.project();
  h.task({ estimateMinutes: 0 });
  const plan = P.planSession(h.state.tasks, 30, h.now);
  assert.equal(plan.plannedMinutes, 25);
  assert.equal(plan.items[0].estimated, false);
  assert.ok(plan.assumptions.some(item => item.includes('25 minutes')));
});

test('planning ranks ongoing work ahead of ordinary tasks', () => {
  const h = harness();
  h.project();
  h.task({ title: 'Ordinary', priority: 'normal', estimateMinutes: 25 });
  const ongoing = h.task({ title: 'Already started', status: 'doing', priority: 'low', estimateMinutes: 25 });
  const plan = P.planSession(h.state.tasks, 25, h.now);
  assert.equal(plan.items[0].task.id, ongoing);
  assert.match(plan.items[0].reason, /progress/);
});

test('planning rejects invalid budgets and never mutates task order', () => {
  const { h } = linkedFixture();
  const before = JSON.stringify(h.state.tasks);
  for (const value of [0, 4, 481, 10.5, NaN]) assert.throws(() => P.planSession(h.state.tasks, value, h.now));
  P.planSession(h.state.tasks, 60, h.now);
  assert.equal(JSON.stringify(h.state.tasks), before);
});

test('task filtering combines title, tag, priority and overdue constraints', () => {
  const h = harness();
  h.project();
  const match = h.task({ title: 'Physics tuning', tags: ['physics'], priority: 'high', dueDate: '2026-09-19' });
  h.task({ title: 'Physics docs', tags: ['physics'], priority: 'low', dueDate: '2026-09-19' });
  h.task({ title: 'Camera tuning', priority: 'high' });
  const result = S.filterTasks(h.state, h.state.activeProjectId, { query: 'physics', tag: 'physics', priorities: ['high'], due: 'overdue' }, h.now);
  assert.deepEqual(result.map(item => item.id), [match]);
});

test('today filtering uses the local date and does not include tomorrow', () => {
  const h = harness();
  h.project();
  const today = h.task({ dueDate: localDayKey(h.now) });
  h.task({ dueDate: '2026-09-21' });
  const result = S.filterTasks(h.state, h.state.activeProjectId, { due: 'today' }, h.now);
  assert.deepEqual(result.map(item => item.id), [today]);
});

test('activity at midnight belongs to exactly one day', () => {
  const h = harness();
  const projectId = h.project();
  const task = h.task();
  const midnight = new Date(2026, 8, 21).getTime();
  h.advance(midnight - h.now);
  h.status(task, 'done');
  h.note();
  const days = S.activityDays(h.state, projectId, h.now, 2);
  assert.equal(days[0].completedTasks, 0);
  assert.equal(days[0].notesCreated, 0);
  assert.equal(days[1].completedTasks, 1);
  assert.equal(days[1].notesCreated, 1);
});

test('dashboard excludes cancelled tasks from completion percentage', () => {
  const h = harness();
  const projectId = h.project();
  h.task({ status: 'done' });
  h.task({ status: 'ready' });
  h.task({ status: 'cancelled' });
  const summary = S.dashboard(h.state, projectId, h.now);
  assert.equal(summary.taskCount, 3);
  assert.equal(summary.completedTasks, 1);
  assert.equal(summary.completionPercent, 50);
});
