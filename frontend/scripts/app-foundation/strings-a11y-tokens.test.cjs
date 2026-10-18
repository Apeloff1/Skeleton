'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('./harness.cjs');
const S = load('src/foundation/strings.ts');
const A = load('src/foundation/a11y.ts');
const RN = { Platform: { select: (o) => o.default } };
const themeTokens = load('src/theme/tokens.ts', { 'react-native': RN });
const T = load('src/foundation/tokens.ts', { '../theme/tokens': themeTokens });

test('t() returns en strings and interpolates params', () => {
  assert.equal(S.t('app.name'), 'Skeleton');
  assert.equal(S.t('auth.signedInAs', { name: 'Ada' }), 'Signed in as Ada');
  assert.equal(S.t('auth.required'), 'Sign in to continue to {area}.');
  assert.equal(S.interpolate('{a}-{b}', { a: 1 }), '1-{b}');
});

test('every en string is non-empty and placeholders are well-formed', () => {
  for (const [k, v] of Object.entries(S.en)) {
    assert.ok(typeof v === 'string' && v.trim(), k);
    assert.ok(!/\{[^}]*$/.test(v), k + ' unbalanced placeholder');
  }
});

test('locale registration falls back per key and to en', () => {
  S.registerDictionary('nb', { 'auth.signIn': 'Logg inn' });
  assert.equal(S.setLocale('nb-NO'), 'nb');
  assert.equal(S.t('auth.signIn'), 'Logg inn');
  assert.equal(S.t('app.name'), 'Skeleton');
  assert.equal(S.setLocale('xx'), 'en');
  assert.equal(S.getLocale(), 'en');
});

test('a11y: touch target, hit slop, motion, labels', () => {
  assert.equal(A.MIN_TOUCH_TARGET, 44);
  assert.deepEqual(A.hitSlopFor(24, 24), { top: 10, bottom: 10, left: 10, right: 10 });
  assert.deepEqual(A.hitSlopFor(60, 50), { top: 0, bottom: 0, left: 0, right: 0 });
  assert.deepEqual(A.touchTargetStyle(), { minHeight: 44, minWidth: 44 });
  assert.equal(A.motionDuration(220, true), 0);
  assert.equal(A.motionDuration(220, false), 220);
  assert.equal(A.motionDuration(-5, false), 0);
  assert.equal(A.composeLabel('Play', '', null, 3, false, ' x '), 'Play, 3, x');
});

test('contrastRatio matches WCAG reference values', () => {
  assert.equal(Math.round(A.contrastRatio('#000000', '#FFFFFF')), 21);
  assert.equal(A.contrastRatio('#777777', '#777777'), 1);
  assert.throws(() => A.contrastRatio('red', '#fff'));
});

test('foundation tokens alias the canonical palette and meet contrast', () => {
  const hex = new Set();
  const walk = (o) => Object.values(o).forEach(v => (typeof v === 'string' ? hex.add(v.toUpperCase()) : walk(v)));
  walk(themeTokens.default.palette);
  for (const [k, v] of Object.entries(T.color)) assert.ok(hex.has(v.toUpperCase()), k + ' not from palette');
  assert.ok(A.contrastRatio(T.color.text, T.color.bg) >= 7, 'text AAA on bg');
  assert.ok(A.contrastRatio(T.color.textMuted, T.color.bg) >= 4.5, 'muted AA on bg');
  assert.ok(A.contrastRatio(T.color.onPrimary, T.color.primary) >= 4.5, 'onPrimary AA');
  assert.equal(T.minTouch, A.MIN_TOUCH_TARGET);
  assert.equal(T.space('md'), 12);
  assert.equal(T.space(7), 7);
  assert.equal(T.isHeadingVariant('h2'), true);
  assert.equal(T.isHeadingVariant('body'), false);
  assert.equal(T.textVariants.h1.fontSize, 28);
});
