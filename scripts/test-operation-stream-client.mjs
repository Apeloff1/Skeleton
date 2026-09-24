import assert from 'node:assert/strict';
import test from 'node:test';

import {
  MemoryOperationCursorStore,
  OperationStreamClient,
} from '../frontend/services/operationStreamClient.ts';

function response(status, payload) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async json() {
      return payload;
    },
  };
}

test('replay persists and acknowledges only an applied cursor', async () => {
  const calls = [];
  const store = new MemoryOperationCursorStore();
  const fetchImpl = async (url, init = {}) => {
    calls.push({url, init});
    if (url.includes('/events/replay?')) {
      return response(200, {
        ok: true,
        operation: {
          operation_id: 'op-1',
          tenant_id: 'tenant-a',
          actor_id: 'actor-a',
          capability: 'chat',
          created_at: '2026-09-24T00:00:00+00:00',
          deadline: '2026-09-24T00:10:00+00:00',
          idempotency_key: 'idem-1',
          trace_id: 'trace-1',
          state: 'running',
          identity_digest: 'a'.repeat(64),
          version: 2,
          updated_at: '2026-09-24T00:00:01+00:00',
        },
        events: [{
          schema_version: 1,
          operation_id: 'op-1',
          event_id: 'event-1',
          sequence: 1,
          type: 'operation.running',
          timestamp: '2026-09-24T00:00:01+00:00',
          payload: {state: 'running'},
        }],
        after_sequence: 0,
        latest_sequence: 1,
        terminal: false,
      });
    }
    if (url.endsWith('/events/ack')) {
      return response(200, {ok: true});
    }
    throw new Error('unexpected request: ' + url);
  };

  const client = new OperationStreamClient({
    operationId: 'op-1',
    consumerId: 'web:1',
    cursorStore: store,
    fetchImpl,
  });
  await client.hydrate();
  const state = await client.replay();

  assert.equal(state.lastSequence, 1);
  assert.equal(state.operationState, 'running');
  assert.equal(state.connection, 'following');
  assert.equal(calls.filter(call => call.url.endsWith('/events/ack')).length, 1);

  const restored = new OperationStreamClient({
    operationId: 'op-1',
    consumerId: 'web:1',
    cursorStore: store,
    fetchImpl,
  });
  await restored.hydrate();
  assert.equal(restored.state.lastSequence, 1);
});

test('replay gap uses authoritative snapshot cursor instead of guessing', async () => {
  const calls = [];
  const store = new MemoryOperationCursorStore();
  const fetchImpl = async (url, init = {}) => {
    calls.push({url, init});
    if (url.includes('/events/replay?')) {
      return response(409, {
        detail: {error: 'replay_gap', resync_required: true},
      });
    }
    if (url.includes('/events/snapshot?')) {
      return response(200, {
        ok: true,
        operation: {
          operation_id: 'op-gap',
          tenant_id: 'tenant-a',
          actor_id: 'actor-a',
          capability: 'chat',
          created_at: '2026-09-24T00:00:00+00:00',
          deadline: '2026-09-24T00:10:00+00:00',
          idempotency_key: 'idem-gap',
          trace_id: 'trace-gap',
          state: 'running',
          identity_digest: 'b'.repeat(64),
          version: 9,
          updated_at: '2026-09-24T00:00:09+00:00',
        },
        compacted_through: 7,
        latest_sequence: 9,
        terminal: false,
      });
    }
    if (url.endsWith('/events/ack')) {
      return response(200, {ok: true});
    }
    throw new Error('unexpected request: ' + url);
  };

  const client = new OperationStreamClient({
    operationId: 'op-gap',
    consumerId: 'web:gap',
    cursorStore: store,
    fetchImpl,
  });
  await client.hydrate();
  const state = await client.replay();

  assert.equal(state.lastSequence, 9);
  assert.equal(state.operationState, 'running');
  assert.equal(state.resyncRequired, false);
  assert.equal(calls.some(call => call.url.includes('/events/snapshot?')), true);
  assert.equal(calls.filter(call => call.url.endsWith('/events/ack')).length, 1);
});

test('invalid authoritative snapshot fails closed', async () => {
  const fetchImpl = async (url) => {
    if (url.includes('/events/snapshot?')) {
      return response(200, {
        ok: true,
        operation: {
          operation_id: 'op-bad',
          tenant_id: 'tenant-a',
          actor_id: 'actor-a',
          capability: 'chat',
          created_at: '2026-09-24T00:00:00+00:00',
          deadline: '2026-09-24T00:10:00+00:00',
          idempotency_key: 'idem-bad',
          trace_id: 'trace-bad',
          state: 'running',
          identity_digest: 'c'.repeat(64),
          version: 2,
          updated_at: '2026-09-24T00:00:02+00:00',
        },
        compacted_through: 8,
        latest_sequence: 7,
        terminal: false,
      });
    }
    throw new Error('unexpected request: ' + url);
  };

  const client = new OperationStreamClient({
    operationId: 'op-bad',
    consumerId: 'web:bad',
    fetchImpl,
  });
  const state = await client.resync();

  assert.equal(state.resyncRequired, true);
  assert.equal(state.connection, 'resync_required');
  assert.equal(state.error, 'invalid_resync_cursor');
});
