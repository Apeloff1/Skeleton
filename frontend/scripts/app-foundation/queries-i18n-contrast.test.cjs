'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('./harness.cjs');
const Q = load('src/foundation/queries.ts');
const S = load('src/foundation/strings.ts');
const A = load('src/foundation/a11y.ts');
const theme = load('src/theme/tokens.ts', { 'react-native': { Platform: { select: (o) => o.default } } });

const slot = (ok) => ({ ok });
const overview = (over = {}) => ({
  process: { pid: 1, python: '3.12', started_at: 0, uptime_s: 3700, deploy_env: 'dev' },
  elapsed_ms: 12, all_green: false,
  registry: slot(true), watchdog: slot(true), cold_storage: slot(true), databases: slot(true),
  feature_flags: slot(true), deprecations: slot(true), boot: slot(true), ...over,
});

test('getJson returns data and throws ApiError with status on failure', async () => {
  const ok = { get: async () => ({ ok: true, status: 200, data: { a: 1 }, error: null }) };
  assert.deepEqual(await Q.getJson(ok, '/x'), { a: 1 });
  const bad = { get: async () => ({ ok: false, status: 503, data: null, error: null }) };
  await assert.rejects(Q.getJson(bad, '/x'), (e) => e instanceof Q.ApiError && e.status === 503 && /HTTP 503/.test(e.message));
  const nul = { get: async () => ({ ok: true, status: 204, data: null, error: null }) };
  await assert.rejects(Q.getJson(nul, '/x'), /HTTP 204/);
});

test('overview health derivations', () => {
  assert.deepEqual(Q.failingSubsystems(null), []);
  assert.equal(Q.healthColour(null), 'grey');
  assert.equal(Q.healthColour(overview({ all_green: true })), 'green');
  assert.equal(Q.healthColour(overview({ boot: slot(false) })), 'yellow');
  const red = overview({ boot: slot(false), databases: slot(false), registry: slot(false) });
  assert.deepEqual(Q.failingSubsystems(red), ['registry', 'databases', 'boot']);
  assert.equal(Q.healthColour(red), 'red');
  assert.deepEqual(Q.failingSubsystems(overview({ watchdog: undefined })), ['watchdog']);
});

test('formatUptime', () => {
  assert.equal(Q.formatUptime(59), '0m');
  assert.equal(Q.formatUptime(3700), '1h 1m');
  assert.equal(Q.formatUptime(90000), '1d 1h');
  assert.equal(Q.formatUptime(-5), '0m');
  assert.equal(Q.formatUptime(NaN), '0m');
});

test('parseVault normalises the unified vault contract', () => {
  const v = Q.parseVault({ ok: true, items: [{ id: 'a', name: 'World', source: 'worldforge', kind: 'monograph' }, { id: 'b' }, null, { name: 'no id' }], counts: { boardroom: 2, bad: 'x', inf: Infinity } });
  assert.equal(v.items.length, 2);
  assert.deepEqual(v.items[1], { id: 'b', name: 'b', source: 'unknown', kind: 'file' });
  assert.deepEqual(v.counts, { boardroom: 2 });
  assert.deepEqual(Q.parseVault(null), { items: [], counts: {} });
  assert.throws(() => Q.parseVault({ ok: false, error: 'locked' }), /locked/);
  assert.deepEqual(Q.vaultKey(80), ['vault', 'unified', 80]);
  assert.deepEqual(Q.overviewKey, ['health', 'overview']);
});

test('nb dictionary covers every en key with matching placeholders', () => {
  const ph = (s) => (s.match(/\{\w+\}/g) || []).sort().join(',');
  const missing = Object.keys(S.en).filter((k) => !(k in S.nb) && k !== 'app.name');
  assert.deepEqual(missing, []);
  for (const [k, v] of Object.entries(S.nb)) {
    assert.ok(k in S.en, 'unknown nb key ' + k);
    assert.equal(ph(v), ph(S.en[k]), 'placeholder mismatch ' + k);
  }
  assert.equal(S.setLocale('nb'), 'nb');
  assert.equal(S.t('tab.projects'), 'Prosjekter');
  assert.equal(S.t('home.failing', { count: 2 }), '2 delsystemer trenger oppmerksomhet');
  assert.equal(S.t('app.name'), 'Skeleton');
  S.setLocale('en');
});

test('canonical theme (dark + light) meets WCAG contrast for primary text roles', () => {
  for (const [mode, c] of Object.entries(theme.default.colorModes)) {
    if (!c.text) continue;
    assert.ok(A.contrastRatio(c.text, c.bg) >= 7, `${mode} text on bg`);
    assert.ok(A.contrastRatio(c.textMuted, c.bg) >= 4.5, `${mode} textMuted on bg`);
    assert.ok(A.contrastRatio(c.onPrimary, c.primary) >= 4.5, `${mode} onPrimary on primary`);
  }
});

test('primitive touch targets reach 44pt via size + hitSlop', () => {
  const reach = (h) => h + 2 * A.hitSlopFor(A.MIN_TOUCH_TARGET, h).top;
  for (const h of [26, 32, 44, 52]) assert.ok(reach(h) >= 44, 'height ' + h);
  const clear = A.hitSlopFor(18, 18);
  assert.ok(18 + clear.left + clear.right >= 44);
});
