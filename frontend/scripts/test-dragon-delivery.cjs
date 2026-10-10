const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');const ts=require('typescript');
const root=path.resolve(__dirname,'../features/Jeeves/companion');
const output=ts.transpileModule(fs.readFileSync(path.join(root,'dragonDelivery.ts'),'utf8'),{
 compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022},reportDiagnostics:true});
const mod={exports:{}};vm.runInNewContext(output.outputText,{module:mod,exports:mod.exports});
const api=mod.exports;
const citation={source_id:'source-a',revision_digest:'a'.repeat(64),note_id:'note-a',source_url:'https://example.test/a',title:'Study',mechanic:'movement',statement:'A reviewed abstract mechanic.',stance:'supports',confidence_ppm:950000,dependence_group:'group-a',approval:'wiki_hoag_approved',review_digest:'b'.repeat(64),review_evidence_digest:'c'.repeat(64),approval_evidence_digest:'d'.repeat(64),expires_at:500};
assert.ok(api.normalizeDeliveryCitations([citation]));
for(const c of [{...citation,source_url:'javascript:alert(1)'},{...citation,approval_evidence_digest:null},{...citation,confidence_ppm:1000001},{...citation,stance:'true'},null])assert.equal(api.normalizeDeliveryCitations([c]),null);
const design=api.starterDeliveryDesign();assert.equal(design.stages,1);assert.equal(design.candidates,1);
assert.equal(api.starterDeliveryDesign('pc_windows').stages,4);
const brief={schema:'skeleton.dragon.delivery_brief.v1',owner:'alice',design,plan_digest:'d'.repeat(64),design_digest:'e'.repeat(64),knowledge_root:'f'.repeat(64),query:'movement',prepared_at:100,expires_at:400,citations:[citation,{...citation,source_id:'source-b',dependence_group:'group-b'}],independent_groups:2,blockers:[],conflicts:[],ready_for_source_generation:true,controls:{effective:['seed'],metadata_only:['hero'],cartridge_single_stage:true},toolchain:'RGBDS',output_extension:'gb',compiler_adapter_available:true,build_state:'not_built',gameplay_state:'not_verified',training_authorized:false,release_authorized:false};
assert.ok(api.normalizeDeliveryBrief(brief,101));
for(const b of [{...brief,expires_at:100},{...brief,prepared_at:200},{...brief,expires_at:401},{...brief,ready_for_source_generation:false},{...brief,blockers:['expired']},{...brief,independent_groups:1},{...brief,release_authorized:true},{...brief,gameplay_state:'verified'},{...brief,citations:[{...citation,approval:'source_reviewed_only'}]}])assert.equal(api.normalizeDeliveryBrief(b,101),null);
const counts=Object.fromEntries(['discovered_sources','almanacs','reviewed_sources','reviewed_notes','wiki_reviews','approved_mechanics','current_memory_cards','pending_recrawls','source_targets','catalog_targets','compiler_adapters'].map(k=>[k,0]));
const overview={schema:'skeleton.dragon.delivery_overview.v1',owner:'alice',knowledge_root:'f'.repeat(64),overall_completion_percent:null,counts,resource_runtime_ready:false,practice_storage_ready:true,memory_reconciliation_required:false,training_authorized:false,release_authorized:false,acquisition:[],next_actions:[]};
assert.ok(api.normalizeDeliveryOverview(overview));
assert.equal(api.normalizeDeliveryOverview({...overview,overall_completion_percent:100}),null);
assert.equal(api.normalizeDeliveryOverview({...overview,counts:{...counts,reviewed_sources:-1}}),null);
assert.equal(api.normalizeDeliveryAlmanacs([{topic_id:'t',headers:['Engineering'],discovered_sources:2,machine_learning_records:0}]).length,1);
for(const name of ['DragonDeliveryWorkbench.tsx','useDragonDelivery.ts']){
const r=ts.transpileModule(fs.readFileSync(path.join(root,name),'utf8'),{fileName:name,reportDiagnostics:true,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}});
assert.equal(r.diagnostics.filter(d=>d.category===ts.DiagnosticCategory.Error).length,0);
}
console.log('Dragon delivery: cited brief, controls, expiry, authority, overview and UI syntax passed');
