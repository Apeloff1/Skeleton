'use strict';
// Server-render tests for foundation primitives via the skeleton-forge harness
// (needs a full yarn install: Babel + react-native-web). Run: yarn test:app-foundation:render
const test = require('node:test');
const assert = require('node:assert/strict');
const { h, load, render, text, attrs } = require('../../skeleton-forge/harness.cjs');

const { AppText } = load('src/foundation/AppText.tsx');
const { Stack, Row } = load('src/foundation/Stack.tsx');

test('AppText headings expose role=heading; body text does not', () => {
  const heading = render(h(AppText, { variant: 'h1' }, 'Projects'));
  assert.match(heading, /role="heading"/);
  assert.equal(text(heading), 'Projects');
  const body = render(h(AppText, null, 'Hello'));
  assert.doesNotMatch(body, /role="heading"/);
});

test('AppText applies token colour and honours explicit accessibility props', () => {
  const html = render(h(AppText, { color: 'danger', accessibilityLabel: 'Error: boom' }, 'boom'));
  assert.match(html, /color:\s*rgba\(248,\s*113,\s*113|#F87171|#f87171/i);
  assert.ok(attrs(html, 'aria-label').includes('Error: boom'));
});

test('Stack/Row lay out children with token gaps', () => {
  const html = render(h(Stack, { gap: 'lg', testID: 'stk' }, h(AppText, null, 'a'), h(AppText, null, 'b')));
  assert.match(html, /data-testid="stk"/);
  assert.match(html, /gap:\s*20px/);
  assert.equal(text(html), 'a b');
  const row = render(h(Row, { gap: 4 }, h(AppText, null, 'x')));
  assert.match(row, /flex-direction:\s*row/);
});
