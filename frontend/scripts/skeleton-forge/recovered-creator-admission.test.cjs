'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('./harness.cjs');
const R = load('src/skeletonForge/run.ts');
const Q = load('src/skeletonForge/questionnaire.ts');
const G = load('src/skeletonForge/galaxyGenres.ts');

test('unverified engine success is never a green qualification', () => {
  for (const verified of [undefined, null, false, 'true']) {
    const report = { status: 'passed', passed: true, verified };
    assert.equal(R.playtestView({playtest: report}).tone, 'warn');
    assert.equal(R.playableSceneView({forge:{playable_archetype:'crafting'}, playable_scene_playtest:report}).tone, 'warn');
  }
  assert.equal(R.playtestView({playtest:{status:'passed',passed:false,verified:true}}).tone,'bad');
});
test('non-Godot target cannot request native qualification', () => {
  const json = Q.questionnaireReducer(Q.INITIAL_STATE,{type:'setOption',key:'target',value:'json'});
  assert.strictEqual(Q.questionnaireReducer(json,{type:'setPlaytestMode',value:'require'}),json);
  assert.equal(Q.buildRunRequest({...json,playtest:'require'}).playtest,undefined);
});
test('all offline genre choices map without duplicated identities', () => {
  assert.equal(G.GALAXY_CHOICES.length,69);
  assert.equal(new Set(G.GALAXY_CHOICES.map(x=>x.id)).size,69);
  for (const x of G.GALAXY_CHOICES) assert.ok(G.mappedBriefGenre(x.id));
});
