import assert from 'node:assert/strict';
import test from 'node:test';

import {
  decodeOperatorControlProjection,
} from '../src/product/operatorControlProjection.ts';

const DIGEST = 'a'.repeat(64);

function base(overrides = {}) {
  return {
    schema_version: 1,
    task_id: 'P1-PROD-04',
    accountability_id: 'ACC-P1-PROD-04',
    operation_id: 'operation-1',
    tenant_id: 'tenant-a',
    canonical_state: 'running',
    terminal: false,
    cancelled: false,
    workspace_projection_digest: DIGEST,
    workspace_decision_digest: 'b'.repeat(64),
    control_known: false,
    last_action: null,
    human_control_receipt_digest: null,
    control_version: null,
    paused: null,
    interrupted: null,
    autonomy_level: null,
    previous_control_receipt_digest: null,
    available_actions: ['cancel'],
    canonical_operation_authority: 'durable-workspace-projection',
    human_control_authority: null,
    production_authority: false,
    ...overrides,
  };
}

function controlled(overrides = {}) {
  return base({
    control_known: true,
    last_action: 'pause',
    human_control_receipt_digest: 'c'.repeat(64),
    control_version: 8,
    paused: true,
    interrupted: false,
    autonomy_level: 0,
    available_actions: ['cancel', 'resume'],
    human_control_authority: 'p1-auto-04-human-control',
    ...overrides,
  });
}

test('unknown control state exposes only canonical cancel', () => {
  const decoded = decodeOperatorControlProjection(base());
  assert.deepEqual(decoded.available_actions, ['cancel']);
  assert.equal(decoded.control_known, false);
});

test('paused AUTO-04 receipt exposes resume plus cancel', () => {
  const decoded = decodeOperatorControlProjection(controlled());
  assert.equal(decoded.last_action, 'pause');
  assert.equal(decoded.paused, true);
  assert.deepEqual(decoded.available_actions, ['cancel', 'resume']);
});

test('resumed control state exposes non-escalating operator actions', () => {
  const decoded = decodeOperatorControlProjection(controlled({
    last_action: 'resume',
    paused: false,
    interrupted: false,
    autonomy_level: 3,
    available_actions: ['cancel', 'interrupt', 'override', 'pause'],
  }));
  assert.deepEqual(
    decoded.available_actions,
    ['cancel', 'interrupt', 'override', 'pause'],
  );
});

test('terminal operation exposes no live controls', () => {
  const decoded = decodeOperatorControlProjection(controlled({
    canonical_state: 'completed',
    terminal: true,
    cancelled: false,
    available_actions: [],
  }));
  assert.deepEqual(decoded.available_actions, []);
});

test('cancelled flag derives only from canonical cancelled state', () => {
  const decoded = decodeOperatorControlProjection(controlled({
    canonical_state: 'cancelled',
    terminal: true,
    cancelled: true,
    available_actions: [],
  }));
  assert.equal(decoded.cancelled, true);

  assert.throws(
    () => decodeOperatorControlProjection(controlled({
      canonical_state: 'running',
      terminal: false,
      cancelled: true,
      available_actions: ['cancel', 'resume'],
    })),
    /cancelled must derive from canonical state/,
  );
});

test('forged available actions fail closed', () => {
  assert.throws(
    () => decodeOperatorControlProjection(controlled({
      available_actions: ['cancel', 'override'],
    })),
    /available_actions do not derive/,
  );
});

test('unknown state cannot smuggle human control fields', () => {
  assert.throws(
    () => decodeOperatorControlProjection(base({
      human_control_receipt_digest: 'd'.repeat(64),
    })),
    /unknown control state cannot set/,
  );
});

test('known state requires AUTO-04 authority identity', () => {
  assert.throws(
    () => decodeOperatorControlProjection(controlled({
      human_control_authority: null,
    })),
    /human control authority drift/,
  );
});

test('approval is not a projectable operator action', () => {
  assert.throws(
    () => decodeOperatorControlProjection(controlled({
      last_action: 'approve',
    })),
    /not a projectable human control/,
  );
});

test('projection cannot claim production authority', () => {
  assert.throws(
    () => decodeOperatorControlProjection(base({
      production_authority: true,
    })),
    /cannot claim production authority/,
  );
});

test('autonomy level is bounded to canonical enum', () => {
  assert.throws(
    () => decodeOperatorControlProjection(controlled({
      autonomy_level: 9,
    })),
    /autonomy_level must be within/,
  );
});
