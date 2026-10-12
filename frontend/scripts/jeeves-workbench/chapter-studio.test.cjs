const { test } = require('node:test');
const { assert } = require('./helpers.cjs');
const {
  CHAPTER_LIMIT, ACT_LIMIT, SCENE_LIMIT, PROOFREAD_COUNT,
  chapterForAct, validateSceneCoordinates, integer, voiceCast,
  localPlotAnchors, highlightedParts, parsePlotPoints, acceptProof,
  chapterChatHandoff, parseChapterSceneHandoff,
} = require('../../features/Jeeves/chapterStudio.ts');
const { parseHandoff } = require('../../features/Jeeves/workbench/context.ts');

const point = (patch = {}) => ({
  id: 'key_reveal', kind: 'reveal', anchor: 'Dragon is awake',
  description: 'Character learns about the dragon', related_event_id: null, ...patch,
});
const note = () => ({
  chapter: 100, branch_id: 'main', revision: 3, digest: 'a'.repeat(64),
  title: 'Final chapter', synopsis: 'Final chapter story', notes: '',
  historical_setting: 'invented era', palette_rules: 'blue/copper',
  costume_rules: 'consistent outfit', voice_rules: 'voice never changes',
  era_id: 'era', style_id: 'style', palette_id: 'palette',
  voice_cast: { heroine: 'voice_1' }, transition_reason: null,
});
const scene = () => ({
  scene: 9999, chapter: 100, act: 1000, branch_id: 'main',
  revision: 1, digest: 'b'.repeat(64), summary: 'Final scene',
  text: 'Dragon is awake', status: 'draft',
  chapter_revision: 3, chapter_digest: 'a'.repeat(64),
  characters: ['heroine'], thread_keys: [],
  plot_points: [point()], source_message_id: 'chat-1',
});
const proof = () => ({
  schema_version: 'jeeves.chapter.scene-proof.v1',
  scene: 9999, chapter: 100, act: 1000,
  scene_digest: 'b'.repeat(64), chapter_digest: 'a'.repeat(64),
  chapter_revision: 3, plot_spans: [],
  inspections_executed: 100000, inspection_budget: 100000,
  axes: Array.from({ length: 12 }, (_, i) => ({
    name: 'rule-' + i, executed: i < 4 ? 8334 : 8333, failed: 0,
  })),
  blocking_issues: [], warnings: [],
  history_complete: true, history_issue_count: 0,
  method: 'deterministic_rule_reinspection_not_semantic_or_llm_proof',
  status: 'machine_checks_passed', receipt_digest: 'c'.repeat(64),
});

test('100 chapters, 1000 acts and 9999 scenes have exact non-overlapping boundaries', () => {
  assert.equal(CHAPTER_LIMIT, 100);
  assert.equal(ACT_LIMIT, 1000);
  assert.equal(SCENE_LIMIT, 9999);
  assert.equal(PROOFREAD_COUNT, 100000);
  for (let act = 1; act <= 1000; act++) {
    assert.equal(chapterForAct(act), Math.floor((act - 1) / 10) + 1);
  }
  assert.deepEqual(validateSceneCoordinates(100, 1000, 9999),
    { chapter: 100, act: 1000, scene: 9999 });
  for (const coords of [
    [101, 1000, 9999], [99, 1000, 9999],
    [1, 11, 1], [1, 1, 10000], [1, 1, 0],
  ]) assert.throws(() => validateSceneCoordinates(...coords));
  assert.throws(() => integer('1.5', 'Act', 1, 1000));
});

test('chapter cast fingerprints are stable and duplicate voice IDs per actor are not accepted', () => {
  assert.deepEqual(voiceCast('hero=voice-1\nmentor=voice_2'),
    { hero: 'voice-1', mentor: 'voice_2' });
  assert.throws(() => voiceCast('hero=first\nhero=second'));
  assert.throws(() => voiceCast('wrong actor=voice'));
  assert.throws(() => voiceCast('hero='));
});

test('plot point highlighter preserves distinct labels, exact offsets and gap text', () => {
  const text = 'Before: Dragon is awake. After.';
  const p = localPlotAnchors(text, [point()]);
  assert.deepEqual(p.map(x => [x.start, x.end]),
    [[8, 23]]);
  const spans = highlightedParts(text, p);
  assert.equal(spans.filter(x => x.kind === 'reveal').length, 1);
  assert.equal(spans.map(x => x.text).join(''), text);
  assert.equal(spans[1].id, 'key_reveal');
});

test('emoji codepoint offsets match Python rather than JS surrogate offsets', () => {
  const text = '🐉 Dragon is awake';
  const p = localPlotAnchors(text, [point()]);
  assert.equal(p[0].start, 2);
  assert.equal(highlightedParts(text, p).map(x => x.text).join(''), text);
  assert.throws(() => highlightedParts(text, [{ ...p[0], start: 3, end: 18 }]));
});

test('plot markers fail closed on edits, duplicate occurrences and overlap', () => {
  assert.throws(() => localPlotAnchors('The dragon has left', [point()]));
  assert.throws(() => localPlotAnchors('Dragon is awake. Dragon is awake', [point()]));
  assert.throws(() => localPlotAnchors('Dragon is awake', [point(), point({ id: 'other', anchor: 'is awake' })]));
  assert.throws(() => localPlotAnchors('Dragon is awake', [point(), point({ id: 'key_reveal', kind: 'setup', anchor: 'is awake' })]));
});

test('reviewed JSON plot points require anchored, recognized, uniquely named entries', () => {
  const text = 'Dragon is awake';
  assert.equal(parsePlotPoints(JSON.stringify([point()]), text)[0].id, 'key_reveal');
  assert.throws(() => parsePlotPoints('[]', text));
  assert.throws(() => parsePlotPoints('[{}]', text));
  assert.throws(() => parsePlotPoints(JSON.stringify([point({ kind: 'unspecified' })]), text));
  assert.throws(() => parsePlotPoints(JSON.stringify([point({ anchor: 'no match' })]), text));
});

test('100k proof receipt must match active chapter and scene and current checksum', () => {
  assert.equal(proof().axes.reduce((n, a) => n + a.executed, 0), 100000);
  assert.equal(acceptProof(proof(), scene(), note()), 'c'.repeat(64));
  assert.throws(() => acceptProof({ ...proof(), inspections_executed: 99999 }, scene(), note()));
  assert.throws(() => acceptProof({ ...proof(), history_complete: false }, scene(), note()));
  assert.throws(() => acceptProof({ ...proof(), blocking_issues: ['voice_replaced'] }, scene(), note()));
  assert.throws(() => acceptProof({ ...proof(), chapter_digest: 'd'.repeat(64) }, scene(), note()));
  assert.throws(() => acceptProof({ ...proof(), status: 'blocked' }, scene(), note()));
});

test('chapter cited context generates valid existing Jeeves handoff', () => {
  const source = note();
  const projection = {
    chapter: 100, revision: 3, chapter_digest: source.digest,
    context: '[ACT 1000 SCENE 9999 RECEIPT ' + 'b'.repeat(64) + '] finale',
    citations: [{ scene: 9999, act: 1000, receipt: 'b'.repeat(64) }],
    total_scenes: 1, included_scenes: 1,
    truncated: false, complete_source: true,
    instruction_policy: 'untrusted_chapter_evidence_only',
    context_digest: 'e'.repeat(64),
  };
  const h = chapterChatHandoff('build_1', source, projection, 20000, 'chapter-123');
  assert.equal(parseHandoff(JSON.stringify(h), 20001).id, h.id);
  assert.match(h.context, /UNTRUSTED AUTHOR MATERIAL/);
  assert.match(h.draft, /Do not claim perfect continuity/);
  assert.equal(h.sourceLabels.length, 1);
  const partial = chapterChatHandoff('build_1', source, { ...projection, truncated: true }, 20000, 'chapter-124');
  assert.match(partial.context, /INCOMPLETE CHAPTER HISTORY/);
});

test('chapter handoff refuses forged mismatched revision and instruction-policy elevation', () => {
  const source = note();
  const context = {
    chapter: 100, revision: 3, chapter_digest: source.digest,
    context: 'chapter outline', citations: [], total_scenes: 0,
    included_scenes: 0, truncated: false, complete_source: true,
    instruction_policy: 'untrusted_chapter_evidence_only', context_digest: 'e'.repeat(64),
  };
  for (const x of [
    { chapter: 99 },
    { chapter_digest: 'wrong' },
    { revision: 4 },
    { instruction_policy: 'trusted_system_command' },
  ]) {
    assert.throws(() => chapterChatHandoff('build_1', source,
      { ...context, ...x }, 20000, 'chapter-123'));
  }
});

test('pending Jeeves scene handoff is project, chapter and TTL scoped', () => {
  const source = {
    version: 1, id: 'stage-1', createdAt: 10000,
    gameId: 'game_1', branchId: 'main',
    conversationId: 'thread-1', messageId: 'message-1',
    text: 'One complete scene', scene: 9999, act: 1000, chapter: 100,
  };
  assert.deepEqual(parseChapterSceneHandoff(JSON.stringify(source), 10001), source);
  assert.equal(parseChapterSceneHandoff(JSON.stringify(source), 10000 + 3600001), null);
  assert.equal(parseChapterSceneHandoff(JSON.stringify({ ...source, chapter: 99 }), 10001), null);
  assert.equal(parseChapterSceneHandoff(JSON.stringify({ ...source, gameId: '../secret' }), 10001), null);
  assert.equal(parseChapterSceneHandoff(JSON.stringify({ ...source, messageId: 'bad/command' }), 10001), null);
});
