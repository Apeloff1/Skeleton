import { existsSync } from 'node:fs';
import assert from 'node:assert/strict';
import test from 'node:test';
import {
  PRODUCT_JOURNEYS, initialJourneySession, journeyById,
  journeyStepHref, nextUnopened, normalizeJourneySession,
  recordJourneyOpen, validBuildId,
} from '../src/product/journeyCatalog.ts';

test('journeys link to unique, existing product-screen routes with no pseudo actions', () => {
  assert.equal(PRODUCT_JOURNEYS.length, 8);
  const ids = new Set();
  for (const journey of PRODUCT_JOURNEYS) {
    assert.equal(ids.has(journey.id), false);
    ids.add(journey.id);
    assert.ok(journey.steps.length >= 5);
    assert.equal(new Set(journey.steps.map(s => s.id)).size, journey.steps.length);
    for (const step of journey.steps) {
      assert.match(step.href, /^\/[a-z0-9-]+$/);
      assert.equal(existsSync(new URL(`../app${step.href}.tsx`, import.meta.url)), true, `Missing screen ${step.href} in ${journey.id}`);
      assert.equal(step.requiresBuild && step.acceptsBuild, undefined);
    }
  }
});

test('session parses malformed or stale local data without inventing progress', () => {
  assert.deepEqual(normalizeJourneySession(null), initialJourneySession());
  assert.deepEqual(normalizeJourneySession({ version: 100, opened: { 'idea-to-game': ['design'] } }), initialJourneySession());
  const restored = normalizeJourneySession({
    version: 1,
    selected: 'invalid-id',
    opened: {
      'idea-to-game': ['describe', 'describe', 'unknown-step', null],
      fake: ['all'],
    },
    last: { journey: 'idea-to-game', step: 'not-a-step' },
  });
  assert.equal(restored.selected, 'idea-to-game');
  assert.deepEqual(restored.opened['idea-to-game'], ['describe']);
  assert.equal(restored.last, null);
  assert.equal('fake' in restored.opened, false);
});

test('opening a step is idempotent, records visited not completion', () => {
  const state = initialJourneySession();
  const opened = recordJourneyOpen(state, 'idea-to-game', 'describe');
  assert.deepEqual(opened.opened['idea-to-game'], ['describe']);
  assert.deepEqual(recordJourneyOpen(opened, 'idea-to-game', 'describe'), opened);
  assert.equal(recordJourneyOpen(opened, 'idea-to-game', 'nonsense'), opened);
  assert.deepEqual(opened.last, { journey: 'idea-to-game', step: 'describe' });
  assert.equal('completed' in opened, false);
});

test('contextual paths carry only validated build IDs, and gated steps need context', () => {
  const flow = journeyById('idea-to-game');
  assert.ok(flow);
  const build = flow.steps.find(s => s.id === 'build');
  const knowledge = flow.steps.find(s => s.id === 'knowledge');
  assert.ok(build && knowledge);
  assert.equal(journeyStepHref(knowledge, ''), null);
  assert.equal(journeyStepHref(build, ''), '/studio');
  assert.equal(journeyStepHref(build, 'game_123-abc'), '/studio?game=game_123-abc');
  assert.equal(journeyStepHref(knowledge, 'game_123-abc'), '/game-kb?game=game_123-abc');
  assert.equal(validBuildId('../../escape'), '');
  assert.equal(validBuildId('a'.repeat(129)), '');
  assert.equal(journeyStepHref(knowledge, '../../escape'), null);
});

test('next-step navigation skips blocked build-only steps and never claims completion', () => {
  const flow = journeyById('idea-to-game');
  assert.ok(flow);
  const opened = ['describe', 'design', 'build'];
  assert.equal(nextUnopened(flow, opened, false)?.id, 'library');
  assert.equal(nextUnopened(flow, opened, true)?.id, 'knowledge');
  assert.equal(nextUnopened(flow, flow.steps.map(s => s.id), true), null);
});
