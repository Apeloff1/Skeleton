'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { h, load, render, text, attrs } = require('./harness.cjs');
const I = load('src/skeletonForge/instruments.ts');
const Q = load('src/skeletonForge/questionnaire.ts');
const Panel = load('src/skeletonForge/components/DesignInstruments.tsx').default;
const Flow = load('src/skeletonForge/components/QuestionnaireFlow.tsx').default;

test('recovered instruments exactly cover the canonical ten tensor axes', () => {
  assert.deepEqual(I.DESIGN_AXES.map((a) => a.id), [
    'risk', 'tempo', 'lethality', 'opacity', 'scarcity',
    'agency', 'spectacle', 'intimacy', 'grind', 'authorial',
  ]);
  assert.equal(I.normaliseAxisEdit(NaN), null);
  assert.equal(I.normaliseAxisEdit(Infinity), null);
  assert.equal(I.normaliseAxisEdit(-1), 0);
  assert.equal(I.normaliseAxisEdit(2), 1);
});

test('axis overrides survive the questionnaire into the same forge request', () => {
  let s = Q.questionnaireReducer(Q.INITIAL_STATE, { type: 'setAxis', axis: 'risk', value: 0.91 });
  s = Q.questionnaireReducer(s, { type: 'setAxis', axis: 'tempo', value: 0.2 });
  s = Q.questionnaireReducer(s, { type: 'setAxis', axis: 'constructor', value: 1 });
  s = Q.questionnaireReducer(s, { type: 'setAxis', axis: 'agency', value: NaN });
  assert.deepEqual(Q.buildRunRequest(s).operator_axes, { risk: 0.91, tempo: 0.2 });
  assert.equal(Q.buildRunRequest(Q.INITIAL_STATE).operator_axes, undefined);
  s = Q.questionnaireReducer(s, { type: 'setAxis', axis: 'risk', value: null });
  assert.deepEqual(Q.buildRunRequest(s).operator_axes, { tempo: 0.2 });
  s = Q.questionnaireReducer(s, { type: 'resetAxes' });
  assert.deepEqual(s.instruments, {});
  assert.equal(Q.buildRunRequest(s).operator_axes, undefined);
});

test('instrument panel is accessible and differentiates automatic from explicit', () => {
  const html = render(h(Panel, { axes: { risk: 0.9 }, onAxis: () => {}, onReset: () => {} }));
  assert.match(text(html), /Game design instruments/);
  assert.match(text(html), /1 of 10 overridden/);
  assert.match(text(html), /90% override/);
  assert.match(text(html), /Automatic/);
  assert.equal((html.match(/data-testid="instrument-track-/g) || []).length, 10);
  assert.ok((html.match(/role="slider"|role="adjustable"/g) || []).length >= 1);
  assert.ok(attrs(html, 'aria-label').includes('Increase Risk'));
  assert.match(html, /data-testid="instrument-reset-all"/);
});

test('existing questionnaire options exposes instrument cockpit without changing defaults', () => {
  const state = { ...Q.INITIAL_STATE, step: 'options', vision: 'fantasy world' };
  const html = render(h(Flow, { state, dispatch: () => {}, beats: Q.FALLBACK_BEATS, onForge: () => {} }));
  assert.match(text(html), /Advanced: ten design sliders/);
  assert.doesNotMatch(html, /data-testid="gameforge-design-instruments"/);
  const review = render(h(Flow, {
    state: { ...state, step: 'review', instruments: { risk: 0.9 } },
    dispatch: () => {}, beats: Q.FALLBACK_BEATS, onForge: () => {},
  }));
  assert.match(text(review), /Design tuning Risk: 90%/);
});


test('complete historical backend genre vote vocabulary is available in the creator brief', () => {
  const genres = Q.BRIEF_FACETS.find((f) => f.id === 'genre').options;
  const expected = [
    'action-adventure', 'action', 'adventure', 'rpg', 'crpg', 'jrpg', 'arpg',
    'soulslike', 'strategy', 'rts', 'tactics', 'platformer', 'metroidvania',
    'simulation', 'city-builder', 'shooter', 'fps', 'horror', 'survival',
    'extraction', 'roguelike', 'roguelite', 'stealth', 'immersive-sim',
    'fighting', 'puzzle', 'deckbuilder', 'card', 'battle-royale', 'mmo',
    'mmorpg', 'visual-novel', 'narrative', 'cozy', 'arcade', 'bullet-heaven',
  ];
  // The historical 36-choice contract is a compatibility floor, not a
  // ceiling: current GameForge exposes all 158 categorized creative choices.
  assert.equal(new Set(genres).size, 158);
  for (const legacy of expected) assert.ok(genres.includes(legacy), 'lost legacy genre: ' + legacy);
  assert.equal(genres.length, new Set(genres).size);
});


test('the legacy full Galaxy matrix questionnaire is reachable from Forge options', () => {
  const state = { ...Q.INITIAL_STATE, step: 'options', vision: 'a narrative adventure' };
  const html = render(h(Flow, {
    state, dispatch: () => {}, beats: Q.FALLBACK_BEATS, onForge: () => {},
    onOpenGalaxyStudio: () => {},
  }));
  assert.match(text(html), /14 production matrices/);
  assert.match(text(html), /100 extended sliders/);
  assert.match(html, /data-testid="q-open-galaxy-studio"/);
});


test('the 69-entry archived-plus-recovered catalog feeds canonical Forge run semantics', () => {
  const G = load('src/skeletonForge/galaxyGenres.ts');
  assert.equal(G.GALAXY_CHOICES.length, 69);
  assert.deepEqual(new Set(Object.keys(G.GALAXY_TO_FORGE_BRIEF)), new Set(G.GALAXY_CHOICES.map((g) => g.id)));
  const known = Q.BRIEF_FACETS.find((f) => f.id === 'genre').options;
  for (const item of G.GALAXY_CHOICES) {
    assert.ok(known.includes(G.mappedBriefGenre(item.id)), item.id + ' lacks a supported backend genre');
  }
  let state = Q.questionnaireReducer(Q.INITIAL_STATE, { type: 'setGalaxyGenre', genre: 'racing' });
  assert.equal(state.brief.genre, 'simulation');
  assert.equal(state.galaxyGenre, 'racing');
  assert.deepEqual(Q.buildRunRequest(state).answers, { genre: 'simulation' });
  assert.match(Q.buildRunRequest(state).vision, /Racing Game/);
  assert.equal(Q.questionnaireReducer(state, { type: 'setGalaxyGenre', genre: '__bogus__' }), state);
  state = Q.questionnaireReducer(state, { type: 'setBrief', facet: 'genre', value: 'rpg' });
  assert.equal(state.galaxyGenre, null);
  assert.equal(state.brief.genre, 'rpg');
});

test('historical specialized genre preserves long authored vision over generated hint', () => {
  const G = load('src/skeletonForge/galaxyGenres.ts');
  assert.equal(G.specializedVision('x'.repeat(4000), 'racing', 4000).length, 4000);
  assert.equal(G.specializedVision('hello', '__bogus__', 4000), 'hello');
  assert.match(G.specializedVision('hello', 'visual_novel'), /Visual Novel/);
});

test('63+ genre options are discoverable within the existing five-step Forge', () => {
  const state = { ...Q.INITIAL_STATE, step: 'options', vision: 'a 2D builder' };
  const html = render(h(Flow, {
    state, dispatch: () => {}, beats: Q.FALLBACK_BEATS, onForge: () => {},
  }));
  assert.match(text(html), /all 69 Galaxy genres/);
  assert.match(html, /data-testid="q-galaxy-genres-toggle"/);
});


test('the recovered 158-genre creative brief supports search while preserving selected genre', () => {
  const Genres = load('src/skeletonForge/genreCatalog.ts');
  assert.equal(Genres.GENRE_COUNT, 158);
  assert.equal(Genres.GENRE_GROUPS.length, 11);
  assert.equal(Genres.GENRE_CHOICES.length, 158);
  assert.equal(new Set(Genres.GENRE_CHOICES).size, 158);
  assert.equal(Genres.POPULAR_GENRES.length, 36);
  for (const term of ['colony-sim', 'tactical-rpg', '4x', 'rhythm', 'racing', 'visual-novel']) {
    assert.ok(Genres.GENRE_CHOICES.includes(term), 'Missing historical genre: ' + term);
  }
  const state = {
    ...Q.INITIAL_STATE,
    step: 'brief', vision: 'Original cross-genre adventure',
    brief: { genre: 'city-builder' },
  };
  const html = render(h(Flow, {
    state, dispatch: () => {}, beats: Q.FALLBACK_BEATS, onForge: () => {},
  }));
  assert.match(text(html), /158 selectable game genres and subgenres/);
  assert.match(html, /data-testid="q-genre-search"/);
  assert.match(html, /data-testid="q-genre-family-racing-sports"/);
  assert.match(html, /data-testid="q-brief-genre-city-builder"/);
  assert.match(text(html), /not a promise of a dedicated playable engine/);
  assert.equal(Q.buildRunRequest(state).answers.genre, 'city-builder');
  assert.equal(Q.buildRunRequest({
    ...state, brief: { genre: 'colony-sim' },
  }).answers.genre, 'colony-sim');
  assert.deepEqual(Genres.filterGenreChoices('colony'), ['colony-sim']);
  assert.ok(Genres.filterGenreChoices('', 'racing-sports').includes('sailing'));
  assert.equal(Genres.filterGenreChoices('___absent___').length, 0);
});

test('recovered saved presets validate all expanded genre options and preserve native options', () => {
  const Presets = load('src/skeletonForge/designPresets.ts');
  for (const genre of ['colony-sim', 'racing', 'survival-horror', 'tactical-rpg']) {
    const state = {
      ...Q.INITIAL_STATE,
      brief: { genre },
      quest: { enabled: true, length: 7 },
      playable: { enabled: true, mode: 'survival', launch: false },
      instruments: { tempo: 0.8, grind: 0.65 },
    };
    const original = Q.buildRunRequest(state);
    const record = Presets.makeDesignPreset('Genre-' + genre, state, 100);
    const restored = Presets.decodeDesignPresets(
      Presets.encodeDesignPresets([record])
    )[0];
    assert.deepEqual(Q.buildRunRequest(restored.state), original);
  }
});
