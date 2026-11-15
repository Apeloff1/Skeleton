'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {compileFunction}=require('node:vm');
const ts=require('typescript');
const source=fs.readFileSync(path.join(__dirname,'../src/features/Jeeves/dragonVaultScan.ts'),'utf8');
const compiled=ts.transpileModule(source,{reportDiagnostics:true,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}});
assert.equal(compiled.diagnostics.filter(x=>x.category===ts.DiagnosticCategory.Error).length,0);
const moduleObject={exports:{}};
compileFunction(compiled.outputText,['require','module','exports'])(()=>{throw Error('Unexpected import');},moduleObject,moduleObject.exports);
const {appendChamberPage,scanArchiveChambers,bestHistoryWindow}=moduleObject.exports;
const digest='a'.repeat(64), time=1800000000;
function page(offset=0,total=128){
 const n=Math.min(8,total-offset),matches=Array.from({length:n},(_,i)=>{
   const k=offset+i;return {session_id:'chamber-'+String(k).padStart(3,'0'),version:1,valid_until:time+90,
     eligible_sources:2,matched_sources:1,distinct_matching_payloads:1,
     matched_terms:k===127?3:k%2+1,best_source_terms:k===127?3:1,scanned_bytes:200};
 });
 return {schema:'skeleton.dragon.vault-discovery.v1',scope_digest:digest,as_of_unix:time,
  earliest_expiry:n?time+90:null,catalogue_size:total,page_offset:offset,scanned_sessions:n,
  query_terms:3,qualified:n,no_grant:0,held:0,eligible_sources:n*2,scanned_bytes:n*200,matches,
  next_cursor:offset+n<total?digest+':'+(offset+n):null,page_local_ranking:true,
  source_text_returned:false,network_executed:false,model_context_permission:false};
}
function harness(mutate=(p)=>p){
 let t=1000,calls=0,owner=true;const abort=new AbortController(),progress=[];
 const options={signal:abort.signal,ownerCurrent:()=>owner,now:()=>t,onProgress:(n,total)=>progress.push([n,total])};
 return {options,progress,abort,detach:()=>{owner=false;},setTime:n=>{t=n;},calls:()=>calls,read:async(q,cursor,signal)=>{
   assert.equal(q,'magnetometer');assert.equal(signal,abort.signal);
   t+=50;calls++;return mutate(page(cursor?Number(cursor.split(':')[1]):0),calls);
 }};
}
async function main(){
 const h=harness(),scan=await scanArchiveChambers(h.read,'magnetometer',h.options);
 assert.equal(h.calls(),17);assert.equal(scan.pages,16);assert.equal(scan.scanned,128);
 assert.equal(scan.matches[0].session_id,'chamber-127');assert.equal(scan.matches.length,128);
 assert.equal(scan.eligibleSources,256);assert.equal(scan.scannedBytes,25600);
 assert.deepEqual(h.progress.at(-1),[128,128]);
 const ids=bestHistoryWindow(scan,h.options.now());assert.equal(ids.length,32);assert.ok(ids.includes('chamber-127'));
 assert.throws(()=>bestHistoryWindow(scan,scan.expiresMonotonic),/expired/);
 const empty=harness(()=>page(0,0));const e=await scanArchiveChambers(empty.read,'magnetometer',empty.options);
 assert.equal(empty.calls(),2);assert.equal(e.matches.length,0);assert.deepEqual(bestHistoryWindow(e,empty.options.now()),[]);
 const a=appendChamberPage(null,page(),0,10,60000);
 assert.throws(()=>appendChamberPage(a,{...page(8),scope_digest:'b'.repeat(64)},10,20,60000),/changed/);
 const duplicate=page(8);duplicate.matches[0]=page().matches[0];
 assert.throws(()=>appendChamberPage(a,duplicate,10,20,60000),/repeated/);
 assert.throws(()=>appendChamberPage(a,page(16),10,20,60000),/changed/);
 assert.throws(()=>appendChamberPage(null,{...page(),earliest_expiry:time+.001},0,20,60000),/expired/);
 const changed=harness((p,n)=>n===17?{...p,scope_digest:'c'.repeat(64)}:p);
 await assert.rejects(scanArchiveChambers(changed.read,'magnetometer',changed.options),/changed/);
 const changedVersion=harness((p,n)=>{if(n===17)p.matches[0].version++;return p;});
 await assert.rejects(scanArchiveChambers(changedVersion.read,'magnetometer',changedVersion.options),/changed/);
 const detach=harness((p,n)=>{if(n===3)detach.detach();return p;});
 await assert.rejects(scanArchiveChambers(detach.read,'magnetometer',detach.options),/detached/);assert.equal(detach.calls(),3);
 const cancel=harness((p,n)=>{if(n===2)cancel.abort.abort();return p;});
 await assert.rejects(scanArchiveChambers(cancel.read,'magnetometer',cancel.options),/detached/);assert.equal(cancel.calls(),2);
 const timeout=harness((p,n)=>{if(n===2)timeout.setTime(62000);return p;});
 await assert.rejects(scanArchiveChambers(timeout.read,'magnetometer',timeout.options),/time window/);
 const revoked=harness((p,n)=>{if(n===2)p.earliest_expiry=time+.01;return p;});
 await assert.rejects(scanArchiveChambers(revoked.read,'magnetometer',revoked.options),/expired/);
 console.log('Archive-wide chamber discovery: 128 positions, 17 reads, ranked historical handoff, expiry and cancellation fences.');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
