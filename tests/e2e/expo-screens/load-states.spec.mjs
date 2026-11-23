// With the backend failing, each screen must say so (role=alert, honest copy,
// a named retry when retrying can help) instead of an empty/zero state, and
// must recover when the backend comes back. axe blocks on name/role rules.
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const BLOCKING = new Set([
  'button-name', 'link-name', 'label', 'nested-interactive', 'aria-allowed-attr', 'aria-required-attr',
  'aria-valid-attr', 'aria-valid-attr-value', 'aria-roles', 'aria-prohibited-attr', 'aria-progressbar-name',
]);

// screen, query, what the alert names, optional action that triggers the load,
// the empty-state copy that must NOT appear on failure.
const CASES = [
  { screen: 'worlds-gallery', what: 'worlds', falseEmpty: /No saved worlds yet/ },
  { screen: 'ops', what: 'the ops overview' },
  { screen: 'trophy-case', what: 'the trophy case', falseEmpty: /No champions crowned yet/ },
  { screen: 'gallery', what: 'your builds', falseEmpty: /No builds yet/ },
  { screen: 'storage', what: 'storage stats' },
  { screen: 'forge-hub', what: 'the forge catalog' },
  { screen: 'flashcards', what: 'classes' },
  { screen: 'apk-build', query: '&build=b-123', what: 'APK artifacts' },
  { screen: 'edit-gamefiles', query: '&build=b-123', what: 'gamefiles', falseEmpty: /No gamefiles yet/ },
  { screen: 'search', what: 'search results', act: async (page) => page.getByRole('textbox').first().fill('dragon'), falseEmpty: /No results for/ },
  { screen: 'groupchat', query: '&game=g-1', what: 'the stage run', act: async (page) => page.getByText('▶ Build missing stages').click() },
];

async function failApi(page, status = 503) {
  await page.unroute('**/api/**').catch(() => {});
  await page.route('**/api/**', (route) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify({ detail: 'maintenance window' }) }));
}

for (const c of CASES) {
  test(`${c.screen}: a failed load is reported, not shown as empty`, async ({ page }) => {
    await failApi(page);
    await page.goto(`/?screen=${c.screen}${c.query ?? ''}`);
    await expect(page.getByTestId('harness-loading')).toHaveCount(0, { timeout: 15_000 });
    if (c.act) await c.act(page);
    const alert = page.getByRole('alert').filter({ hasText: `Could not load ${c.what}` });
    await expect(alert).toBeVisible({ timeout: 45_000 });
    await expect(alert).toContainText('unavailable right now');
    await expect(alert).toContainText('maintenance window');
    await expect(alert.getByRole('button', { name: `Try again: ${c.what}` })).toBeVisible();
    if (c.falseEmpty) await expect(page.getByText(c.falseEmpty)).toHaveCount(0);
    await expect(page.getByTestId('harness-crash')).toHaveCount(0);
    const axe = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
    const blocking = axe.violations.filter((v) => BLOCKING.has(v.id));
    expect(blocking.map((v) => ({ id: v.id, html: v.nodes[0]?.html })), 'axe name/role violations').toEqual([]);
  });
}

test('auth failures do not offer a pointless retry', async ({ page }) => {
  await failApi(page, 403);
  await page.goto('/?screen=worlds-gallery');
  const alert = page.getByRole('alert').filter({ hasText: 'Could not load worlds' });
  await expect(alert).toBeVisible({ timeout: 45_000 });
  await expect(alert).toContainText('does not have access');
  await expect(alert.getByRole('button')).toHaveCount(0);
});

test('worlds-gallery recovers on retry once the backend answers', async ({ page }) => {
  await failApi(page);
  await page.goto('/?screen=worlds-gallery');
  const retry = page.getByRole('button', { name: 'Try again: worlds' });
  await expect(retry).toBeVisible({ timeout: 45_000 });
  await page.unroute('**/api/**');
  await page.route('**/api/**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ worlds: [] }) }));
  await retry.click();
  await expect(page.getByText(/No saved worlds yet/)).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('zaibatsu reports offline instead of "connecting…" forever', async ({ page }) => {
  await failApi(page);
  await page.goto('/?screen=zaibatsu');
  await expect(page.getByText(/offline/)).toBeVisible({ timeout: 45_000 });
  await expect(page.getByLabel('Offline')).toBeVisible();
});
