'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { h, load, render, text, attrs } = require('./harness.cjs');

const Console = load('src/skeletonForge/components/CockpitConsole.tsx');
const CockpitConsole = Console.default;

const entries = [
  { id: 2, command: 'BIND ERA nope', ok: false, summary: 'unknown era', result: null, at: 9000 },
  { id: 1, command: 'STATUS', ok: true, summary: 'Era soulslike · ledger 3 blocks · archetype extraction', result: {}, at: 0 },
];

test('empty console explains what to try and lists suggestions', () => {
  const html = render(h(CockpitConsole, { entries: [], onSubmit: () => {} }));
  const t = text(html);
  assert.match(t, /No commands yet/);
  assert.match(html, /data-testid="console-input"/);
  assert.match(html, /data-testid="console-suggest-status"/);
  assert.match(html, /data-testid="console-suggest-auto-archetype"/);
  assert.ok(attrs(html, 'aria-label').includes('Cockpit command'));
  assert.doesNotMatch(html, /data-testid="console-clear"/);
});

test('transcript renders newest first with status and relative time', () => {
  const html = render(h(CockpitConsole, { entries, onSubmit: () => {}, onClear: () => {}, now: 10000 }));
  const labels = attrs(html, 'aria-label');
  const i2 = labels.indexOf('BIND ERA nope: failed, unknown era');
  const i1 = labels.indexOf('STATUS: ok, Era soulslike · ledger 3 blocks · archetype extraction');
  assert.ok(i2 >= 0 && i1 > i2, 'newest entry first');
  const t = text(html);
  assert.match(t, /2 commands/);
  assert.match(t, /just now/);
  assert.match(t, /10s ago/);
  assert.match(html, /data-testid="console-clear"/);
});

test('invalid initial command disables send', () => {
  const html = render(h(CockpitConsole, { entries: [], onSubmit: () => {}, initialCommand: 'FLY away' }));
  const send = html.slice(html.indexOf('data-testid="console-send"') - 400, html.indexOf('data-testid="console-send"') + 50);
  assert.match(send, /aria-disabled="true"/);
  const ok = render(h(CockpitConsole, { entries: [], onSubmit: () => {}, initialCommand: 'STATUS' }));
  const send2 = ok.slice(ok.indexOf('data-testid="console-send"') - 400, ok.indexOf('data-testid="console-send"') + 50);
  assert.doesNotMatch(send2, /aria-disabled="true"/);
});

test('ago formatting', () => {
  assert.equal(Console.ago(0, 3000), 'just now');
  assert.equal(Console.ago(0, 42000), '42s ago');
  assert.equal(Console.ago(0, 5 * 60000), '5m ago');
  assert.equal(Console.ago(0, 3 * 3600000), '3h ago');
  assert.equal(Console.ago(5000, 0), 'just now');
});
