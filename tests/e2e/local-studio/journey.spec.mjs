// Main Local Studio journey: onboarding -> prompt -> live build -> project ->
// edit/save -> headless playtest -> export, plus locked/validation/404 states
// and WCAG 2.2 AA checks (axe, when @axe-core/playwright is installed).
import { readFileSync } from 'node:fs';
import { test, expect } from '@playwright/test';

const urlFile = process.env.SKELETON_STUDIO_URL_FILE;
if (!urlFile) throw new Error('SKELETON_STUDIO_URL_FILE must point at run/studio.url');
const studioUrl = readFileSync(urlFile, 'utf8').trim();
if (!/^http:\/\/127\.0\.0\.1:\d+\/studio\/#token=[A-Za-z0-9_-]+$/.test(studioUrl)) throw new Error('malformed studio.url');
const origin = new URL(studioUrl).origin;
const requirePlaytest = process.env.SKELETON_E2E_REQUIRE_PLAYTEST !== '0';

let AxeBuilder = null;
try { ({ default: AxeBuilder } = await import('@axe-core/playwright')); } catch { AxeBuilder = null; }

async function expectAccessible(page, label) {
  if (!AxeBuilder) return;
  const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze();
  const summary = results.violations.map(v => `${v.id}: ${v.nodes.map(n => n.target.join(' ')).join(', ')}`);
  expect(summary, `${label} axe violations`).toEqual([]);
}

async function unlock(page) {
  await page.goto(studioUrl);
  await expect(page).toHaveURL(/#\/$/);
  await expect(page.locator('#conn')).toHaveText(/Connected/);
}

test('locked without the launch token, and token never stays in the URL', async ({ page }) => {
  await page.goto(`${origin}/studio/`);
  await expect(page.getByRole('heading', { level: 1, name: 'Open Studio from Skeleton' })).toBeVisible();
  await expectAccessible(page, 'locked');
  await unlock(page);
  expect(page.url()).not.toContain('token=');
});

test('validation, keyboard skip link and not-found states', async ({ page }) => {
  await unlock(page);
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to main content' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('#main')).toBeFocused();

  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'New game' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'New game' })).toBeFocused();
  await expect(page.getByRole('link', { name: 'New game' })).toHaveAttribute('aria-current', 'page');
  await page.getByLabel('Describe your game').fill('');
  await page.getByRole('button', { name: 'Build game' }).click();
  await expect(page.getByText('Describe the game you want to build.')).toBeVisible();
  await expect(page.getByLabel('Describe your game')).toHaveAttribute('aria-invalid', 'true');
  await expect(page.getByLabel('Describe your game')).toBeFocused();
  await expectAccessible(page, 'new game (invalid)');

  await page.goto(`${origin}/studio/#/nowhere`);
  await expect(page.getByRole('heading', { level: 1, name: 'Page not found' })).toBeVisible();
  await page.goto(`${origin}/studio/#/game/does-not-exist`);
  await expect(page.getByRole('heading', { level: 1, name: 'Not found' })).toBeVisible();
});

test('settings shows health without leaking secrets', async ({ page }) => {
  await unlock(page);
  await page.getByRole('link', { name: 'Settings' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Settings' })).toBeVisible();
  await expect(page.getByText(/ready|needs attention/).first()).toBeVisible();
  const text = await page.locator('main').innerText();
  expect(text).not.toMatch(/sk-[A-Za-z0-9]{10,}/);
  await expectAccessible(page, 'settings');
});

test('prompt -> live build -> edit -> playtest -> export @responsive', async ({ page }, testInfo) => {
  await unlock(page);
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'New game' }).click();
  await page.getByRole('button', { name: 'Platformer' }).click();
  await expect(page.getByLabel('Describe your game')).not.toHaveValue('');
  await page.getByRole('radio', { name: requirePlaytest ? /Required/ : /If Godot is available/ }).check();
  await page.getByRole('button', { name: 'Build game' }).click();

  await expect(page.getByRole('heading', { level: 1, name: 'Building your game' })).toBeVisible();
  await expect(page.getByRole('progressbar', { name: 'Build progress' })).toBeVisible();
  const open = page.getByRole('link', { name: /^Open / });
  await expect(open).toBeVisible({ timeout: 200_000 });
  await expect(open).toBeFocused();
  if (requirePlaytest) await expect(page.locator('dl.kv')).toContainText(/CORE_LOOP_OK/);
  await expectAccessible(page, 'build done');
  await open.click();

  await expect(page.getByRole('heading', { level: 2, name: 'Project files' })).toBeVisible();
  const script = page.getByRole('navigation', { name: 'Project files' }).getByRole('button', { name: /\.gd$/ }).first();
  const scriptPath = await script.innerText();
  await script.click();
  const editor = page.locator('#editor');
  await expect(editor).toBeEditable();
  await editor.press('End');
  await editor.press('Control+End');
  await editor.type(`\n# e2e ${testInfo.project.name}\n`);
  await editor.press('Control+s');
  await expect(page.getByText(`Saved ${scriptPath}.`)).toBeVisible();
  await expectAccessible(page, 'project view');

  if (requirePlaytest) {
    await page.getByRole('button', { name: 'Run playtest' }).click();
    await expect(page.getByRole('heading', { name: /Playtest (passed|failed)/ })).toBeVisible({ timeout: 120_000 });
    await expect(page.getByRole('heading', { name: 'Playtest passed' })).toBeVisible();
  }

  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download project (.zip)' }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/\.zip$/);

  await page.getByRole('link', { name: '← My games' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'My games' })).toBeVisible();
  await expect(page.getByRole('list', { name: 'Games' }).getByRole('listitem').first()).toBeVisible();
  await expectAccessible(page, 'my games');
});
