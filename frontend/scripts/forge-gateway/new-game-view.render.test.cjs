'use strict';
// Server-render tests for the new-game flow component. Run: yarn test:forge-gateway
const test = require('node:test');
const assert = require('node:assert/strict');
const { h, load, render, text, attrs } = require('../skeleton-forge/harness.cjs');

const { NewGameView } = load('src/forgeGateway/NewGameView.tsx');
const { summarise } = load('src/forgeGateway/model.ts');
const noop = () => {};
const base = { brief: '', playtest: 'auto', onBriefChange: noop, onPlaytestChange: noop, onSubmit: noop, onReset: noop };

test('form: heading, labelled field, examples and an accessible radio group', () => {
  const html = render(h(NewGameView, { ...base, state: { kind: 'idle' } }));
  assert.match(html, /role="heading"[^>]*>New game</);
  assert.ok(attrs(html, 'aria-label').includes('Describe your game'));
  assert.match(html, /role="radiogroup"/);
  const radios = html.match(/role="radio"/g) || [];
  assert.equal(radios.length, 3);
  assert.equal((html.match(/aria-checked="true"/g) || []).length, 1);
  assert.ok(attrs(html, 'aria-label').some((label) => label.startsWith('If available.')));
  for (const label of ['Use the Platformer example', 'Use the Top-down shooter example', 'Use the Roguelike RPG example', 'Build game']) {
    assert.ok(attrs(html, 'aria-label').includes(label), label);
  }
  assert.match(text(html), /0 \/ 4000 characters/);
});

test('form: validation and server errors are alerts; unavailable server disables submit', () => {
  const invalid = render(h(NewGameView, { ...base, state: { kind: 'idle' }, validationError: 'Describe the game you want to build.' }));
  assert.match(invalid, /role="alert"[\s\S]*Describe the game you want to build\./);
  assert.match(invalid, /aria-invalid="true"/);
  const failed = render(h(NewGameView, { ...base, state: { kind: 'error', status: 429, retryable: true, message: 'Too many builds started.' } }));
  assert.match(failed, /data-testid="new-game-error"/);
  assert.match(text(failed), /Try again/);
  const off = render(h(NewGameView, { ...base, state: { kind: 'idle' }, unavailableReason: 'Game building is not configured on this server yet.' }));
  assert.match(off, /role="alert"[\s\S]*not configured/);
  assert.match(off, /aria-disabled="true"[^>]*aria-label="Build game"|aria-label="Build game"[^>]*aria-disabled="true"/);
});

test('tracking: progressbar exposes its value and a polite live status', () => {
  const summary = summarise({ execution_id: 'e', status: 'running', progress: 0.5, message: 'playtesting' });
  const html = render(h(NewGameView, { ...base, state: { kind: 'tracking', executionId: 'e', summary, transientError: null } }));
  assert.match(html, /role="progressbar"/);
  assert.match(html, /aria-valuenow="50"/);
  assert.match(html, /aria-live="polite"/);
  assert.match(text(html), /Building your game.*50% · playtesting/);
});

test('done: success shows proof and next steps; failure is an alert with recovery', () => {
  const ok = summarise({ execution_id: 'e', status: 'succeeded', result: { ok: true, spec: { title: 'Fox Roofs', genre: 'platformer' }, proof: 'CORE_LOOP_OK' } });
  const success = render(h(NewGameView, { ...base, onOpenBuilds: noop, state: { kind: 'done', executionId: 'e', summary: ok, view: {} } }));
  assert.match(text(success), /Fox Roofs is ready.*Genre: platformer.*Proof: CORE_LOOP_OK/);
  assert.ok(attrs(success, 'aria-label').includes('Open my builds'));
  const bad = summarise({ execution_id: 'e', status: 'failed', error: 'deadline exceeded' });
  const failure = render(h(NewGameView, { ...base, state: { kind: 'done', executionId: 'e', summary: bad, view: {} } }));
  assert.match(failure, /role="alert"[\s\S]*deadline exceeded/);
  assert.ok(attrs(failure, 'aria-label').includes('Edit and try again'));
});
