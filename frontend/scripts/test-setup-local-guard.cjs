'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const { compileFunction } = require('node:vm');
const ts = require('typescript');

function clientWithChat(chat) {
  const source = fs.readFileSync(path.join(__dirname, '../src/product/appReadinessClient.ts'), 'utf8');
  const compiled = ts.transpileModule(source, { reportDiagnostics: true, compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } });
  assert.equal(compiled.diagnostics.length, 0);
  const dependencies = {
    '../utils/apiClient': { default: { get: async path => path === '/api/ai/chat/readiness' ? { ok: true, data: chat } : null } },
    '../auth/gameforgeAuth': { authHeaders: () => ({}), getAuthToken: () => 'local-test-token', getAuthEpoch: () => 1,
      checkMe: async () => ({ observed: true, authenticated: true, role: 'admin' }) },
    './appHealthClient': { probeAppHealth: async () => ({ services: [] }) },
  };
  const mod = { exports: {} };
  compileFunction(compiled.outputText, ['require', 'module', 'exports'])(name => {
    assert.ok(name in dependencies, `Unexpected runtime dependency: ${name}`);
    return dependencies[name];
  }, mod, mod.exports);
  return mod.exports;
}

function chatReadiness(code) {
  return { schema_version: 'backend.ai.chat-readiness.v1', available: false,
    checks: { models: { available: false, code } },
    models: { available: false, readiness: { code } } };
}

for (const code of ['local_guard_unavailable', 'local_guard_configuration_invalid']) {
  test(`setup explains ${code} without claiming chat is ready`, async () => {
    const state = await clientWithChat(chatReadiness(code)).readAppReadiness();
    const chat = state.checks.find(item => item.id === 'chat');
    assert.equal(chat.status, 'blocked');
    assert.match(chat.message, /guard/i);
    assert.match(chat.action, /guard|weights/i);
  });
}

test('setup ignores untrusted, contradictory guard codes', async () => {
  const payload = chatReadiness('local_guard_unavailable');
  payload.checks.models.code = 'malicious-secret';
  const state = await clientWithChat(payload).readAppReadiness();
  const chat = state.checks.find(item => item.id === 'chat');
  assert.equal(chat.status, 'blocked');
  assert.doesNotMatch(chat.message, /trusted guard|malicious-secret/i);
  assert.doesNotMatch(chat.action, /malicious-secret/i);
});
