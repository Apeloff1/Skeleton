'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');
const root=path.resolve(__dirname,'../src/features/Jeeves');
function load(file){
 const source=fs.readFileSync(path.join(root,file),'utf8');
 const transpiled=ts.transpileModule(source,{fileName:file,reportDiagnostics:true,
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}});
 assert.equal(transpiled.diagnostics.filter(d=>d.category===ts.DiagnosticCategory.Error).length,0,file);
 const module={exports:{}};
 if(!file.endsWith('.tsx')&&!file.includes('useDragonLife'))vm.runInNewContext(transpiled.outputText,{module,exports:module.exports,Math,Number,Array,Object},{timeout:1500});
 return {source,exports:module.exports};
}
const {dragonLevelProfile,evidenceLevel}=load('companion/dragonLevelProfile.ts').exports;
const {evolutionRitual,evolutionPetReaction}=load('companion/dragonEvolutionRituals.ts').exports;
const {DRAGON_POSES}=load('companion/dragonGesturePoses.ts').exports;
const phases=['snuggle','sleeping','listening','curious','launching','crawling','acquiring','celebrating','burning','distilling'];
const fallback={gesture:'blink',thought:'Existing authored beat'};
let prior=0;
for(let stage=0;stage<6;stage++){
 const early=dragonLevelProfile(stage*10+1,stage,'sleeping');
 const grown=dragonLevelProfile(stage*10+10,stage,'sleeping');
 assert.ok(grown.breathMs>=early.breathMs);
 assert.ok(grown.blinkMs>=early.blinkMs);
 assert.ok(grown.scale>=prior);
 prior=grown.scale;
 const earlyBeats=new Set(),grownBeats=new Set();
 for(let n=0;n<12;n++){
  earlyBeats.add(evolutionRitual(early,'sleeping',n,fallback).thought);
  grownBeats.add(evolutionRitual(grown,'sleeping',n,fallback).thought);
 }
 assert.ok(grownBeats.size>earlyBeats.size,'actual stage repertoire should unlock gradually');
 assert.ok(grownBeats.size<=6);
 for(let level=stage*10+1;level<=stage*10+10;level++){
  for(const phase of phases){
   const p=dragonLevelProfile(level,stage,phase);
   assert.ok(p.amplitude<=1&&p.amplitude>=0&&p.treasure<=6);
   assert.ok(p.beatMs>=3000&&p.blinkMs>=4000);
   for(let tick=0;tick<12;tick++){
    const beat=evolutionRitual(p,phase,tick,fallback);
    assert.ok(DRAGON_POSES[beat.gesture],beat.gesture+' must use real physical pose');
    if(phase==='burning'||phase==='distilling')assert.equal(beat,fallback);
   }
   assert.ok(evolutionPetReaction(p,level).length>0);
  }
 }
}
for(let i=0;i<=1000;i++){
 const level=evidenceLevel(i);
 assert.ok(level>=1&&level<=50);
 if(i>0)assert.ok(level>=evidenceLevel(i-1));
}
assert.ok(evolutionPetReaction(dragonLevelProfile(60,5,'sleeping'),1).includes('Hoarder'));
assert.equal(dragonLevelProfile(60,5,'snuggle').treasure,6);
const actor=load('companion/DragonCompanion.tsx').source;
const hook=load('companion/useDragonLife.ts').source;
const treasury=load('DragonTreasuryPanel.tsx').source;
assert.ok(actor.includes('life.profile.wingScale')&&actor.includes('treasuryScene'));
assert.ok(hook.includes('evolutionRitual(profile,state.phase')&&hook.includes('evolutionPetReaction(profile,count)'));
assert.ok(hook.includes("AppState.addEventListener('change'")&&hook.includes('loops.forEach(a=>a.stop())'));
assert.ok(treasury.includes('evolutionStage={evolution.stage}')&&treasury.includes('level={evolution.level}'));
assert.ok(treasury.includes('getTreasuryPassage')&&treasury.includes('passage.span_sha256'));
console.log('Hoarder motion: all 60 levels, all 10 phases, deterministic physical gestures and staged cozy reactions qualified.');
