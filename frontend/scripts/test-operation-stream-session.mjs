import assert from 'node:assert/strict';
import test from 'node:test';

import {
  OperationBrowserSession,
} from '../services/operationStreamSession.ts';

function snapshot(state = 'running', version = 1) {
  return {
    operation_id: 'op-browser',
    tenant_id: 'tenant-a',
    actor_id: 'actor-a',
    capability: 'chat',
    created_at: '2026-09-27T00:00:00+00:00',
    deadline: '2026-09-27T00:10:00+00:00',
    idempotency_key: 'idem-browser',
    trace_id: 'trace-browser',
    state,
    identity_digest: 'digest-browser',
    version,
    updated_at: '2026-09-27T00:00:00+00:00',
  };
}

function event(sequence, type, payload = {}) {
  return {
    schema_version: 1,
    operation_id: 'op-browser',
    event_id: `browser-event-${sequence}`,
    sequence,
    type,
    timestamp: '2026-09-27T00:00:00+00:00',
    payload,
  };
}

class MemoryCursorStore {
  values = new Map();
  writes = [];

  key(operationId, consumerId) {
    return `${consumerId}:${operationId}`;
  }

  async load(operationId, consumerId) {
    return this.values.get(this.key(operationId, consumerId)) ?? 0;
  }

  async save(operationId, consumerId, sequence) {
    this.values.set(this.key(operationId, consumerId), sequence);
    this.writes.push(sequence);
  }

  async clear(operationId, consumerId) {
    this.values.delete(this.key(operationId, consumerId));
  }
}

class ScriptedTransport {
  constructor({ replay, resync, cancel }) {
    this.replayScript = replay;
    this.resyncScript = resync;
    this.cancelScript = cancel;
    this.replayCalls = [];
    this.acks = [];
    this.resyncCalls = 0;
    this.cancelCalls = 0;
  }

  async replay(operationId, consumerId, afterSequence, limit) {
    this.replayCalls.push({ operationId, consumerId, afterSequence, limit });
    return this.replayScript(afterSequence, limit);
  }

  async acknowledge(operationId, consumerId, sequence) {
    this.acks.push({ operationId, consumerId, sequence });
    return { ok: true };
  }

  async resync(operationId, consumerId) {
    this.resyncCalls += 1;
    return this.resyncScript?.(operationId, consumerId) ?? null;
  }

  async cancel(operationId) {
    this.cancelCalls += 1;
    return this.cancelScript?.(operationId) ?? { ok: false, error: 'unsupported' };
  }
}

test('browser disconnect and reconnect resumes from persisted accepted cursor', async () => {
  const cursors = new MemoryCursorStore();
  const transport = new ScriptedTransport({
    replay(afterSequence) {
      if (afterSequence === 0) {
        return {
          ok: true,
          payload: {
            ok: true,
            operation: snapshot('running', 2),
            events: [
              event(1, 'operation.created', { state: 'created' }),
              event(2, 'operation.running', { state: 'running' }),
            ],
            after_sequence: 0,
            latest_sequence: 2,
            stream_latest_sequence: 4,
            has_more: true,
            terminal: false,
          },
        };
      }
      assert.equal(afterSequence, 2);
      return {
        ok: true,
        payload: {
          ok: true,
          operation: snapshot('completed', 4),
          events: [
            event(3, 'assistant_content', {
              text: 'canonical answer',
              mode: 'replace',
            }),
            event(4, 'operation.completed', {
              state: 'completed',
              final_output: 'canonical answer',
              result_ref: 'result:browser',
            }),
          ],
          after_sequence: 2,
          latest_sequence: 4,
          stream_latest_sequence: 4,
          has_more: false,
          terminal: true,
        },
      };
    },
  });

  const first = new OperationBrowserSession(
    'op-browser',
    transport,
    cursors,
    {
      consumerId: 'browser-session-a',
      replayLimit: 2,
    },
  );
  const beforeDisconnect = await first.replayOnce();
  assert.equal(beforeDisconnect.lastSequence, 2);
  assert.equal(beforeDisconnect.terminal, false);
  assert.equal(await cursors.load('op-browser', 'browser-session-a'), 2);

  const reconnected = new OperationBrowserSession(
    'op-browser',
    transport,
    cursors,
    {
      consumerId: 'browser-session-a',
      replayLimit: 2,
    },
  );
  const terminal = await reconnected.resume();

  assert.equal(terminal.lastSequence, 4);
  assert.equal(terminal.terminal, true);
  assert.equal(terminal.displayedAssistantContent, 'canonical answer');
  assert.equal(terminal.terminalResultRef, 'result:browser');
  assert.deepEqual(
    transport.replayCalls.map((item) => item.afterSequence),
    [0, 2],
  );
  assert.deepEqual(
    transport.acks.map((item) => item.sequence),
    [2, 4],
  );
  assert.equal(await cursors.load('op-browser', 'browser-session-a'), 4);
});

test('slow browser recovers from compacted replay gap through authoritative floor', async () => {
  const cursors = new MemoryCursorStore();
  let staleReplaySeen = false;
  const transport = new ScriptedTransport({
    replay(afterSequence) {
      if (afterSequence === 0) {
        return {
          ok: true,
          payload: {
            ok: true,
            operation: snapshot('running', 1),
            events: [
              event(1, 'operation.created', { state: 'created' }),
            ],
            after_sequence: 0,
            latest_sequence: 1,
            stream_latest_sequence: 5,
            has_more: true,
            terminal: false,
          },
        };
      }
      if (afterSequence === 1 && !staleReplaySeen) {
        staleReplaySeen = true;
        return {
          ok: false,
          replayGap: true,
          error: 'replay_gap',
        };
      }
      assert.equal(afterSequence, 3);
      return {
        ok: true,
        payload: {
          ok: true,
          operation: snapshot('completed', 5),
          events: [
            event(4, 'assistant_content', {
              text: 'recovered',
              mode: 'replace',
            }),
            event(5, 'operation.completed', {
              state: 'completed',
              final_output: 'recovered',
              result_ref: 'result:recovered',
            }),
          ],
          after_sequence: 3,
          latest_sequence: 5,
          stream_latest_sequence: 5,
          has_more: false,
          terminal: true,
        },
      };
    },
    resync() {
      return {
        ok: true,
        operation: snapshot('running', 3),
        compacted_through: 3,
        resume_after_sequence: 3,
        latest_sequence: 5,
        terminal: false,
        active_consumer_count: 1,
      };
    },
  });

  const session = new OperationBrowserSession(
    'op-browser',
    transport,
    cursors,
    {
      consumerId: 'slow-browser',
      replayLimit: 1,
      maxResyncAttempts: 2,
    },
  );

  const first = await session.replayOnce();
  assert.equal(first.lastSequence, 1);

  const recovered = await session.resume();
  assert.equal(recovered.lastSequence, 5);
  assert.equal(recovered.terminal, true);
  assert.equal(recovered.resyncRequired, false);
  assert.equal(recovered.displayedAssistantContent, 'recovered');
  assert.equal(transport.resyncCalls, 1);
  assert.deepEqual(cursors.writes, [1, 3, 5]);
});

test('cancel-complete race exposes exactly one canonical terminal outcome per session', async () => {
  for (const winner of ['completed', 'cancelled']) {
    const cursors = new MemoryCursorStore();
    const terminalType = `operation.${winner}`;
    const terminalPayload = winner === 'completed'
      ? {
          state: 'completed',
          final_output: 'winner',
          result_ref: 'result:winner',
        }
      : { state: 'cancelled' };

    const transport = new ScriptedTransport({
      replay() {
        return {
          ok: true,
          payload: {
            ok: true,
            operation: snapshot(winner, 2),
            events: [
              event(1, 'operation.created', { state: 'created' }),
              event(2, terminalType, terminalPayload),
            ],
            after_sequence: 0,
            latest_sequence: 2,
            stream_latest_sequence: 2,
            has_more: false,
            terminal: true,
          },
        };
      },
      cancel() {
        return {
          ok: true,
          changed: winner === 'cancelled',
          operation: snapshot(winner, 2),
        };
      },
    });

    const session = new OperationBrowserSession(
      'op-browser',
      transport,
      cursors,
      { consumerId: `race-${winner}` },
    );

    const cancellation = await session.cancel();
    assert.equal(cancellation.ok, true);

    const terminal = await session.resume();
    assert.equal(terminal.terminal, true);
    assert.equal(terminal.operationState, winner);
    assert.equal(
      terminal.events.filter((item) =>
        ['operation.completed', 'operation.cancelled'].includes(item.type)
      ).length,
      1,
    );
    if (winner === 'completed') {
      assert.equal(terminal.displayedAssistantContent, 'winner');
      assert.equal(terminal.contentState, 'canonical');
    } else {
      assert.equal(terminal.displayedAssistantContent, '');
      assert.equal(terminal.contentState, 'discarded');
    }
  }
});


test('terminal authoritative resync snapshot reconciles canonical output before fencing', async () => {
  const cursors = new MemoryCursorStore();
  const transport = new ScriptedTransport({
    replay() {
      return {
        ok: false,
        replayGap: true,
        error: 'replay_gap',
      };
    },
    resync() {
      return {
        ok: true,
        operation: snapshot('completed', 5),
        compacted_through: 5,
        resume_after_sequence: 5,
        latest_sequence: 5,
        terminal: true,
        active_consumer_count: 1,
        canonical_result: {
          status: 'completed',
          final_output: 'snapshot canonical',
          result_ref: 'result:snapshot-canonical',
        },
      };
    },
  });

  const session = new OperationBrowserSession(
    'op-browser',
    transport,
    cursors,
    { consumerId: 'terminal-resync-browser' },
  );

  const terminal = await session.resume();

  assert.equal(terminal.terminal, true);
  assert.equal(terminal.connection, 'terminal');
  assert.equal(terminal.contentState, 'canonical');
  assert.equal(terminal.displayedAssistantContent, 'snapshot canonical');
  assert.equal(terminal.terminalResultRef, 'result:snapshot-canonical');
  assert.equal(terminal.resyncRequired, false);
  assert.equal(transport.resyncCalls, 1);
  assert.deepEqual(cursors.writes, [5]);
});


test('browser terminal artifact result linkage survives reconnect', async () => {
  const cursors = new MemoryCursorStore();
  await cursors.save('op-browser', 'artifact-browser', 1);
  const transport = new ScriptedTransport({
    replay(afterSequence) {
      assert.equal(afterSequence, 1);
      return {
        ok: true,
        payload: {
          ok: true,
          operation: snapshot('completed', 2),
          events: [
            event(2, 'operation.completed', {
              state: 'completed',
              final_output: 'artifact ready',
              result_ref: 'artifact:stage7-output',
              message_id: 'message:stage7-output',
            }),
          ],
          after_sequence: 1,
          latest_sequence: 2,
          stream_latest_sequence: 2,
          has_more: false,
          terminal: true,
        },
      };
    },
  });

  const session = new OperationBrowserSession(
    'op-browser',
    transport,
    cursors,
    { consumerId: 'artifact-browser' },
  );
  const terminal = await session.resume();

  assert.equal(terminal.terminal, true);
  assert.equal(terminal.displayedAssistantContent, 'artifact ready');
  assert.equal(terminal.terminalResultRef, 'artifact:stage7-output');
  assert.equal(terminal.terminalMessageId, 'message:stage7-output');
  assert.equal(
    await cursors.load('op-browser', 'artifact-browser'),
    2,
  );
});
