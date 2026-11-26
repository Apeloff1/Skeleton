const { test } = require('node:test');
const { assert, load } = require('./helpers.cjs');
const { readJourneyEnvelope, readJourneyArtifact, stagedJourneyDraft, canonicalJourneyJSON } = load('../journeys/journeyDraft');
const digest = 'a'.repeat(64);
const request = { journey_id: 'plan', goal: 'An original game', options: { strategy: 'dependency_first', max_tasks: 4, time_budget_minutes: 120, cost_budget: 0 }, source_refs: [] };
const envelope = 'JEEVES_WORKFLOW_REQUEST_V1=' + JSON.stringify({ request_digest: digest, request });
test('prepared request survives canonical transcript reload and preserves chosen options', () => {
  const saved = JSON.parse(JSON.stringify({ role: 'user', text: 'Prepare JSON.\n' + envelope + '\nOUTPUT_SCHEMA={}' }));
  assert.deepEqual(readJourneyEnvelope(saved.text), { request, request_digest: digest });
});
test('ambiguous duplicate, malformed and unbounded request envelopes are rejected', () => {
  assert.equal(readJourneyEnvelope(envelope + '\n' + envelope), null);
  assert.equal(readJourneyEnvelope('JEEVES_WORKFLOW_REQUEST_V1={broken'), null);
  assert.equal(readJourneyEnvelope(envelope + 'x'.repeat(16000)), null);
  assert.equal(readJourneyEnvelope(envelope.replace('plan', 'unknown')), null);
});
test('exact append and replace preserve all authored bytes including unicode and whitespace', () => {
  const authored = '  🐲 Field notes\nDo not lose this.\n';
  assert.equal(stagedJourneyDraft(authored, authored, envelope, 'append'), authored + '\n\n' + envelope);
  assert.equal(stagedJourneyDraft(authored, authored, envelope, 'replace'), envelope);
  assert.throws(() => stagedJourneyDraft(authored + 'edit', authored, envelope, 'replace'), /changed after preview/);
  assert.throws(() => stagedJourneyDraft('x'.repeat(16000), 'x'.repeat(16000), envelope, 'append'), /exceeds/);
  assert.equal(authored, '  🐲 Field notes\nDo not lose this.\n');
});
test('a second guided request cannot ambiguously append over a previous prepared request', () => {
  assert.throws(() => stagedJourneyDraft(envelope, envelope, envelope, 'append'), /already contains/);
  assert.equal(stagedJourneyDraft(envelope, envelope, envelope, 'replace'), envelope);
});
test('typed reply requires exact journey and request binding; complete JSON fences are supported', () => {
  const artifact = { schema_version: 'skeleton.ai.workflow_artifact.v1', journey_id: 'plan', request_digest: digest, title: 'Reviewed plan', tasks: [] };
  assert.deepEqual(readJourneyArtifact('```json\n' + JSON.stringify(artifact) + '\n```', request, digest), artifact);
  assert.throws(() => readJourneyArtifact(JSON.stringify({ ...artifact, request_digest: 'b'.repeat(64) }), request, digest), /does not match/);
  assert.throws(() => readJourneyArtifact('prose\n' + JSON.stringify(artifact), request, digest), /not a complete JSON/);
});
test('canonical request encoding ignores key order without losing source unicode', () => {
  assert.equal(canonicalJourneyJSON({ z: ['é', '🐲'], a: 1 }), canonicalJourneyJSON({ a: 1, z: ['é', '🐲'] }));
});
test('header-valid malformed model rows cannot enter the structured editor', () => {
  const artifact = { schema_version: 'skeleton.ai.workflow_artifact.v1', journey_id: 'plan', request_digest: digest, title: 'Malformed plan' };
  for (const tasks of [[null], [3], [{ title: { injected: 'object' } }], Array.from({ length: 25 }, () => ({ title: 'Too many' }))]) {
    assert.throws(() => readJourneyArtifact(JSON.stringify({ ...artifact, tasks }), request, digest), /invalid structured items/);
  }
});
const { studioHandoffSpec, existingStudioHandoff } = load('../journeys/journeyDraft');
test('studio handoff recovers only the exact original plan without edit grants', () => {
  const preview = { journey_id: 'studio', artifact_digest: digest, artifact: { title: 'Inspect source', journey_id: 'studio', goal: 'Review the original project', steps: [{ operation: 'project.inspect', description: 'Read saved source' }], completion_requirements: [] } };
  const spec = studioHandoffSpec('project-1', preview, 'thread-1', 'reply-1', 'native');
  const original = { project_id: 'project-1', goal: spec.goal, execution_mode: 'plan', allow_edits: false, completion_mode: 'native', completion_requirements: [] };
  assert.equal(existingStudioHandoff([], spec), null);
  assert.equal(existingStudioHandoff([original], spec), 0);
  assert.equal(studioHandoffSpec('project-1', preview, 'thread-1', 'reply-1', 'native').keyMaterial, spec.keyMaterial);
  for (const changes of [{ project_id: 'other' }, { goal: spec.goal + '\nchanged' }, { execution_mode: 'run' }, { allow_edits: true }, { completion_mode: 'original' }, { completion_requirements: ['edit'] }]) {
    assert.throws(() => existingStudioHandoff([{ ...original, ...changes }], spec), /different studio goal or authorization/);
  }
  assert.throws(() => existingStudioHandoff([original, original], spec), /More than one/);
  const edited = studioHandoffSpec('project-1', { ...preview, artifact: { ...preview.artifact, goal: 'A changed request' } }, 'thread-1', 'reply-1', 'native');
  assert.equal(edited.origin, spec.origin);
  assert.throws(() => existingStudioHandoff([original], edited), /different studio goal/);
});
test('studio handoff refuses oversized content instead of silently truncating it', () => {
  assert.throws(() => studioHandoffSpec('project-1', { journey_id: 'studio', artifact_digest: digest, artifact: { title: 'Long', journey_id: 'studio', goal: 'x'.repeat(7500), steps: [], completion_requirements: [] } }, 'thread-1', 'reply-1', 'native'), /exceeds/);
});
