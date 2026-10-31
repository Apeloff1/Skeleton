const assert = require('node:assert/strict');
const { readFileSync, copyFileSync, writeFileSync, mkdtempSync, symlinkSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const keys = ['EXPO_PUBLIC_BACKEND_URL', 'EXPO_BACKEND_URL', 'EXPO_PUBLIC_SKELETON_URL', 'EXPO_SKELETON_URL', 'EXPO_PUBLIC_BACKEND_FALLBACK_URL'];
function version(values = {}, projectRoot = root) {
  const env = { ...process.env, ...Object.fromEntries(keys.map(key => [key, ''])), APP_MANIFEST: '', ...values };
  const result = spawnSync(process.execPath, ['-e', "process.stdout.write(require('./metro.config.js').cacheVersion)"], { cwd: projectRoot, env, encoding: 'utf8', timeout: 30000 });
  assert.equal(result.status, 0, result.stderr);
  assert.ok(result.stdout.trim());
  return result.stdout.trim();
}

test('real Metro configuration invalidates transformed modules when any public endpoint changes', () => {
  const baseline = version();
  assert.equal(version(), baseline, 'the same public configuration keeps its cache namespace');
  for (const key of keys) {
    assert.notEqual(version({ [key]: 'http://localhost:18001' }), baseline, `${key} must invalidate old inlined endpoint values`);
  }
});

test('Docker contexts exclude host Metro transforms with previously inlined endpoints', () => {
  const frontendIgnore = readFileSync(path.join(root, '.dockerignore'), 'utf8').split(/\r?\n/);
  const repositoryIgnore = readFileSync(path.join(root, '..', '.dockerignore'), 'utf8').split(/\r?\n/);
  assert.ok(frontendIgnore.includes('.metro-cache'));
  assert.ok(repositoryIgnore.includes('frontend/.metro-cache'));
});

test('real Expo manifest overrides cannot reuse previously inlined Constants endpoints', () => {
  const baseline = version();
  const emptyOverride = version({ APP_MANIFEST: JSON.stringify({ extra: {} }) });
  const configuredOverride = version({ APP_MANIFEST: JSON.stringify({ extra: { EXPO_PUBLIC_BACKEND_URL: 'http://localhost:18002' } }) });
  assert.notEqual(emptyOverride, baseline, 'an override replaces the configured Constants manifest even without endpoint fields');
  assert.notEqual(configuredOverride, emptyOverride);
  assert.notEqual(version({ APP_MANIFEST: JSON.stringify({ expo: { extra: { EXPO_PUBLIC_SKELETON_URL: 'http://localhost:18010' } } }) }), emptyOverride);
});

test('resolved app manifest endpoint defaults invalidate cache with unchanged environment', () => {
  const project = mkdtempSync(path.join(tmpdir(), 'skeleton-metro-env-'));
  try {
    symlinkSync(path.join(root, 'node_modules'), path.join(project, 'node_modules'), 'dir');
    copyFileSync(path.join(root, 'metro.config.js'), path.join(project, 'metro.config.js'));
    writeFileSync(path.join(project, 'package.json'), JSON.stringify({ name: 'metro-env-proof', version: '1.0.0' }));
    const manifest = endpoint => ({ expo: { name: 'Metro env proof', slug: 'metro-env-proof', extra: { EXPO_PUBLIC_BACKEND_URL: endpoint } } });
    writeFileSync(path.join(project, 'app.json'), JSON.stringify(manifest('http://localhost:18003')));
    const before = version({}, project);
    writeFileSync(path.join(project, 'app.json'), JSON.stringify(manifest('http://localhost:18004')));
    assert.notEqual(version({}, project), before);
  } finally {
    rmSync(project, { recursive: true, force: true });
  }
});
