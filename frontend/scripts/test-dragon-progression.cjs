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
const sandboxModule={exports:{}};
vm.runInNewContext(model.code,{module:sandboxModule,exports:sandboxModule.exports,Math,Array,Number,Set,Object},
 {filename:'dragonProgression.js',timeout:1500});
const m=sandboxModule.exports;
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
for(const name of ['DragonDemoPlayer.tsx','useDragonAcademy.ts','DragonNativeWorkshop.tsx'])load(name);
const nativeModel=load('dragonNativeTargets.ts');
const nativeExports={exports:{}};
vm.runInNewContext(nativeModel.code,{module:nativeExports,exports:nativeExports.exports,
 Math,Array,Number,Set,Object}, {filename:'dragonNativeTargets.js',timeout:1500});
const n=nativeExports.exports;
const gb={id:'game_boy',family:'Nintendo',generation:'8-bit handheld',year:1989,
 cpu:'SM83',graphics:'OAM tiles',sound:'PSG',input:'D-pad',toolchain:'RGBDS',
 output:'gb',status:'native_source'};
assert.equal(n.normalizeNativeTargets([gb]).length,1);
assert.equal(n.normalizeNativeTargets([{...gb,status:'phantom'}]).length,0);
assert.equal(n.titleCaseId('game_boy'),'Game Boy');
const curriculum={owner:'a'.repeat(64),curriculum_level:1,
 native_source_attempts:0,unlocked:[],blocked:[],structural_build_targets:[],
 next_recommendation:null,proof_scope:'structural ROM only',
 schema:'skeleton.ai.dragon.native_curriculum.v1'};
assert.ok(n.normalizeNativeCurriculum(curriculum));
assert.equal(n.normalizeNativeCurriculum({...curriculum,owner:'bad'}),null);
const source=fs.readFileSync(path.join(dir,'DragonNativeWorkshop.tsx'),'utf8');
assert.ok(source.includes('Native game forge')&&source.includes('Generate native game source ZIP'));
assert.ok(source.includes('Adaptive native acquisition'));
assert.ok(source.includes('Generate suggested practice game'));
const nativeHook=fs.readFileSync(path.join(dir,'useDragonAcademy.ts'),'utf8');
assert.ok(nativeHook.includes("'/native/generate'")&&nativeHook.includes("'/archive'"));
assert.ok(nativeHook.includes("'/native/curriculum/generate'")&&
 nativeHook.includes("'/native/curriculum'"));
assert.ok(nativeHook.includes('adaptive:true'), 'new opt-in practice uses evidence-gated curriculum');
assert.ok(nativeHook.includes('Crypto.digest(')&&nativeHook.includes('Sharing.shareAsync('));

const demoPlayer=fs.readFileSync(path.join(dir,'DragonDemoPlayer.tsx'),'utf8');
const hook=fs.readFileSync(path.join(dir,'useDragonAcademy.ts'),'utf8');
const workspace=fs.readFileSync(path.resolve(dir,'../ChatWorkspace.tsx'),'utf8');
assert.ok(hook.includes('checkMe()')&&hook.includes('getAuthToken()'), 'authenticated academy only');
assert.ok(hook.includes('authHeaders()')&&hook.includes('digestStringAsync'), 'bearer auth and demo hash verification');
assert.ok(demoPlayer.includes('onShouldStartLoadWithRequest')&&
 demoPlayer.includes('incognito')&&demoPlayer.includes('allowFileAccess={false}'), 'game must stay isolated');
assert.ok(workspace.includes('useDragonAcademy()')&&
 workspace.includes('DragonDemoPlayer'), 'real Jeeves app must mount the practice client');
assert.ok(!hook.includes('grantXP')&&!hook.includes('incrementXP'), 'client may not mint skill XP');
const panel=fs.readFileSync(path.join(dir,'DragonCompanionPanel.tsx'),'utf8');
assert.ok(panel.includes('<DragonQuestBoard'), 'academy must actually render in companion');
assert.ok(panel.includes('validateDragonProgress'), 'untrusted progress may not drive character costume');
console.log('Dragon RPG: progression, authenticated host binding, sandboxed playable UI and syntax checks.');
