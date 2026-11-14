'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { ROOT, load } = require('./harness.cjs');
const M = load('src/skeletonForge/foundation/model.ts');
const Q = load('src/skeletonForge/questionnaire.ts');
const H = load('src/skeletonForge/creatorBridge.ts');
const Store = load('src/skeletonForge/foundation/storage.ts');

const AT = '2026-11-13T12:00:00.000Z';
function project(id = 'p_original') {
  let q = Q.questionnaireReducer(M.freshQuestionnaire(),
    { type: 'setVision', vision: 'Original community action adventure' });
  q = Q.questionnaireReducer(q, { type: 'setPlayableEnabled', value: true });
  q = Q.questionnaireReducer(q, { type: 'setPlayableMode', value: 'stealth' });
  return { id, title: 'Original project', createdAt: AT, updatedAt: AT,
    questionnaire: q, lastRun: null };
}
function receipt() {
  return { phase: 'done', succeeded: true, error: null, startedAt: 1, finishedAt: 2,
    payload: {
      succeeded: true, files: { 'secret-project.gd': 'source kept only in memory' },
      source_manifest: { schema: 'example' },
      source_export: { status: 'ready', bytes: 300, file_count: 1,
        manifest_sha256: 'a'.repeat(64) },
      run: { run_id: 'test', succeeded: true, stages: [] },
    } };
}

test('Studio → Forge → Studio applies all eight original native modes only to the source revision', () => {
  for (const { id } of Q.PLAYABLE_SLICES) {
    const original = project();
    const stamped = H.handoffFromStudio(original.questionnaire, original.id, original.updatedAt,
      1700000000000);
    const edited = Q.questionnaireReducer(original.questionnaire, { type: 'setPlayableMode', value: id });
    const outgoing = H.handoffToStudio(edited, stamped, 1700000005000);
    const accepted = H.studioStateFromHandoff(outgoing, 1700000005001);
    assert.ok(accepted);
    assert.equal(accepted.playable.mode, id);
    const merged = M.reconcileStudioReturn([original], stamped.studioProjectId,
      stamped.studioProjectUpdatedAt, accepted, '2026-11-13T14:00:00.000Z');
    assert.equal(merged.status, 'applied');
    assert.equal(merged.projects[0].id, original.id);
    assert.equal(merged.projects[0].questionnaire.playable.mode, id);
    assert.equal(Q.buildRunRequest(merged.projects[0].questionnaire).playable_archetype, id);
    assert.equal(merged.projects[0].updatedAt, '2026-11-13T14:00:00.000Z');
  }
});

test('replayed return after a successful write acknowledges exact equality, not a duplicate copy', () => {
  const original = project();
  const edited = Q.questionnaireReducer(original.questionnaire, { type: 'setAxis', axis: 'risk', value: 0.65 });
  const first = M.reconcileStudioReturn([original], original.id, original.updatedAt,
    edited, '2026-11-13T14:00:00.000Z');
  assert.equal(first.status, 'applied');
  const retried = M.reconcileStudioReturn(first.projects, original.id, original.updatedAt,
    edited, '2026-11-13T14:30:00.000Z');
  assert.equal(retried.status, 'already-applied');
  assert.deepEqual(retried.projects, first.projects);
});

test('concurrent Studio edits cannot be overwritten; conflict recovery makes a separate project', () => {
  const original = project();
  const saved = M.reconcileStudioReturn([original], original.id, AT,
    Q.questionnaireReducer(original.questionnaire, { type: 'setVision', vision: 'Another author change' }),
    '2026-11-13T14:00:00.000Z');
  const returnDraft = Q.questionnaireReducer(original.questionnaire,
    { type: 'setVision', vision: 'Original cockpit return' });
  const conflict = M.reconcileStudioReturn(saved.projects, original.id, AT, returnDraft,
    '2026-11-13T15:00:00.000Z');
  assert.equal(conflict.status, 'conflict');
  assert.deepEqual(conflict.projects, saved.projects);
  const recovered = M.recoverStudioReturnAsCopy(conflict.projects, returnDraft,
    '2026-11-13T15:00:00.000Z');
  assert.equal(recovered.projects.length, 2);
  assert.equal(recovered.projects[1].questionnaire.vision, 'Another author change');
  assert.equal(recovered.project.questionnaire.vision, 'Original cockpit return');
  assert.notEqual(recovered.project.id, original.id);
  const again = M.recoverStudioReturnAsCopy(recovered.projects, returnDraft,
    '2026-11-13T15:00:00.000Z');
  assert.equal(new Set(again.projects.map(x => x.id)).size, 3);
  assert.equal(M.reconcileStudioReturn([], original.id, AT, returnDraft,
    '2026-11-13T15:00:00.000Z').status, 'missing');
});

test('run receipts retain summary but not generated source or an expired ZIP offer', async () => {
  const original = project();
  const state = { ...M.initialFoundationState(), projects: [original], activeId: original.id };
  const recorded = M.applyRecordRun(state, original.id, receipt());
  const item = recorded.projects[0];
  assert.equal(item.lastRun.payload.files, undefined);
  assert.equal(item.lastRun.payload.source_manifest, undefined);
  assert.equal(item.lastRun.payload.source_export.status, 'unavailable');
  const disk = Store.memoryKv();
  await Store.saveFoundation(disk, M.persistSnapshot(recorded));
  assert.doesNotMatch(disk.dump()[Store.KEYS.projects], /source kept only in memory/);
  const restored = await Store.loadFoundation(disk);
  assert.equal(restored.projectsCorrupt, false);
  assert.equal(restored.projects[0].lastRun.payload.source_export.status, 'unavailable');
});

test('edited source preserves historical receipt only as outdated, not current qualification', () => {
  const original = { ...project(), lastRun: receipt() };
  const changed = Q.questionnaireReducer(original.questionnaire,
    { type: 'setAxis', axis: 'tempo', value: 0.9 });
  const result = M.reconcileStudioReturn([original], original.id, AT, changed,
    '2026-11-13T17:00:00.000Z');
  assert.equal(result.status, 'applied');
  assert.equal(result.projects[0].lastRunOutdated, true);
  assert.equal(M.openTarget(result.projects[0], null, 'idle'), 'brief');
  assert.match(M.projectStatus(result.projects[0], null, 'idle'), /build again/);
  assert.equal(M.nextStudioRevision(AT, AT), '2026-11-13T12:00:00.001Z');
});

test('corrupt, duplicate and unsupported authored Studio records hold all saves', () => {
  const original = project();
  assert.equal(M.sanitizeProjects([original, { ...original }]).corrupt, true);
  const invalid = { ...original,
    questionnaire: { ...original.questionnaire, playable: { enabled: true, mode: 'remote-code', launch: false } },
  };
  assert.equal(M.sanitizeProjects([invalid]).corrupt, true);
  const bad = { ...original, questionnaire: { ...original.questionnaire,
    quest: { enabled: true, length: 200 } } };
  assert.equal(M.sanitizeProjects([bad]).corrupt, true);
});

test('actual source wiring consumes one-time return and reopens the matching active Studio', () => {
  const file = rel => fs.readFileSync(path.join(ROOT, rel), 'utf8');
  const live = file('src/skeletonForge/components/foundation/FoundationScreen.tsx');
  const shell = file('src/skeletonForge/components/foundation/FoundationShell.tsx');
  const scope = file('src/skeletonForge/creatorStorageScope.ts');
  assert.match(live, /consumeCreatorBridge\('studio'\)/);
  assert.match(live, /reconcileStudioReturn\(/);
  assert.match(live, /recoverStudioReturnAsCopy\(/);
  assert.match(live, /storeCreatorBridge\(returned\)/);
  assert.match(live, /handoffFromStudio\(project\.questionnaire, project\.id, project\.updatedAt\)/);
  assert.match(live, /key=\{authEpoch\}/);
  assert.match(shell, /ports\.onOpenCockpit\(active \?\? undefined\)/);
  for (const key of ['onboarded', 'projects', 'prefs']) {
    assert.ok(scope.includes("'skeleton.studio." + key + ".v1'"));
  }
});
