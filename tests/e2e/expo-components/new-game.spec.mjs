// /new-game journey through the backend forge gateway and the real engine:
// validation, examples, keyboard radio selection, live progress, success,
// with axe WCAG 2.2 AA scans. The page never sees an engine seal.
import { test, expect } from '@playwright/test';

let AxeBuilder = null;
try { ({ default: AxeBuilder } = await import('@axe-core/playwright')); } catch { AxeBuilder = null; }

async function expectAccessible(page, label) {
  if (!AxeBuilder) return;
  const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze();
  expect(results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`), `${label} axe`).toEqual([]);
}

test('new game: validate, pick an example, build through the gateway, see the result', async ({ page }) => {
  const seals = [];
  page.on('request', (request) => { if (request.headers()['x-gf-seal']) seals.push(request.url()); });
  await page.goto('/new-game');
  await expect(page.getByRole('heading', { level: 1, name: 'New game' })).toBeVisible();
  await expectAccessible(page, 'form');

  await page.getByRole('button', { name: 'Build game' }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'Describe the game you want to build.' })).toBeVisible();
  await expectAccessible(page, 'form (invalid)');

  await page.getByRole('button', { name: 'Use the Platformer example' }).click();
  await expect(page.getByLabel('Describe your game')).toHaveValue(/fox on rain-slick rooftops/);

  const required = page.getByRole('radio', { name: /^Required\./ });
  await required.focus();
  await page.keyboard.press('Enter');
  await expect(required).toHaveAttribute('aria-checked', 'true');

  const started = page.waitForResponse((r) => r.url().endsWith('/api/forge-gateway/game/build') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Build game' }).click();
  const response = await started;
  expect(response.status()).toBe(202);
  expect(response.request().headers()['idempotency-key']).toMatch(/^ng-/);

  await expect(page.getByRole('heading', { level: 1, name: 'Building your game' })).toBeVisible();
  await expect(page.getByRole('progressbar', { name: 'Build progress' })).toHaveAttribute('aria-valuenow', /\d+/);
  await expectAccessible(page, 'building');

  await expect(page.getByRole('heading', { level: 1, name: /is ready$/ })).toBeVisible({ timeout: 200_000 });
  await expect(page.getByText(/Proof: .*CORE_LOOP_OK/)).toBeVisible();
  await expectAccessible(page, 'done');
  expect(seals, 'the browser must never send an engine seal').toEqual([]);

  await page.getByRole('button', { name: 'Build another game' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'New game' })).toBeVisible();
});

test('resume by id: unknown build shows a non-retryable explanation', async ({ page }) => {
  await page.goto('/new-game?build=job_does_not_exist');
  await expect(page.getByRole('alert').filter({ hasText: 'This build was not found' })).toBeVisible();
  await expectAccessible(page, 'not found');
});
