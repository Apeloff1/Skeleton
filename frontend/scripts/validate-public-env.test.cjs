'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { validatePublicEnv } = require('./validate-public-env.cjs');

const ok = { EXPO_PUBLIC_BACKEND_URL: 'https://api.example.org', EXPO_PUBLIC_SKELETON_URL: 'https://skl.example.org' };

test('development accepts localhost', () => {
  assert.deepEqual(validatePublicEnv('development', {
    EXPO_PUBLIC_BACKEND_URL: 'http://localhost:8001', EXPO_PUBLIC_SKELETON_URL: 'http://localhost:8010',
  }), []);
});

test('production accepts https public URLs', () => {
  assert.deepEqual(validatePublicEnv('production', ok), []);
});

test('staging rejects localhost and missing URLs', () => {
  const p = validatePublicEnv('staging', { EXPO_PUBLIC_BACKEND_URL: 'http://localhost:8001' });
  assert.ok(p.some((m) => m.includes('localhost')));
  assert.ok(p.some((m) => m.includes('EXPO_PUBLIC_SKELETON_URL is required')));
});

test('production rejects http, overlay, and secret-looking public vars', () => {
  const p = validatePublicEnv('production', {
    ...ok, EXPO_PUBLIC_BACKEND_URL: 'http://api.example.org', EXPO_PUBLIC_DEV_LOG_OVERLAY: '1',
    EXPO_PUBLIC_STRIPE_SECRET: 'x',
  });
  assert.ok(p.some((m) => m.includes('https')));
  assert.ok(p.some((m) => m.includes('OVERLAY')));
  assert.ok(p.some((m) => m.includes('looks like a secret')));
});

test('unknown environment rejected', () => {
  assert.ok(validatePublicEnv('qa', ok).length > 0);
});

test('checked-in env templates validate for their environment', () => {
  for (const env of ['development', 'staging', 'production']) {
    const file = path.join(__dirname, '..', '..', 'deploy', 'environments', `frontend.${env}.env.example`);
    const vars = Object.fromEntries(fs.readFileSync(file, 'utf8').split('\n')
      .filter((l) => l && !l.startsWith('#')).map((l) => l.split(/=(.*)/s).slice(0, 2)));
    assert.deepEqual(validatePublicEnv(env, vars), [], env);
  }
});
