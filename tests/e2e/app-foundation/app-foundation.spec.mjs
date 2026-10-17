// App foundation browser cases (plan: docs/qa/APP_FOUNDATION_E2E_TEST_PLAN.md,
// flows F1–F5 from #4098). Drives the production web export served by the
// frontend container; the backend is reached directly for test-account setup.
import { expect, test } from '@playwright/test';

const API = (process.env.SKELETON_E2E_BASE_URL || 'http://localhost:8001').replace(/\/$/, '');

/** Fail a test on any uncaught page exception (crash = broken flow). */
function trackPageErrors(page) {
  const errors = [];
  page.on('pageerror', (err) => errors.push(String(err && err.message ? err.message : err)));
  return errors;
}

async function expectRendered(page) {
  // Expo web mounts into #root; a blank root means the bundle failed to boot.
  await expect(page.locator('#root')).not.toBeEmpty();
  await expect.poll(async () => (await page.locator('#root').innerText()).trim().length).toBeGreaterThan(0);
}

async function registerAccount(request) {
  const email = `pw-e2e-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
  const password = `Pw-${Math.random().toString(36).slice(2)}-pass`;
  const res = await request.post(`${API}/api/auth/register`, { data: { email, password } });
  expect(res.ok(), `register HTTP ${res.status()}: ${(await res.text()).slice(0, 600)}`).toBeTruthy();
  return { email, password };
}

test.describe.configure({ mode: 'serial' });

test('stack: frontend /healthz and backend /api/health are up', async ({ request }) => {
  expect((await request.get('/healthz')).ok()).toBeTruthy();
  expect((await request.get(`${API}/api/health`)).ok()).toBeTruthy();
});

test('F1 onboarding: entry route boots the app shell without crashing', async ({ page }) => {
  const errors = trackPageErrors(page);
  await page.goto('/');
  await expectRendered(page);
  expect(errors, errors.join('\n')).toEqual([]);
});

test('F1 onboarding: welcome lands on the /product shell', async ({ page }) => {
  const errors = trackPageErrors(page);
  await page.goto('/welcome');
  await expectRendered(page);
  // welcome auto-advances (safety net) and always router.replace('/product').
  await page.waitForURL(/\/product(\?|$)/, { timeout: 45_000 });
  await expect(page.getByTestId('product-guided-journeys')).toBeVisible();
  expect(errors, errors.join('\n')).toEqual([]);
});

test('F1 onboarding: product shell exposes guided journeys entry', async ({ page }) => {
  const errors = trackPageErrors(page);
  await page.goto('/product');
  await expect(page.getByTestId('product-guided-journeys')).toBeVisible();
  expect(errors, errors.join('\n')).toEqual([]);
});

test('F2 sign-in: gated screen rejects a wrong password and accepts the right one', async ({ page, request }) => {
  const errors = trackPageErrors(page);
  const { email, password } = await registerAccount(request);
  await page.goto('/ai-chat');
  const emailBox = page.getByTestId('gate-email');
  await expect(emailBox, 'anonymous user must see the sign-in gate').toBeVisible();

  await emailBox.fill(email);
  await page.getByTestId('gate-pass').fill('definitely-wrong-password');
  await page.getByTestId('gate-submit').click();
  await expect(page.getByTestId('gate-error')).toBeVisible();
  await expect(emailBox, 'wrong password must not pass the gate').toBeVisible();

  await page.getByTestId('gate-pass').fill(password);
  await page.getByTestId('gate-submit').click();
  await expect(page.getByTestId('gate-submit'), 'valid credentials must pass the gate').toBeHidden({ timeout: 30_000 });
  expect(errors, errors.join('\n')).toEqual([]);
});

for (const [flow, href] of [
  ['F3 create: brief screen', '/ai-game-generator'],
  ['F3 create: game factory handoff', '/game-factory'],
  ['F4 watch: studio build screen', '/studio'],
  ['F5 open: build library', '/my-builds'],
  ['F5 open: galaxy result view', '/galaxy'],
]) {
  test(`${flow} (${href}) renders without crashing`, async ({ page }) => {
    const errors = trackPageErrors(page);
    const res = await page.goto(href);
    expect(res && res.ok(), `${href} HTTP ${res && res.status()}`).toBeTruthy();
    await expectRendered(page);
    expect(errors, errors.join('\n')).toEqual([]);
  });
}
