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
test('F1-01 onboarding: entry routes exist (index, welcome, setup, product shell)', () => {
  for (const href of ['/index', '/_layout', '/welcome', '/setup', '/product', '/hub']) {
    assert.ok(route(href), `missing app${href}.tsx`);
  }
});
test('F1-02 onboarding: welcome persists a seen-flag and always lands on /product', () => {
  const w = src('app/welcome.tsx');
  assert.match(w, /WELCOME_FLAG_KEY\s*=\s*'@codedock:welcome_seen:v1'/);
  assert.match(w, /safeSetItem\(WELCOME_FLAG_KEY, '1'\)/);
  assert.match(w, /router\.replace\('\/product'\)/);
  // Auto-advance safety net so a frozen splash never strands the player.
  assert.match(w, /setTimeout\(\(\) => \{\s*handleEnter\(\);\s*\}, \d+\)/);
});
test('F1-03 onboarding: first journey starts at the brief and is resumable', () => {
  const s = initialJourneySession();
  assert.equal(s.selected, 'idea-to-game');
  const j = journeyById(s.selected);
  assert.deepEqual(j.steps.map((x) => x.href), ['/ai-game-generator', '/galaxy', '/studio', '/game-kb', '/my-builds']);
  for (const step of j.steps) assert.ok(route(step.href), `journey step route missing: ${step.href}`);
  assert.equal(nextUnopened(j, [], false).id, 'describe');
});

// ── F2 Sign-in ───────────────────────────────────────────────────────────
const AUTH_PATHS = ['/api/auth/login', '/api/auth/register', '/api/auth/me', '/api/auth/session', '/api/auth/logout'];
const code = (text) => text.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, '');
test('F2-01 sign-in: client talks only to the canonical auth contract', () => {
  const a = src('src/auth/gameforgeAuth.ts');
  for (const p of AUTH_PATHS) assert.ok(a.includes(`'${p}'`), `auth client must call ${p}`);
  const used = [...new Set(code(a).match(/['"`]\/api\/[^'"`?]+/g).map((x) => x.slice(1)))];
  assert.deepEqual(used.filter((x) => !AUTH_PATHS.includes(x)), [], 'auth client calls a non-canonical endpoint');
});
test('F2-02 sign-in: web uses localStorage, native uses SecureStore, nobody uses AsyncStorage', () => {
  for (const f of ['src/auth/gameforgeAuth.ts', 'src/auth/StudioLoginGate.tsx']) {
    assert.equal(/AsyncStorage/.test(code(src(f))), false, `${f} must not touch AsyncStorage`);
  }
  const a = code(src('src/auth/gameforgeAuth.ts'));
  const persist = a.slice(a.indexOf('async function persist'), a.indexOf('async function loadStored'));
  assert.match(persist, /if \(Platform\.OS === 'web'\) \{[^}]*localStorage\.setItem\(KEY, token\)[\s\S]*\} else if \(token\) \{\s*await SecureStore\.setItemAsync\(KEY, token\)/);
  const load = a.slice(a.indexOf('async function loadStored'), a.indexOf('async function initializeStoredToken'));
  assert.match(load, /Platform\.OS === 'web'\) return localStorage\.getItem\(KEY\)[\s\S]*SecureStore\.getItemAsync\(KEY\)/);
});
test('F2-03 sign-in: 401 clears the session; unverifiable /me fails closed', () => {
  const a = code(src('src/auth/gameforgeAuth.ts'));
  const me = a.slice(a.indexOf('export async function checkMe'), a.indexOf('export async function loginEmail'));
  assert.match(me, /const unknown = \(error: string\): MeResult => \(\{ authenticated: false, enforced: true, role: 'anonymous', user: null, observed: false, error \}\)/);
  assert.match(me, /if \(r\.status === 401\) \{\s*await persist\(''\);\s*return \{ authenticated: false/);
  assert.match(me, /if \(!r\.ok \|\| !r\.data \|\| typeof r\.data\.authenticated !== 'boolean'[^\n]*\{\s*return unknown\(/);
});
test('F2-04 sign-in: gate shows unavailable on unverified /me, renders children only when authed', () => {
  const g = src('src/auth/StudioLoginGate.tsx');
  // Gated content is reachable only through the final return, after every non-authed status has returned.
  assert.equal((g.match(/\{children\}/g) || []).length, 1);
  assert.match(g, /return <AuthCtx\.Provider value=\{authValue\}>\{children\}<\/AuthCtx\.Provider>;\s*\}/);
  const body = g.slice(g.indexOf('export default function StudioLoginGate'));
  const finalReturn = body.indexOf('{children}</AuthCtx.Provider>');
  for (const st of ['loading', 'unavailable', 'unauth']) {
    const at = body.indexOf(`if (status === '${st}') {`);
    assert.ok(at > 0 && at < finalReturn, `status '${st}' must return before gated content`);
  }
  assert.match(g, /me\.observed === false\) \{[^}]*setStatus\('unavailable'\)/);
  assert.match(g, /me\.authenticated \|\| \(!requireAuthenticated && !me\.enforced\) \? 'authed' : 'unauth'/);
  assert.match(g, /testID="gate-error"/);
});

// ── F3 Create project from brief ─────────────────────────────────────────
test('F3-01 create: brief screen hands off the generated artifact to game-factory', () => {
  const g = src('app/ai-game-generator.tsx');
  assert.match(g, /queueGameBuilderArtifact\(data, type\)/);
  assert.match(g, /router\.replace\('\/game-factory'\)/);
  assert.ok(route('/game-factory'));
  assert.ok(existsSync(new URL('../src/features/GameFactory/gameBuilderHandoff.ts', import.meta.url)));
});
test('F3-02 create: build-scoped steps carry only safe project ids (128 ok, 129 rejected)', () => {
  const steps = journeyById('idea-to-game').steps;
  const build = steps.find((s) => s.id === 'build');
  const kb = steps.find((s) => s.id === 'knowledge');
  assert.equal(journeyStepHref(build, 'game_123-abc'), '/studio?game=game_123-abc');
  assert.equal(validBuildId('x'.repeat(128)), 'x'.repeat(128));
  for (const bad of ['../etc', 'a b', '', 'x'.repeat(129), '<script>', 'a%2F..', 'a/b', null, 42]) {
    assert.equal(validBuildId(bad), '', `accepted ${String(bad).slice(0, 20)}`);
    assert.equal(journeyStepHref(build, bad), '/studio');
    assert.equal(journeyStepHref(kb, bad), null);
  }
});

// ── F4 Watch build ───────────────────────────────────────────────────────
// Payloads mirror GET /api/galaxy-studio/status/{build_id}: {build_id,status,bg_status,...}
const status = (s, extra = {}) => ({ data: { build_id: 'b1', status: s, bg_status: 'running', ...extra } });
test('F4-01 watch: building is pending; completed is success only without error', () => {
  assert.equal(classifyBuildJob(status('building')), 'pending');
  assert.equal(classifyBuildJob(status('completed')), 'completed');
  assert.equal(classifyBuildJob(status('completed', { error: 'boom' })), 'failed');
  assert.equal(classifyBuildJob(status('failed')), 'failed');
});
test('F4-02 watch: building → completed reports progress then success', async () => {
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
test('F4-03 watch: repeated status outages surface disconnected, never failed or success', async () => {
  const r = await watchBuildJob(async () => { throw new Error('ECONNREFUSED secret-host'); }, {
    intervalMs: 100, maxIntervalMs: 100, maxChecks: 10, maxConsecutiveErrors: 2,
  });
  assert.equal(r.phase, 'disconnected');
  assert.equal(r.message.includes('secret-host'), false);
  assert.match(r.message, /may still be running/);
});
test('F4-04 watch: leaving the screen stops polling without cancelling the backend build', async () => {
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

test('F4-02b watch: an endless build exhausts the budget as timeout, never success or failure', async () => {
  const r = await watchBuildJob(async () => status('building'), { intervalMs: 100, maxIntervalMs: 100, maxChecks: 3 });
  assert.equal(r.phase, 'timeout');
  assert.equal(r.checks, 3);
  assert.match(r.message, /may still be running/);
});

// ── F5 Open result ───────────────────────────────────────────────────────
test('F5-01 open: library lists real builds and Open resumes that build in Galaxy', () => {
  const m = src('app/my-builds.tsx');
  assert.match(m, /\/api\/galaxy-studio\/my-builds\?limit=100/);
  assert.match(m, /'@galaxy_studio_active_build_v1'/);
  assert.match(m, /build_id: b\.build_id/);
  assert.match(m, /router\.push\('\/galaxy'\)/);
  for (const href of ['/my-builds', '/galaxy', '/playable', '/studio']) assert.ok(route(href), href);
});
test('F5-02 open: knowledge step is locked until a build exists, then deep-links it', () => {
  const j = journeyById('idea-to-game');
  const kb = j.steps.find((s) => s.id === 'knowledge');
  assert.equal(journeyStepHref(kb, ''), null);
  assert.equal(journeyStepHref(kb, 'b_42'), '/game-kb?game=b_42');
  let s = initialJourneySession();
  for (const id of ['describe', 'design', 'build']) s = recordJourneyOpen(s, j.id, id);
  assert.equal(nextUnopened(j, s.opened[j.id], false).id, 'library');
  assert.equal(nextUnopened(j, s.opened[j.id], true).id, 'knowledge');
});
test('F5-03 all journeys resolve to shipped routes (no dead links in the core shell)', () => {
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
  // Keep diagnostic output bounded and independent of response bodies or tokens.
  // The header is set only by the backend load-shedding boundary.
  const rejectionSource = r.headers.get('x-skeleton-rejection-source') === 'load-shedding'
    ? 'load-shedding' : 'unclassified';
  return { ok: r.ok, status: r.status, data, rejectionSource };
}
test('LIVE F1-F5: bootstrap → register/sign-in → create from brief → watch → open', live, async (t) => {
  const ctx = {};
  const need = (k) => assert.ok(ctx[k], `precondition missing: ${k} (an earlier live case failed)`);
  await t.test('F1-04 bootstrap names the application', async () => {
    const boot = await call('GET', '/api/app/bootstrap');
    assert.equal(boot.ok, true, `bootstrap HTTP ${boot.status}`);
    assert.ok(String(boot.data?.application?.name || '').trim(), 'application name must be non-empty');
  });
  await t.test('F2-05 register, sign in, /me, reject bad and missing credentials', async () => {
    // Reserved TLDs (.test, .invalid, .localhost) fail backend EmailStr validation (#4113).
    const email = `qa-e2e-${Date.now()}@${process.env.SKELETON_E2E_EMAIL_DOMAIN || 'example.com'}`;
    const password = `Qa-${Math.random().toString(36).slice(2)}-pass`;
    const reg = await call('POST', '/api/auth/register', { email, password });
    assert.equal(reg.ok, true, `register HTTP ${reg.status}`);
    const login = await call('POST', '/api/auth/login', { email, password });
    assert.equal(login.ok, true, `login HTTP ${login.status}`);
    assert.ok(login.data?.access_token, 'login must return a token');
    const me = await call('GET', '/api/auth/me', undefined, login.data.access_token);
    assert.equal(me.data?.authenticated, true);
    const bad = await call('POST', '/api/auth/login', { email, password: 'wrong-password' });
    assert.equal(bad.status, 401, `wrong password must be 401, got ${bad.status}`);
    const anon = await call('GET', '/api/auth/me');
    const failureReason = anon.data?.reason === 'load_shedding'
      ? 'load_shedding' : 'unclassified';
    assert.equal(anon.ok, true,
      `/me without token HTTP ${anon.status} source=${anon.rejectionSource} reason=${failureReason}`);
    assert.equal(anon.data?.authenticated, false, 'no token must not be authenticated');
    assert.equal(me.data?.user?.role, 'viewer', 'registration must not grant write privileges');
    ctx.viewerToken = login.data.access_token;
    // Authorized build creation requires a separately provisioned editor/admin.
    // CI supplies an ephemeral admin via the backend's canonical seed contract.
    const adminEmail = process.env.SKELETON_E2E_ADMIN_EMAIL;
    const adminPassword = process.env.SKELETON_E2E_ADMIN_PASSWORD;
    assert.ok(adminEmail && adminPassword, 'live write flow needs ephemeral admin credentials');
    const admin = await call('POST', '/api/auth/login', { email: adminEmail, password: adminPassword });
    assert.equal(admin.ok, true, `ephemeral admin login HTTP ${admin.status}`);
    assert.equal(admin.data?.role, 'admin', 'seeded account must be an admin');
    const adminMe = await call('GET', '/api/auth/me', undefined, admin.data.access_token);
    assert.equal(adminMe.data?.user?.role, 'admin', 'admin session must revalidate');
    ctx.token = admin.data.access_token;
  });
  await t.test('F3-03 create from brief and start the build', async () => {
    need('token');
    const brief = { title: 'QA Foundation Probe', genre: 'Action', description: 'Small arena brawler used by the QA foundation suite.' };
    // Viewer denial is part of the live security contract, not a test failure.
    const denied = await call('POST', '/api/galaxy-studio/create', brief, ctx.viewerToken);
    assert.equal(denied.status, 403, 'new viewer must not create a build');
    const created = await call('POST', '/api/galaxy-studio/create', brief, ctx.token);
    assert.equal(created.ok, true, `create HTTP ${created.status}`);
    const buildId = validBuildId(created.data?.build_id);
    assert.ok(buildId, 'create must return a safe build_id');
    // The full ten-batch live generator exceeded 60 seconds while generating real assets.
    // Preserve the complete source-producing flow. CI observed all ten batches finishing
    // before a three-minute deadline stopped real delivery-floor generation; use a
    // bounded ten-minute budget for the full workload rather than forging completion.
    const started = await call('POST', '/api/galaxy-studio/start-build', { build_id: buildId, build_duration_minutes: 10 }, ctx.token);
    assert.equal(started.ok, true, `start-build HTTP ${started.status}: ${String(started.data?.detail?.code || started.data?.detail || "unavailable").slice(0, 240)}`);
    ctx.buildId = buildId;
  });
  await t.test('F4-05 watch the live build to completed', async () => {
    need('buildId');
    const maxChecks = Number(process.env.SKELETON_E2E_MAX_CHECKS || 120);
    let lastStatus = null;
    const outcome = await watchBuildJob(async () => {
      const response = await call('GET', `/api/galaxy-studio/status/${ctx.buildId}`, undefined, ctx.token);
      if (response.ok) lastStatus = response.data;
      return response.ok ? { data: response.data } : { ok: false };
    }, { intervalMs: 2_000, maxIntervalMs: 10_000, maxChecks });
    const reason = String(lastStatus?.execution?.stop_reason || lastStatus?.redundancy?.error_details?.at(-1)?.code || lastStatus?.error || 'none').slice(0, 160);
    t.diagnostic(`watch outcome: ${outcome.phase}; checks=${outcome.checks}; stop_reason=${reason}`);
    assert.equal(outcome.phase, 'completed', `${outcome.message}; stop_reason=${reason}`);
    ctx.completed = true;
  });
  await t.test('F5-04 new build appears in the library', async () => {
    need('buildId');
    const lib = await call('GET', '/api/galaxy-studio/my-builds?limit=100', undefined, ctx.token);
    assert.equal(lib.ok, true, `my-builds HTTP ${lib.status}`);
    assert.ok((lib.data?.builds || []).some((b) => b.build_id === ctx.buildId), 'new build must appear in the library');
  });
});
