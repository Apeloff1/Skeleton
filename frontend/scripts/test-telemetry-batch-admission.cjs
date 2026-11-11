'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const frontend = path.resolve(__dirname, '..');
function compile(relative) {
  const source = fs.readFileSync(path.join(frontend, relative), 'utf8');
  return ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
      esModuleInterop: true,
    },
  }).outputText;
}

const privacyJs = compile('src/utils/telemetryPrivacy.ts');
const loggerJs = compile('src/utils/modalLogger.ts');

function createLogger() {
  const disk = new Map();
  const uploads = [];
  const statuses = [];
  const privacySandbox = vm.createContext({ exports: {} });
  vm.runInContext(privacyJs, privacySandbox, { timeout: 5000 });
  const modules = {
    './apiBase': { API_BASE: 'https://example.invalid' },
    './telemetryPrivacy': privacySandbox.exports,
    './featureFlags': { getFeatureFlag: () => true },
    'react': {
      useEffect() {},
      useMemo: fn => fn(),
      useRef: initial => ({ current: initial }),
    },
    '@react-native-async-storage/async-storage': {
      async getItem(key) { return disk.get(key) ?? null; },
      async setItem(key, value) { disk.set(key, value); },
      async removeItem(key) { disk.delete(key); },
    },
    'expo-crypto': {
      randomUUID: () => '00000000-0000-4000-8000-000000000001',
    },
  };
  const sandbox = vm.createContext({
    exports: {},
    require: id => {
      assert.ok(id in modules, 'unexpected dependency: ' + id);
      return modules[id];
    },
    async fetch(url, options) {
      assert.equal(url, 'https://example.invalid/api/telemetry/batch');
      const payload = JSON.parse(options.body);
      uploads.push(payload.events);
      return { ok: statuses.length ? statuses.shift() : true };
    },
    setInterval: () => 1,
    console,
    Date,
  });
  vm.runInContext(loggerJs, sandbox, { timeout: 5000 });
  return { logger: sandbox.exports, disk, uploads, statuses };
}

test('event uploads are split into server-accepted batches of at most 100', async () => {
  const { logger, uploads, disk } = createLogger();
  for (let i = 0; i < 245; i++) {
    logger.recordEvent('Editor', 'step:' + i, 'info', { safe: 'ok' });
  }
  await logger.flushTelemetry();
  await logger.flushTelemetry();
  await logger.flushTelemetry();
  assert.deepEqual(uploads.map(batch => batch.length), [100, 100, 45]);
  assert.equal(disk.has('@telemetry/queue'), false);
});

test('failed network requests stay sanitized and are retried', async () => {
  const { logger, uploads, statuses, disk } = createLogger();
  statuses.push(false, true);
  logger.recordEvent('Editor', 'safe_action', 'info', 'Bearer super-secret');
  await logger.flushTelemetry();
  assert.equal(uploads.length, 1);
  const stored = disk.get('@telemetry/queue');
  assert.ok(stored);
  assert.equal(stored.includes('super-secret'), false);
  await logger.flushTelemetry();
  assert.equal(uploads.length, 2);
  assert.equal(JSON.stringify(uploads).includes('super-secret'), false);
});

test('legacy tampered stored telemetry cannot bypass outbound redaction', async () => {
  const { logger, uploads, disk } = createLogger();
  disk.set('@telemetry/queue', JSON.stringify([{
    modal_id: 'Editor',
    session_id: 's_fake',
    event: 'error',
    severity: 'error',
    detail: {
      authorization: 'Bearer private-password',
      message: 'api_key=private-password',
    },
  }]));
  await logger.flushTelemetry();
  assert.equal(uploads.length, 1);
  assert.equal(JSON.stringify(uploads).includes('private-password'), false);
});
