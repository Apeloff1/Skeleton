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
    },post:async(url,body,options)=>{
      requests.push({url,body,options});return {ok:true,status:200,data:payload,error:null,rid:'wire-fixture'};
    }}},
    '../auth/gameforgeAuth':{getAuthToken:()=> 'fixture-owner',authHeaders:()=>({Authorization:'Bearer fixture-owner'})},
    './chatErrors':load('src/product/chatErrors.ts'),
    './crawlerPilotReceipt':load('src/product/crawlerPilotReceipt.ts')
  });
  return {requests,read:modules.getDragonTreasury,readVault:modules.getDragonVault,
    quota:modules.getDragonVaultQuota,discover:modules.discoverDragonVault,
    retire:modules.retireDragonSession,restore:modules.restoreDragonVaultPrimary,redundancy:modules.getDragonVaultRedundancy,repairReplica:modules.repairDragonVaultReplica,set:value=>{payload=value;}};
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
  const healthy=structuredClone(p);
  healthy.index_health={active_grants:2,qualified_segments:1,missing_segments:1,
    stale_segments:0,invalid_segments:0,eligible_archive_members:12,materialized_archive_members:7};
  const healthClient=client(healthy);
  assert.deepEqual((await healthClient.read('current_only','magnetometer')).index_health,healthy.index_health);
  for(const patch of [{active_grants:1},{materialized_archive_members:13},{missing_segments:-1},{stale_segments:1}]){
    const bad=structuredClone(healthy);Object.assign(bad.index_health,patch);
    healthClient.set(bad);
    await assert.rejects(healthClient.read('current_only','magnetometer'),err=>err.kind==='protocol');
  }
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
  const vault=fixture.vault,vc=client(vault),selection=vault.vault_window;
  assert.deepEqual(await vc.read('historic_only','magnetometer',undefined,undefined,{vaultSessions:selection}),vault);
  assert.ok(vc.requests[0].url.includes('vault_sessions='+selection.join(',')));
  assert.equal(vault.current_indexed,0);
  assert.equal(vault.evolution.expedition_growth,0);
  for(const change of [
    v=>{v.vault_window=['other'];},v=>{v.current_indexed=1;},
    v=>{v.evolution.expedition_growth=100;},v=>{v.revisit_plan=['a'.repeat(64)];},
    v=>{v.hits[0].session_id='other';},v=>{v.hits[0].archive_only=false;},
    v=>{v.family_rows[0].refresh_url='https://example.org/';}
  ]){
    const bad=structuredClone(vault);change(bad);vc.set(bad);
    await assert.rejects(vc.read('historic_only','magnetometer',undefined,undefined,{vaultSessions:selection}),e=>e.kind==='protocol');
  }
  await assert.rejects(vc.read('current_only','',undefined,undefined,{vaultSessions:selection}),e=>e.kind==='protocol');
  await assert.rejects(vc.read('historic_only','',undefined,undefined,{vaultSessions:['same','same']}),e=>e.kind==='protocol');
  const state={state:'vaulted',accepted_at:1700000000,active_slot_released:true,snapshot_digest:'a'.repeat(64),
    execution_authorized:false,historical_grant_extended:false};
  const page={schema:'skeleton.dragon.vault-catalog.v1',sessions:[
    {session_id:'vaulted-fixture',version:3,vault:state,archive_expires_at:null,legacy_runtime:false,integrity_held:false}],
    next_cursor:null,capacity:128,as_of_unix:1800000000,archive_use_verified:false,network_executed:false};
  vc.set(page);assert.deepEqual(await vc.readVault(),page);
  for(const patch of [{capacity:129},{archive_use_verified:true},{next_cursor:'vaulted-fixture'}]){
    vc.set({...page,...patch});await assert.rejects(vc.readVault(),e=>e.kind==='protocol');
  }
  const receipt={schema:'skeleton.dragon.vault-command.v1',session_id:'vaulted-fixture',version:3,
    vault:state,outcome:'vaulted',network_executed:false};
  const command={expected_version:1,idempotency_key:'test-retire',retention_acknowledged:true};
  vc.set(receipt);assert.deepEqual(await vc.retire('vaulted-fixture',command),receipt);
  vc.set({...receipt,vault:{...state,active_slot_released:false}});
  await assert.rejects(vc.retire('vaulted-fixture',command),e=>e.kind==='protocol');
  const quota={schema:'skeleton.dragon.vault-quota.v1',as_of_unix:1800000000,active_reserved:3,vault_reserved:2,
    distinct_reserved:4,dual_reserved:1,active_capacity:32,vault_capacity:128,active:1,vaulted:1,in_transit:1,
    tombstoned:0,missing:1,integrity_held:0,missing_auto_reclaimed:false,source_records_erased:false,read_only:true};
  vc.set(quota);assert.deepEqual(await vc.quota(),quota);
  for(const patch of [{dual_reserved:2},{missing:0},{missing_auto_reclaimed:true},{vault_reserved:129}]){
    vc.set({...quota,...patch});await assert.rejects(vc.quota(),e=>e.kind==='protocol');
  }
  const discovery={schema:'skeleton.dragon.vault-discovery.v1',scope_digest:'e'.repeat(64),as_of_unix:1800000000,
    earliest_expiry:1800000100,catalogue_size:12,page_offset:0,scanned_sessions:8,query_terms:2,
    qualified:1,no_grant:6,held:1,eligible_sources:3,scanned_bytes:900,
    matches:[{session_id:'vaulted-fixture',version:3,valid_until:1800000100,eligible_sources:3,
      matched_sources:2,distinct_matching_payloads:1,matched_terms:2,best_source_terms:1,scanned_bytes:900}],
    next_cursor:'e'.repeat(64)+':8',page_local_ranking:true,source_text_returned:false,network_executed:false,model_context_permission:false};
  vc.set(discovery);assert.deepEqual(await vc.discover('optical magnetometer'),discovery);
  for(const mutate of [
    x=>{x.next_cursor='a'.repeat(64)+':8';},x=>{x.qualified=2;},x=>{x.matches[0].matched_sources=4;},
    x=>{x.matches[0].valid_until=x.as_of_unix;},x=>{x.model_context_permission=true;},
    x=>{x.matches[0].distinct_matching_payloads=3;},x=>{x.matches[0].scanned_bytes=901;},
  ]){const bad=structuredClone(discovery);mutate(bad);vc.set(bad);await assert.rejects(vc.discover('optical'),e=>e.kind==='protocol');}
  const repair={schema:'skeleton.dragon.vault-restore.v1',session_id:'vaulted-fixture',version:2,
    outcome:'restored',snapshot_digest:'a'.repeat(64),ancestor_rollback:false,capture_consent_extended:false,
    historical_grant_extended:false,network_executed:false,model_context_permission:false};
  vc.set(repair);assert.deepEqual(await vc.restore('vaulted-fixture',command),repair);
  for(const patch of [{ancestor_rollback:true},{capture_consent_extended:true},{historical_grant_extended:true},
    {model_context_permission:true},{version:1},{snapshot_digest:'wrong'}]){
    vc.set({...repair,...patch});await assert.rejects(vc.restore('vaulted-fixture',command),e=>e.kind==='protocol');
  }
  const redundancy={schema:'skeleton.dragon.vault-redundancy.v1',session_id:'vaulted-fixture',version:2,as_of_unix:1800000000,
    state:'repairable_primary',primary:'held',replica:'exact',snapshot_digest:'a'.repeat(64),independent_backup:false,
    read_only:true,source_text_returned:false,historical_grant_extended:false,network_executed:false};
  vc.set(redundancy);assert.deepEqual(await vc.redundancy('vaulted-fixture'),redundancy);
  for(const patch of [{state:'redundant'},{independent_backup:true},{source_text_returned:true},{snapshot_digest:null}]){
    vc.set({...redundancy,...patch});await assert.rejects(vc.redundancy('vaulted-fixture'),e=>e.kind==='protocol');
  }
  const duplicate={schema:'skeleton.dragon.vault-replica-repair.v1',session_id:'vaulted-fixture',version:2,
    outcome:'repaired',snapshot_digest:'a'.repeat(64),primary_rewritten:false,witness_rewritten:false,
    historical_grant_extended:false,network_executed:false,independent_backup:false};
  vc.set(duplicate);assert.deepEqual(await vc.repairReplica('vaulted-fixture',command),duplicate);
  for(const patch of [{primary_rewritten:true},{witness_rewritten:true},{historical_grant_extended:true},{version:1}]){
    vc.set({...duplicate,...patch});await assert.rejects(vc.repairReplica('vaulted-fixture',command),e=>e.kind==='protocol');
  }
  console.log('Treasury and cold custody: canonical wire parity, archive windows, quota, discovery and bidirectional exact-copy repair.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
