import assert from 'node:assert/strict';
import test from 'node:test';

import {
  MAX_OPERATION_CONTENT_CHARS,
  OPERATION_OUTPUT_DELTA_TYPE,
  OPERATION_OUTPUT_SNAPSHOT_TYPE,
  OPERATION_STREAM_SCHEMA_VERSION,
  createOperationClientState,
  reduceOperationEvent,
  reduceOperationReplay,
} from '../services/operationStreamReducer.ts';

function event(sequence, type = 'operation.running', overrides = {}) {
  return {
    schema_version: OPERATION_STREAM_SCHEMA_VERSION,
    operation_id: 'op-1',
    event_id: `event-${sequence}`,
    sequence,
    type,
    timestamp: '2026-09-21T12:00:00+00:00',
    payload: { state: type.replace('operation.', '') },
    ...overrides,
  };
}

function snapshot(state = 'running') {
  return {
    operation_id: 'op-1',
    tenant_id: 'tenant-a',
    actor_id: 'actor-a',
    capability: 'chat',
    created_at: '2026-09-21T12:00:00+00:00',
    deadline: '2026-09-21T12:10:00+00:00',
    idempotency_key: 'idem-1',
    trace_id: 'trace-1',
    state,
    identity_digest: 'digest-1',
    version: 1,
    updated_at: '2026-09-21T12:00:00+00:00',
  };
}

test('ordered events advance the durable replay cursor exactly once', () => {
  let state = createOperationClientState('op-1');
  state = reduceOperationEvent(state, event(1, 'operation.created'));
  state = reduceOperationEvent(state, event(2, 'operation.running'));

  assert.equal(state.lastSequence, 2);
  assert.equal(state.operationState, 'running');
  assert.equal(state.events.length, 2);
  assert.equal(state.resyncRequired, false);
});

test('an exact duplicate event id at an already accepted sequence is ignored', () => {
  const accepted = reduceOperationEvent(
    createOperationClientState('op-1'),
    event(1, 'operation.created'),
  );
  const duplicate = reduceOperationEvent(
    accepted,
    event(1, 'operation.created'),
  );

  assert.deepEqual(duplicate, accepted);
});

test('a new event id for an old sequence fails closed as out of order', () => {
  const accepted = reduceOperationEvent(
    createOperationClientState('op-1'),
    event(1, 'operation.created'),
  );
  const next = reduceOperationEvent(
    accepted,
    event(1, 'operation.created', { event_id: 'different-id' }),
  );

  assert.equal(next.resyncRequired, true);
  assert.equal(next.error, 'out_of_order_event');
});

test('sequence gaps require explicit resync', () => {
  const state = reduceOperationEvent(
    createOperationClientState('op-1'),
    event(2),
  );

  assert.equal(state.resyncRequired, true);
  assert.equal(state.error, 'sequence_gap');
  assert.equal(state.lastSequence, 0);
});

test('cross-operation events cannot enter local state', () => {
  const state = reduceOperationEvent(
    createOperationClientState('op-1'),
    event(1, 'operation.created', { operation_id: 'op-other' }),
  );

  assert.equal(state.resyncRequired, true);
  assert.equal(state.error, 'cross_operation_event');
});

test('terminal events fence later events', () => {
  let state = createOperationClientState('op-1');
  state = reduceOperationEvent(state, event(1, 'operation.cancelled'));
  assert.equal(state.terminal, true);
  assert.equal(state.connection, 'terminal');

  state = reduceOperationEvent(state, event(2, 'operation.running'));
  assert.equal(state.resyncRequired, true);
  assert.equal(state.error, 'event_after_terminal');
});

test('replay must begin from the exact local cursor', () => {
  const state = createOperationClientState('op-1', 4);
  const next = reduceOperationReplay(state, {
    ok: true,
    operation: snapshot(),
    events: [event(5)],
    after_sequence: 3,
    latest_sequence: 5,
    terminal: false,
  });

  assert.equal(next.resyncRequired, true);
  assert.equal(next.error, 'cursor_mismatch');
});

test('replay with missing server events fails closed', () => {
  const state = createOperationClientState('op-1', 4);
  const next = reduceOperationReplay(state, {
    ok: true,
    operation: snapshot(),
    events: [],
    after_sequence: 4,
    latest_sequence: 5,
    terminal: false,
  });

  assert.equal(next.resyncRequired, true);
  assert.equal(next.error, 'server_events_missing');
});

test('terminal replay can reconstruct terminal state from the event stream', () => {
  const state = createOperationClientState('op-1');
  const next = reduceOperationReplay(state, {
    ok: true,
    operation: snapshot('completed'),
    events: [
      event(1, 'operation.created'),
      event(2, 'operation.completed'),
    ],
    after_sequence: 0,
    latest_sequence: 2,
    terminal: true,
  });

  assert.equal(next.lastSequence, 2);
  assert.equal(next.operationState, 'completed');
  assert.equal(next.terminal, true);
  assert.equal(next.connection, 'terminal');
  assert.equal(next.resyncRequired, false);
});

test('unsupported stream schema forces resync instead of silent downgrade', () => {
  const state = reduceOperationEvent(
    createOperationClientState('op-1'),
    event(1, 'operation.created', { schema_version: 99 }),
  );

  assert.equal(state.resyncRequired, true);
  assert.equal(state.error, 'unsupported_schema_version');
});

test('provisional output deltas append once and exact duplicate replay is ignored', () => {
  let state = createOperationClientState('op-1');
  const delta = event(1, OPERATION_OUTPUT_DELTA_TYPE, {
    payload: { delta: 'hello ' },
  });
  state = reduceOperationEvent(state, delta);
  state = reduceOperationEvent(state, delta);
  state = reduceOperationEvent(
    state,
    event(2, OPERATION_OUTPUT_DELTA_TYPE, {
      payload: { delta: 'world' },
    }),
  );

  assert.equal(state.provisionalContent, 'hello world');
  assert.equal(state.displayContent, 'hello world');
  assert.equal(state.contentState, 'provisional');
  assert.equal(state.terminalReconciled, false);
  assert.equal(state.lastSequence, 2);
});

test('output snapshot replaces provisional content without changing authority', () => {
  let state = createOperationClientState('op-1');
  state = reduceOperationEvent(
    state,
    event(1, OPERATION_OUTPUT_DELTA_TYPE, {
      payload: { delta: 'partial' },
    }),
  );
  state = reduceOperationEvent(
    state,
    event(2, OPERATION_OUTPUT_SNAPSHOT_TYPE, {
      payload: { content: 'normalized provisional snapshot' },
    }),
  );

  assert.equal(state.provisionalContent, 'normalized provisional snapshot');
  assert.equal(state.authoritativeContent, null);
  assert.equal(state.displayContent, 'normalized provisional snapshot');
  assert.equal(state.contentState, 'provisional');
  assert.equal(state.terminalReconciled, false);
});

test('completed terminal result replaces provisional content authoritatively', () => {
  let state = createOperationClientState('op-1');
  state = reduceOperationEvent(
    state,
    event(1, OPERATION_OUTPUT_DELTA_TYPE, {
      payload: { delta: 'draft answer' },
    }),
  );
  state = reduceOperationEvent(
    state,
    event(2, 'operation.completed', {
      payload: {
        state: 'completed',
        result: { final_output: 'verified final answer' },
      },
    }),
  );

  assert.equal(state.terminal, true);
  assert.equal(state.provisionalContent, 'draft answer');
  assert.equal(state.authoritativeContent, 'verified final answer');
  assert.equal(state.displayContent, 'verified final answer');
  assert.equal(state.contentState, 'authoritative');
  assert.equal(state.terminalReconciled, true);
});

test('completed terminal without result preserves provisional label instead of promoting it', () => {
  let state = createOperationClientState('op-1');
  state = reduceOperationEvent(
    state,
    event(1, OPERATION_OUTPUT_DELTA_TYPE, {
      payload: { delta: 'still provisional' },
    }),
  );
  state = reduceOperationEvent(
    state,
    event(2, 'operation.completed', {
      payload: { state: 'completed' },
    }),
  );

  assert.equal(state.terminal, true);
  assert.equal(state.displayContent, 'still provisional');
  assert.equal(state.authoritativeContent, null);
  assert.equal(state.contentState, 'provisional');
  assert.equal(state.terminalReconciled, false);
});

for (const terminalType of ['operation.failed', 'operation.cancelled']) {
  test(`${terminalType} discards provisional output from user-visible final content`, () => {
    let state = createOperationClientState('op-1');
    state = reduceOperationEvent(
      state,
      event(1, OPERATION_OUTPUT_DELTA_TYPE, {
        payload: { delta: 'unsafe partial answer' },
      }),
    );
    state = reduceOperationEvent(
      state,
      event(2, terminalType, {
        payload: {
          state: terminalType.replace('operation.', ''),
          error_code: 'bounded_failure',
        },
      }),
    );

    assert.equal(state.terminal, true);
    assert.equal(state.provisionalContent, 'unsafe partial answer');
    assert.equal(state.displayContent, '');
    assert.equal(state.authoritativeContent, null);
    assert.equal(state.contentState, 'discarded');
    assert.equal(state.terminalReconciled, true);
  });
}

test('malformed terminal result forces resync instead of accepting ambiguous final output', () => {
  let state = createOperationClientState('op-1');
  state = reduceOperationEvent(
    state,
    event(1, OPERATION_OUTPUT_DELTA_TYPE, {
      payload: { delta: 'draft' },
    }),
  );
  state = reduceOperationEvent(
    state,
    event(2, 'operation.completed', {
      payload: { state: 'completed', result: { final_output: 42 } },
    }),
  );

  assert.equal(state.resyncRequired, true);
  assert.equal(state.error, 'invalid_terminal_result');
  assert.equal(state.lastSequence, 1);
  assert.equal(state.terminal, false);
});

test('provisional output is bounded and over-budget deltas fail closed', () => {
  let state = createOperationClientState('op-1');
  state = reduceOperationEvent(
    state,
    event(1, OPERATION_OUTPUT_SNAPSHOT_TYPE, {
      payload: { content: 'x'.repeat(MAX_OPERATION_CONTENT_CHARS) },
    }),
  );
  assert.equal(state.resyncRequired, false);
  assert.equal(state.provisionalContent.length, MAX_OPERATION_CONTENT_CHARS);

  state = reduceOperationEvent(
    state,
    event(2, OPERATION_OUTPUT_DELTA_TYPE, {
      payload: { delta: 'overflow' },
    }),
  );
  assert.equal(state.resyncRequired, true);
  assert.equal(state.error, 'provisional_content_exceeds_content_budget');
  assert.equal(state.lastSequence, 1);
});

test('authoritative terminal output is independently content bounded', () => {
  const state = reduceOperationEvent(
    createOperationClientState('op-1'),
    event(1, 'operation.completed', {
      payload: {
        state: 'completed',
        final_output: 'x'.repeat(MAX_OPERATION_CONTENT_CHARS + 1),
      },
    }),
  );

  assert.equal(state.resyncRequired, true);
  assert.equal(state.error, 'authoritative_content_exceeds_content_budget');
  assert.equal(state.terminal, false);
});

test('same event id with altered payload is a duplicate conflict', () => {
  let state = reduceOperationEvent(
    createOperationClientState('op-1'),
    event(1, OPERATION_OUTPUT_DELTA_TYPE, {
      event_id: 'stable-event',
      payload: { delta: 'first' },
    }),
  );
  state = reduceOperationEvent(
    state,
    event(1, OPERATION_OUTPUT_DELTA_TYPE, {
      event_id: 'stable-event',
      payload: { delta: 'tampered' },
    }),
  );

  assert.equal(state.resyncRequired, true);
  assert.equal(state.error, 'duplicate_event_id_conflict');
  assert.equal(state.lastSequence, 1);
  assert.equal(state.provisionalContent, 'first');
});

test('same event id with reordered payload keys remains an exact duplicate', () => {
  const accepted = reduceOperationEvent(
    createOperationClientState('op-1'),
    event(1, 'operation.running', {
      event_id: 'stable-event',
      payload: { state: 'running', version: 2, trace_id: 'trace-1' },
    }),
  );
  const duplicate = reduceOperationEvent(
    accepted,
    event(1, 'operation.running', {
      event_id: 'stable-event',
      payload: { trace_id: 'trace-1', version: 2, state: 'running' },
    }),
  );

  assert.deepEqual(duplicate, accepted);
});

test('malformed payload fails closed instead of crashing reducer', () => {
  const malformed = event(1, OPERATION_OUTPUT_DELTA_TYPE, {
    payload: null,
  });
  const state = reduceOperationEvent(
    createOperationClientState('op-1'),
    malformed,
  );

  assert.equal(state.resyncRequired, true);
  assert.equal(state.error, 'invalid_event_identity');
  assert.equal(state.lastSequence, 0);
});

test('missing event timestamp fails closed', () => {
  const state = reduceOperationEvent(
    createOperationClientState('op-1'),
    event(1, 'operation.running', { timestamp: '' }),
  );

  assert.equal(state.resyncRequired, true);
  assert.equal(state.error, 'invalid_event_identity');
});
