'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ts=require('typescript');
const base=path.resolve(__dirname,'../src/features/Jeeves');
const read=name=>fs.readFileSync(path.join(base,name),'utf8');
test('prototype sources compile syntactically and both crawler surfaces mount the local viewer',()=>{
  for(const name of ['companion/atelier/AtelierPrototype.tsx','companion/atelier/AtelierPrototype.web.tsx','companion/atelier/atelierStage.web.ts','CrawlerWorkspace.tsx','CrawlerReleasePrototype.tsx']){
    const output=ts.transpileModule(read(name),{fileName:name,compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX},reportDiagnostics:true});
    const errors=output.diagnostics.filter(d=>d.category===ts.DiagnosticCategory.Error);
    assert.equal(errors.length,0,name+': '+errors.map(e=>ts.flattenDiagnosticMessageText(e.messageText,' ')).join(' | '));
  }
  assert.match(read('CrawlerWorkspace.tsx'),/<AtelierPrototype key=.{1,120}active\.session_id/);
  assert.match(read('CrawlerReleasePrototype.tsx'),/getCrawlEvents\(atelierSessionId,abort.signal\)/);
  assert.match(read('CrawlerReleasePrototype.tsx'),/atelierEvent.version===session.version/);
});
test('browser owns opt-in, context disposal and no crawler mutation',()=>{
  const ui=read('companion/atelier/AtelierPrototype.web.tsx');
  const stage=read('companion/atelier/atelierStage.web.ts');
  assert.match(ui,/verifyFile\(selection.model,receipt\)/);
  assert.match(ui,/if\(!focused\)/);
  assert.match(ui,/stage.current\?\.dispose\(\)/);
  assert.match(stage,/manager.setURLModifier/);
  assert.match(stage,/!uri.startsWith\('blob:'\)/);
  assert.match(stage,/canvas.removeEventListener\('webglcontextlost',lost\)/);
  assert.match(stage,/mixer.uncacheRoot/);
  assert.match(stage,/graphics.dispose\(\)/);
  assert.match(stage,/director.reduced/);
  assert.doesNotMatch(ui+stage,/\b(?:fetch|XMLHttpRequest|sendBeacon|createCrawl|runCrawl|controlCrawl)\s*\(/);
});
