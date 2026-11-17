'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');

const config = readFileSync(resolve(__dirname, '../nginx.conf'), 'utf8');

test('first-run setup ingress has exactly one exact location', () => {
  const matches = [...config.matchAll(/^\s*location\s*=\s*\/setup\s*\{/gm)];
  assert.equal(matches.length, 1, 'duplicate setup locations make production nginx refuse startup');
  const start = matches[0].index + matches[0][0].length;
  const end = config.indexOf('\n    }', start);
  assert.ok(end > start, 'setup block must close');
  const setup = config.slice(start, end);
  assert.match(setup, /try_files\s+\/setup\.html\s+\/setup\/index\.html\s+=404;/);
  assert.doesNotMatch(setup, /try_files[^;]*\s+\/index\.html\s*;/);
  assert.match(setup, /Cache-Control\s+"no-store"\s+always;/);
  assert.match(setup, /Permissions-Policy\s+"camera=\(\), microphone=\(\), geolocation=\(\)"\s+always;/);
  assert.match(setup, /Content-Security-Policy\s+"frame-ancestors 'self'; base-uri 'self'; object-src 'none'"\s+always;/);
});

test('static export, health, backend and engine retain separate routing', () => {
  assert.match(config, /^\s*location\s+\/\s*\{/m);
  assert.match(config, /location\s+=\s+\/healthz/);
  assert.match(config, /application_backend/);
  assert.match(config, /application_engine/);
});
