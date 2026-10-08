/* Ensure Dragon RPG progression is receipt-driven rather than decorative. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const ts=require('typescript');
const dir=path.resolve(__dirname,'../features/Jeeves/companion');
const load=(name)=>{
 const source=fs.readFileSync(path.join(dir,name),'utf8');
 const result=ts.transpileModule(source,{fileName:name,reportDiagnostics:true,
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,
    jsx:ts.JsxEmit.ReactJSX}});
 const errors=(result.diagnostics||[]).filter(d=>d.category===ts.DiagnosticCategory.Error);
 assert.equal(errors.length,0,name+' invalid TS: '+errors.map(x=>ts.flattenDiagnosticMessageText(x.messageText,' ')).join(','));
 return {source,code:result.outputText};
};
const model=load('dragonProgression.ts');
const module={exports:{}};
vm.runInNewContext(model.code,{module,exports:module.exports,Math,Array,Number,Set,Object},
 {filename:'dragonProgression.js',timeout:1500});
const m=module.exports;
const proof={
 schema:'skeleton.ai.dragon.practice_progress.v1',level:2,xp:85,next_level_xp:225,
 verified_lessons:1,demos_built:4,demos_reviewed:1,demo_attempts:4,
 failed_attempts:0,skills:{research:4,game_design:8,prototyping:12,verification:6},
 unlocked:['little_explorer','apprentice_forge'],
};
assert.equal(m.validateDragonProgress(proof).xp,85);
assert.equal(m.dragonRank(2),'Apprentice Forge');
assert.equal(m.levelFraction(proof),10/150);
for(const mutation of [
 {...proof,level:99},
 {...proof,xp:8000},
 {...proof,level:2,demos_reviewed:8},
 {...proof,skills:{...proof.skills,game_design:Infinity}},
 {...proof,schema:'unsafe'},
 {...proof,unlocked:['a'.repeat(200)]},
 ]){
 assert.equal(m.validateDragonProgress(mutation),null,'forged progression was accepted');
}
const goodAttempt={
 attempt_id:'a'.repeat(64),lesson_id:'b'.repeat(64),kind:'jump_lab',
 state:'built',artifact_digest:'c'.repeat(64),
 supported:['movement','platforming'],deferred:[],
};
assert.equal(m.normalizeDragonAttempts([goodAttempt,{...goodAttempt,state:'fictional'}]).length,1);
for(const name of ['DragonQuestBoard.tsx','DragonCompanion.tsx','DragonCompanionPanel.tsx']){
 const result=load(name);
 if(name==='DragonQuestBoard.tsx'){
  assert.ok(result.source.includes('No autonomous work without approval'));
  assert.ok(result.source.includes('onRunPractice'));
  assert.ok(result.source.includes('connect'));
 }
 if(name==='DragonCompanion.tsx')assert.ok(result.source.includes('levelBadge'));
}
const panel=fs.readFileSync(path.join(dir,'DragonCompanionPanel.tsx'),'utf8');
assert.ok(panel.includes('<DragonQuestBoard'), 'academy must actually render in companion');
assert.ok(panel.includes('validateDragonProgress'), 'untrusted progress may not drive character costume');
console.log('Dragon RPG: validated tiers, badges, honest XP, normalized attempt history and UI syntax.');
