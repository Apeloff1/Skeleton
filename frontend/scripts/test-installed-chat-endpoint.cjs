'use strict';
// Test the real native endpoint resolver and EAS configuration before packaging.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const { compileFunction } = require('node:vm');
const ts = require('typescript');

const config = require('../app.config.js');

function inEnv(values, callback) {
  const names = ['EAS_BUILD_PROFILE', 'EXPO_PUBLIC_BACKEND_URL', 'EXPO_BACKEND_URL', 'EXPO_PUBLIC_SKELETON_URL'];
  const before = Object.fromEntries(names.map(name => [name, process.env[name]]));
  for (const name of names) {
    if (values[name] === undefined) delete process.env[name];
    else process.env[name] = values[name];
  }
  try { return callback(); }
  finally {
    for (const name of names) {
      if (before[name] === undefined) delete process.env[name];
      else process.env[name] = before[name];
    }
  }
}

function endpoint(platform, backend, { development = false } = {}) {
  return inEnv(backend === undefined ? {} : { EXPO_PUBLIC_BACKEND_URL: backend }, () => {
    const source = fs.readFileSync(path.join(__dirname, '../src/utils/apiBase.ts'), 'utf8');
    const compiled = ts.transpileModule(source, {
      reportDiagnostics: true,
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    });
    assert.equal(compiled.diagnostics.length, 0);
    const previous = global.__DEV__;
    global.__DEV__ = development;
    try {
      const mod = { exports: {} };
      compileFunction(compiled.outputText, ['require', 'module', 'exports'])((name) => {
        if (name === 'react-native') return { Platform: { OS: platform } };
        if (name === 'expo-constants') return { default: { expoConfig: { extra: {} } } };
        assert.fail('Unexpected dependency: ' + name);
      }, mod, mod.exports);
      return mod.exports;
    } finally { global.__DEV__ = previous; }
  });
}

test('web may use its documented local backend', () => {
  const mod = endpoint('web', undefined);
  assert.equal(mod.API_BASE, 'http://localhost:8001');
  assert.equal(mod.nativeBackendConfigurationIssue(), null);
});

test('unconfigured native build fails closed instead of calling handset localhost', () => {
  const mod = endpoint('android', undefined);
  assert.equal(mod.API_BASE, '');
  assert.match(mod.nativeBackendConfigurationIssue(), /localhost points to the phone/i);
});

test('native API accepts an explicitly configured secure host', () => {
  const mod = endpoint('android', 'https://api.example.org/');
  assert.equal(mod.API_BASE, 'https://api.example.org');
  assert.equal(mod.nativeBackendConfigurationIssue(), null);
});

for (const invalid of [
  'http://localhost:8001', 'http://192.168.1.5:8001', 'http://api.example.org',
  'https://localhost:8001', 'https://user:secret@api.example.org',
  'https://api.example.org/backend', 'https://api.example.org/?token=fake',
]) {
  test('native release rejects unsafe backend ' + invalid, () => {
    const mod = endpoint('android', invalid);
    assert.equal(mod.API_BASE, '');
    assert.ok(mod.nativeBackendConfigurationIssue());
  });
}

test('explicit loopback for Android emulator is allowed only in development', () => {
  const mod = endpoint('android', 'http://10.0.2.2:8001', { development: true });
  assert.equal(mod.API_BASE, 'http://10.0.2.2:8001');
});

for (const profile of ['apk', 'preview', 'production']) {
  test(profile + ' EAS build rejects a disconnected native backend', () => {
    for (const invalid of [undefined, 'http://localhost:8001', 'http://192.168.1.5:8001', 'https://localhost', 'https://user:pass@api.example.org']) {
      assert.throws(() => inEnv({ EAS_BUILD_PROFILE: profile, EXPO_PUBLIC_BACKEND_URL: invalid }, () => config({ config: {} })), /EXPO_PUBLIC_BACKEND_URL/);
    }
    const configured = inEnv({ EAS_BUILD_PROFILE: profile, EXPO_PUBLIC_BACKEND_URL: 'https://api.example.org' }, () => config({ config: {} }));
    assert.equal(configured.extra.EXPO_PUBLIC_BACKEND_URL, 'https://api.example.org');
  });
}
