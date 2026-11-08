// GF-P0-58 operator approval state machine. Run: npx -y tsx --test scripts/game-frontier/approval-state.test.ts
import test from 'node:test';
import assert from 'node:assert/strict';
import { approvalReducer, mayCallRuntime, visibleApprovals, type ApprovalQueue } from '../../src/features/Jeeves/GameFrontierApprovalState';

const action = { id: 'a1', label: 'Spawn quest giver', editor: 'authoring', action: 'add_actor', parameters: { x: 1 } };
const seed = (): ApprovalQueue => approvalReducer([], { type: 'request', action });
const at = (q: ApprovalQueue) => q.find(e => e.action.id === 'a1')!;

test('new actions start pending and duplicates are ignored', () => {
  const q = approvalReducer(seed(), { type: 'request', action });
  assert.equal(q.length, 1);
  assert.equal(at(q).status, 'pending');
});

test('approve requires confirmation before runtime may be called', () => {
  const asked = approvalReducer(seed(), { type: 'ask', id: 'a1', intent: 'approve' });
  assert.equal(at(asked).status, 'confirming');
  assert.equal(mayCallRuntime(at(seed()), at(asked)), false);
  const confirmed = approvalReducer(asked, { type: 'confirm', id: 'a1' });
  assert.equal(at(confirmed).status, 'running');
  assert.equal(mayCallRuntime(at(asked), at(confirmed)), true);
  const done = approvalReducer(confirmed, { type: 'succeeded', id: 'a1', receipt: 'a'.repeat(64) });
  assert.equal(at(done).status, 'approved');
  assert.equal(at(done).receipt, 'a'.repeat(64));
});

test('confirm without ask is a no-op (no runtime call from pending)', () => {
  const q = approvalReducer(seed(), { type: 'confirm', id: 'a1' });
  assert.equal(at(q).status, 'pending');
  assert.equal(mayCallRuntime(at(seed()), at(q)), false);
});

test('reject path never calls runtime', () => {
  const asked = approvalReducer(seed(), { type: 'ask', id: 'a1', intent: 'reject' });
  const confirmed = approvalReducer(asked, { type: 'confirm', id: 'a1' });
  assert.equal(at(confirmed).status, 'rejected');
  assert.equal(mayCallRuntime(at(asked), at(confirmed)), false);
});

test('cancel returns to pending; runtime failure → error → retry → pending', () => {
  const asked = approvalReducer(seed(), { type: 'ask', id: 'a1', intent: 'approve' });
  assert.equal(at(approvalReducer(asked, { type: 'cancel', id: 'a1' })).status, 'pending');
  const running = approvalReducer(asked, { type: 'confirm', id: 'a1' });
  const failed = approvalReducer(running, { type: 'failed', id: 'a1', error: 'forbidden' });
  assert.equal(at(failed).status, 'error');
  assert.equal(at(failed).error, 'forbidden');
  assert.equal(at(approvalReducer(failed, { type: 'retry', id: 'a1' })).status, 'pending');
});

test('terminal states ignore further events', () => {
  const rejected = approvalReducer(approvalReducer(seed(), { type: 'ask', id: 'a1', intent: 'reject' }), { type: 'confirm', id: 'a1' });
  for (const ev of [{ type: 'ask', id: 'a1', intent: 'approve' }, { type: 'confirm', id: 'a1' }, { type: 'succeeded', id: 'a1' }] as const)
    assert.equal(at(approvalReducer(rejected, ev as any)).status, 'rejected');
});

test('untrusted request payloads are bounded and isolated from caller mutation', () => {
  const changing = { ...action, parameters: { x: 1, room: { id: 'a' } } };
  const q = approvalReducer([], { type: 'request', action: changing });
  changing.parameters.room.id = 'changed';
  assert.deepEqual(at(q).action.parameters, { x: 1, room: { id: 'a' } });
  assert.equal(approvalReducer([], { type: 'request', action: { ...action, parameters: { x: NaN } } }).length, 0);
  assert.equal(approvalReducer([], { type: 'request', action: { ...action, id: '../../other' } }).length, 0);
  const cycle: any = {}; cycle.self = cycle;
  assert.equal(approvalReducer([], { type: 'request', action: { ...action, parameters: cycle } }).length, 0);
});

test('a different action cannot borrow another confirmation', () => {
  const before = approvalReducer(seed(), { type: 'ask', id: 'a1', intent: 'approve' });
  const other = approvalReducer([], { type: 'request', action: { ...action, id: 'a2' } });
  const otherConfirmed = approvalReducer(
    approvalReducer(other, { type: 'ask', id: 'a2', intent: 'approve' }),
    { type: 'confirm', id: 'a2' });
  assert.equal(mayCallRuntime(at(before), otherConfirmed[0]), false);
});

test('unknown confirmation intent cannot authorize runtime', () => {
  const asked = approvalReducer(seed(), { type: 'ask', id: 'a1', intent: 'forged' as any });
  assert.equal(at(asked).status, 'pending');
  assert.equal(at(approvalReducer(asked, { type: 'confirm', id: 'a1' })).status, 'pending');
});

test('editor tab visibility cannot re-admit or erase an in-flight action', () => {
  const other = { ...action, id: 'handbook-one', editor: 'handbook' };
  let all = approvalReducer(seed(), { type: 'request', action: other });
  all = approvalReducer(all, { type: 'ask', id: action.id, intent: 'approve' });
  all = approvalReducer(all, { type: 'confirm', id: action.id });
  assert.equal(at(all).status, 'running');
  assert.deepEqual(visibleApprovals(all, [other]).map(e => e.action.id), [other.id]);
  const restored = visibleApprovals(all, [action]);
  assert.equal(restored.length, 1);
  assert.equal(restored[0].status, 'running');
  const repeated = approvalReducer(all, { type: 'confirm', id: action.id });
  assert.equal(mayCallRuntime(at(all), at(repeated)), false);
  assert.equal(at(repeated).status, 'running');
  const done = approvalReducer(all, { type: 'succeeded', id: action.id, receipt: 'a'.repeat(64) });
  assert.equal(visibleApprovals(done, [action])[0].status, 'approved');
});


test('runtime cannot approve an action without an exact receipt hash', () => {
  const asked = approvalReducer(seed(), { type: 'ask', id: action.id, intent: 'approve' });
  const running = approvalReducer(asked, { type: 'confirm', id: action.id });
  for (const receipt of (['abc', 'G'.repeat(64), '', undefined] as const)) {
    const result = approvalReducer(running, { type: 'succeeded', id: action.id, receipt });
    assert.equal(at(result).status, 'error');
    assert.equal(at(result).receipt, undefined);
  }
  const verified = approvalReducer(running, {
    type: 'succeeded', id: action.id, receipt: 'f'.repeat(64),
  });
  assert.equal(at(verified).status, 'approved');
});


test('reused action ID with changed parameters revokes prior approval', () => {
  const asked = approvalReducer(seed(), { type: 'ask', id: action.id, intent: 'approve' });
  const changed = { ...action, parameters: { x: 999 } };
  assert.equal(visibleApprovals(asked, [changed]).length, 0);
  const revoked = approvalReducer(asked, { type: 'request', action: changed });
  assert.equal(at(revoked).status, 'rejected');
  assert.equal(at(approvalReducer(revoked, { type: 'confirm', id: action.id })).status, 'rejected');
  assert.equal(mayCallRuntime(at(asked), at(revoked)), false);
});


test('editor visibility requires source action identity not id alone', () => {
  const before = seed();
  assert.equal(visibleApprovals(before, [action]).length, 1);
  assert.equal(visibleApprovals(before, [{ ...action, editor: 'handbook' }]).length, 0);
  assert.equal(visibleApprovals(before, [{ ...action, action: 'delete_project' }]).length, 0);
  assert.equal(visibleApprovals(before, [{ ...action, label: 'Other intent' }]).length, 0);
  assert.equal(visibleApprovals(before, [{ ...action, parameters: { x: -1 } }]).length, 0);
});


test('cyclic or accessor-bearing incoming views cannot reactivate stale approval', () => {
  const saved = seed();
  const cyclic: any = {};
  cyclic.self = cyclic;
  assert.equal(visibleApprovals(saved, [{ ...action, parameters: cyclic }]).length, 0);
  const hostile: any = {};
  Object.defineProperty(hostile, 'x', { enumerable: true, get() {
    throw new Error('never evaluate untrusted view getter');
  }});
  assert.equal(visibleApprovals(saved, [{ ...action, parameters: hostile }]).length, 0);
});
