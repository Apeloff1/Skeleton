/**
 * Replay the companion journal, mission approval and capture projection.
 * Provenance is a digest cursor, not a claim that a source was reviewed.
 */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const root = path.resolve(__dirname, '../features/Jeeves/companion');
const cache = {};
function load(name) {
  if (cache[name]) return cache[name];
  const content = fs.readFileSync(path.join(root, name), 'utf8');
  const result = ts.transpileModule(content, {
    fileName: name,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  });
  const module = { exports: {} };
  const localRequire = (id) => load(id.replace(/^\.\//, '').replace(/\.js$/, '') + (id.endsWith('.ts') ? '' : '.ts'));
  vm.runInNewContext(result.outputText, {
    module, exports: module.exports, require: localRequire,
    Math, Number, Object, Array, Set, String,
  }, { timeout: 1500, filename: name });
  cache[name] = module.exports;
  return module.exports;
}
const { reduceDragonJournal, EMPTY_COMPANION_JOURNAL } = load('dragonJournal.ts');
const { companionFromCapture } = load('dragonCompanionState.ts');
const { approveResearchMission, proposeResearchMission } = load('conversationInterests.ts');
const { effectiveMotion, DEFAULT_COMPANION_PREFERENCES } = load('dragonPreferences.ts');

const event = (sequence, kind, payload = {}, chain = null) => ({
  schema: 'skeleton.ai.dragon_crawl.event.v1',
  event_id: chain ? chain.digest : 'id-' + sequence,
  sequence, kind, url: 'https://example.org/a', at: sequence, payload,
  ...(chain ? { previous_digest: chain.previous, digest: chain.digest } : {}),
});
const digest = (n) => n.toString(16).padStart(64, 'a');

let journal = reduceDragonJournal(EMPTY_COMPANION_JOURNAL, event(1, 'acquisition_accepted'));
journal = reduceDragonJournal(journal, event(2, 'burn_started'));
journal = reduceDragonJournal(journal, event(3, 'burn_complete', { persisted: true }));
const early = reduceDragonJournal(journal, event(4, 'distill_complete', {}));
assert.equal(early.distilled, 0);
assert.ok(early.warnings.includes('Distillation rejected: separate distillation receipt missing'));
journal = reduceDragonJournal(journal, event(4, 'distill_complete', { distilled: true }));
assert.equal(journal.indexed, 1);
assert.equal(journal.distilled, 1);
assert.equal(journal.state.phase, 'celebrating');
assert.equal(journal.state.glasses, false);
assert.equal(journal.distilling.length, 0);

const genesis = '0'.repeat(64);
const first = digest(1);
const second = digest(2);
let chained = reduceDragonJournal(EMPTY_COMPANION_JOURNAL, event(1, 'frontier_discovered', {}, { previous: genesis, digest: first }));
assert.equal(chained.provenance, true);
assert.equal(chained.chainHead, first);
const broken = reduceDragonJournal(chained, event(2, 'robots_check', {}, { previous: digest(9), digest: second }));
assert.ok(broken.warnings.includes('Event chain rejected: cursor does not continue'));
assert.equal(broken.lastSequence, 1);
const stripped = reduceDragonJournal(chained, event(2, 'robots_check'));
assert.ok(stripped.warnings.includes('Event chain rejected: provenance disappeared'));

const capture = companionFromCapture('captured');
assert.equal(capture.glasses, false);
assert.equal(capture.fire, false);
assert.equal(capture.phase, 'acquiring');
assert.equal(companionFromCapture('completed').phase, 'celebrating');

const mission = proposeResearchMission([{ id: 'interest:dragons', topic: 'dragons', weight: 1, source: 'conversation', evidence: 'topic' }]);
assert.equal(approveResearchMission(mission, { approved: true, privacy: 'local-only', sourceHosts: ['example.org'] }), null);
const approved = approveResearchMission(mission, { approved: true, privacy: 'approved-research', sourceHosts: ['Example.org', 'not a host'] });
assert.equal(JSON.stringify(approved.sourceHosts), '["example.org"]');
assert.equal(approved.includeConversationHistory, false);
assert.equal(approved.query, 'dragons');
assert.equal(effectiveMotion(DEFAULT_COMPANION_PREFERENCES, false, true), 'off');
assert.equal(effectiveMotion({ ...DEFAULT_COMPANION_PREFERENCES, lowPower: true }, false, false), 'off');
assert.equal(effectiveMotion(DEFAULT_COMPANION_PREFERENCES, false, false), 'gentle');
console.log('dragon journal chain, distillation receipt, capture projection and mission approval ok');
