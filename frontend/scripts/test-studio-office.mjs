import assert from 'node:assert/strict';
import test from 'node:test';

import {
  OfficeController,
  goldenRequestBody,
  officeFailure,
  officeHeadline,
  officeHeaders,
  officeUrl,
  parseOfficeSse,
} from '../src/features/Office/studioOfficeClient.ts';

test('golden request does not replace the server brief', () => {
  const body = goldenRequestBody(4);
  assert.deepEqual(body, { frames: 4, live: false });
  assert.equal('brief' in body, false);
  assert.equal(officeUrl('http://127.0.0.1:8010/', '/api/v1/game/office/golden'), 'http://127.0.0.1:8010/api/v1/game/office/golden');
  const headers = officeHeaders(' seal ', 'studio');
  assert.equal(headers['x-gf-seal'], 'seal');
  assert.equal(headers['x-skeleton-tenant'], 'studio');
});

test('headline distinguishes empty, doctor red, degraded, and CORE_LOOP_OK', () => {
  assert.equal(officeHeadline({ phase: 'idle', error: '', run: null }).tone, 'empty');
  assert.equal(officeHeadline({ phase: 'loading', error: '', run: null }).tone, 'loading');
  assert.equal(officeHeadline({ phase: 'error', error: 'Charter denied.', run: null }).title, 'Office request failed');
  const red = officeHeadline({
    phase: 'ready',
    error: '',
    run: { run_id: '1', status: 'failed', error: { code: 'doctor_red' }, result: { codes: ['configuration_blocked'] } },
  });
  assert.equal(red.tone, 'failed');
  assert.match(red.detail, /configuration_blocked/);
  const degraded = officeHeadline({
    phase: 'ready',
    error: '',
    run: { run_id: '1', status: 'succeeded', result: { degraded: true, godot_ran: false, core_loop_ok: false, degraded_reason: 'missing-godot-binary' } },
  });
  assert.equal(degraded.tone, 'degraded');
  assert.match(degraded.title, /Godot did not run/);
  assert.doesNotMatch(degraded.title, /CORE_LOOP_OK/);
  const proved = officeHeadline({
    phase: 'ready',
    error: '',
    run: { run_id: '1', status: 'succeeded', result: { core_loop_ok: true, godot_ran: true, degraded: false } },
  });
  assert.equal(proved.title, 'CORE_LOOP_OK');
});

test('sse parser keeps a partial frame and charter denial is explicit', () => {
  const parsed = parseOfficeSse('id: 1\ndata: {"type":"operation.progress","payload":{"thought":"doctor green=true codes=[]"}}\n\ndata: {"type":');
  assert.equal(parsed.events.length, 1);
  assert.equal(parsed.events[0].type, 'operation.progress');
  assert.equal(parsed.rest, 'data: {"type":');
  assert.match(officeFailure(403, { detail: { error: 'charter_denied' } }), /Charter denied/);
  assert.match(officeFailure(401, {}), /seal/);
});

test('controller polls a degraded golden run and does not send a brief', async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, method: init?.method || 'GET', body: init?.body || null, seal: init?.headers?.['x-gf-seal'] });
    if (String(url).endsWith('/golden')) {
      return new Response(JSON.stringify({ run_id: 'run-1', status: 'queued', status_ref: '/api/v1/game/office/runs/run-1' }), { status: 202 });
    }
    if (String(url).endsWith('/stream')) {
      return new Response('no', { status: 404 });
    }
    return new Response(JSON.stringify({
      run_id: 'run-1',
      charter_id: 'game_builder',
      status: 'succeeded',
      heartbeat_seq: 3,
      steps: [{ index: 0, tool: 'game_build', status: 'succeeded', thought: 'game_build ok=true godot_did_not_prove' }],
      result: { degraded: true, godot_ran: false, core_loop_ok: false, degraded_reason: 'missing-godot-binary' },
      error: null,
    }), { status: 200 });
  };
  const office = new OfficeController({ base: 'http://127.0.0.1:8010', fetchImpl });
  office.setSeal('seal');
  office.setTenant('default');
  await office.startGolden();
  const snapshot = office.getSnapshot();
  assert.equal(snapshot.phase, 'ready');
  assert.equal(snapshot.run?.result?.core_loop_ok, false);
  assert.equal(officeHeadline(snapshot).tone, 'degraded');
  assert.equal(calls[0].method, 'POST');
  assert.deepEqual(JSON.parse(calls[0].body), { frames: 4, live: false });
  assert.equal(calls[0].seal, 'seal');
  assert.equal(calls.some((call) => String(call.body || '').includes('ash')), false);
});
