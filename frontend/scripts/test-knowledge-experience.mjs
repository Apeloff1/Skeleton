import assert from 'node:assert/strict';
import test from 'node:test';
import { confirmedApprovalCount, parseEditableKnowledge } from '../src/product/knowledgeExperience.ts';

test('approval totals count only confirmed approvals', () => {
  assert.equal(confirmedApprovalCount({ alpha: {approved:true}, beta: {approved:false}, gamma: null, delta: {} }), 1);
  assert.equal(confirmedApprovalCount([]), 0);
  assert.equal(confirmedApprovalCount('yes'), 0);
});

test('knowledge editor rejects malformed and non-object JSON', () => {
  for (const value of ['{', 'null', 'false', '1', '[]', '"text"']) {
    assert.throws(() => parseEditableKnowledge(value));
  }
  assert.deepEqual(parseEditableKnowledge('{"enemy":{"hp":100}}'), {enemy:{hp:100}});
});
