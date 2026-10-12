const { test } = require('node:test');
const { assert } = require('./helpers.cjs');
const {
  OUTCOME_SCHEMA, parsePlanDraft, acceptSimulation, acceptOutcomeAudit,
  chooseOption, compactPlayerContext, exampleThreeEndingPlan,
} = require('../../features/Jeeves/outcomeStudio.ts');

const hash = char => char.repeat(64);
const base = () => exampleThreeEndingPlan();
const state = () => ({
  quests: { charter_quest: 'completed' },
  meters: { karma: 50, 'reputation:faction:council': 40 },
  choices: ['protect_city', 'restore'], flags: [], known_lore: ['secret_gate'],
});
function turn(plan = base()) {
  return {
    schema_version: 'jeeves.branching-playthrough.v1',
    plan_digest: hash('a'), position: null, ending_id: 'peace',
    ending: plan.endings.find(x => x.id === 'peace'),
    ending_accepted: true, available_options: [], state: state(),
    steps: [
      { node: 'gates', scene: 1, character: 'aria', place: 'glass_city',
        choice: 'protect_city', intent: 'Help Aria',
        emotional_consequence: 'Hope grows', consequences: [],
        receipt_digest: hash('b') },
      { node: 'ending_gate', scene: 2, character: 'aria', place: 'glass_city',
        choice: 'restore', intent: 'Restore the charter',
        emotional_consequence: 'City is saved', consequences: [],
        receipt_digest: hash('c') },
    ],
    threads: { lost_charter: { status: 'closed' } },
    unresolved_threads: [], unresolved_character_arcs: [],
    unresolved_place_lore: [], unresolved_quest_conclusions: [],
    unresolved_faction_conclusions: [], missing_ending_lore: [],
    receipt_digest: hash('d'),
  };
}

test('example branching studio provides authored NPC, place, lore, and three endings', () => {
  const plan = base();
  assert.equal(plan.schema_version, OUTCOME_SCHEMA);
  assert.equal(plan.nodes.length, 2);
  assert.equal(plan.characters.length, 1);
  assert.equal(plan.places.length, 1);
  assert.deepEqual(plan.endings.map(e => e.tone), ['good', 'neutral', 'evil']);
  assert.equal(parsePlanDraft(JSON.stringify(plan), 'build_1', 'main').title, plan.title);
});

test('narrative draft must target selected project and branch with complete graph', () => {
  const raw = JSON.stringify(base());
  assert.throws(() => parsePlanDraft(raw, '../escape', 'main'));
  assert.throws(() => parsePlanDraft(raw, 'build_1', 'bad/branch'));
  assert.throws(() => parsePlanDraft(raw, 'build_1', 'other'));
  assert.throws(() => parsePlanDraft('{}', 'build_1', 'main'));
  assert.throws(() => parsePlanDraft('malformed', 'build_1', 'main'));
  assert.throws(() => parsePlanDraft(JSON.stringify({ ...base(), endings: [] }), 'build_1', 'main'));
});

test('verified player receipts must match every selected and replayed dialogue action', () => {
  const answer = turn();
  assert.equal(acceptSimulation(answer, hash('a'), ['protect_city', 'restore']).ending_id, 'peace');
  assert.throws(() => acceptSimulation(answer, hash('e'), ['protect_city', 'restore']));
  assert.throws(() => acceptSimulation(answer, hash('a'), ['restore', 'protect_city']));
  assert.throws(() => acceptSimulation({ ...answer, receipt_digest: 'fake' },
    hash('a'), ['protect_city', 'restore']));
  assert.throws(() => acceptSimulation({ ...answer, steps: [answer.steps[0]] },
    hash('a'), ['protect_city', 'restore']));
});

test('only unlocked choices can advance, and endings disable further choices', () => {
  const current = { ...turn(), position: 'ending_gate', ending_id: null,
    ending: null, available_options: [
      { id: 'restore', label: 'Save the charter', dialogue: 'We can help',
        intent: 'protect', emotional_consequence: 'hope',
        next_node: null, ending: 'peace' },
    ] };
  assert.equal(chooseOption(current, 'restore'), 'restore');
  assert.throws(() => chooseOption(current, 'tyranny'));
  assert.throws(() => chooseOption(turn(), 'restore'));
  assert.throws(() => acceptSimulation({ ...current, ending_id: 'peace' },
    hash('a'), ['protect_city', 'restore']));
});

test('auditor never certifies truncated histories or unresolved ending outcomes', () => {
  const valid = {
    schema_version: 'jeeves.branching-outcome-audit.v1',
    plan_digest: hash('a'), paths_inspected: 8,
    complete: true, reachable_endings: ['peace','truce','tyranny'],
    unreachable_endings: [], issue_count: 0, issues: [],
    all_paths_verified: true, literary_perfection_guaranteed: false,
  };
  assert.equal(acceptOutcomeAudit(valid, hash('a')).all_paths_verified, true);
  assert.throws(() => acceptOutcomeAudit({ ...valid, complete: false }, hash('a')));
  assert.throws(() => acceptOutcomeAudit({ ...valid, unreachable_endings: ['tyranny'] }, hash('a')));
  assert.throws(() => acceptOutcomeAudit(valid, hash('b')));
});

test('Jeeves receives NPC backstories and evidence-bound playthroughs as untrusted context', () => {
  const context = compactPlayerContext(base(), turn());
  assert.match(context, /UNTRUSTED AUTHOR-EDITED FICTION/);
  assert.match(context, /Aria/);
  assert.match(context, /Glass City/);
  assert.match(context, /protect_city/);
  assert.match(context, /charter_quest/);
  assert.match(context, /SCENE 2/);
  assert.ok(context.length <= 4000);
});
