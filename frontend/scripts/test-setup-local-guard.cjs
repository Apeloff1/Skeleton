'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const { compileFunction } = require('node:vm');
const ts = require('typescript');

function clientWithChat(chat, checkMeImpl) {
  const source = fs.readFileSync(path.join(__dirname, '../src/product/appReadinessClient.ts'), 'utf8');
  const compiled = ts.transpileModule(source, { reportDiagnostics: true, compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } });
  assert.equal(compiled.diagnostics.length, 0);
  const dependencies = {
    '../utils/apiClient': { default: { get: async path => path === '/api/ai/chat/readiness' ? { ok: true, data: chat } : null } },
    '../auth/gameforgeAuth': { authHeaders: () => ({}), getAuthToken: () => 'local-test-token', getAuthEpoch: () => 1,
      checkMe: checkMeImpl || (async () => ({ observed: true, authenticated: true, role: 'admin' })) },
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

test('setup remains observable but denies privileged readiness when account transport throws', async () => {
  const state = await clientWithChat(chatReadiness('local_guard_unavailable'), async () => {
    throw new Error('private upstream transport failure');
  }).readAppReadiness();
  const account = state.checks.find(item => item.id === 'account');
  const chat = state.checks.find(item => item.id === 'chat');
  const crawler = state.checks.find(item => item.id === 'crawler');
  assert.equal(account.status, 'unknown');
  assert.equal(chat.status, 'unknown');
  assert.equal(crawler.status, 'unknown');
  assert.doesNotMatch(JSON.stringify(state.checks), /private upstream transport failure/);
});

// Exercise the real Setup component with React's actual SSR hooks. Endpoint
// fixtures represent the legitimate export/browser resolution difference; no
// health, account, model or storage success is supplied by this render test.
function setupInitialMarkup(endpoint) {
  const React = require('react');
  const { renderToStaticMarkup } = require('react-dom/server');
  const filename = path.join(__dirname, '../src/features/Setup/AppSetupWorkspace.tsx');
  const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    fileName: filename, reportDiagnostics: true, compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
      jsx: ts.JsxEmit.React, esModuleInterop: true,
    },
  });
  assert.equal(compiled.diagnostics.length, 0);
  const element = tag => ({ children, accessibilityRole, accessibilityLiveRegion }) =>
    React.createElement(tag, { role: accessibilityRole, 'aria-live': accessibilityLiveRegion }, children);
  const dependencies = {
    react: React,
    'react-native': { ActivityIndicator: element('span'), SafeAreaView: element('main'),
      ScrollView: element('div'), Text: element('span'), TouchableOpacity: element('button'), View: element('div') },
    '@expo/vector-icons': { Ionicons: () => null },
    'expo-router': { useRouter: () => ({ push: () => { throw Error('SSR must not navigate'); } }) },
    'expo-clipboard': { setStringAsync: () => { throw Error('SSR must not copy commands'); } },
    '../../product/appReadinessClient': { readAppReadiness: () => { throw Error('SSR must not issue readiness probes'); } },
    './AppSetupWorkspace.styles': { __esModule: true, default: {}, colors: { accent: '#fff' } },
    '../Office/StudioOfficePanel': { __esModule: true, default: () => null },
    '../../auth/gameforgeAuth': { getAuthEpoch: () => 1, subscribeAuthChanges: () => () => {} },
    '../../utils/apiBase': { API_BASE: endpoint, nativeBackendConfigurationIssue: () => null },
  };
  const module = { exports: {} };
  compileFunction(compiled.outputText, ['require', 'module', 'exports'])(name => {
    assert.ok(name in dependencies, 'Unexpected Setup render dependency: ' + name);
    return dependencies[name];
  }, module, module.exports);
  return renderToStaticMarkup(React.createElement(module.exports.default));
}

test('Setup first render is identical for static-export fallback and browser installation origins', () => {
  const exported = setupInitialMarkup('http://localhost:8001');
  for (const endpoint of ['http://127.0.0.1:8790', 'https://installed.example', '']) {
    const initial = setupInitialMarkup(endpoint);
    assert.equal(initial, exported, 'First markup must not depend on a client-only runtime origin');
    assert.doesNotMatch(initial, /localhost:8001|127\.0\.0\.1:8790|installed\.example/);
    assert.match(initial, /Application API:.*Resolving this installation/);
    assert.match(initial, /No readiness verdict until the services respond/);
    assert.match(initial, /Check again/);
    assert.match(initial, /This page does not start services or change credentials/);
    assert.doesNotMatch(initial, /suppressHydrationWarning/);
  }
});
