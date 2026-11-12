/**
 * Real Chromium first-user acceptance for Dragon's authenticated research pilot.
 *
 * This intentionally NEVER starts physical crawling or publishes a source.
 * It exercises the exported Expo route, sign-in, conservative defaults,
 * untrusted URL preflight, six-stage navigation and honest release holds.
 * It is picked up by the existing App Foundation E2E browser config after
 * the production stack is actually built, on a non-draft / dispatch run.
 */
import { test, expect } from '@playwright/test';

const API = (process.env.SKELETON_E2E_BASE_URL || 'http://localhost:8001').replace(/\/$/, '');

function trackCrashes(page) {
  const failures = [];
  page.on('pageerror', error => failures.push(String(error?.message || error)));
  return failures;
}

async function freshAccount(request) {
  const nonce = Math.random().toString(36).slice(2, 11);
  const email = `dragon-pilot-e2e-${Date.now()}-${nonce}@example.com`;
  const password = `SourceOnly-Pw-${nonce}-2026`;
  const response = await request.post(`${API}/api/auth/register`, {
    data: { email, password },
  });
  expect(response.ok(), `isolated registration HTTP ${response.status()}`).toBeTruthy();
  return { email, password };
}

test('Dragon pilot: anonymous users are gated, signed-in users see safe six-stage first run', async ({ page, request }) => {
  const crashes = trackCrashes(page);
  const crawlerWrites = [];
  page.on('request', req => {
    // All capture mutations must remain absent; this browser test only
    // previews syntax, never exercises a public/private web source.
    if (req.method() !== 'GET' && /\/api\/dragon-academy\/crawler\/sessions(?:\/|$)/.test(req.url())) {
      crawlerWrites.push({ method: req.method(), url: req.url().replace(/\?.*$/, '') });
    }
  });

  const navigation = await page.goto('/dragon-crawler-pilot');
  expect(navigation && navigation.ok(), 'exported pilot route is reachable').toBeTruthy();
  await expect(page.getByTestId('gate-email')).toBeVisible();
  await expect(page.getByTestId('dragon-crawler-pilot')).toHaveCount(0);
  await expect(page.getByText('Sign in to Dragon research pilot')).toBeVisible();

  const account = await freshAccount(request);
  await page.getByTestId('gate-email').fill(account.email);
  await page.getByTestId('gate-pass').fill(account.password);
  await page.getByTestId('gate-submit').click();
  await expect(page.getByTestId('gate-submit')).toBeHidden({ timeout: 30_000 });
  await expect(page.getByTestId('dragon-crawler-pilot')).toBeVisible();
  await expect(page.getByText('Your research mission', { exact: true })).toBeVisible();

  // The browser must not pre-grant capture merely because a viewer signs in.
  const create = page.getByTestId('pilot-create');
  await expect(create).toBeVisible();
  await expect(create).toBeDisabled();
  for (const stage of ['scope', 'capture', 'sources', 'research', 'review', 'receipt']) {
    await expect(page.getByTestId('pilot-stage-' + stage)).toBeVisible();
  }

  // Only local syntax preview happens; no fetch or backend crawl mutation.
  await page.getByTestId('pilot-seeds').fill('http://127.0.0.1/private');
  await page.getByRole('button', { name: 'Preview host scope' }).click();
  await expect(page.getByText(
    'Use credential-free HTTPS public DNS hostnames without custom ports or fragments.',
  )).toBeVisible();
  await expect(create).toBeDisabled();

  await page.getByTestId('pilot-stage-receipt').click();
  await expect(page.getByText('6. Pilot evidence and release gates', { exact: true })).toBeVisible();
  await expect(page.getByText(/Release authorized: NO/)).toBeVisible();
  await expect(page.getByText(/Publishing and model-training permission: NO/)).toBeVisible();

  // Small-phone geometry must keep stage navigation discoverable rather than
  // overflowing into an unclickable or blank document.
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByTestId('pilot-stage-scope')).toBeVisible();
  await expect(page.getByTestId('pilot-stage-receipt')).toBeVisible();

  expect(crawlerWrites, 'Preview and login must never mutate crawler sessions').toEqual([]);
  expect(crashes, 'Real browser route emitted an uncaught exception').toEqual([]);
});
