import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import {
  WORLD_STAGES, mapWorldEvidence, mountedWorldSystems, projectHref,
  readArtifactPreview, validProjectId, worldProjectLinks,
} from '../src/product/worldWorkspace.ts';

test('all world stages are actionable backed by a real pipeline stage', () => {
  assert.deepEqual(WORLD_STAGES.map(s => s.id), ['world','narrative','mechanics','assets']);
  assert.equal(new Set(WORLD_STAGES.map(s => s.id)).size, 4);
});
test('evidence only marks server-confirmed present artifacts', () => {
  const rows = mapWorldEvidence({artifacts:[
    {name:'world_graph.json',stage:'world',present:true,summary:'Three connected regions'},
    {name:'terrain.json',stage:'world',present:false},
    {name:'quests.json',stage:'narrative',present:'true'},
    {name:'mechanics.json',stage:'mechanics',present:true,summary:'Combat and exploration'},
  ]});
  assert.deepEqual(rows.map(s => s.available), [1,0,1,0]);
  assert.equal(rows[0].total,2);
  assert.equal(rows[1].present,false);
  assert.deepEqual(rows[2].rawNames,['mechanics.json']);
  assert.equal(mapWorldEvidence(null).every(x=>!x.present),true);
});
test('artifact preview comes only from canonical returned data and is bounded', () => {
  const kb={ data:{'world_graph.json':{regions:['a','b'],data:'a'.repeat(9000)}} };
  assert.ok(readArtifactPreview(kb,'world_graph.json')?.includes('regions'));
  assert.ok((readArtifactPreview(kb,'world_graph.json')||'').length<=1600);
  assert.equal(readArtifactPreview(kb,'__proto__'),null);
  assert.equal(readArtifactPreview(kb,'missing'),null);
});
test('mounted systems are deduplicated and cannot imply operation readiness', () => {
  assert.deepEqual(mountedWorldSystems({systems:[{system:'economy',label:'Economy'}, {system:'economy'}, {key:'quests'}]}),[
    {key:'economy',label:'Economy'}, {key:'quests',label:'quests'}
  ]);
  assert.deepEqual(mountedWorldSystems({error:'service unavailable'}),[]);
});
test('project deep links preserve correctly named destination parameters', () => {
  const id='world_a-33';
  assert.equal(projectHref('/worldforge',id),'/worldforge?game=world_a-33');
  assert.equal(projectHref('/asset-genesis',id),'/asset-genesis?game=world_a-33');
  assert.equal(projectHref('/compose-scene',id),'/compose-scene?build=world_a-33');
  assert.equal(projectHref('/systems-forge',id),'/systems-forge?build=world_a-33');
  assert.equal(projectHref('/physics-studio',id),'/physics-studio?pid=world_a-33');
  assert.equal(projectHref('/game-kb','../nonsense'),null);
  assert.equal(validProjectId('a'.repeat(129)),'');
  for(const link of worldProjectLinks(id)){
    assert.equal(existsSync(new URL(`../app/${link.href.split('?')[0].slice(1)}.tsx`,import.meta.url)),true);
  }
});
