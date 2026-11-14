'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { ROOT, h, load, render } = require('./harness.cjs');

test('all offline questionnaire panels render without importing the Expo API runtime', () => {
  const Q = load('src/skeletonForge/questionnaire.ts');
  const Flow = load('src/skeletonForge/components/QuestionnaireFlow.tsx').default;
  const html = render(h(Flow, {
    state: { ...Q.INITIAL_STATE, step: 'options' },
    beats: Q.FALLBACK_BEATS, dispatch: () => {}, onForge: () => {},
  }));
  // Native input controls are shown only after a brief genre is selected,
  // never in the Forge-options panel.
  const chosenGenreHtml = render(h(Flow, {
    state: { ...Q.INITIAL_STATE, step: 'brief', brief: { genre: 'rpg' } },
    beats: Q.FALLBACK_BEATS, dispatch: () => {}, onForge: () => {},
  }));
  assert.match(chosenGenreHtml, /q-genre-control-preview/);
  assert.match(html, /q-jeeves-quality-panel/);
  assert.match(html, /q-native-playtest-mode/);
  const expoPrefix = path.join(ROOT, 'node_modules', 'expo-modules-core', 'src');
  assert.ok(!Object.keys(require.cache).some(file => file.startsWith(expoPrefix)),
    'a pure editor SSR test must not load a native Expo module');
});
