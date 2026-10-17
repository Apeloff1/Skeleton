/**
 * App foundation E2E suite: onboarding, sign-in, create project from brief,
 * watch build, open result. Plan: docs/qa/APP_FOUNDATION_E2E_TEST_PLAN.md.
 *
 * Tier 1 (always runs, no backend): route + source contracts and the pure
 * product modules that drive each flow.
 * Tier 2 (live, opt-in): set SKELETON_E2E_BASE_URL (e.g. http://localhost:8001)
 * to drive the real backend HTTP flow end to end. Skipped otherwise.
 */
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';
import { classifyBuildJob, watchBuildJob } from '../src/product/buildJobLifecycle.ts';
import {
  PRODUCT_JOURNEYS, initialJourneySession, journeyById, journeyStepHref,
  nextUnopened, recordJourneyOpen, validBuildId,
} from '../src/product/journeyCatalog.ts';

const src = (rel) => readFileSync(new URL(`../${rel}`, import.meta.url), 'utf8');
const route = (href) => existsSync(new URL(`../app${href}.tsx`, import.meta.url));

// ── F1 Onboarding ────────────────────────────────────────────────────────
test('F1 onboarding: entry routes exist (index, welcome, setup, product shell)', () => {
  for (const href of ['/index', '/_layout', '/welcome', '/setup', '/product', '/hub']) {
    assert.ok(route(href), `missing app${href}.tsx`);
  }
});
test('F1 onboarding: welcome persists a seen-flag and always lands on /product', () => {
  const w = src('app/welcome.tsx');
  assert.match(w, /WELCOME_FLAG_KEY\s*=\s*'@codedock:welcome_seen:v1'/);
  assert.match(w, /safeSetItem\(WELCOME_FLAG_KEY, '1'\)/);
  assert.match(w, /router\.replace\('\/product'\)/);
  // Auto-advance safety net so a frozen splash never strands the player.
  assert.match(w, /setTimeout\(\(\) => \{\s*handleEnter\(\);\s*\}, \d+\)/);
});
test('F1 onboarding: first journey starts at the brief and is resumable', () => {
  const s = initialJourneySession();
  assert.equal(s.selected, 'idea-to-game');
  const j = journeyById(s.selected);
  assert.deepEqual(j.steps.map((x) => x.href), ['/ai-game-generator', '/galaxy', '/studio', '/game-kb', '/my-builds']);
  for (const step of j.steps) assert.ok(route(step.href), `journey step route missing: ${step.href}`);
  assert.equal(nextUnopened(j, [], false).id, 'describe');
});

// ── F2 Sign-in ───────────────────────────────────────────────────────────
test('F2 sign-in: client talks only to the canonical auth contract', () => {
  const a = src('src/auth/gameforgeAuth.ts');
  for (const p of ['/api/auth/login', '/api/auth/register', '/api/auth/me', '/api/auth/session', '/api/auth/logout']) {
    assert.ok(a.includes(`'${p}'`), `auth client must call ${p}`);
  }
  // Tokens never go to unencrypted AsyncStorage.
  assert.equal(/AsyncStorage/.test(a.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, '')), false);
  assert.match(a, /SecureStore\.setItemAsync/);
  // 401 clears the session; unverifiable /me fails closed (observed:false).
  assert.match(a, /r\.status === 401\) \{\s*await persist\(''\)/);
  assert.match(a, /observed: false/);
});
test('F2 sign-in: gate shows unavailable on unverified /me, never silently authed', () => {
  const g = src('src/auth/StudioLoginGate.tsx');
  assert.match(g, /me\.observed === false\) \{[^}]*setStatus\('unavailable'\)/);
  assert.match(g, /me\.authenticated \|\| \(!requireAuthenticated && !me\.enforced\) \? 'authed' : 'unauth'/);
  assert.match(g, /testID="gate-error"/);
});

// ── F3 Create project from brief ─────────────────────────────────────────
test('F3 create: brief screen hands off the generated artifact to game-factory', () => {
  const g = src('app/ai-game-generator.tsx');
  assert.match(g, /queueGameBuilderArtifact\(data, type\)/);
  assert.match(g, /router\.replace\('\/game-factory'\)/);
  assert.ok(route('/game-factory'));
  assert.ok(existsSync(new URL('../features/GameFactory/gameBuilderHandoff.ts', import.meta.url)));
});
test('F3 create: build-accepting steps carry only safe project ids', () => {
  const build = journeyById('idea-to-game').steps.find((s) => s.id === 'build');
  assert.equal(journeyStepHref(build, 'game_123-abc'), '/studio?game=game_123-abc');
  for (const bad of ['../etc', 'a b', '', 'x'.repeat(129), '<script>', null, 42]) {
    assert.equal(validBuildId(bad), '');
    assert.equal(journeyStepHref(build, bad), '/studio');
  }
});

// ── F4 Watch build ───────────────────────────────────────────────────────
// Payloads mirror GET /api/galaxy-studio/status/{build_id}: {build_id,status,bg_status,...}
const status = (s, extra = {}) => ({ data: { build_id: 'b1', status: s, bg_status: 'running', ...extra } });
test('F4 watch: building is pending; completed is success only without error', () => {
  assert.equal(classifyBuildJob(status('building')), 'pending');
  assert.equal(classifyBuildJob(status('completed')), 'completed');
  assert.equal(classifyBuildJob(status('completed', { error: 'boom' })), 'failed');
  assert.equal(classifyBuildJob(status('failed')), 'failed');
});
test('F4 watch: building → completed reports progress then success', async () => {
  const seq = ['building', 'building', 'completed'];
  const pend = [];
  let i = 0;
  const r = await watchBuildJob(async () => status(seq[i++]), {
    intervalMs: 100, maxIntervalMs: 100, maxChecks: 10, onPending: (n) => pend.push(n),
  });
  assert.equal(r.phase, 'completed');
  assert.equal(r.checks, 3);
  assert.deepEqual(pend, [1, 2]);
});
test('F4 watch: repeated status outages surface disconnected, never failed or success', async () => {
  const r = await watchBuildJob(async () => { throw new Error('ECONNREFUSED secret-host'); }, {
    intervalMs: 100, maxIntervalMs: 100, maxChecks: 10, maxConsecutiveErrors: 2,
  });
  assert.equal(r.phase, 'disconnected');
  assert.equal(r.message.includes('secret-host'), false);
  assert.match(r.message, /may still be running/);
});
test('F4 watch: leaving the screen stops polling without cancelling the backend build', async () => {
  const c = new AbortController();
  let calls = 0;
  const p = watchBuildJob(async () => { calls += 1; return status('building'); }, {
    signal: c.signal, intervalMs: 100, maxIntervalMs: 100, maxChecks: 50,
  });
  setTimeout(() => c.abort(), 30);
  const r = await p;
  assert.equal(r.phase, 'aborted');
  assert.match(r.message, /not cancelled/);
  assert.equal(calls, 1);
});

// ── F5 Open result ───────────────────────────────────────────────────────
test('F5 open: library lists real builds and Open resumes that build in Galaxy', () => {
  const m = src('app/my-builds.tsx');
  assert.match(m, /\/api\/galaxy-studio\/my-builds\?limit=100/);
  assert.match(m, /'@galaxy_studio_active_build_v1'/);
  assert.match(m, /build_id: b\.build_id/);
  assert.match(m, /router\.push\('\/galaxy'\)/);
  for (const href of ['/my-builds', '/galaxy', '/playable', '/studio']) assert.ok(route(href), href);
});
test('F5 open: knowledge step is locked until a build exists, then deep-links it', () => {
  const j = journeyById('idea-to-game');
  const kb = j.steps.find((s) => s.id === 'knowledge');
  assert.equal(journeyStepHref(kb, ''), null);
  assert.equal(journeyStepHref(kb, 'b_42'), '/game-kb?game=b_42');
  let s = initialJourneySession();
  for (const id of ['describe', 'design', 'build']) s = recordJourneyOpen(s, j.id, id);
  assert.equal(nextUnopened(j, s.opened[j.id], false).id, 'library');
  assert.equal(nextUnopened(j, s.opened[j.id], true).id, 'knowledge');
});
test('all journeys resolve to shipped routes (no dead links in the core shell)', () => {
  const missing = PRODUCT_JOURNEYS.flatMap((j) => j.steps.filter((s) => !route(s.href)).map((s) => `${j.id}:${s.href}`));
  assert.deepEqual(missing, []);
});

// ── Tier 2: live backend flow (opt-in) ───────────────────────────────────
const BASE = (process.env.SKELETON_E2E_BASE_URL || '').replace(/\/+$/, '');
const live = { skip: BASE ? false : 'set SKELETON_E2E_BASE_URL to run the live flow' };
async function call(method, path, body, token) {
  const r = await fetch(`${BASE}${path}`, {
    method,
    headers: { 'content-type': 'application/json', ...(token ? { authorization: `Bearer ${token}` } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(20_000),
  });
  let data = null;
  try { data = await r.json(); } catch {}
  return { ok: r.ok, status: r.status, data };
}
test('LIVE F1-F5: bootstrap → register/sign-in → create from brief → watch → open', live, async (t) => {
  const boot = await call('GET', '/api/app/bootstrap');
  assert.equal(boot.ok, true, `bootstrap HTTP ${boot.status}`);
  assert.equal(typeof boot.data?.application?.name, 'string');

  const email = `qa-e2e-${Date.now()}@example.test`;
  const password = `Qa-${Math.random().toString(36).slice(2)}-pass`;
  const reg = await call('POST', '/api/auth/register', { email, password });
  assert.equal(reg.ok, true, `register HTTP ${reg.status}`);
  const login = await call('POST', '/api/auth/login', { email, password });
  assert.equal(login.ok, true, `login HTTP ${login.status}`);
  const token = login.data.access_token;
  const me = await call('GET', '/api/auth/me', undefined, token);
  assert.equal(me.data?.authenticated, true);
  const bad = await call('POST', '/api/auth/login', { email, password: 'wrong-password' });
  assert.equal(bad.ok, false, 'wrong password must not sign in');

  const brief = { title: 'QA Foundation Probe', genre: 'Action', description: 'Small arena brawler used by the QA foundation suite.' };
  const created = await call('POST', '/api/galaxy-studio/create', brief, token);
  assert.equal(created.ok, true, `create HTTP ${created.status}`);
  const buildId = validBuildId(created.data?.build_id);
  assert.ok(buildId, 'create must return a safe build_id');

  const started = await call('POST', '/api/galaxy-studio/start-build', { build_id: buildId, build_duration_minutes: 1 }, token);
  assert.equal(started.ok, true, `start-build HTTP ${started.status}`);

  const maxChecks = Number(process.env.SKELETON_E2E_MAX_CHECKS || 120);
  const outcome = await watchBuildJob(async () => {
    const s = await call('GET', `/api/galaxy-studio/status/${buildId}`, undefined, token);
    return s.ok ? { data: s.data } : { ok: false };
  }, { intervalMs: 2_000, maxIntervalMs: 10_000, maxChecks });
  t.diagnostic(`watch outcome: ${outcome.phase} after ${outcome.checks} checks`);
  assert.equal(outcome.phase, 'completed', outcome.message);

  const lib = await call('GET', '/api/galaxy-studio/my-builds?limit=100', undefined, token);
  assert.equal(lib.ok, true, `my-builds HTTP ${lib.status}`);
  assert.ok((lib.data?.builds || []).some((b) => b.build_id === buildId), 'new build must appear in the library');
});
