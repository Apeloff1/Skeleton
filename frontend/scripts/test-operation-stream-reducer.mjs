import assert from 'node:assert/strict';
import test from 'node:test';

import {
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



test('provisional output deltas accumulate without becoming authoritative', () => {
  let state = createOperationClientState('op-1');
  state = reduceOperationEvent(
    state,
    event(1, 'operation.output.delta', { payload: { delta: 'Hel' } }),
  );
  state = reduceOperationEvent(
    state,
    event(2, 'operation.output.delta', { payload: { delta: 'lo' } }),
  );

  assert.equal(state.provisionalContent, 'Hello');
  assert.equal(state.authoritativeContent, null);
  assert.equal(state.contentState, 'provisional');
  assert.equal(state.terminal, false);
});


test('authoritative completion replaces provisional output exactly', () => {
  let state = createOperationClientState('op-1');
  state = reduceOperationEvent(
    state,
    event(1, 'operation.output.snapshot', {
      payload: { content: 'draft answer' },
    }),
  );
  state = reduceOperationEvent(
    state,
    event(2, 'operation.completed', {
      payload: {
        state: 'completed',
        final_output: 'verified final answer',
      },
    }),
  );

  assert.equal(state.provisionalContent, 'verified final answer');
  assert.equal(state.authoritativeContent, 'verified final answer');
  assert.equal(state.contentState, 'authoritative');
  assert.equal(state.terminal, true);
  assert.equal(state.resyncRequired, false);
});


test('completion after provisional content without final authority requires resync', () => {
  let state = createOperationClientState('op-1');
  state = reduceOperationEvent(
    state,
    event(1, 'operation.output.delta', { payload: { delta: 'draft' } }),
  );
  state = reduceOperationEvent(
    state,
    event(2, 'operation.completed', { payload: { state: 'completed' } }),
  );

  assert.equal(state.resyncRequired, true);
  assert.equal(state.error, 'terminal_result_missing');
  assert.equal(state.terminal, false);
});


test('failed or cancelled terminal events discard provisional content status', () => {
  let failed = createOperationClientState('op-1');
  failed = reduceOperationEvent(
    failed,
    event(1, 'operation.output.delta', { payload: { delta: 'draft' } }),
  );
  failed = reduceOperationEvent(
    failed,
    event(2, 'operation.failed', { payload: { state: 'failed' } }),
  );

  assert.equal(failed.contentState, 'discarded');
  assert.equal(failed.authoritativeContent, null);
  assert.equal(failed.terminal, true);
});
