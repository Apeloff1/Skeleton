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


test('public URL userinfo never ships to clients, regardless of environment', () => {
  for (const environment of ['development', 'staging', 'production']) {
    for (const field of ['EXPO_PUBLIC_BACKEND_URL', 'EXPO_PUBLIC_SKELETON_URL']) {
      for (const url of [
        'https://build-user:private-value@api.example.org',
        'https://build-user@api.example.org',
        'https://:private-value@api.example.org',
        'https://build%2duser:private%2dvalue@api.example.org',
      ]) {
        const issues = validatePublicEnv(environment, { ...ok, [field]: url });
        assert.ok(issues.some(issue => issue.includes(field) && issue.includes('credentials')),
          'expected credential rejection for ' + field + ' in ' + environment);
        assert.ok(!issues.join('\n').includes('private-value'), 'credential leaked in diagnostics');
      }
    }
  }
});

test('staging and production reject entire IPv4 loopback range and localhost names', () => {
  const addresses = [
    'https://127.0.0.2',
    'https://127.255.255.254',
    'https://127.1',
    'https://0x7f000001',
    'https://localhost.',
    'https://app.localhost',
    'https://LOCALHOST',
  ];
  for (const environment of ['staging', 'production']) {
    for (const address of addresses) {
      for (const field of ['EXPO_PUBLIC_BACKEND_URL', 'EXPO_PUBLIC_SKELETON_URL']) {
        const issues = validatePublicEnv(environment, { ...ok, [field]: address });
        assert.ok(issues.some(issue => issue.includes(field) && issue.includes('loopback')),
          'accepted loopback ' + address + ' in ' + environment + ' for ' + field);
      }
    }
  }
});

test('staging and production reject IPv6 and mapped IPv4 loopback addresses', () => {
  const addresses = [
    'https://[::1]',
    'https://[0:0:0:0:0:0:0:1]',
    'https://[::ffff:127.0.0.2]',
    'https://[::ffff:7f00:2]',
    'https://[0:0:0:0:0:ffff:7f00:2]',
    'https://[::ffff:7fff:ffff]',
  ];
  for (const environment of ['staging', 'production']) {
    for (const address of addresses) {
      const issues = validatePublicEnv(environment, { ...ok, EXPO_PUBLIC_BACKEND_URL: address });
      assert.ok(issues.some(issue => issue.includes('EXPO_PUBLIC_BACKEND_URL') && issue.includes('loopback')),
        'accepted IPv6 loopback ' + address + ' in ' + environment);
    }
  }
});

test('public IPs and routable DNS are not falsely flagged as loopback', () => {
  for (const environment of ['staging', 'production']) {
    for (const address of [
      'https://128.0.0.1',
      'https://127.example.org',
      'https://[2001:db8::1]',
      'https://[::ffff:8.8.8.8]',
      'https://api.example.org',
    ]) {
      const issues = validatePublicEnv(environment, { ...ok, EXPO_PUBLIC_BACKEND_URL: address });
      assert.deepEqual(issues, [], 'unexpected rejection for ' + address + ' in ' + environment);
    }
  }
});

test('development permits local loopback hosts but still refuses credentials', () => {
  for (const address of ['http://127.0.0.2:8001', 'http://[::1]:8001', 'http://[::ffff:7f00:2]:8001']) {
    assert.deepEqual(validatePublicEnv('development', { ...ok, EXPO_PUBLIC_BACKEND_URL: address }), []);
  }
  const issues = validatePublicEnv('development', {
    ...ok,
    EXPO_PUBLIC_BACKEND_URL: 'http://dev:secret@127.0.0.2:8001',
  });
  assert.ok(issues.some(issue => issue.includes('credentials')));
});
