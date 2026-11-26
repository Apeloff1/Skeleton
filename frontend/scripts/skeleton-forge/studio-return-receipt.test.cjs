'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('./harness.cjs');
const F = load('src/skeletonForge/foundation/model.ts');
const Q = load('src/skeletonForge/questionnaire.ts');
const at = '2026-11-14T12:00:00.000Z';
const later = '2026-11-14T12:00:01.000Z';
const receipt = 'a'.repeat(64);
const design = vision => ({ ...F.freshQuestionnaire(), vision });
const project = () => ({ id: 'p_origin', title: 'Original', createdAt: at, updatedAt: at,
  questionnaire: design('Original world'), lastRun: null });

test('source-bound return survives acknowledgement failure after a newer edit', () => {
  const original = project();
  const imported = F.reconcileStudioReturn([original], original.id, at, design('Forge edit'), later, receipt);
  assert.equal(imported.status, 'applied');
  assert.equal(imported.projects[0].studioReturnReceipt, receipt);
  const saved = F.sanitizeProjects(JSON.parse(JSON.stringify(imported.projects)));
  assert.equal(saved.corrupt, false);
  const revised = { ...saved.projects[0], questionnaire: design('Newer local edit'),
    updatedAt: '2026-11-14T12:00:02.000Z' };
  const retry = F.reconcileStudioReturn([revised], original.id, at, design('Forge edit'), later, receipt);
  assert.equal(retry.status, 'already-applied');
  assert.equal(retry.projects[0].questionnaire.vision, 'Newer local edit');
});

test('conflict copy is recovered exactly once across reload and different clocks', () => {
  const original = { ...project(), updatedAt: later };
  const conflict = F.reconcileStudioReturn([original], original.id, at, design('Forge copy'), later, receipt);
  assert.equal(conflict.status, 'conflict');
  const first = F.recoverStudioReturnAsCopy(conflict.projects, design('Forge copy'), later, receipt);
  assert.equal(first.projects.length, 2);
  const reloaded = F.sanitizeProjects(JSON.parse(JSON.stringify(first.projects)));
  assert.equal(reloaded.corrupt, false);
  const retry = F.recoverStudioReturnAsCopy(reloaded.projects, design('Forge copy'),
    '2026-11-14T12:00:03.000Z', receipt);
  assert.equal(retry.projects.length, 2);
  assert.equal(retry.project.id, first.project.id);
  assert.equal(retry.projects.find(p => p.id === original.id).questionnaire.vision, 'Original world');
});

test('duplicate and malformed return receipts are held instead of silently normalized', () => {
  const a = { ...project(), studioReturnReceipt: receipt };
  assert.equal(F.sanitizeProjects([a]).corrupt, false);
  assert.equal(F.sanitizeProjects([a, { ...a, id: 'p_other' }]).corrupt, true);
  assert.equal(F.sanitizeProjects([{ ...a, studioReturnReceipt: 'not-a-digest' }]).corrupt, true);
  assert.equal(F.reconcileStudioReturn([a], a.id, at, Q.INITIAL_STATE, later, 'invalid').status, 'invalid');
  assert.throws(() => F.recoverStudioReturnAsCopy([a], Q.INITIAL_STATE, later, 'invalid'), /receipt/);
});
