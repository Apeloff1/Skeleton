import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createOperationClientState,
  reduceOperationEvent,
} from '../services/operationStreamReducer.ts';
import {
  PRODUCT_PROJECTION_SCHEMA_VERSION,
  projectWorkspaceOperation,
} from '../services/productProjection.ts';

function event(sequence, type, payload = {}) {
  return {
    schema_version: 1,
    operation_id: 'op-1',
    event_id: `event-${sequence}`,
    sequence,
    type,
    timestamp: '2026-09-28T12:00:00+00:00',
    payload: {
      state: type.replace('operation.', ''),
      ...payload,
    },
  };
}

function snapshot(state, version, overrides = {}) {
  return {
    operation_id: 'op-1',
    tenant_id: 'tenant-a',
    actor_id: 'actor-a',
    capability: 'chat',
    created_at: '2026-09-28T12:00:00+00:00',
    deadline: '2026-09-28T12:10:00+00:00',
    idempotency_key: 'idem-prod-03',
    trace_id: 'trace-prod-03',
    state,
    identity_digest: 'identity-prod-03',
    version,
    updated_at: '2026-09-28T12:00:05+00:00',
    ...overrides,
  };
}

function runningState(payload = {}) {
  let state = createOperationClientState('op-1');
  state = reduceOperationEvent(state, event(1, 'operation.created'));
  state = reduceOperationEvent(state, event(2, 'operation.validated'));
  state = reduceOperationEvent(state, event(3, 'operation.authorized'));
  state = reduceOperationEvent(state, event(4, 'operation.admitted'));
  state = reduceOperationEvent(
    state,
    event(5, 'operation.running', payload),
  );
  return state;
}

test('workspace projection derives bounded fields from accepted durable events', () => {
  const state = runningState({
    progress: 0.72,
    progress_label: 'Generating verified answer',
    blockers: [
      {
        blocker_id: 'tool-latency',
        summary: 'Tool response is delayed.',
        evidence_digest: 'a'.repeat(64),
      },
    ],
    cost: {
      currency: 'usd',
      spent: 0.25,
      budget: 1,
    },
    evidence: [
      {
        source: 'receipt://tool-1',
        digest: 'b'.repeat(64),
        category: 'tool_receipt',
      },
    ],
  });

  const projection = projectWorkspaceOperation(
    state,
    snapshot('running', 5),
  );

  assert.equal(
    projection.schemaVersion,
    PRODUCT_PROJECTION_SCHEMA_VERSION,
  );
  assert.equal(projection.operationId, 'op-1');
  assert.equal(projection.tenantId, 'tenant-a');
  assert.equal(projection.operationState, 'running');
  assert.equal(projection.operationVersion, 5);
  assert.equal(projection.cursorSequence, 5);
  assert.equal(projection.progress, 0.72);
  assert.equal(
    projection.progressLabel,
    'Generating verified answer',
  );
  assert.deepEqual(
    projection.blockers.map((item) => item.blockerId),
    ['tool-latency'],
  );
  assert.deepEqual(projection.cost, {
    currency: 'USD',
    spent: 0.25,
    budget: 1,
  });
  assert.equal(projection.evidence[0].digest, 'b'.repeat(64));
  assert.equal(projection.terminalResult, null);
  assert.equal(projection.writable, false);
});

test('resync-required client state cannot masquerade as workspace authority', () => {
  const state = reduceOperationEvent(
    createOperationClientState('op-1'),
    event(2, 'operation.validated'),
  );
  assert.equal(state.resyncRequired, true);

  assert.throws(
    () => projectWorkspaceOperation(
      state,
      snapshot('validated', 2),
    ),
    /requires authoritative resync/,
  );
});

test('workspace requires client lifecycle convergence with durable snapshot', () => {
  const state = runningState();

  assert.throws(
    () => projectWorkspaceOperation(
      state,
      snapshot('completed', 6),
    ),
    /cursor is behind durable authority/,
  );

  assert.throws(
    () => projectWorkspaceOperation(
      state,
      snapshot('retrying', 5),
    ),
    /has not converged/,
  );
});

test('foreign accepted-event material is rejected even if local state is forged', () => {
  const state = runningState();
  const forged = {
    ...state,
    events: [
      ...state.events.slice(0, -1),
      {
        ...state.events.at(-1),
        operation_id: 'op-other',
      },
    ],
  };

  assert.throws(
    () => projectWorkspaceOperation(
      forged,
      snapshot('running', 5),
    ),
    /unaccepted event/,
  );
});

test('cost projection cannot regress', () => {
  let state = createOperationClientState('op-1');
  state = reduceOperationEvent(
    state,
    event(1, 'operation.created', {
      cost: { currency: 'USD', spent: 0.5, budget: 1 },
    }),
  );
  state = reduceOperationEvent(
    state,
    event(2, 'operation.validated', {
      cost: { currency: 'USD', spent: 0.4, budget: 1 },
    }),
  );

  assert.throws(
    () => projectWorkspaceOperation(
      state,
      snapshot('validated', 2),
    ),
    /cannot decrease/,
  );
});

test('blocker lifecycle is derived only from accepted event history', () => {
  let state = runningState({
    blockers: [
      {
        blocker_id: 'dependency',
        summary: 'Dependency unavailable.',
      },
    ],
  });
  state = reduceOperationEvent(
    state,
    event(6, 'operation.retrying'),
  );
  state = reduceOperationEvent(
    state,
    event(7, 'operation.running', {
      blockers: [
        {
          blocker_id: 'dependency',
          active: false,
          summary: 'ignored',
        },
      ],
    }),
  );

  const projection = projectWorkspaceOperation(
    state,
    snapshot('running', 7),
  );

  assert.equal(
    projection.blockers.some((item) => item.blockerId === 'dependency'),
    false,
  );
});

test('waiting state produces a bounded state-derived blocker', () => {
  let state = runningState();
  state = reduceOperationEvent(
    state,
    event(6, 'operation.waiting_for_user'),
  );

  const projection = projectWorkspaceOperation(
    state,
    snapshot('waiting_for_user', 6),
  );

  assert.deepEqual(
    projection.blockers.map((item) => item.blockerId),
    ['state:waiting-for-user'],
  );
  assert.equal(projection.progress, 0.65);
});

test('completed workspace exposes only canonically reconciled result', () => {
  let state = createOperationClientState('op-1');
  state = reduceOperationEvent(
    state,
    event(1, 'operation.created'),
  );
  state = reduceOperationEvent(
    state,
    event(2, 'operation.completed', {
      result: {
        status: 'completed',
        final_output: 'canonical final answer',
        result_ref: 'result:final',
        message_id: 'message:final',
      },
    }),
  );

  const projection = projectWorkspaceOperation(
    state,
    snapshot('completed', 2),
  );

  assert.equal(projection.progress, 1);
  assert.deepEqual(projection.terminalResult, {
    status: 'completed',
    resultRef: 'result:final',
    messageId: 'message:final',
    failureCode: null,
    finalOutput: 'canonical final answer',
  });
});

test('terminal canonical-result status substitution is rejected', () => {
  let state = createOperationClientState('op-1');
  state = reduceOperationEvent(state, event(1, 'operation.created'));
  state = reduceOperationEvent(
    state,
    event(2, 'operation.cancelled'),
  );

  assert.throws(
    () => projectWorkspaceOperation(
      state,
      snapshot('cancelled', 2),
      {
        status: 'completed',
        final_output: 'forged',
      },
    ),
    /status mismatch/,
  );
});
