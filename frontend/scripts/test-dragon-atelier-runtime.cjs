'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const root = path.resolve(__dirname,'../src/features/Jeeves/companion/atelier');
function load(name) {
  const code=ts.transpileModule(fs.readFileSync(path.join(root,name+'.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true},reportDiagnostics:true});
  assert.equal(code.diagnostics.filter(d=>d.category===ts.DiagnosticCategory.Error).length,0);
  const module={exports:{}};
  vm.runInNewContext(code.outputText,{module,exports:module.exports,require:(name)=>{if(name==='../emeraldAssetPin.json')return require(path.join(root,'../emeraldAssetPin.json'));if(name==='./evolutionPin.json')return require(path.join(root,'evolutionPin.json'));if(name==='./scholarWingfoldPin.json')return require(path.join(root,'scholarWingfoldPin.json'));throw new Error('Unexpected import '+name);},TextDecoder,DataView,Uint8Array},{timeout:2000});
  return module.exports;
}
const a=load('atelierAsset'), d=load('atelierDirector');
const clips=Array.from({length:380},(_,i)=>'clip_'+i);
const families={ground:clips.slice(0,320),takeoff:clips.slice(320,340),flight:clips.slice(340,360),landing:clips.slice(360)};
const sha='a'.repeat(64);
const doc={asset:{version:'2.0'},buffers:[{byteLength:4}],bufferViews:[{buffer:0,byteLength:4}],nodes:Array.from({length:108},()=>({})),skins:[{joints:Array.from({length:108},(_,i)=>i)}],animations:clips.map(name=>({name}))};
function glb(document) {
  let encoded=Buffer.from(JSON.stringify(document)); encoded=Buffer.concat([encoded,Buffer.alloc((4-encoded.length%4)%4,32)]);
  const data=Buffer.alloc(encoded.length+32);
  data.write('glTF');data.writeUInt32LE(2,4);data.writeUInt32LE(data.length,8);data.writeUInt32LE(encoded.length,12);data.writeUInt32LE(0x4e4f534a,16);encoded.copy(data,20);data.writeUInt32LE(4,20+encoded.length);data.writeUInt32LE(0x004e4942,24+encoded.length);
  return data.buffer.slice(data.byteOffset,data.byteOffset+data.byteLength);
}
function receipt(bytes,overrides={}) { return a.parseReceipt({schema:a.ATELIER_SCHEMA,asset:'emerald_continuum.glb',sha256:sha,bytes,joints:108,clips,families,...overrides},sha); }
test('exact structure and clip family binding',()=>{
  const data=glb(doc),r=receipt(data.byteLength);
  a.inspectBuffer(data,r);
  assert.equal(r.families.ground.length,320);
  assert.equal(Object.isFrozen(r.families),true);
});
test('production pin rejects synthetic receipts and exceeds the obsolete cap',()=>{
  assert.equal(a.PEAK_MODEL_BYTES,463149740);
  assert.ok(a.MAX_MODEL_BYTES>=a.PEAK_MODEL_BYTES);
  assert.throws(()=>a.parsePeakReceipt({schema:a.ATELIER_SCHEMA,asset:'emerald_continuum.glb',sha256:sha,bytes:128,joints:108,clips,families}),/digest/);
});
test('unknown clip, overlapping families, digest, and external texture fail closed',()=>{
  assert.throws(()=>receipt(128,{sha256:'b'.repeat(64)}),/digest/);
  assert.throws(()=>receipt(128,{families:{...families,landing:families.flight}}),/overlapping/);
  const data=glb({...doc,images:[{uri:'https://example.invalid/a.png'}]});
  assert.throws(()=>a.inspectBuffer(data,receipt(data.byteLength)),/resource property/);
});
test('sequence: ground, takeoff, flight, landing, ground; stale finish ignored',()=>{
  let s=d.startDirector(families);
  s=d.setIntent(s,families,true,false);assert.equal(s.step.family,'takeoff');
  const old=s.step.serial;
  s=d.completeStep(s,families,old);assert.equal(s.step.family,'flight');
  assert.equal(d.completeStep(s,families,old),s);
  s=d.setIntent(s,families,false,false);assert.equal(s.step.family,'landing');
  s=d.completeStep(s,families,s.step.serial);assert.equal(s.step.family,'ground');
});
test('intent reversal mid takeoff uses landing and reduced motion immediately grounds',()=>{
  let s=d.setIntent(d.startDirector(families),families,true,false);
  s=d.setIntent(s,families,false,false);assert.equal(s.step.family,'takeoff');
  s=d.completeStep(s,families,s.step.serial);assert.equal(s.step.family,'landing');
  s=d.setIntent(s,families,true,true);assert.equal(s.step.family,'ground');assert.equal(s.airborne,false);
  assert.equal(d.completeStep(s,families,s.step.serial),s);
});
test('capture is presentation only; fire and distillation are not flight',()=>{
  for (const phase of ['snuggle','listening','burning','distilling','celebrating','sleeping']) assert.equal(d.flightIntent({phase,wings:true}),false);
  for (const phase of ['launching','crawling','acquiring']) assert.equal(d.flightIntent({phase,wings:true}),true);
  assert.equal(d.flightIntent({phase:'acquiring',wings:false}),false);
});

test('manual exact clip inspection cannot claim a live event or manufacture a clip',()=>{
  let live=d.setIntent(d.startDirector(families),families,true,false);
  const manual=d.inspectClip(live,families,'landing',families.landing[19],false);
  assert.equal(manual.step.clip,families.landing[19]);
  assert.equal(manual.airborne,false);
  assert.equal(manual.step.repeat,true);
  assert.notEqual(manual.step.serial,live.step.serial);
  assert.throws(()=>d.inspectClip(manual,families,'flight',families.landing[0],false),/does not belong/);
  live=d.resetLive(manual,families,true,false);
  assert.equal(live.step.family,'takeoff');assert.equal(live.airborne,true);
  assert.notEqual(live.step.serial,manual.step.serial);
  assert.equal(d.resetLive(live,families,true,true).step.family,'ground');
});

test('single original-model lease is held through delayed cleanup and cannot release a replacement',()=>{
  const {acquireAtelierLease}=load('atelierLease');
  assert.throws(()=>acquireAtelierLease(2),/less than 4/);
  const old=acquireAtelierLease(undefined);
  assert.throws(()=>acquireAtelierLease(8),/still active/);
  old.release();
  const current=acquireAtelierLease(8);
  old.release();
  assert.throws(()=>acquireAtelierLease(8),/still active/);
  current.release();
  acquireAtelierLease(8).release();
});

test('playback measurements are bounded and exclude background gaps',()=>{
  const {PlaybackMeter,seekTime}=load('atelierPlaybackMeter');
  const m=new PlaybackMeter(3);
  m.observe(0,1);m.observe(10,2);m.observe(30,3);m.observe(70,4);m.observe(120,5);
  const stats=m.read();assert.equal(stats.samples,3);assert.equal(stats.p95IntervalMs,50);assert.equal(stats.slowIntervals,2);
  assert.equal(stats.meanRenderSubmissionMs,4);
  m.observe(2000,1);assert.equal(m.read().samples,0);
  m.observe(2010,2);assert.equal(m.read().samples,1);
  m.reset();assert.equal(m.read().meanIntervalMs,null);
  assert.equal(seekTime(4,.5),2);assert.equal(seekTime(4,-2),0);
  assert.ok(seekTime(4,1)<4);assert.throws(()=>seekTime(0,1),/Invalid clip/);
});

test('weighted lifecycle has six bounded display forms without modifying original pin',()=>{
  const stages=['hatchling','scout','scholar','pathfinder','archivist','hoarder'];
  for(let i=0;i<stages.length;i++){
    assert.equal(a.evolutionStageForLevel(1+i*10),stages[i]);
    assert.equal(a.evolutionStageForLevel(10+i*10),stages[i]);
  }
  assert.equal(a.evolutionStageForLevel(0),null);
  assert.equal(a.evolutionStageForLevel(1.5),null);
  assert.equal(a.evolutionStageForLevel(NaN),null);
  assert.equal(a.evolutionStageForLevel(100), 'hoarder');
  assert.equal(a.expectedVariantBytes('hoarder'),463149740);
});
test('each exact developmental receipt binds its own immutable bytes and growth is never a live family',()=>{
  const p=require(path.join(root,'evolutionPin.json'));
  for(const stage of a.EVOLUTION_STAGES){
    const x=p.forms[stage];
    const row={schema:a.EVOLUTION_SCHEMA,asset:x.asset,stage,sha256:x.sha256,bytes:x.bytes,joints:108,
      clips:[...clips,x.growth],families,growth:x.growth,source_sha256:p.donorSha256};
    const admitted=a.parseEvolutionReceipt(row,stage);
    assert.equal(admitted.clips.length,381);
    assert.equal(admitted.growthClip,x.growth);
    assert.equal(admitted.variant,stage);
    assert.ok(!Object.values(admitted.families).flat().includes(x.growth));
    assert.throws(()=>a.parseEvolutionReceipt({...row,bytes:x.bytes+1},stage),/identity/);
    assert.throws(()=>a.parseEvolutionReceipt({...row,sha256:'b'.repeat(64)},stage),/identity/);
    assert.throws(()=>a.parseEvolutionReceipt({...row,source_sha256:'f'.repeat(64)},stage),/identity/);
    assert.throws(()=>a.parseEvolutionReceipt({...row,clips:[...clips,'wrong-growth']},stage),/growth catalogue/);
    assert.throws(()=>a.parseEvolutionReceipt({...row,stage:'hoarder'},stage),/identity/);
    assert.throws(()=>a.parseVariantReceipt(row,'hoarder'),/Wrong asset/);
  }
});


test('developmental stages may only show explicit frozen poses while clearance is unverified',()=>{
  const {enforceDragonClearanceHold}=load('atelierMotionPolicy');
  for(const stage of ['hatchling','scout','scholar','pathfinder','archivist']){
    for(const intent of [{airborne:true,reduced:false},{airborne:false,reduced:false},
                         {airborne:true,reduced:true}]){
      const result=enforceDragonClearanceHold(stage,intent);
      assert.equal(result.airborne,false);
      assert.equal(result.reduced,true);
      assert.equal(result.mode,'manual-pose-only');
      assert.equal(result.isClearanceHold,true);
      assert.ok(Object.isFrozen(result));
    }
  }
  const original=enforceDragonClearanceHold('hoarder',{airborne:true,reduced:false});
  assert.equal(original.airborne,true);
  assert.equal(original.reduced,false);
  assert.equal(original.mode,'original-event-driven');
  assert.equal(original.isClearanceHold,false);
  assert.equal(enforceDragonClearanceHold('hoarder',{airborne:false,reduced:true}).reduced,true);
});

test('renderer independently enforces developmental hold even if UI omits it',()=>{
  const stage=fs.readFileSync(path.join(root,'atelierStage.web.ts'),'utf8');
  const ui=fs.readFileSync(path.join(root,'AtelierPrototype.web.tsx'),'utf8');
  assert.match(stage,/desired=\{airborne:!receipt\.variant&&airborne,reduced:!!receipt\.variant\|\|reduced\}/);
  assert.match(stage,/let desired=\{airborne:false,reduced:!!receipt\.variant\}/);
  assert.match(ui,/enforceDragonClearanceHold\(variant,intent\.current\)/);
  assert.match(ui,/disabled=\{reducedMotion\|\|variant!=='hoarder'\}/);
  assert.match(ui,/Developmental animation clearance hold:/);
});


test('Scholar wingfold experiment requires independent original SHA, source rig and frozen authority',()=>{
  const p=require(path.join(root,'scholarWingfoldPin.json'));
  const growth='growth-scholar-to-pathfinder';
  const v={schema:a.SCHOLAR_CANDIDATE_SCHEMA,stage:'scholar',candidate:'scholar-wingfold-r1',
    asset:'scholar.glb',bytes:p.bytes,sha256:p.sha256,joints:108,
    clips:[...clips,growth],families,growth,
    source_sha256:p.donorSha256,parent_model_sha256:p.sourceSha256,
    local_z_radians:.18,preliminary_clearance_only:true,
    artist_approved:false,continuous_collision_qualified:false,
    equipment_enabled:false,release_qualified:false};
  const valid=a.parseVariantReceipt(v,'scholar-wingfold-r1');
  assert.equal(valid.variant,'scholar-wingfold-r1');
  assert.equal(valid.experimental,true);
  assert.equal(valid.growthClip,growth);
  assert.equal(valid.sha256,p.sha256);
  assert.equal(valid.clips.length,381);
  assert.equal(a.expectedVariantBytes('scholar-wingfold-r1'),p.bytes);
  assert.equal(a.evolutionStageForLevel(21),'scholar');
  assert.throws(()=>a.parseScholarCandidateReceipt({...v,sha256:'0'.repeat(64)}),/mismatch/);
  assert.throws(()=>a.parseScholarCandidateReceipt({...v,parent_model_sha256:'0'.repeat(64)}),/mismatch/);
  assert.throws(()=>a.parseScholarCandidateReceipt({...v,artist_approved:true}),/mismatch/);
  assert.throws(()=>a.parseScholarCandidateReceipt({...v,equipment_enabled:true}),/mismatch/);
  assert.throws(()=>a.parseScholarCandidateReceipt({...v,release_qualified:true}),/mismatch/);
  assert.throws(()=>a.parseScholarCandidateReceipt({...v,clips:[...clips,'wrong-growth']}),/Missing original clip/);
  assert.throws(()=>a.parseVariantReceipt(v,'scholar'),/identity/);
  const policy=load('atelierMotionPolicy').enforceDragonClearanceHold('scholar-wingfold-r1',{airborne:true,reduced:false});
  assert.equal(policy.mode,'manual-pose-only');
  assert.equal(policy.airborne,false);
  assert.equal(policy.reduced,true);
});
