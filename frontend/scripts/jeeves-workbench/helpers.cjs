const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

require.extensions['.ts'] = (module, filename) => {
  const result = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
    fileName: filename,
  });
  module._compile(result.outputText, filename);
};

const root = path.resolve(__dirname, '../../features/Jeeves/workbench');
const load = name => require(path.join(root, `${name}.ts`));
const { createWorkbench, applyCommand } = load('domain');
const { validateWorkbench } = load('validation');
const { inspectIntegrity } = load('integrity');
const NOW = new Date(2026, 8, 20, 12).getTime();

function harness(prefix = 'test') {
  let sequence = 0;
  let now = NOW;
  const clock = { now: () => now, id: () => `${prefix}-${++sequence}` };
  const context = () => ({ now, id: clock.id });
  let state = createWorkbench(context());
  const run = command => {
    const before = JSON.stringify(state);
    const previous = state;
    const result = applyCommand(state, command, context());
    assert.equal(JSON.stringify(previous), before, 'commands must not mutate their input');
    state = result.state;
    assertValid(state);
    return result.createdId;
  };
  const project = (input = {}) => run({ type: 'project.create', input: { title: 'Orbital garden', goal: 'Ship a tiny playable prototype', ...input } });
  const task = (input = {}) => run({ type: 'task.create', input: { title: 'Build movement', projectId: state.activeProjectId, ...input } });
  const note = (input = {}) => run({ type: 'note.create', input: { title: 'Movement experiment', body: 'Compare acceleration curves.', projectId: state.activeProjectId, ...input } });
  const source = (input = {}) => run({ type: 'source.create', input: { title: 'Test observation', kind: 'observation', projectId: state.activeProjectId, ...input } });
  const card = (input = {}) => run({ type: 'card.create', input: { question: 'What does delta time mean?', answer: 'Elapsed time since the previous frame.', projectId: state.activeProjectId, ...input } });
  const prompt = (input = {}) => run({ type: 'prompt.create', input: { title: 'Review a mechanic', template: 'Review this mechanic.', projectId: state.activeProjectId, ...input } });
  const record = (collection, id) => state[collection].find(item => item.id === id);
  const update = (kind, id, patch) => {
    const collection = `${kind === 'source' ? 'source' : kind}s`;
    return run({ type: `${kind}.update`, id, revision: record(collection, id).revision, patch });
  };
  const remove = (kind, id) => run({ type: `${kind}.delete`, id, revision: record(`${kind}s`, id).revision });
  const status = (id, value) => run({ type: 'task.status', id, revision: record('tasks', id).revision, status: value });
  const review = (id, grade = 'good') => run({ type: 'card.review', id, revision: record('cards', id).revision, grade, durationMs: 1200 });
  return {
    get state() { return state; },
    get now() { return now; },
    clock, context, run, project, task, note, source, card, prompt, record, update, remove, status, review,
    advance: milliseconds => { now += milliseconds; },
    replace: value => { state = value; },
  };
}

function assertValid(state) {
  const validated = validateWorkbench(state);
  assert.equal(validated.ok, true, JSON.stringify(validated.ok ? [] : validated.issues));
  assert.deepEqual(inspectIntegrity(state), []);
}

function linkedFixture(prefix = 'fixture') {
  const h = harness(prefix);
  const project = h.project();
  const source = h.source({ title: 'Physics reference', kind: 'url', locator: 'https://example.com/physics', excerpt: 'Integrate velocity over time.' });
  const note = h.note({ sourceIds: [source], tags: ['physics'], confidence: 'supported' });
  const related = h.note({ title: 'Camera decision', relatedNoteIds: [note], kind: 'decision' });
  const prerequisite = h.task({ title: 'Create scene', estimateMinutes: 10 });
  const task = h.task({ dependencies: [prerequisite], noteIds: [note], estimateMinutes: 30 });
  const card = h.card({ noteId: note, sourceIds: [source], tags: ['physics'] });
  const prompt = h.prompt();
  const globalPrompt = h.prompt({ projectId: null, title: 'Shared review' });
  return { h, project, source, note, related, prerequisite, task, card, prompt, globalPrompt };
}

function memoryStorage(initial = {}) {
  const data = new Map(Object.entries(initial));
  const writes = [];
  return {
    data, writes,
    async getItem(key) { return data.get(key) ?? null; },
    async setItem(key, value) { writes.push({ key, value }); data.set(key, value); },
    async removeItem(key) { data.delete(key); },
  };
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

const tick = () => new Promise(resolve => setImmediate(resolve));
module.exports = { assert, load, harness, linkedFixture, memoryStorage, deferred, tick, assertValid, NOW };
