import assert from 'node:assert/strict';
import test from 'node:test';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {CREATOR_SCHEMA,CREATOR_MAX_BYTES,CREATOR_MAX_DOCUMENT_BYTES,creatorBytes,canonicalCreatorJSON,normalizeCreatorDocument,
  verifyCreatorProject,normalizeCreatorSummaries,normalizeCreatorHistory,
  createCreatorExport,parseCreatorExport,createCreatorMutation} from '../src/product/dragonCreatorProject.ts';

const hash=async value=>createHash('sha256').update(value,'utf8').digest('hex');
const board=['############',...Array.from({length:8},()=> '#..........#'),'############'];
function document(){return {schema:CREATOR_SCHEMA,title:'The Moss Garden',style:'fixed_screen_puzzle',targets:['pc_linux'],seed:4294967295,
  portable_design:{palette:'vga_dusk',hero:'hatchling',quest_theme:'forest',difficulty:4,stages:1,candidates:8,
    project_notes:'Original garden homebrew',procedural_levels:false,campaign_pathing:'branching',challenge_profile:'balanced'},
  authored_puzzles:[[...board]],cited_brief:{text:'A garden by the sea. 🌿\n作者',citations:[{source_id:'local-notes',revision_digest:'a'.repeat(64),title:'Garden ideas',url:'https://example.org/garden'}]}};}
async function project(){const d=document();return {schema:CREATOR_SCHEMA,project_id:'abcdef12-1234-5678-9012-abcdef123456',version:2,
  document:d,document_sha256:await hash(canonicalCreatorJSON(d)),created_at:'2026-11-20T10:00:00+00:00',updated_at:'2026-11-20T10:01:00+00:00',
  source_only:true,approval_restored:false};}

test('canonical source bytes agree with Python for Unicode, key order and exact bounded integer fields',()=>{
  const d=document();
  const python=execFileSync('python3',['-c','import json,sys; print(json.dumps(json.load(sys.stdin),sort_keys=True,separators=(",",":"),ensure_ascii=False),end="")'],{input:JSON.stringify(d),encoding:'utf8'});
  assert.equal(canonicalCreatorJSON(d),python);
  assert.deepEqual(normalizeCreatorDocument(d),d);
  const reordered=Object.fromEntries(Object.entries(d).reverse());
  assert.equal(canonicalCreatorJSON(reordered),python);
});

test('unfinished authored boards remain savable without invoking solver or granting build authority',()=>{
  const d=document();assert.equal(d.authored_puzzles[0].join('').includes('@'),false);
  assert.deepEqual(normalizeCreatorDocument(d),d);
  for(const field of ['approved','rights_approved','compiled','playtest_passed']){
    assert.equal(normalizeCreatorDocument({...d,[field]:true}),null);
  }
});

test('strict document schema rejects malformed board campaigns, integer coercion and unknown fields',()=>{
  const mutations=[
    d=>d.portable_design.stages=2,d=>d.portable_design.procedural_levels=true,
    d=>d.authored_puzzles[0][0]='bad',d=>d.authored_puzzles[0][1]='#....x.....#',
    d=>d.style='roguelike',d=>d.seed=true,d=>d.seed=NaN,d=>d.seed=4294967296,
    d=>d.portable_design.difficulty=4.5,d=>d.portable_design.candidates=25,
    d=>d.portable_design.palette=['vga_dusk'],d=>d.targets=['pc_linux','pc_linux'],
    d=>d.portable_design.solver_result=true,d=>d.title='../../unsafe',d=>delete d.cited_brief,
  ];
  for(const mutate of mutations){const d=document();mutate(d);assert.equal(normalizeCreatorDocument(d),null,String(mutate));}
});

test('brief references are bounded data and reject malformed or approval-shaped citations',()=>{
  for(const mutate of [d=>d.cited_brief.text='x'.repeat(12001),d=>d.cited_brief.text='\u0000',
    d=>d.cited_brief.citations[0].revision_digest='broken',d=>d.cited_brief.citations[0].url='javascript:alert(1)',
    d=>d.cited_brief.citations[0].approved=true,d=>d.cited_brief.citations=Array.from({length:33},()=>d.cited_brief.citations[0])]){
    const d=document();mutate(d);assert.equal(normalizeCreatorDocument(d),null);
  }
});

test('portable export verifies document integrity and preserves authored source without transport approval',async()=>{
  const original=document(),raw=await createCreatorExport(original,hash);
  assert.deepEqual(await parseCreatorExport(raw,hash),original);
  const envelope=JSON.parse(raw);envelope.document.authored_puzzles[0][2]='#.###......#';
  await assert.rejects(parseCreatorExport(JSON.stringify(envelope),hash),/integrity/);
  envelope.document_sha256=await hash(canonicalCreatorJSON(envelope.document));
  envelope.approval_restored=true;
  await assert.rejects(parseCreatorExport(JSON.stringify(envelope),hash),/not a creator/);
});

test('JSON and import limits reject excessive UTF-8 bytes, invalid Unicode and executable object values',async()=>{
  assert.throws(()=>canonicalCreatorJSON({x:'🌿'.repeat(CREATOR_MAX_BYTES/4)}),/128 KiB/);
  assert.throws(()=>canonicalCreatorJSON({x:'\ud800'}),/Unicode/);
  assert.throws(()=>canonicalCreatorJSON({x:Infinity}));
  const circular={};circular.x=circular;assert.throws(()=>canonicalCreatorJSON(circular));
  await assert.rejects(parseCreatorExport(' '.repeat(CREATOR_MAX_BYTES+1),hash),/128 KiB/);
  await assert.rejects(parseCreatorExport('<html>Login</html>',hash),/valid creator/);
});

test('every accepted near-limit Unicode document retains room for its complete portable export envelope',async()=>{
  function nearLimit(bytes){
    const d=document();d.title='A'.repeat(80);d.targets=['pc_linux','pc_windows','steam_deck'];
    Object.assign(d.portable_design,{palette:'modern_neon',hero:'astronaut',quest_theme:'ancient_ruins',
      difficulty:10,stages:8,candidates:24,project_notes:'A'.repeat(200),challenge_profile:'challenging'});
    d.authored_puzzles=Array.from({length:8},()=>Array.from({length:10},()=>'############'));
    d.cited_brief.text='🌿'.repeat(12000);
    d.cited_brief.citations=Array.from({length:32},()=>({source_id:'a'.repeat(128),revision_digest:'a'.repeat(64),
      title:'a'.repeat(200),url:'https://example.org/'+'a'.repeat(2028)}));
    let remaining=bytes-creatorBytes(canonicalCreatorJSON(d));assert.ok(remaining>=0);
    for(const citation of d.cited_brief.citations){const title=[...citation.title];
      for(let n=0;n<title.length&&remaining;n++){
        const increment=remaining>=3?3:1;title[n]=increment===3?'🌿':'é';remaining-=increment;
      }
      citation.title=title.join('');if(!remaining)break;
    }
    assert.equal(remaining,0);assert.equal(creatorBytes(canonicalCreatorJSON(d)),bytes);return d;
  }
  const d=nearLimit(CREATOR_MAX_DOCUMENT_BYTES);
  assert.deepEqual(normalizeCreatorDocument(d),d);
  const exported=await createCreatorExport(d,hash);
  assert.ok(creatorBytes(exported)<=CREATOR_MAX_BYTES);
  assert.deepEqual(await parseCreatorExport(exported,hash),d);
  assert.equal(normalizeCreatorDocument(nearLimit(CREATOR_MAX_DOCUMENT_BYTES+1)),null);
});

test('saved response requires exact document digest, version, identity and source-only flags',async()=>{
  const p=await project();assert.deepEqual(await verifyCreatorProject(p,hash),p);
  for(const patch of [{document_sha256:'0'.repeat(64)},{project_id:'../../../other'},
    {version:513},{version:true},{source_only:false},{approval_restored:true},{updated_at:'invalid'}]){
    assert.equal(await verifyCreatorProject({...p,...patch},hash),null);
  }
  const altered=structuredClone(p);altered.document.title='Changed peer source';
  assert.equal(await verifyCreatorProject(altered,hash),null);
  assert.equal((await verifyCreatorProject({...p,head_version:3},hash)).version,2);
  assert.equal(await verifyCreatorProject({...p,head_version:1},hash),null);
});

test('library summaries reject duplicate identities and malformed scoped pages rather than filter silently',async()=>{
  const p=await project();const {document:d,...summary}=p;const row={...summary,title:d.title,style:d.style,targets:d.targets};
  assert.deepEqual(normalizeCreatorSummaries([row]),[row]);
  assert.equal(normalizeCreatorSummaries([row,row]),null);
  assert.equal(normalizeCreatorSummaries([{...row,approval_restored:true}]),null);
  assert.equal(normalizeCreatorSummaries(Array.from({length:33},()=>row)),null);
});

test('history rejects foreign, repeated, unordered and future revisions',async()=>{
  const p=await project();const first={version:2,title:p.document.title,document_sha256:p.document_sha256,created_at:p.updated_at};
  const second={...first,version:1};const payload={ok:true,project_id:p.project_id,head_version:2,revisions:[first,second]};
  assert.deepEqual(normalizeCreatorHistory(payload,p.project_id),{head_version:2,revisions:[first,second],next_before_version:null});
  for(const patch of [{project_id:'other'},{head_version:1},{revisions:[first,first]},{revisions:[second,first]}]){
    assert.equal(normalizeCreatorHistory({...payload,...patch},p.project_id),null);
  }
});

test('bounded history pages expose every older revision with strict descending exclusive cursors',async()=>{
  const p=await project();
  const revisions=Array.from({length:512},(_,index)=>({version:512-index,title:p.document.title,
    document_sha256:p.document_sha256,created_at:p.updated_at}));
  const seen=[];let before;
  for(let page=0;page<16;page++){
    const rows=revisions.filter(r=>before===undefined||r.version<before).slice(0,32);
    const cursor=rows.at(-1).version>1?rows.at(-1).version:null;
    const payload={ok:true,project_id:p.project_id,head_version:512,revisions:rows,next_before_version:cursor};
    const normalized=normalizeCreatorHistory(payload,p.project_id,before);
    assert.ok(normalized);assert.equal(normalized.revisions.length,32);
    seen.push(...normalized.revisions.map(r=>r.version));before=normalized.next_before_version??undefined;
  }
  assert.deepEqual(seen,Array.from({length:512},(_,i)=>512-i));
  assert.equal(new Set(seen).size,512);
  const rows=revisions.slice(32,64),payload={ok:true,project_id:p.project_id,head_version:512,revisions:rows,next_before_version:449};
  assert.ok(normalizeCreatorHistory(payload,p.project_id,481));
  for(const patch of [{next_before_version:450},{next_before_version:1},{next_before_version:'449'},
    {next_before_version:null},{revisions:[...rows.slice(0,31),rows[0]]},
    {revisions:rows.filter(r=>r.version!==470)},{revisions:[],next_before_version:449}]){
    assert.equal(normalizeCreatorHistory({...payload,...patch},p.project_id,481),null);
  }
  assert.equal(normalizeCreatorHistory(payload,p.project_id,480),null);
  assert.equal(normalizeCreatorHistory(payload,p.project_id,1),null);
});

test('lost acknowledgement retry retains exact original idempotency body and CAS despite later editing',async()=>{
  const p=await project(),draft=document(),op=createCreatorMutation(draft,'retry-key-123',p);
  const body=op.body;draft.title='New draft after request';draft.authored_puzzles[0][1]='#.###......#';p.version=3;
  assert.equal(op.method,'PUT');assert.equal(op.projectId,p.project_id);assert.equal(op.body,body);
  assert.equal(JSON.parse(op.body).idempotency_key,'retry-key-123');
  assert.equal(JSON.parse(op.body).expected_version,2);
  assert.equal(JSON.parse(op.body).expected_sha256,p.document_sha256);
  assert.equal(op.document.title,'The Moss Garden');assert.equal(op.document.authored_puzzles[0][1],'#..........#');
  assert.throws(()=>createCreatorMutation(document(),'key',{...p,project_id:'../foreign'}),/identity/);
});

test('save-copy drops prior project authority while retaining the entire edited source document',async()=>{
  const d=document(),op=createCreatorMutation(d,'copy-key',null),body=JSON.parse(op.body);
  assert.equal(op.method,'POST');assert.equal(op.projectId,null);assert.deepEqual(body.document,d);
  assert.equal(Object.hasOwn(body,'expected_version'),false);assert.equal(Object.hasOwn(body,'expected_sha256'),false);
});
