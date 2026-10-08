/**
 * Exercise the real authoring catalogue with TypeScript compilation.
 * This protects truthful event-driven state and phase-specific visual comfort.
 */
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const ts=require('typescript');
const root=path.resolve(__dirname,'../features/Jeeves/companion');
function transpile(name){
 const content=fs.readFileSync(path.join(root,name),'utf8');
 const result=ts.transpileModule(content,{fileName:name,reportDiagnostics:true,
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}});
 const errors=(result.diagnostics||[]).filter(d=>d.category===ts.DiagnosticCategory.Error);
 assert.equal(errors.length,0,name+' syntactic errors: '+errors.map(x=>ts.flattenDiagnosticMessageText(x.messageText,' ')).join(' | '));
 return {content,code:result.outputText};
}
const authored=transpile('dragonChoreography.ts');
const scope={exports:{}};
vm.runInNewContext(authored.code,{module:scope,exports:scope.exports,Math,Number,Object,Array},
 {timeout:1500,filename:'dragonChoreography.js'});
const {DRAGON_BEATS,DRAGON_CHOREOGRAPHY_COUNT,directDragon}=scope.exports;
const phases=['snuggle','listening','curious','launching','crawling','acquiring','burning','distilling','celebrating','sleeping'];
assert.equal(DRAGON_CHOREOGRAPHY_COUNT,120,'120 hand-authored beats are required');
assert.deepEqual(Object.keys(DRAGON_BEATS).sort(),[...phases].sort());
for(const phase of phases){
 const variants=DRAGON_BEATS[phase];
 assert.equal(variants.length,12,phase+' should have 12 meaningful moments');
 assert.ok(new Set(variants.map(x=>x.thought)).size>=10,phase+' repetitive captions');
 for(const tick of [0,1,2,9,11,12,29]){
  const flags={phase,fire:phase==='burning',glasses:phase==='distilling',
   snuggly:phase==='snuggle'||phase==='sleeping',embers:phase==='burning'};
  const full=directDragon(flags,'full',tick,false);
  assert.equal(full.beat,variants[tick%12]);
  assert.equal(full.animated,true);
  assert.ok(full.layers<=4,'unbounded visual effects');
  assert.ok(full.tempoMs>=2000,'no flashing rapid beat cycle');
  const gentle=directDragon(flags,'gentle',tick,false);
  assert.ok(gentle.layers<=2,'gentle exceeded particle budget');
  assert.ok(gentle.amplitude<full.amplitude);
  const off=directDragon(flags,'off',tick,false);
  const os=directDragon(flags,'full',tick,true);
  for(const quiet of [off,os]){
   assert.equal(quiet.animated,false);
   assert.equal(quiet.amplitude,0);
   assert.equal(quiet.layers,0);
  }
 }
}
for(const name of ['useDragonLife.ts','DragonAtmosphere.tsx','DragonCompanion.tsx','DragonCompanionPanel.tsx'])transpile(name);
const life=fs.readFileSync(path.join(root,'useDragonLife.ts'),'utf8');
const component=fs.readFileSync(path.join(root,'DragonCompanion.tsx'),'utf8');
const panel=fs.readFileSync(path.join(root,'DragonCompanionPanel.tsx'),'utf8');
assert.ok(life.includes("AppState.addEventListener('change'"),'background work must stop');
assert.ok(life.includes('useNativeDriver:true'),'no JS frame loop');
assert.ok(life.includes('loops.forEach(a=>a.stop())'),'cleanup required');
assert.ok(life.includes('reducedMotion'),'respect OS preferences');
assert.ok(component.includes('DragonAtmosphere')&&component.includes('life.pet'),'scene and touch reaction must render');
assert.ok(panel.includes('motion={motion}')&&panel.includes('skeleton.dragon.motion.v1'),'gentle/off prefs must reach animator and persist');
assert.ok(panel.includes('never start research or change memory'),'pet interactions must remain cosmetic');
console.log('Dragon life: 120 real phase beats, 10 phases, bounded motion, reduced-motion and syntax checks passed.');
