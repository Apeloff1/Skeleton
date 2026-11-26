const { test } = require('node:test');
const { assert, load, harness, memoryStorage, deferred, tick, assertValid } = require('./helpers.cjs');
const { WorkbenchStore } = load('WorkbenchStore');
const { WORKBENCH_KEY } = load('types');
const { prepareJourneyCommit, commitJourneyArtifact } = load('../journeys/journeyWorkbench');

const HASH = 'a'.repeat(64);
const CURRENT = () => true;
function fixture(journey = 'research', messageId = 'reply-1') {
  const request = { journey_id: journey, goal: 'Review original work', options: {},
    source_refs: [{ id: 'source1', label: 'Author supplied observation', locator: 'https://example.test/source', excerpt: 'Observed behavior.' }] };
  const artifact = { schema_version: 'skeleton.ai.workflow_artifact.v1', journey_id: journey,
    request_digest: HASH, title: 'Reviewed artifact' };
  if (journey === 'research') Object.assign(artifact, { summary: 'A cautious result.',
    claims: [{ text: 'The source reports this result.', source_ids: ['source1'], confidence: 'supported' }], open_questions: ['Does it repeat?'] });
  if (journey === 'creative') {
    request.options = { artifact: 'story' };
    Object.assign(artifact, { artifact_kind: 'story', items: [{ id: 'opening', title: 'Opening', description: 'The traveler follows the river.' }] });
  }
  if (journey === 'plan') {
    request.options = { max_tasks: 8, time_budget_minutes: 120, cost_budget: 10 };
    artifact.tasks = [
      { id: 'release', title: 'Release', description: 'Verify the delivery.', estimate_minutes: 10, cost: 1, depends_on: ['review'] },
      { id: 'build', title: 'Build', description: 'Create the prototype.', estimate_minutes: 30, cost: 2, depends_on: [] },
      { id: 'review', title: 'Review', description: 'Inspect actual behavior.', estimate_minutes: 20, cost: 0, depends_on: ['build'] },
    ];
  }
  if (journey === 'study') {
    request.options = { format: 'mixed', max_cards: 6 };
    artifact.cards = [
      { question: 'Which option is correct?', answer: 'Second choice', explanation: 'The observed rule supports the second choice.', choices: ['First choice', 'Second choice'], correct_choice: 1, source_ids: ['source1'] },
      { question: 'Explain the rule.', answer: 'A worked explanation.', explanation: 'Apply it to the observed case.', choices: [], correct_choice: null, source_ids: [] },
    ];
  }
  if (journey === 'studio') Object.assign(artifact, { goal: 'Inspect saved source', steps: [], completion_requirements: [] });
  return { preview: { schema_version: 'skeleton.ai.workflow_preview.v1', journey_id: journey,
    request_digest: HASH, artifact, artifact_digest: 'b'.repeat(64),
    checks: { structure_valid: true, execution_performed: false, factual_accuracy_verified: false },
    warnings: ['Unverified draft'], execution_authorized: false },
    origin: { conversationId: 'canonical-thread', messageId, request } };
}
async function open() {
  const storage = memoryStorage();
  const store = new WorkbenchStore(storage, harness('artifact').clock);
  await store.initialize(); await store.settled();
  const projectId = store.dispatch({ type: 'project.create', input: { title: 'Destination' } }).createdId;
  await store.settled();
  const prepare = input => prepareJourneyCommit(store.getSnapshot().state, projectId, input.preview, input.origin);
  return { store, storage, projectId, prepare };
}

test('research becomes one source-linked unverified note with authored source locations and deduplication', async () => {
  const { store, prepare } = await open();
  const input = fixture();
  const plan = prepare(input);
  assert.equal(Object.isFrozen(plan), true);
  assert.equal(Object.isFrozen(plan.preview.artifact.claims[0]), true);
  input.preview.artifact.summary = 'Changed after preview';
  input.origin.request.source_refs[0].locator = 'https://changed.test/';
  const result = await commitJourneyArtifact(store, plan, CURRENT);
  assert.equal(result.status, 'saved');
  const state = store.getSnapshot().state;
  assert.equal(state.notes.length, 1); assert.equal(state.sources.length, 1);
  assert.equal(state.notes[0].confidence, 'unverified');
  assert.deepEqual(state.notes[0].sourceIds, [state.sources[0].id]);
  assert.match(state.notes[0].body, /https:\/\/example.test\/source/);
  assert.doesNotMatch(state.notes[0].body, /changed.test|Changed after preview/);
  assert.match(state.notes[0].body, /Jeeves journey: canonical-thread\/reply-1\/research/);
  assert.throws(() => prepare(fixture()), /already been applied/);
  const changed = fixture(); changed.preview.artifact.summary = 'A different result under the same origin';
  assert.throws(() => prepare(changed), /already been applied/);
  assertValid(state);
});

test('plan creates actual task dependencies, preserves declared costs, persists, and undoes as one transaction', async () => {
  const { store, storage, prepare } = await open();
  const result = await commitJourneyArtifact(store, prepare(fixture('plan')), CURRENT);
  assert.equal(result.status, 'saved');
  const state = store.getSnapshot().state;
  const named = title => state.tasks.find(task => task.title === title);
  assert.deepEqual(named('Release').dependencies, [named('Review').id]);
  assert.deepEqual(named('Review').dependencies, [named('Build').id]);
  assert.deepEqual(named('Build').dependencies, []);
  assert.equal(named('Build').estimateMinutes, 30);
  assert.match(named('Build').description, /Proposed cost units: 2/);
  assert.equal(named('Build').status, 'inbox');
  assert.deepEqual(JSON.parse(storage.data.get(WORKBENCH_KEY)).tasks, state.tasks);
  store.undo(); await store.settled();
  assert.equal(store.getSnapshot().state.tasks.length, 0);
  assert.equal(store.getSnapshot().state.projects.length, 1);
});

test('study retains MCQ alternatives, answer and provenance and initializes fresh scheduling', async () => {
  const { store, prepare } = await open();
  const result = await commitJourneyArtifact(store, prepare(fixture('study')), CURRENT);
  assert.equal(result.status, 'saved');
  const cards = store.getSnapshot().state.cards;
  assert.equal(cards.length, 2);
  assert.match(cards[0].question, /A\. First choice\nB\. Second choice/);
  assert.equal(cards[0].answer, 'Second choice');
  assert.match(cards[0].explanation, /Author supplied observation/);
  assert.match(cards[0].explanation, /Jeeves journey: canonical-thread\/reply-1\/study/);
  assert.equal(cards[0].schedule.state, 'new');
  assert.equal(cards[0].schedule.repetitions, 0);
  assert.throws(() => prepare(fixture('study')), /already been applied/);
});

test('creative drafts save as notes and Studio effects remain on their existing owner', async () => {
  const { store, prepare } = await open();
  assert.equal((await commitJourneyArtifact(store, prepare(fixture('creative')), CURRENT)).status, 'saved');
  assert.equal(store.getSnapshot().state.notes[0].kind, 'note');
  assert.match(store.getSnapshot().state.notes[0].body, /traveler follows the river/);
  assert.throws(() => prepare(fixture('studio')), /existing Studio goal form/);
});

test('stale Workbench, archived destination, failed storage and conflicts block application', async () => {
  const { store, storage, projectId, prepare } = await open();
  const plan = prepare(fixture('study'));
  store.dispatch({ type: 'note.create', input: { projectId, title: 'Newer work' } }); await store.settled();
  assert.equal((await commitJourneyArtifact(store, plan, CURRENT)).status, 'refused');
  assert.equal(store.getSnapshot().state.cards.length, 0);
  const state = store.getSnapshot().state;
  store.dispatch({ type: 'project.update', id: projectId, revision: state.projects[0].revision, patch: { status: 'archived' } });
  assert.throws(() => prepare(fixture()), /active Workbench project/);
  await store.settled();
  const other = await open(); const pending = other.prepare(fixture());
  other.storage.setItem = async () => { throw new Error('Full'); };
  other.store.dispatch({ type: 'preferences.update', patch: { focusMinutes: 30 } }); await other.store.settled();
  assert.equal((await commitJourneyArtifact(other.store, pending, CURRENT)).status, 'refused');
  const conflict = await open(); const conflictPlan = conflict.prepare(fixture());
  conflict.storage.data.set(WORKBENCH_KEY, 'changed elsewhere');
  conflict.store.dispatch({ type: 'preferences.update', patch: { focusMinutes: 35 } }); await conflict.store.settled();
  assert.equal(conflict.store.getSnapshot().saveStatus, 'conflict');
  assert.equal((await commitJourneyArtifact(conflict.store, conflictPlan, CURRENT)).status, 'refused');
  assert.equal(storage.data.has(WORKBENCH_KEY), true);
});

test('invalid model fields, forged source IDs, cycles, oversized notes and over-budget plans stay inert', async () => {
  const { store, prepare } = await open();
  const invalid = [];
  const choices = fixture('study'); choices.preview.artifact.cards[0].correct_choice = 0; invalid.push(choices);
  const source = fixture(); source.preview.artifact.claims[0].source_ids = ['invented']; invalid.push(source);
  const cycle = fixture('plan'); cycle.preview.artifact.tasks[1].depends_on = ['release']; invalid.push(cycle);
  const budget = fixture('plan'); budget.origin.request.options.cost_budget = 0; invalid.push(budget);
  const flags = fixture(); flags.preview.execution_authorized = true; invalid.push(flags);
  const long = fixture();
  long.preview.artifact.claims = Array.from({ length: 12 }, () => ({ text: 'x'.repeat(2000), source_ids: [], confidence: 'uncertain' }));
  long.preview.artifact.summary = 's'.repeat(4000);
  long.preview.artifact.open_questions = Array.from({ length: 12 }, (_, index) => index + 'q'.repeat(999)); invalid.push(long);
  const before = store.getSnapshot().state;
  invalid.forEach(value => assert.throws(() => prepare(value)));
  assert.equal(store.getSnapshot().state, before);
});

test('account changes before commit refuse writes; changes during save cannot report old-account success', async () => {
  const { store, storage, prepare } = await open();
  const plan = prepare(fixture()); const writes = storage.writes.length;
  assert.equal((await commitJourneyArtifact(store, plan, () => false)).status, 'refused');
  assert.equal(store.getSnapshot().state.notes.length, 0);
  assert.equal(storage.writes.length, writes);
  const gate = deferred(); const save = storage.setItem; let current = true;
  storage.setItem = async (key, value) => { if (key === WORKBENCH_KEY) await gate.promise; return save(key, value); };
  const operation = commitJourneyArtifact(store, plan, () => current);
  await tick(); current = false; gate.resolve();
  const result = await operation;
  assert.equal(result.status, 'unsaved');
  assert.equal(store.getSnapshot().state.notes.length, 1);
  assert.match(result.message, /account changed/);
});

test('failed writes report unsaved and the origin cannot be applied twice after storage recovers', async () => {
  const { store, storage, prepare } = await open();
  const input = fixture('study'); const plan = prepare(input); const save = storage.setItem;
  storage.setItem = async (key, value) => { if (key === WORKBENCH_KEY) throw new Error('Full'); return save(key, value); };
  const result = await commitJourneyArtifact(store, plan, CURRENT);
  assert.equal(result.status, 'unsaved');
  assert.equal(store.getSnapshot().state.cards.length, 2);
  assert.match(result.message, /do not reapply/);
  storage.setItem = save; store.retrySave(); await store.settled();
  assert.throws(() => prepare(input), /already been applied/);
  assert.equal((await commitJourneyArtifact(store, plan, CURRENT)).status, 'refused');
  assert.equal(store.getSnapshot().state.cards.length, 2);
});

test('destination capacity and cross-project repeated origins are refused before changes', async () => {
  const { store, prepare } = await open();
  await commitJourneyArtifact(store, prepare(fixture('study')), CURRENT);
  const original = store.getSnapshot().state;
  const almostFull = { ...original, cards: Array.from({ length: 1999 }, (_, index) => ({
    ...original.cards[0], id: `capacity-card-${index}`,
  })) };
  assertValid(almostFull);
  const fresh = fixture('study', 'different-reply');
  assert.throws(() => prepareJourneyCommit(almostFull, original.projects[0].id, fresh.preview, fresh.origin), /capacity/);
  const another = store.dispatch({ type: 'project.create', input: { title: 'Another destination' } }).createdId;
  const repeated = fixture('study');
  assert.throws(() => prepareJourneyCommit(store.getSnapshot().state, another, repeated.preview, repeated.origin), /already been applied/);
  assert.equal(store.getSnapshot().state.cards.length, 2);
  await store.settled();
});

test('a failing account check after mutation cannot report refusal as if no records changed', async () => {
  const { store, prepare } = await open(); let checks = 0;
  const result = await commitJourneyArtifact(store, prepare(fixture()), () => {
    if (++checks >= 3) throw new Error('Account observation unavailable');
    return true;
  });
  assert.equal(result.status, 'unsaved');
  assert.equal(store.getSnapshot().state.notes.length, 1);
  assert.match(result.message, /do not reapply/);
});
