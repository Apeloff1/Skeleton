'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('./harness.cjs');
const F = load('src/skeletonForge/foundation/model.ts');
const S = load('src/skeletonForge/foundation/storage.ts');
const at = '2026-11-14T12:00:00.000Z';
const project = (id, vision) => ({
  id, title: vision, createdAt: at, updatedAt: at,
  questionnaire: { ...F.freshQuestionnaire(), vision }, lastRun: null,
});
const snap = projects => ({
  onboarded: true, projects, prefs: F.DEFAULT_PREFS, holdSaves: false, projectsCorrupt: false,
});
function deferred() {
  let resolve; const promise = new Promise(yes => { resolve = yes; });
  return { promise, resolve };
}

test('queued return observes the latest project save and serializes publication', async () => {
  const base = S.memoryKv(), entered = deferred(), release = deferred();
  let blocked = false;
  const store = {
    getItem: base.getItem,
    async setItem(key, value) {
      if (key === S.KEYS.projects && !blocked) {
        blocked = true; entered.resolve(); await release.promise;
      }
      await base.setItem(key, value);
    },
  };
  const edit = S.saveFoundation(store, snap([project('p_a', 'Newer edit')]));
  await entered.promise;
  const update = S.updateFoundation(store, current => {
    assert.equal(current.projects[0].questionnaire.vision, 'Newer edit');
    return { snapshot: { ...current, projects: [...current.projects, project('p_b', 'Recovered')] }, result: 'applied' };
  });
  const read = S.loadFoundation(store);
  release.resolve();
  await edit;
  assert.equal(await update, 'applied');
  assert.deepEqual((await read).projects.map(p => p.id), ['p_a', 'p_b']);
});

test('failed return does not overwrite held source data or poison subsequent operations', async () => {
  const store = S.memoryKv();
  await S.saveFoundation(store, snap([project('p_a', 'Original')]));
  await assert.rejects(S.updateFoundation(store, () => { throw Error('reconcile failed'); }), /reconcile failed/);
  assert.equal((await S.loadFoundation(store)).projects[0].title, 'Original');
  await store.setItem(S.KEYS.projects, '{broken');
  await assert.rejects(S.updateFoundation(store, () => assert.fail('corrupt library admitted')), /held/);
  assert.equal(store.dump()[S.KEYS.projects], '{broken');
});

test('snapshot count bound does not enqueue a partial publication', async () => {
  const store = S.memoryKv();
  await S.saveFoundation(store, snap([project('p_a', 'Original')]));
  const before = store.dump();
  await assert.rejects(S.saveFoundation(store, snap(Array(S.MAX_STUDIO_PROJECTS + 1).fill(project('p_b', 'Rejected')))), /count/);
  assert.deepEqual(store.dump(), before);
});
