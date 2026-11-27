import assert from 'node:assert/strict';
import test from 'node:test';
import {createHash} from 'node:crypto';
import {CREATOR_COMPARISON_SCHEMA,normalizeCreatorComparison} from '../src/product/dragonCreatorComparison.ts';

const digest=value=>createHash('sha256').update(typeof value==='string'?value:JSON.stringify(value)).digest('hex');
const id='abcdef12-1234-5678-9012-abcdef123456';
const fromDigest='a'.repeat(64),toDigest='b'.repeat(64);
const clone=value=>JSON.parse(JSON.stringify(value));
function fixture(){return {ok:true,schema:CREATOR_COMPARISON_SCHEMA,project_id:id,
  from:{version:1,document_sha256:fromDigest},to:{version:2,document_sha256:toDigest},observed_head_version:3,
  changes:{fields:[{path:'title',before:'Original Quest',after:'Revised Quest',before_truncated:false,after_truncated:false,before_sha256:digest('Original Quest'),after_sha256:digest('Revised Quest')}],
    brief:{changed:true,before_preview:'Before',after_preview:'After',before_characters:6,after_characters:5,before_sha256:digest('Before'),after_sha256:digest('After')},
    citations:{before_count:0,after_count:1,order_changed:true,removed:[],added:[{reference_sha256:'c'.repeat(64),source_id:'reference-one',revision_digest:'d'.repeat(64),title:'A design reference',url:'https://example.test/reference',title_truncated:false,url_truncated:false,count:1}]},
    boards:{before_count:1,after_count:1,items:[{stage:1,kind:'modified',changed_cells:1,cells:[[2,3,'#','.']]}]}},
  source_only:true,approval_restored:false};}
const normalize=value=>normalizeCreatorComparison(value,id,1,2,fromDigest,toDigest);

test('comparison is bound to the exact saved pair even after a newer head appears',()=>{
  const raw=fixture(),result=normalize(raw);
  assert.deepEqual(result,raw);assert.equal(result.observed_head_version,3);
  result.changes.fields[0].before='Edited after normalization';
  assert.equal(raw.changes.fields[0].before,'Original Quest');
  assert.equal(result.approval_restored,false);
});

test('foreign, substituted, uncommitted and authority-bearing identities cannot display as this comparison',()=>{
  for(const edit of [value=>value.project_id='bbbbbbbb-1234-5678-9012-abcdef123456',value=>value.from.version=2,
    value=>value.to.document_sha256='f'.repeat(64),value=>value.observed_head_version=1,value=>value.observed_head_version=513,
    value=>value.approval_restored=true,value=>value.source_only=false,value=>value.execution_authorized=true,
    value=>value.from.owner_id='foreign']){const raw=fixture();edit(raw);assert.equal(normalize(raw),null,String(edit));}
});

test('all board tiles are explicit, bounded, unique and preserve add/remove semantics',()=>{
  const raw=fixture();raw.changes.boards={before_count:0,after_count:1,items:[{stage:1,kind:'added',changed_cells:120,
    cells:Array.from({length:120},(_,index)=>[Math.floor(index/12),index%12,null,'.'])}]};
  assert.ok(normalize(raw));
  const removed=clone(raw);removed.changes.boards.before_count=1;removed.changes.boards.after_count=0;
  removed.changes.boards.items[0].kind='removed';removed.changes.boards.items[0].cells=removed.changes.boards.items[0].cells.map(([row,column,before,after])=>[row,column,after,before]);
  assert.ok(normalize(removed),'removing an authored stage also preserves every exact tile change');
  for(const edit of [value=>value.changes.boards.items[0].cells[1]=value.changes.boards.items[0].cells[0],
    value=>value.changes.boards.items[0].cells[0][0]=10,value=>value.changes.boards.items[0].cells[0][1]=12,
    value=>value.changes.boards.items[0].cells[0][2]='#',value=>value.changes.boards.items[0].kind='modified',
    value=>value.changes.boards.items[0].changed_cells=119,value=>value.changes.boards.items[0].cells[0][3]='script']){
    const changed=clone(raw);edit(changed);assert.equal(normalize(changed),null,String(edit));
  }
});

test('citation counts, exact-record membership and reordering cannot hide multiplicity changes',()=>{
  const raw=fixture();raw.changes.citations.added[0].count=2;raw.changes.citations.after_count=2;
  assert.ok(normalize(raw));
  for(const edit of [value=>value.changes.citations.added[0].count=3,
    value=>value.changes.citations.added[0].url='javascript:alert(1)',value=>value.changes.citations.order_changed=false,
    value=>value.changes.citations.removed=[value.changes.citations.added[0]],value=>value.changes.citations.before_count=33]){
    const changed=clone(raw);edit(changed);assert.equal(normalize(changed),null,String(edit));
  }
  raw.changes.citations={before_count:2,after_count:2,order_changed:true,added:[],removed:[]};
  assert.ok(normalize(raw),'existing references can be reordered without fabricated additions');
});

test('brief previews count Unicode code points and keep truncated content distinct from complete source',()=>{
  const raw=fixture();raw.changes.brief.before_preview='🐲'.repeat(240);raw.changes.brief.before_characters=12000;
  assert.ok(normalize(raw));
  raw.changes.brief.before_preview+='🐲';assert.equal(normalize(raw),null);
  raw.changes.brief.before_preview='short';assert.equal(normalize(raw),null);
  raw.changes.brief.before_preview='🐲'.repeat(240);raw.changes.brief.changed=false;assert.equal(normalize(raw),null);
});

test('field changes retain typed values and reject unknown paths, duplicate fields and coercion',()=>{
  for(const [path,before,after] of [['seed',0,4294967295],['targets',['pc_linux'],['pc_windows']],
    ['portable_design.procedural_levels',false,true],['portable_design.difficulty',1,10]]){
    const raw=fixture();raw.changes.fields=[{path,before,after,before_truncated:false,after_truncated:false,before_sha256:'1'.repeat(64),after_sha256:'2'.repeat(64)}];
    assert.ok(normalize(raw));
  }
  for(const edit of [value=>value.changes.fields[0].path='__proto__.approved',value=>value.changes.fields.push(value.changes.fields[0]),
    value=>value.changes.fields[0].before_truncated=true,value=>value.changes.fields[0].after_sha256=value.changes.fields[0].before_sha256,
    value=>{value.changes.fields[0].path='seed';value.changes.fields[0].before=true;}]){
    const raw=fixture();edit(raw);assert.equal(normalize(raw),null,String(edit));
  }
});

test('identical saved source is a valid empty comparison without changing approval',()=>{
  const raw=fixture();raw.to={...raw.from};raw.observed_head_version=1;
  raw.changes={fields:[],brief:{changed:false,before_preview:'',after_preview:'',before_characters:0,after_characters:0,before_sha256:digest(''),after_sha256:digest('')},
    citations:{before_count:0,after_count:0,order_changed:false,added:[],removed:[]},boards:{before_count:0,after_count:0,items:[]}};
  assert.ok(normalizeCreatorComparison(raw,id,1,1,fromDigest,fromDigest));
  raw.to={version:2,document_sha256:toDigest};raw.observed_head_version=2;
  assert.equal(normalize(raw),null,'different source identities cannot silently claim an empty diff');
});
