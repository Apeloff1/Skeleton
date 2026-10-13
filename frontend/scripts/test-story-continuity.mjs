import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  STORY_KINDS, storyIndexPath, prepareStoryEvent,
} from '../src/product/storyContinuity.ts';

const draft = (change = {}) => ({
  eventId: 'chapter1_gate_open', branchId: 'main',
  act: '1', scene: '2', beat: '0', kind: 'witness',
  text: 'A guard sees the hero opening the gate.',
  characterIds: 'hero, guard', witnessIds: 'guard',
  speakerId: '', threadKey: '', knowledgeRequired: 'gate_closed',
  knowledgeGranted: 'gate_open', ...change,
});

test('canonical story URLs remain game-scoped and cannot inject paths', () => {
  assert.equal(storyIndexPath('my_game-1'),
    '/api/playable/my_game-1/story-index');
  for (const invalid of ['', '../admin', 'a/b', 'x?branch=other', 'x'.repeat(129)]) {
    assert.throws(() => storyIndexPath(invalid), /canonical game/);
  }
});

test('validated editor evidence uses only backend-recognized fields', () => {
  const event = prepareStoryEvent(draft());
  assert.equal(event.event_id, 'chapter1_gate_open');
  assert.equal(event.branch_id, 'main');
  assert.deepEqual([event.act, event.scene, event.beat], [1, 2, 0]);
  assert.deepEqual(event.character_ids, ['hero', 'guard']);
  assert.deepEqual(event.witness_ids, ['guard']);
  assert.deepEqual(event.knowledge_required, ['gate_closed']);
  assert.deepEqual(event.knowledge_granted, ['gate_open']);
  assert.equal(event.source_thread_id, null);
  assert.equal(event.source_message_id, null);
  assert.equal(Object.hasOwn(event, 'owner_id'), false);
  assert.equal(Object.hasOwn(event, 'record_status'), false);
});

test('only known event types, witness membership and one speaker are permitted', () => {
  assert.equal(STORY_KINDS.length, 11);
  assert.throws(() => prepareStoryEvent(draft({ kind: 'fabricated' })),
    /supported story event kind/);
  assert.throws(() => prepareStoryEvent(draft({ witnessIds: 'stranger' })),
    /Witnesses must also be listed/);
  assert.throws(() => prepareStoryEvent(draft({ speakerId: 'outsider' })),
    /speaker must be a participant/);
  assert.throws(() => prepareStoryEvent(draft({ kind: 'dialogue' })),
    /Dialogue requires its speaker/);
  assert.equal(prepareStoryEvent(draft({ kind: 'dialogue', speakerId: 'hero' })).speaker_id,
    'hero');
});

test('promises, resolutions, deaths and revivals carry causal constraints', () => {
  for (const kind of ['promise', 'resolution']) {
    assert.throws(() => prepareStoryEvent(draft({ kind })),
      /require a plot thread/);
    assert.equal(prepareStoryEvent(draft({ kind, threadKey: 'gate-arc' })).thread_key,
      'gate-arc');
  }
  for (const kind of ['death', 'revival']) {
    assert.throws(() => prepareStoryEvent(draft({
      kind, characterIds: '', witnessIds: '',
    })), /affected character/);
  }
});

test('numeric chapter, scene, beat bounds reject negative or non-integer input', () => {
  for (const bad of [{ act: '0' }, { act: '10001' }, { scene: '0' },
    { scene: '100001' }, { beat: '-1' }, { beat: '1.1' },
    { beat: '100001' }, { act: 'NaN' }, { scene: '2e3' }]) {
    assert.throws(() => prepareStoryEvent(draft(bad)), /supported range/);
  }
});

test('source records reject duplicates, overlong or unsafe identifiers', () => {
  for (const bad of [
    { characterIds: 'hero,hero' },
    { witnessIds: 'guard,guard' },
    { knowledgeGranted: 'a,a' },
    { eventId: '../escape' },
    { branchId: 'x'.repeat(97) },
    { knowledgeRequired: Array(21).fill('a').map((x,i)=>x+i).join(',') },
  ]) {
    assert.throws(() => prepareStoryEvent(draft(bad)));
  }
});

test('writer refuses empty text, dangerous controls and >4000 characters', () => {
  for (const text of ['', ' '.repeat(10), 'x'.repeat(4001), 'Invalid\u0000control']) {
    assert.throws(() => prepareStoryEvent(draft({ text })), /Story evidence text/);
  }
});

test('Story Index screen uses only registered, authenticated story API and receipt verification', () => {
  const screen = readFileSync(new URL('../app/story-index.tsx', import.meta.url), 'utf8');
  assert.ok(screen.includes('storyIndexPath(game)'));
  assert.ok(screen.includes('prepareStoryEvent({ ...draft, branchId: branch })'));
  assert.ok(screen.includes('saved.event?.record_status'));
  assert.ok(screen.includes("'creator_reviewed_evidence'"));
  assert.ok(screen.includes('authHeaders()'));
  assert.equal(screen.includes("'/api/pipeline/'"), false);
});
