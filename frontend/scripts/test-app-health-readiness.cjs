'use strict';
// Exercise the actual TypeScript health client without a running application.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const { compileFunction } = require('node:vm');
const ts = require('typescript');

function loadClient(bootstrap) {
  const source = fs.readFileSync(path.join(__dirname, '../src/product/appHealthClient.ts'), 'utf8');
  const compiled = ts.transpileModule(source, {
    reportDiagnostics: true,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  });
  assert.equal(compiled.diagnostics.length, 0);
  const dependencies = {
    '../utils/apiBase': { API_BASE: 'http://backend.test', SKELETON_API_BASE: 'http://engine.test' },
    './appBootstrapClient': {
      getAppBootstrap: async () => bootstrap,
      getAppRuntimeStatus: async () => null,
      bootstrapService: (value, name) => value?.services.find(service => service.name === name),
    },
    '../utils/apiClient': { readBoundedResponseText: async response => ({ text: await response.text(), oversized: false }) },
  };
  const mod = { exports: {} };
  compileFunction(compiled.outputText, ['require', 'module', 'exports'])(name => {
    assert.ok(name in dependencies, `Unexpected dependency ${name}`);
    return dependencies[name];
  }, mod, mod.exports);
  return mod.exports;
}

function loadRuntimeClient(payload) {
  const source = fs.readFileSync(path.join(__dirname, '../src/product/appBootstrapClient.ts'), 'utf8');
  const compiled = ts.transpileModule(source, {
    reportDiagnostics: true,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  });
  assert.equal(compiled.diagnostics.length, 0);
  const mod = { exports: {} };
  compileFunction(compiled.outputText, ['require', 'module', 'exports'])(name => {
    assert.equal(name, '../utils/apiClient');
    return { default: { get: async () => ({ ok: true, data: payload }) } };
  }, mod, mod.exports);
  return mod.exports;
}

for (const bootstrap of [null, { services: [
  { name: 'backend', health_path: '/api/health/ready' },
  { name: 'skeleton', health_path: '/api/v1/health/live' },
], application: { name: 'Skeleton', version: '16.0.0' } }]) {
  test(`frontend probes readiness and distinguishes unhealthy backend (${bootstrap ? 'bootstrap' : 'fallback'})`, async () => {
    const client = loadClient(bootstrap);
    const original = global.fetch;
    const requested = [];
    let backendStatus = 'ready';
    let backendIdentity = { name: 'Skeleton', version: '16.0.0', component: 'backend', ingress_prefix: '/api' };
    global.fetch = async url => {
      requested.push(url);
      const body = url.startsWith('http://backend.test') ? { status: backendStatus, canonical_application: backendIdentity } : {
        alive: true,
        application: { name: 'Skeleton', version: '16.0.0', component: 'engine', ingress_prefix: '/api/v1' },
      };
      return { ok: true, status: 200, url, redirected: false, text: async () => JSON.stringify(body) };
    };
    try {
      const ready = await client.probeAppHealth();
      assert.equal(ready.services.find(service => service.name === 'backend').ok, true);
      assert.equal(ready.ok, false); // Direct fallback cannot prove whole-application readiness.
      assert.ok(requested.includes('http://backend.test/api/health/ready'));
      backendStatus = 'healthy'; // Legacy process liveness is not the new readiness verdict.
      const notReady = await client.probeAppHealth();
      assert.equal(notReady.services.find(service => service.name === 'backend').ok, false);
      backendStatus = 'ready';
      backendIdentity = { name: 'Other', version: '16.0.0', component: 'backend', ingress_prefix: '/api' };
      const wrongService = await client.probeAppHealth();
      assert.equal(wrongService.services.find(service => service.name === 'backend').ok, false);
      backendIdentity = undefined;
      const missingIdentity = await client.probeAppHealth();
      assert.equal(missingIdentity.services.find(service => service.name === 'backend').ok, false);
    } finally {
      global.fetch = original;
    }
  });
}

test('aggregate status retains product degradation while all services are reachable', async () => {
  const payload = {
    ok: false,
    checked_at: new Date().toISOString(),
    application: { name: 'Skeleton', version: '16.0.0', assembly_schema_version: 1 },
    scope: 'public-runtime',
    services: [
      { name: 'backend', ok: true, status: 200, latency_ms: 1, detail: 'healthy' },
      { name: 'skeleton', ok: true, status: 200, latency_ms: 1, detail: 'healthy',
        application: { name: 'Skeleton', version: '16.0.0', component: 'engine', ingress_prefix: '/api/v1' } },
      { name: 'mongo', ok: true, status: 200, latency_ms: 1, detail: 'healthy' },
    ],
    product: { available: false, canonical_actions: 0, ready_actions: 0, ready_pct: 0,
      governed_unbound: 0, unsafe_actions: 0, policy_gaps: 0, attestation_sha256: '', detail: 'unavailable' },
  };
  const client = loadRuntimeClient(payload);
  const degraded = await client.getAppRuntimeStatus();
  assert.equal(degraded?.ok, false);
  assert.equal(degraded?.product.available, false);
  payload.ok = true; // An inconsistent optimistic verdict must be rejected.
  assert.equal(await client.getAppRuntimeStatus(), null);
  payload.product.available = true;
  assert.equal((await client.getAppRuntimeStatus())?.ok, true);
});
