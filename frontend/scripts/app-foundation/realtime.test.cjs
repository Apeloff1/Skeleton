'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('./harness.cjs');
const C = load('src/foundation/realtime/core.ts');
const { EventStreamClient } = load('src/foundation/realtime/client.ts', { './core': C });
const P = load('src/foundation/realtime/presence.ts');

const env = (id, type = 'build.progress', extra = {}) => JSON.stringify({ v: 1, id, ts: `2026-10-17T16:00:0${id}Z`, channel: type.split('.')[0], type, payload: {}, ...extra });
const frame = (id, type, data) => `id: ${id}\nevent: ${type}\ndata: ${data}\n\n`;

// ── fake clock + mock SSE server ───────────────────────────────────────
function fakeClock(seed = [0.5]) {
  let t = 0; const timers = new Map(); let seq = 0; let r = 0;
  return {
    now: () => t,
    setTimeout: (fn, ms) => { const id = ++seq; timers.set(id, { at: t + ms, fn }); return id; },
    clearTimeout: (id) => timers.delete(id),
    random: () => seed[r++ % seed.length],
    pending: () => [...timers.values()].map(x => x.at - t).sort((a, b) => a - b),
    async advance(ms) {
      const end = t + ms;
      for (;;) {
        const due = [...timers.entries()].filter(([, v]) => v.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
        if (!due) break;
        timers.delete(due[0]); t = due[1].at; due[1].fn();
        await new Promise(setImmediate);
      }
      t = end;
    },
  };
}
function mockServer() {
  const conns = [];
  const transport = (path, o) => new Promise((resolve) => {
    const c = { path, headers: o.headers, signal: o.signal, open: (s = 200) => o.onOpen(s), send: (txt) => o.onChunk(txt), end: (r = { kind: 'eof' }) => resolve(r) };
    o.signal.addEventListener('abort', () => resolve({ kind: 'aborted' }));
    conns.push(c);
  });
  return { conns, transport, last: () => conns[conns.length - 1] };
}
const tick = () => new Promise(setImmediate);

test('SseParser: frames, multi-line data, CRLF split across chunks, comments, retry', () => {
  const p = new C.SseParser();
  assert.deepEqual(p.feed(': hb\n'), [{ kind: 'comment', text: 'hb' }]);
  assert.deepEqual(p.feed('id: 7\r'), []);
  assert.deepEqual(p.feed('\nevent: build.log\r\ndata: a\ndata: b\nretry: 2500\n'), []);
  const out = p.feed('\n');
  assert.deepEqual(out, [{ kind: 'frame', frame: { id: '7', event: 'build.log', data: 'a\nb', retry: 2500 } }]);
  assert.deepEqual(p.feed('data:x\n\n'), [{ kind: 'frame', frame: { id: '7', event: 'message', data: 'x', retry: undefined } }], 'id persists per spec');
  assert.deepEqual(p.feed('event: only\n\n'), [], 'no data → no dispatch');
});

test('parseEnvelope: v1 validation, unknown fields ignored, optional fields typed', () => {
  const ok = C.parseEnvelope(JSON.stringify({ v: 1, id: '9', ts: 't', channel: 'build', type: 'build.started', payload: { a: 1 }, job_id: 'j1', correlation_id: 'r', extra: 'x', secret: 's' }));
  assert.equal(ok.ok, true);
  assert.deepEqual(ok.envelope, { v: 1, id: '9', ts: 't', channel: 'build', type: 'build.started', payload: { a: 1 }, job_id: 'j1', correlation_id: 'r' });
  assert.equal(C.parseEnvelope('{bad').reason, 'invalid_json');
  assert.equal(C.parseEnvelope('[]').reason, 'not_object');
  assert.equal(C.parseEnvelope({ v: 2, id: '1', type: 'x', channel: 'build' }).reason, 'unsupported_version');
  assert.equal(C.parseEnvelope({ v: 1, type: 'x', channel: 'build' }).reason, 'missing_id');
  assert.equal(C.parseEnvelope({ v: 1, type: 'x', channel: 'build' }, '5').reason, 'missing_id', 'envelope id is required; the SSE id line is not a substitute');
  assert.equal(C.parseEnvelope({ v: 1, id: 3, type: 'x', channel: 'build', payload: [1], job_id: 4 }).envelope.payload.constructor, Object);
  assert.equal(C.parseEnvelope({ v: 1, id: 3, type: 'x', channel: 'build', job_id: 4 }).envelope.job_id, undefined);
  assert.equal(C.parseEnvelope({ v: 1, id: '1', channel: 'build' }).reason, 'missing_type');
});

test('buildStreamPath / resumeHeaders', () => {
  assert.equal(C.buildStreamPath({ channels: ['presence', 'build', 'build'] }), '/api/v1/events?channels=build,presence');
  assert.equal(C.buildStreamPath({ channels: [], jobId: 'a b' }), '/api/v1/events?channels=build,agent,presence&job_id=a%20b');
  assert.equal(C.buildStreamPath({ channels: ['agent'], cursor: '42', useCursorParam: true }), '/api/v1/events?channels=agent&cursor=42');
  assert.equal(C.buildStreamPath({ channels: ['agent'], cursor: '42' }), '/api/v1/events?channels=agent');
  assert.deepEqual(C.resumeHeaders('42'), { 'Last-Event-ID': '42' });
  assert.deepEqual(C.resumeHeaders(null), {});
});

test('backoff: full jitter within [250ms, min(30s, 0.5s·2^n)], retry floor, healthy reset', () => {
  assert.equal(C.backoffDelay(0, () => 0), 250);
  assert.equal(C.backoffDelay(0, () => 1), 500);
  assert.equal(C.backoffDelay(3, () => 1), 4000);
  assert.equal(C.backoffDelay(20, () => 1), 30000);
  assert.equal(C.backoffDelay(20, () => 0.5), 15000);
  assert.equal(C.backoffDelay(0, () => 0, 5000), 5000);
  assert.equal(C.backoffDelay(0, () => 0, 99999), 30000);
  for (let a = 0; a < 12; a++) for (const r of [0, 0.3, 0.99]) { const d = C.backoffDelay(a, () => r); assert.ok(d >= 250 && d <= 30000); }
  assert.equal(C.nextAttempt(4, 0, 59_999), 5);
  assert.equal(C.nextAttempt(4, 0, 60_000), 0);
  assert.equal(C.nextAttempt(2, null, 1e9), 3);
  assert.equal(C.isStreamDead(0, 44_999), false);
  assert.equal(C.isStreamDead(0, 45_000), true);
});

test('applyItem: cursor advances, reset resumes at head_id, lagged keeps Last-Event-ID, bad frames rejected', () => {
  let s = C.initialStreamState('3');
  let r = C.applyItem(s, { kind: 'frame', frame: { id: '4', event: 'build.progress', data: env('4') } }, 10);
  assert.equal(r.state.cursor, '4'); assert.equal(r.effects[0].kind, 'deliver'); assert.equal(r.state.lastActivityAt, 10);
  r = C.applyItem(r.state, { kind: 'comment', text: 'hb' }, 20);
  assert.equal(r.state.lastActivityAt, 20); assert.deepEqual(r.effects, []);
  r = C.applyItem(r.state, { kind: 'frame', frame: { id: '5', event: 'stream.lagged', data: JSON.stringify({ v: 1, type: 'stream.lagged', payload: { dropped: 7, resume_from: '1' } }) } }, 30);
  assert.deepEqual(r.effects, [{ kind: 'lagged', dropped: 7 }]); assert.equal(r.state.lagged, 7);
  assert.equal(r.state.cursor, '4', 'a control frame never moves Last-Event-ID');
  const reset = JSON.stringify({ v: 1, ts: '2026-10-17T16:00:00.123Z', type: 'stream.reset', payload: { reason: 'cursor_aged_out', cursor: '4', head_id: '40', oldest_id: '20' } });
  r = C.applyItem(r.state, { kind: 'frame', frame: { event: 'stream.reset', data: reset } }, 40);
  assert.deepEqual(r.effects, [{ kind: 'reset' }]); assert.equal(r.state.cursor, '40'); assert.equal(r.state.resets, 1);
  r = C.applyItem(r.state, { kind: 'frame', frame: { event: 'stream.reset', data: '{}' } }, 41);
  assert.equal(r.state.cursor, null, 'reset without head_id clears the cursor');
  const fresh = C.applyItem(C.initialStreamState(null), { kind: 'frame', frame: { event: 'stream.lagged', data: JSON.stringify({ v: 1, type: 'stream.lagged', payload: { dropped: 3, resume_from: '41' } }) } }, 42);
  assert.equal(fresh.state.cursor, '41', 'resume_from is used only when there is no cursor yet');
  r = C.applyItem(r.state, { kind: 'frame', frame: { id: '6', event: 'x', data: 'nope', retry: 3000 } }, 50);
  assert.equal(r.state.rejected, 1); assert.equal(r.state.cursor, null, 'rejected frame does not advance cursor'); assert.equal(r.state.retryFloorMs, 3000);
});

test('parseEnvelope: sample envelope from tests/test_realtime_envelope.py (#4128)', () => {
  // RealtimeEvent(id="42", ts="2026-10-17T16:00:00.123Z", channel="build",
  //   type="build.progress", payload={"pct": 50}, job_id="job-7", correlation_id="corr-1")
  // Wire JSON is sort_keys + compact separators, matching RealtimeEvent.to_json().
  const wire = '{"channel":"build","correlation_id":"corr-1","id":"42","job_id":"job-7","payload":{"pct":50},"ts":"2026-10-17T16:00:00.123Z","type":"build.progress","v":1}';
  const sse = `retry: 2000\n\n: hb\n\nid: 42\nevent: build.progress\ndata: ${wire}\n\n`;
  const parsed = new C.SseParser().feed(sse);
  assert.equal(parsed.length, 2);
  assert.deepEqual(parsed[0], { kind: 'comment', text: 'hb' });
  assert.equal(parsed[1].frame.id, '42');
  assert.equal(parsed[1].frame.event, 'build.progress');
  const env = C.parseEnvelope(parsed[1].frame.data, parsed[1].frame.id);
  assert.equal(env.ok, true);
  assert.deepEqual(env.envelope, {
    v: 1, id: '42', ts: '2026-10-17T16:00:00.123Z', channel: 'build', type: 'build.progress',
    payload: { pct: 50 }, job_id: 'job-7', correlation_id: 'corr-1',
  });
  assert.equal(C.parseEnvelope(wire, '41').reason, 'id_mismatch');
  const projected = C.reduceBuildProgress({}, env.envelope);
  assert.equal(projected['job-7'].percent, 50);
  assert.deepEqual(C.realtimeAuthHeaders('seal.1.abc'), { 'x-gf-seal': 'seal.1.abc' });
  assert.deepEqual(C.realtimeAuthHeaders('  '), {});
  // ControlEvent(type="stream.lagged", payload={"dropped": 3}) has no id line.
  const lagged = '{"payload":{"dropped":3,"resume_from":"41"},"ts":"2026-10-17T16:00:00.123Z","type":"stream.lagged","v":1}';
  const control = new C.SseParser().feed(`event: stream.lagged\ndata: ${lagged}\n\n`);
  assert.equal(control[0].frame.id, undefined);
  assert.equal(control[0].frame.event, 'stream.lagged');
});

test('reduceBuildProgress projects build events per job', () => {
  const e = (type, payload, job = 'j1', ts = 't1') => ({ v: 1, id: '1', ts, channel: 'build', type, payload, job_id: job });
  let b = C.reduceBuildProgress({}, e('build.started', { stage: 'queued' }));
  assert.deepEqual(b.j1, { jobId: 'j1', status: 'running', percent: null, message: 'queued', updatedAt: 't1' });
  b = C.reduceBuildProgress(b, e('build.progress', { progress: 0.426, message: 'compiling' }));
  assert.equal(b.j1.percent, 43); assert.equal(b.j1.message, 'compiling');
  b = C.reduceBuildProgress(b, e('build.log', { line: 'x' }));
  assert.equal(b.j1.percent, 43); assert.equal(b.j1.status, 'running');
  b = C.reduceBuildProgress(b, e('build.completed', {}));
  assert.equal(b.j1.status, 'completed'); assert.equal(b.j1.percent, 100);
  assert.equal(C.reduceBuildProgress(b, { ...e('agent.step', {}), channel: 'agent' }), b);
  assert.equal(C.reduceBuildProgress(b, { ...e('build.progress', {}), job_id: undefined }), b);
  assert.equal(C.reduceBuildProgress({}, e('build.failed', { percent: 250 })).j1.percent, 100);
});

test('client: delivers events, resumes with Last-Event-ID after EOF with jittered backoff', async () => {
  const clock = fakeClock([1]); const srv = mockServer(); const got = []; const states = [];
  const c = new EventStreamClient({ channels: ['build'], transport: srv.transport, clock, headers: () => ({ 'x-gf-seal': 't' }), onEvent: (e) => got.push(e.id), onState: (s) => states.push(s.status) });
  c.start(); await tick();
  assert.equal(srv.conns.length, 1);
  assert.equal(srv.last().path, '/api/v1/events?channels=build');
  assert.deepEqual(srv.last().headers, { 'x-gf-seal': 't' });
  srv.last().open(); srv.last().send(frame('1', 'build.started', env('1', 'build.started')) + frame('2', 'build.progress', env('2')));
  assert.deepEqual(got, ['1', '2']);
  assert.equal(c.getState().status, 'open');
  srv.last().end(); await tick();
  assert.equal(c.getState().status, 'reconnecting');
  assert.deepEqual(clock.pending().filter(d => d <= 500), [500], 'attempt 0 delay = 0.5s with random=1');
  await clock.advance(500);
  assert.equal(srv.conns.length, 2);
  assert.equal(srv.last().headers['Last-Event-ID'], '2');
  c.stop(); assert.equal(c.getState().status, 'closed');
  assert.ok(states.includes('connecting') && states.includes('open'));
});

test('client: ?cursor= mode when headers are unavailable; backoff grows then resets after 60s healthy', async () => {
  const clock = fakeClock([1]); const srv = mockServer();
  const c = new EventStreamClient({ channels: ['agent'], transport: srv.transport, clock, useCursorParam: true, initialCursor: '10' });
  c.start(); await tick();
  assert.equal(srv.last().path, '/api/v1/events?channels=agent&cursor=10');
  assert.equal(srv.last().headers['Last-Event-ID'], undefined);
  const delays = [];
  for (let i = 0; i < 4; i++) {
    srv.last().end({ kind: 'error', error: 'network_error' }); await tick();
    const d = Math.min(...clock.pending()); delays.push(d); await clock.advance(d);
  }
  assert.deepEqual(delays, [500, 1000, 2000, 4000]);
  srv.last().open(); await clock.advance(60_000 - 1); // watchdog would fire; keep alive with heartbeats
  c.stop();
  const clock2 = fakeClock([1]); const srv2 = mockServer();
  const c2 = new EventStreamClient({ channels: ['agent'], transport: srv2.transport, clock: clock2 });
  c2.start(); await tick();
  for (let i = 0; i < 3; i++) { srv2.last().end(); await tick(); await clock2.advance(Math.min(...clock2.pending())); }
  srv2.last().open();
  for (let i = 0; i < 5; i++) { await clock2.advance(14_000); srv2.last().send(': hb\n'); }
  srv2.last().end(); await tick();
  assert.equal(c2.getState().attempt, 0, 'healthy ≥60s resets attempts');
  assert.equal(Math.min(...clock2.pending()), 500);
  c2.stop();
});

test('client: 45s silence aborts and reconnects; heartbeats keep it alive', async () => {
  const clock = fakeClock([1]); const srv = mockServer();
  const c = new EventStreamClient({ channels: ['build'], transport: srv.transport, clock });
  c.start(); await tick(); srv.last().open();
  for (let i = 0; i < 4; i++) { await clock.advance(15_000); srv.last().send(': hb\n'); }
  assert.equal(srv.conns.length, 1, 'heartbeats every 15s keep the stream');
  await clock.advance(45_000); await tick();
  assert.equal(srv.conns[0].signal.aborted, true, 'dead stream aborted');
  await clock.advance(30_000);
  assert.equal(srv.conns.length, 2, 'reconnected after backoff');
  c.stop();
});

test('client: stream.reset resumes at head_id; lagged reconnects immediately without moving the cursor; 401 stops', async () => {
  const clock = fakeClock([1]); const srv = mockServer(); let resets = 0; const lagged = [];
  const c = new EventStreamClient({ channels: ['build'], transport: srv.transport, clock, initialCursor: '99', onReset: () => resets++, onLagged: (d) => lagged.push(d) });
  c.start(); await tick();
  assert.equal(srv.last().headers['Last-Event-ID'], '99');
  srv.last().open();
  const reset = JSON.stringify({ v: 1, ts: '2026-10-17T16:00:00.123Z', type: 'stream.reset', payload: { reason: 'cursor_aged_out', cursor: '99', head_id: '120', oldest_id: '80' } });
  srv.last().send(`event: stream.reset\ndata: ${reset}\n\n`);
  assert.equal(resets, 1);
  assert.equal(c.getState().cursor, '120');
  const laggedBody = JSON.stringify({ v: 1, ts: '2026-10-17T16:00:00.123Z', type: 'stream.lagged', payload: { dropped: 12, resume_from: '100' } });
  srv.last().send(`event: stream.lagged\ndata: ${laggedBody}\n\n`);
  assert.deepEqual(lagged, [12]);
  assert.equal(c.getState().cursor, '120', 'control frame does not move the cursor');
  await tick();
  assert.equal(srv.conns[0].signal.aborted, true, 'lagged aborts the live stream');
  await clock.advance(0);
  assert.equal(srv.conns.length, 2, 'reconnects immediately');
  assert.equal(srv.last().headers['Last-Event-ID'], '120');
  srv.last().end({ kind: 'http', status: 401 }); await tick();
  assert.equal(c.getState().status, 'closed');
  await clock.advance(60_000);
  assert.equal(srv.conns.length, 2, 'no reconnect after auth failure');
});

test('client: stale connection callbacks are ignored after stop/reconnect', async () => {
  const clock = fakeClock([1]); const srv = mockServer(); const got = [];
  const c = new EventStreamClient({ channels: ['build'], transport: srv.transport, clock, onEvent: (e) => got.push(e.id) });
  c.start(); await tick();
  const first = srv.last();
  c.stop();
  first.send(frame('1', 'build.progress', env('1')));
  first.end(); await tick(); await clock.advance(60_000);
  assert.deepEqual(got, []); assert.equal(srv.conns.length, 1);
});

test('presence: join, heartbeat, leave once; errors swallowed; validation', async () => {
  const posts = []; let intervalFn = null; let cleared = false;
  const stop = P.startPresence('app', 'c_1', {
    post: async (path, body) => { posts.push([path, body.action]); if (body.action === 'heartbeat') throw new Error('net'); },
    setInterval: (fn, ms) => { intervalFn = fn; assert.equal(ms, 15_000); return 1; },
    clearInterval: () => { cleared = true; },
  });
  await tick();
  intervalFn(); await tick();
  stop(); stop(); await tick();
  assert.deepEqual(posts, [['/api/v1/presence', 'join'], ['/api/v1/presence', 'heartbeat'], ['/api/v1/presence', 'leave']]);
  assert.equal(cleared, true);
  assert.deepEqual(P.presenceBody('join', 'app', 'c'), { action: 'join', scope: 'app', client_id: 'c' });
  assert.deepEqual(P.presenceBody('join', 'app', 'c', { tab: 'forge' }), { action: 'join', scope: 'app', client_id: 'c', meta: { tab: 'forge' } });
  assert.deepEqual(P.presenceBody('heartbeat', 'app', 'c', { tab: 'forge' }), { action: 'heartbeat', scope: 'app', client_id: 'c' });
  assert.throws(() => P.presenceBody('join', '', 'c'));
  assert.match(P.newClientId(() => 0.5), /^c_8{16}$/);
});
