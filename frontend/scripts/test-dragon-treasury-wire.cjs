'use strict';
// Real crawler product client receives canonical Python-generated fixture JSON.
// Only HTTP transport, authentication and native export hashing are mocked.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {compileFunction}=require('node:vm');
const ts=require('typescript');
const root=path.resolve(__dirname,'..');
const fixture=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));

function load(file,imports={}){
  const result=ts.transpileModule(fs.readFileSync(path.join(root,file),'utf8'),{
    fileName:file,reportDiagnostics:true,compilerOptions:{
      module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}});
  assert.equal(result.diagnostics.filter(d=>d.category===ts.DiagnosticCategory.Error).length,0);
  const module={exports:{}};
  compileFunction(result.outputText,['require','module','exports'])(id=>{
    assert.ok(Object.hasOwn(imports,id),'Unexpected dependency: '+id);return imports[id];
  },module,module.exports);
  return module.exports;
}

function client(initial){
  let payload=structuredClone(initial);
  const requests=[];
  const modules=load('src/product/crawlerClient.ts',{
    'expo-crypto':{CryptoDigestAlgorithm:{SHA256:'SHA256'},digestStringAsync:async()=>{throw Error('Unexpected export');}},
    '../utils/apiBase':{API_BASE:'https://backend.test'},
    '../utils/apiClient':{__esModule:true,default:{get:async(url,options)=>{
      requests.push({url,options});return {ok:true,status:200,data:payload,error:null,rid:'wire-fixture'};
    }}},
    '../auth/gameforgeAuth':{getAuthToken:()=> 'fixture-owner',authHeaders:()=>({Authorization:'Bearer fixture-owner'})},
    './chatErrors':load('src/product/chatErrors.ts'),
    './crawlerPilotReceipt':load('src/product/crawlerPilotReceipt.ts')
  });
  return {requests,read:modules.getDragonTreasury,set:value=>{payload=value;}};
}

async function main(){
  for(const [key,query] of [['normal','magnetometer'],['capped','magnetometer'],['historic','relic'],['at_time','relic']]){
    const expected=fixture[key],f=client(expected);
    const options=key==='at_time'?{observedBefore:expected.observed_before}:{};
    const result=await f.read(expected.mode,query,undefined,undefined,options);
    assert.deepEqual(result,expected);
    assert.ok(f.requests[0].url.includes('/companion/treasury?mode='+expected.mode));
    assert.equal(f.requests[0].options.retries,0);
  }
  const p=fixture.capped;
  assert.equal(p.index_admission,'temporal_query_rerank_v2');
  assert.equal(p.query_admission.scanned_representatives,299);
  assert.equal(p.query_admission.matching_representatives,1);
  assert.equal(p.query_admission.prioritized_representatives,1);
  assert.equal(p.query_admission.score_basis,'permitted_plane_scan_bm25');
  assert.equal(p.hits.length,1);
  assert.ok(p.hits[0].score>0);
  assert.equal(fixture.historic.hits.length,1);
  assert.equal(fixture.historic.hits[0].plane,'historic');
  const f=client(p);
  for(const mutation of [
    q=>{delete q.query_admission;},
    q=>{q.query_admission.scanned_bytes=-1;},
    q=>{q.query_admission.scanned_representatives=300;},
    q=>{q.query_admission.matching_representatives=500;},
    q=>{q.query_admission.prioritized_representatives=193;},
    q=>{q.query_admission.full_structural_corpus=true;},
    q=>{q.query_admission.score_basis='unknown';},
    q=>{q.candidate_limit_reached=false;},
    q=>{q.index_admission='temporal_diversity_v1';},
    q=>{q.hits[0].plane='historic';},
    q=>{q.index_admission='unreviewed_strategy';},
  ]){
    const corrupt=structuredClone(p);mutation(corrupt);f.set(corrupt);
    await assert.rejects(f.read('current_only','magnetometer'),err=>err.kind==='protocol');
  }
  console.log('Canonical treasury Python -> TypeScript: 4 accepted projections, 11 rejected corrupt receipts.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
