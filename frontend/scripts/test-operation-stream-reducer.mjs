import assert from 'node:assert/strict';
import test from 'node:test';

import {
  OPERATION_STREAM_SCHEMA_VERSION,
  createOperationClientState,
  operationCursorStorageKey,
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

test('assistant content is provisional and exact duplicates do not double-apply', () => {
  let state = createOperationClientState('op-1');
  const first = event(1, 'assistant_content', {
    payload: { text: 'Hello ', mode: 'append' },
  });
  state = reduceOperationEvent(state, first);
  state = reduceOperationEvent(state, first);

  assert.equal(state.lastSequence, 1);
  assert.equal(state.provisionalAssistantContent, 'Hello ');
  assert.equal(state.displayedAssistantContent, 'Hello ');
  assert.equal(state.canonicalAssistantContent, null);
  assert.equal(state.contentState, 'provisional');
  assert.equal(state.contentReconciled, false);

  state = reduceOperationEvent(
    state,
    event(2, 'assistant_content', {
      payload: { text: 'world', mode: 'append' },
    }),
  );
  assert.equal(state.displayedAssistantContent, 'Hello world');
});

test('assistant content replace mode resets provisional projection only', () => {
  let state = createOperationClientState('op-1');
  state = reduceOperationEvent(
    state,
    event(1, 'assistant_content', {
      payload: { text: 'partial', mode: 'append' },
    }),
  );
  state = reduceOperationEvent(
    state,
    event(2, 'assistant_content', {
      payload: { text: 'replaced', mode: 'replace' },
    }),
  );

  assert.equal(state.provisionalAssistantContent, 'replaced');
  assert.equal(state.displayedAssistantContent, 'replaced');
  assert.equal(state.contentState, 'provisional');
});

test('completed terminal replaces provisional display with canonical output', () => {
  let state = createOperationClientState('op-1');
  state = reduceOperationEvent(
    state,
    event(1, 'assistant_content', {
      payload: { text: 'draft', mode: 'append' },
    }),
  );
  state = reduceOperationEvent(
    state,
    event(2, 'operation.completed', {
      payload: {
        state: 'completed',
        final_output: 'canonical answer',
        result_ref: 'result:1',
        message_id: 'message:1',
      },
    }),
  );

  assert.equal(state.lastSequence, 2);
  assert.equal(state.terminal, true);
  assert.equal(state.connection, 'terminal');
  assert.equal(state.canonicalAssistantContent, 'canonical answer');
  assert.equal(state.displayedAssistantContent, 'canonical answer');
  assert.equal(state.contentState, 'canonical');
  assert.equal(state.contentReconciled, true);
  assert.equal(state.terminalResultRef, 'result:1');
  assert.equal(state.terminalMessageId, 'message:1');
  assert.equal(state.terminalEventId, 'event-2');
});

test('failed or cancelled terminal discards provisional assistant content', () => {
  let failed = createOperationClientState('op-1');
  failed = reduceOperationEvent(
    failed,
    event(1, 'assistant_content', {
      payload: { text: 'unsafe partial', mode: 'append' },
    }),
  );
  failed = reduceOperationEvent(
    failed,
    event(2, 'operation.failed', {
      payload: {
        state: 'failed',
        failure_code: 'provider_unavailable',
      },
    }),
  );

  assert.equal(failed.displayedAssistantContent, '');
  assert.equal(failed.provisionalAssistantContent, '');
  assert.equal(failed.contentState, 'discarded');
  assert.equal(failed.failureCode, 'provider_unavailable');

  let cancelled = createOperationClientState('op-1');
  cancelled = reduceOperationEvent(
    cancelled,
    event(1, 'assistant_content', {
      payload: { text: 'partial', mode: 'append' },
    }),
  );
  cancelled = reduceOperationEvent(
    cancelled,
    event(2, 'operation.cancelled', {
      payload: { state: 'cancelled' },
    }),
  );
  assert.equal(cancelled.displayedAssistantContent, '');
  assert.equal(cancelled.contentState, 'discarded');
});

test('rejected assistant payload never advances the accepted cursor', () => {
  const state = reduceOperationEvent(
    createOperationClientState('op-1'),
    event(1, 'assistant_content', {
      payload: { mode: 'append' },
    }),
  );

  assert.equal(state.resyncRequired, true);
  assert.equal(state.error, 'invalid_assistant_content');
  assert.equal(state.lastSequence, 0);
  assert.equal(state.events.length, 0);
  assert.equal(state.seenEventIds.length, 0);
});

test('completed terminal without canonical content cannot promote provisional text', () => {
  let state = createOperationClientState('op-1');
  state = reduceOperationEvent(
    state,
    event(1, 'assistant_content', {
      payload: { text: 'draft only', mode: 'append' },
    }),
  );
  state = reduceOperationEvent(
    state,
    event(2, 'operation.completed', {
      payload: { state: 'completed' },
    }),
  );

  assert.equal(state.resyncRequired, true);
  assert.equal(state.error, 'completed_without_canonical_content');
  assert.equal(state.lastSequence, 1);
  assert.equal(state.displayedAssistantContent, 'draft only');
  assert.equal(state.terminal, false);
});

test('server terminal snapshot can reconcile from canonical result', () => {
  const state = createOperationClientState('op-1');
  const next = reduceOperationReplay(state, {
    ok: true,
    operation: snapshot('completed'),
    events: [],
    after_sequence: 0,
    latest_sequence: 0,
    terminal: true,
    canonical_result: {
      status: 'completed',
      final_output: 'snapshot answer',
      result_ref: 'result:snapshot',
    },
  });

  assert.equal(next.terminal, true);
  assert.equal(next.contentReconciled, true);
  assert.equal(next.displayedAssistantContent, 'snapshot answer');
  assert.equal(next.terminalResultRef, 'result:snapshot');
});

test('generic terminal event requires an explicit terminal state', () => {
  const state = reduceOperationEvent(
    createOperationClientState('op-1'),
    event(1, 'terminal', {
      payload: { final_output: 'answer' },
    }),
  );

  assert.equal(state.resyncRequired, true);
  assert.equal(state.error, 'invalid_terminal_state');
  assert.equal(state.lastSequence, 0);
});

test('unsupported stream schema forces resync instead of silent downgrade', () => {
  const state = reduceOperationEvent(
    createOperationClientState('op-1'),
    event(1, 'operation.created', { schema_version: 99 }),
  );

  assert.equal(state.resyncRequired, true);
  assert.equal(state.error, 'unsupported_schema_version');
});


test('partial replay with unread stream head remains non-terminal', () => {
  const state = createOperationClientState('op-1');
  const next = reduceOperationReplay(state, {
    ok: true,
    operation: snapshot('completed'),
    events: [event(1, 'operation.created')],
    after_sequence: 0,
    latest_sequence: 1,
    stream_latest_sequence: 3,
    has_more: true,
    terminal: false,
  });

  assert.equal(next.lastSequence, 1);
  assert.equal(next.terminal, false);
  assert.equal(next.connection, 'following');
  assert.equal(next.resyncRequired, false);
});

test('terminal replay with unread events fails closed', () => {
  const state = createOperationClientState('op-1');
  const next = reduceOperationReplay(state, {
    ok: true,
    operation: snapshot('completed'),
    events: [event(1, 'operation.created')],
    after_sequence: 0,
    latest_sequence: 1,
    stream_latest_sequence: 3,
    has_more: true,
    terminal: true,
  });

  assert.equal(next.resyncRequired, true);
  assert.equal(next.error, 'terminal_with_unread_events');
  assert.equal(next.terminal, false);
});

test('server has_more metadata must match the authoritative stream head', () => {
  const state = createOperationClientState('op-1');
  const next = reduceOperationReplay(state, {
    ok: true,
    operation: snapshot(),
    events: [event(1, 'operation.created')],
    after_sequence: 0,
    latest_sequence: 1,
    stream_latest_sequence: 2,
    has_more: false,
    terminal: false,
  });

  assert.equal(next.resyncRequired, true);
  assert.equal(next.error, 'server_has_more_mismatch');
});

test('caught-up terminal replay reconciles exactly once', () => {
  const state = createOperationClientState('op-1');
  const next = reduceOperationReplay(state, {
    ok: true,
    operation: snapshot('completed'),
    events: [
      event(1, 'operation.created'),
      event(2, 'operation.completed', {
        payload: {
          state: 'completed',
          final_output: 'final answer',
          result_ref: 'result:final',
        },
      }),
    ],
    after_sequence: 0,
    latest_sequence: 2,
    stream_latest_sequence: 2,
    has_more: false,
    terminal: true,
  });

  assert.equal(next.lastSequence, 2);
  assert.equal(next.terminal, true);
  assert.equal(next.contentState, 'canonical');
  assert.equal(next.displayedAssistantContent, 'final answer');
  assert.equal(next.terminalResultRef, 'result:final');
  assert.equal(next.resyncRequired, false);
});


test('persisted cursor keys are isolated per consumer identity', () => {
  const first = operationCursorStorageKey('op-1', 'client-a');
  const second = operationCursorStorageKey('op-1', 'client-b');
  const otherOperation = operationCursorStorageKey('op-2', 'client-a');

  assert.notEqual(first, second);
  assert.notEqual(first, otherOperation);
  assert.match(first, /^codedock:operation-cursor:/);
  assert.throws(
    () => operationCursorStorageKey('op-1', '   '),
    /consumerId is required/,
  );
});


test('disconnect and reconnect replay pages preserve exact accepted cursor continuity', () => {
  let state = createOperationClientState('op-1');
  state = reduceOperationReplay(state, {
    ok: true,
    operation: snapshot('running'),
    events: [
      event(1, 'operation.created'),
      event(2, 'operation.running'),
    ],
    after_sequence: 0,
    latest_sequence: 2,
    stream_latest_sequence: 4,
    has_more: true,
    terminal: false,
  });

  assert.equal(state.lastSequence, 2);
  assert.equal(state.resyncRequired, false);
  assert.equal(state.terminal, false);

  state = reduceOperationReplay(state, {
    ok: true,
    operation: snapshot('completed'),
    events: [
      event(3, 'assistant_content', {
        payload: { text: 'final', mode: 'replace' },
      }),
      event(4, 'operation.completed', {
        payload: {
          state: 'completed',
          final_output: 'final',
          result_ref: 'result:reconnect',
        },
      }),
    ],
    after_sequence: 2,
    latest_sequence: 4,
    stream_latest_sequence: 4,
    has_more: false,
    terminal: true,
  });

  assert.equal(state.lastSequence, 4);
  assert.equal(state.terminal, true);
  assert.equal(state.resyncRequired, false);
  assert.equal(state.displayedAssistantContent, 'final');
  assert.equal(state.events.length, 4);
  assert.equal(new Set(state.seenEventIds).size, 4);
});

test('slow-client page gaps fail closed instead of skipping retained work', () => {
  let state = createOperationClientState('op-1');
  state = reduceOperationReplay(state, {
    ok: true,
    operation: snapshot('running'),
    events: [event(1, 'operation.created')],
    after_sequence: 0,
    latest_sequence: 1,
    stream_latest_sequence: 5,
    has_more: true,
    terminal: false,
  });
  assert.equal(state.lastSequence, 1);

  const next = reduceOperationReplay(state, {
    ok: true,
    operation: snapshot('running'),
    events: [event(3, 'operation.running')],
    after_sequence: 1,
    latest_sequence: 3,
    stream_latest_sequence: 5,
    has_more: true,
    terminal: false,
  });

  assert.equal(next.lastSequence, 1);
  assert.equal(next.resyncRequired, true);
  assert.equal(next.error, 'sequence_gap');
});

test('cancel-complete race is terminal-fenced in both arrival orders', () => {
  let cancelledFirst = createOperationClientState('op-1');
  cancelledFirst = reduceOperationEvent(
    cancelledFirst,
    event(1, 'operation.cancelled', {
      payload: { state: 'cancelled' },
    }),
  );
  cancelledFirst = reduceOperationEvent(
    cancelledFirst,
    event(2, 'operation.completed', {
      payload: { state: 'completed', final_output: 'too late' },
    }),
  );
  assert.equal(cancelledFirst.resyncRequired, true);
  assert.equal(cancelledFirst.error, 'event_after_terminal');

  let completedFirst = createOperationClientState('op-1');
  completedFirst = reduceOperationEvent(
    completedFirst,
    event(1, 'operation.completed', {
      payload: {
        state: 'completed',
        final_output: 'winner',
        result_ref: 'result:winner',
      },
    }),
  );
  completedFirst = reduceOperationEvent(
    completedFirst,
    event(2, 'operation.cancelled', {
      payload: { state: 'cancelled' },
    }),
  );
  assert.equal(completedFirst.resyncRequired, true);
  assert.equal(completedFirst.error, 'event_after_terminal');
  assert.equal(completedFirst.displayedAssistantContent, 'winner');
});
