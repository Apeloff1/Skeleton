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
  vm.runInNewContext(code.outputText,{module,exports:module.exports,require:(name)=>{if(name==='../emeraldAssetPin.json')return require(path.join(root,'../emeraldAssetPin.json'));throw new Error('Unexpected import '+name);},TextDecoder,DataView,Uint8Array},{timeout:2000});
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
