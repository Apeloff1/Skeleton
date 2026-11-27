const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const ts = require('typescript');

const frontend = path.resolve(__dirname, '../..');
const repository = path.resolve(frontend, '..');
const clone = value => JSON.parse(JSON.stringify(value));
function compiled(relative) {
  const filename = path.join(frontend, relative);
  return ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    fileName: filename,
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText;
}
function evaluate(code, dependency) {
  const module = { exports: {} };
  new Function('module', 'exports', 'require', code)(module, module.exports, dependency);
  return module.exports;
}
const noDependency = name => { throw Error('Unexpected dependency: ' + name); };
const errors = evaluate(compiled('src/product/chatErrors.ts'), noDependency);
const queue = evaluate(compiled('src/features/Jeeves/forgeParameters/forgeQueuedSave.ts'), noDependency);
const clientCode = compiled('src/product/gameFrontierAuthoringClient.ts');

// These are real canonical Python projections, not copies of expected counts or
// manufactured operation identities. No provider, database or native run occurs.
const python = spawnSync('python3', ['-c', `
import json
from skeleton.forge.game_frontier_studio_authoring import authored_summary
from skeleton.forge.game_frontier_studio_document import create_authoring_project
from skeleton.forge.game_frontier_studio_production_recipes import search_recipes
from skeleton.forge.game_frontier_studio_system_expansions import search_expansions
from skeleton.forge.game_frontier_studio_directed_production import search_directions
from skeleton.forge.game_frontier_studio_final_production import search_final_actions
from skeleton.forge.game_frontier_studio_worldline_production import search_worldlines
from skeleton.forge.game_frontier_studio_phase_production import search_phases
from skeleton.forge.game_frontier_studio_campaign_production import search_campaigns
from skeleton.forge.game_frontier_studio_chronicle_production import search_chronicles
from skeleton.forge.game_frontier_studio_epoch_production import search_epochs
from skeleton.forge.game_frontier_studio_continuity_production import search_continuities
from skeleton.forge.game_frontier_studio_saga_production import search_sagas
from skeleton.forge.game_frontier_studio_epic_variations import search_epics
summary = authored_summary(create_authoring_project('real-catalog'))
# Existing HTTP document wrapper around the canonical source projection.
summary.update(schema='skeleton.game.frontier_studio_document.v1', expected_version=1, already_saved=False)
searches = dict(classic=search_recipes, expanded=search_expansions, directed=search_directions,
 final=search_final_actions, worldline=search_worldlines, phase=search_phases,
 campaign=search_campaigns, chronicle=search_chronicles, epoch=search_epochs,
 continuity=search_continuities, saga=search_sagas, epic=search_epics)
pages = {name: search(limit=2) for name, search in searches.items()}
filtered = search_epics(saga='homecoming', epic='cosmic_finale', domain='realm', limit=2)
last = search_epics(offset=len(__import__('skeleton.forge.game_frontier_studio_epic_variations', fromlist=['EPIC_ACTIONS']).EPIC_ACTIONS)-1, limit=2)
print(json.dumps(dict(document=summary, pages=pages, filtered=filtered, last=last)))
`], { cwd: repository, encoding: 'utf8', timeout: 30000, maxBuffer: 1024 * 1024 });
assert.equal(python.status, 0, 'Canonical Python catalog import must succeed: ' + python.stderr);
const canonical = JSON.parse(python.stdout);
function client(response) {
  const calls = [];
  const api = {
    post: async (route, body, options) => { calls.push({ method: 'POST', route, body: clone(body), options });
      throw Error('Explicit test transport failure after send'); },
    get: async (route, options) => { calls.push({ route, options }); return { ok: true, status: 200,
      data: clone(response), error: null, rid: 'canonical-transport' }; },
  };
  const exports = evaluate(clientCode, name => {
    if (name === '../utils/apiClient') return { default: api };
    if (name === '../auth/gameforgeAuth') return {
      authHeaders: () => ({ Authorization: 'Bearer explicit-test-account' }),
      getAuthEpoch: () => 1, getAuthToken: () => 'explicit-test-account', initializeStoredToken: async () => {},
    };
    if (name === './chatErrors') return errors;
    if (name === './gameLearningClient') return { learningRequestKey: () => 'explicit-request-id' };
    if (name === '../features/Jeeves/forgeParameters/forgeQueuedSave') return queue;
    throw Error('Unexpected client dependency: ' + name);
  });
  return { ...exports, calls };
}
const search = (h, generation, selected = {}) => h.searchForgeRecipes('', selected.domain || '',
  selected.offset || 0, 2, generation, '', '', '', '', '', '', '', '', '', selected.saga || '', selected.epic || '');

test('real canonical authored_summary is accepted by inspectForge with Saga/Epic counts', async () => {
  const h = client(canonical.document);
  const doc = await h.inspectForge('real-catalog');
  assert.equal(doc.catalog_total, 50000000000000);
  assert.equal(doc.saga_recipe_count, 4500000000000);
  assert.equal(doc.epic_recipe_count, 45000000000000);
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].options.retries, 0);
  assert.equal(h.calls[0].options.headers.Authorization, 'Bearer explicit-test-account');
  for (const field of ['saga_recipe_count', 'epic_recipe_count']) {
    const missing = clone(canonical.document); delete missing[field];
    await assert.rejects(client(missing).inspectForge('real-catalog'), /invalid original game authoring source/);
  }
  const stale = { ...canonical.document, catalog_total: 5000000000000, recipe_catalog_count: 4999999999500 };
  await assert.rejects(client(stale).inspectForge('real-catalog'), /invalid original game authoring source/);
});

test('all twelve canonical recipe namespaces retain exact generation grammar and bounded transport', async () => {
  for (const [generation, page] of Object.entries(canonical.pages)) {
    const h = client(page);
    const result = await search(h, generation).catch(error => { error.message = generation + ': ' + error.message; throw error; });
    assert.equal(result.total_catalog, page.total_catalog, generation);
    assert.equal(result.items.length, 2);
    assert.equal(h.calls.length, 1);
    const url = new URL(h.calls[0].route, 'https://local.invalid');
    assert.equal(url.searchParams.get('generation'), generation);
    assert.equal(h.calls[0].options.retries, 0);
    for (const item of result.items) assert.equal(h.isForgeRecipeOperation(item.operation, generation), true);
  }
});

test('exact Saga and Epic selections change real canonical returned operations and preserve last-page bounds', async () => {
  const h = client(canonical.filtered);
  const result = await search(h, 'epic', { domain: 'realm', saga: 'homecoming', epic: 'cosmic_finale' });
  assert.ok(result.matched < canonical.pages.epic.matched);
  assert.deepEqual(result.items.map(item => item.epic), ['cosmic_finale', 'cosmic_finale']);
  assert.ok(result.items.every(item => item.saga === 'homecoming'));
  const url = new URL(h.calls[0].route, 'https://local.invalid');
  assert.equal(url.searchParams.get('saga'), 'homecoming');
  assert.equal(url.searchParams.get('epic'), 'cosmic_finale');
  const tail = await search(client(canonical.last), 'epic', { offset: canonical.last.offset });
  assert.equal(tail.items.length, 1);
  assert.equal(tail.next_offset, null);
});

test('wrong counts, missing metadata, mismatched selection, invalid grammar and oversized pages are rejected', async () => {
  const mutations = [
    page => { page.total_catalog = canonical.pages.saga.total_catalog; },
    page => { delete page.epics; },
    page => { delete page.sagas; },
    page => { page.items[0].operation = canonical.pages.saga.items[0].operation; },
    page => { page.items[0].operation += '_'; },
    page => { page.items[0].operation = page.items[0].operation.replace('____________', '_____________'); },
    page => { page.items[0].actual_project_mutation = false; },
    page => { page.items[0].epic = 'cosmic_finale'; },
    page => { page.offset = 1; },
    page => { page.next_offset = 64; },
    page => { page.matched = NaN; },
    page => { page.items = Array(65).fill(page.items[0]); },
  ];
  for (const mutate of mutations) {
    const page = clone(canonical.pages.epic); mutate(page);
    await assert.rejects(search(client(page), 'epic'), error => error.kind === 'protocol');
  }
  await assert.rejects(search(client(canonical.pages.epic), 'epic', { epic: 'cosmic_finale' }),
    error => error.kind === 'protocol');
});

test('invalid cross-generation filters, unbounded pages, unknown generations and text scans never dispatch', async () => {
  const h = client(canonical.pages.epic);
  const invalid = [
    () => h.searchForgeRecipes('', '', 0, 65, 'epic'),
    () => h.searchForgeRecipes('', '', -1, 2, 'epic'),
    () => h.searchForgeRecipes('', '', Infinity, 2, 'epic'),
    () => h.searchForgeRecipes('', '', 0, 2, 'unknown'),
    () => h.searchForgeRecipes('scan', '', 0, 2, 'epic'),
    () => h.searchForgeRecipes('', '', 0, 2, 'saga', '', '', '', '', '', '', '', '', '', '', 'cosmic_finale'),
    () => h.searchForgeRecipes('', '', 0, 2, 'epic', '', '', '', '', '', '', '', '', 'narrative_recall'),
    () => h.searchForgeRecipes('', '', 0, 2, 'classic', '', '', '', '', '', '', '', '', '', 'homecoming'),
  ];
  for (const invoke of invalid) await assert.rejects(invoke(), error => error.kind === 'validation');
  assert.equal(h.calls.length, 0);
});

test('Saga/Epic names enter only the explicit existing preview/save transaction', async () => {
  const h = client(canonical.document);
  for (const generation of ['saga', 'epic']) {
    const operation = canonical.pages[generation].items[0].operation;
    // The only effect is a deliberately failed fixture POST to the existing pure
    // preview route; this does not execute a model, database or native operation.
    await assert.rejects(h.editForge('real-catalog', canonical.document,
      [{ action: operation, parameters: { layer: 'ground', x: 0, y: 0, width: 4, height: 4, floor: 0, wall: 1, seed: 42 } }],
      true, 'explicit-preview-' + generation), error => error instanceof h.ForgeEditError && error.preDispatch === false);
    const call = h.calls.at(-1);
    assert.equal(call.method, 'POST');
    assert.equal(call.route, '/api/game-frontier-authoring/projects/real-catalog/edits/preview');
    assert.equal(call.body.steps[0].action, operation);
    assert.equal(call.body.idempotency_key, 'explicit-preview-' + generation);
    assert.equal(call.options.retries, 0);
  }
});

test('changing generation clears every incompatible filter and preserves explicit search and queue', () => {
  const filename = path.join(frontend, 'src/features/Jeeves/GameFrontierAuthoringPanel.tsx');
  const source = fs.readFileSync(filename, 'utf8');
  const tree = ts.createSourceFile(filename, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let initializer;
  function visit(node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(tree) === 'chooseRecipeGeneration')
      initializer = node.initializer.getText(tree);
    ts.forEachChild(node, visit);
  }
  visit(tree);
  assert.ok(initializer, 'Generation selection must have one canonical filter transition.');
  const code = ts.transpileModule('const choose = ' + initializer + '; module.exports = choose;', {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText;
  const names = ['setRecipeGeneration', 'setRecipeQuery', 'setSystemLayer', 'setDirector', 'setFinish',
    'setWorldline', 'setPhase', 'setCampaign', 'setChronicle', 'setEpoch', 'setContinuity',
    'setSaga', 'setEpic', 'setRecipeResults', 'setRecipeChoices'];
  for (const generation of ['classic', 'saga', 'epic', 'continuity']) {
    const actual = {};
    const module = { exports: {} };
    new Function('module', ...names, code)(module, ...names.map(name => value => { actual[name] = value; }));
    module.exports(generation);
    assert.equal(actual.setRecipeGeneration, generation);
    for (const name of names.slice(1, -2)) assert.equal(actual[name], '', name);
    assert.equal(actual.setRecipeResults, null);
    assert.deepEqual(actual.setRecipeChoices, { sagas: [], epics: [] });
  }
  assert.match(source, /\['saga', 'Saga compositions'\]/);
  assert.match(source, /\['epic', 'Epic compositions'\]/);
  assert.match(source, /\.\.\.recipeChoices\.sagas/);
  assert.match(source, /\.\.\.recipeChoices\.epics/);
  assert.match(source, /title="Queue editor action"/);
  assert.match(source, /title="Preview changes"/);
  assert.match(source, /title="Save source changes"/);
});
