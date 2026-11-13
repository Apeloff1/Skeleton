'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('./harness.cjs');
const G = load('src/foundation/sessionGate.ts');

const snap = (status, extra = {}) => ({ status, enforced: true, role: 'anonymous', error: null, ...extra });

test('unknown and checking sessions wait', () => {
  assert.deepEqual(G.decideGate(snap('unknown'), '/account'), { kind: 'wait' });
  assert.deepEqual(G.decideGate(snap('checking'), '/account'), { kind: 'wait' });
  assert.equal(G.INITIAL_SESSION.status, 'unknown');
});

test('anonymous with enforced auth redirects to sign-in with returnTo', () => {
  const d = G.decideGate(snap('anonymous'), '/account?tab=a');
  assert.equal(d.kind, 'redirect');
  assert.equal(d.to, '/sign-in?returnTo=' + encodeURIComponent('/account?tab=a'));
});

test('anonymous allowed when backend does not enforce auth, unless a role is required', () => {
  assert.deepEqual(G.decideGate(snap('anonymous', { enforced: false }), '/account'), { kind: 'allow' });
  assert.equal(G.decideGate(snap('anonymous', { enforced: false }), '/x', { requiredRole: 'admin' }).kind, 'redirect');
});

test('authenticated allowed; role requirement enforced', () => {
  assert.deepEqual(G.decideGate(snap('authenticated', { role: 'user' }), '/a'), { kind: 'allow' });
  assert.equal(G.decideGate(snap('authenticated', { role: 'user' }), '/a', { requiredRole: 'admin' }).kind, 'error');
  assert.equal(G.decideGate(snap('authenticated', { role: 'owner' }), '/a', { requiredRole: 'admin' }).kind, 'allow');
  assert.equal(G.roleSatisfies('custom', 'custom'), true);
  assert.equal(G.roleSatisfies('admin', 'custom'), false);
});

test('unavailable surfaces an error message', () => {
  assert.deepEqual(G.decideGate(snap('unavailable', { error: 'down' }), '/'), { kind: 'error', message: 'down' });
  assert.equal(G.decideGate(snap('unavailable'), '/').kind, 'error');
});

test('safeReturnTo rejects external, protocol-relative and sign-in loops', () => {
  assert.equal(G.safeReturnTo('/account'), '/account');
  assert.equal(G.safeReturnTo('https://evil.example'), '/');
  assert.equal(G.safeReturnTo('//evil.example'), '/');
  assert.equal(G.safeReturnTo('/\\evil'), '/');
  assert.equal(G.safeReturnTo('/sign-in?returnTo=/x'), '/');
  assert.equal(G.safeReturnTo(undefined, '/home'), '/home');
  assert.equal(G.safeReturnTo(['x']), '/');
});

test('snapshotFromMe maps the /api/auth/me contract', () => {
  assert.deepEqual(G.snapshotFromMe({ authenticated: true, enforced: true, role: 'admin', observed: true }),
    { status: 'authenticated', enforced: true, role: 'admin', error: null });
  assert.equal(G.snapshotFromMe({ authenticated: true, enforced: true }).role, 'user');
  assert.deepEqual(G.snapshotFromMe({ authenticated: false, enforced: false, role: 'x' }),
    { status: 'anonymous', enforced: false, role: 'anonymous', error: null });
  const u = G.snapshotFromMe({ authenticated: false, enforced: true, observed: false, error: 'boom' });
  assert.equal(u.status, 'unavailable');
  assert.equal(u.error, 'boom');
});
