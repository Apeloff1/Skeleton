// Renders every reviewed Expo route in the react-native-web screen harness and
// runs axe. Blocking: the name/role rules this pass is responsible for.
// Everything else axe reports is written to each test's axe-summary.json as
// the backlog for follow-up passes (contrast, landmarks, headings).
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const { files } = JSON.parse(fs.readFileSync(path.join(here, '../../../frontend/scripts/a11y/reviewed-screens.json'), 'utf8'));
const SCREENS = files.filter((f) => f.startsWith('app/')).map((f) => f.slice(4, -4));

export const BLOCKING_RULES = [
  'button-name', 'link-name', 'label', 'input-button-name', 'nested-interactive',
  'aria-command-name', 'aria-input-field-name', 'aria-toggle-field-name',
  'aria-allowed-attr', 'aria-required-attr', 'aria-valid-attr', 'aria-valid-attr-value',
  'aria-roles', 'aria-prohibited-attr', 'duplicate-id-aria',
];

for (const screen of SCREENS) {
  test(`${screen}: accessible names and roles`, async ({ page }, info) => {
    const pageErrors = [];
    page.on('pageerror', (e) => pageErrors.push(String(e.message)));
    // Backend is offline on purpose: screens must still render a usable UI.
    await page.route('**/api/**', (route) => route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"offline (harness)"}' }));
    await page.goto(`/?screen=${encodeURIComponent(screen)}`);
    await expect(page.getByTestId('harness-loading')).toHaveCount(0, { timeout: 15_000 });
    await expect(page.getByTestId('harness-error')).toHaveCount(0);
    await page.waitForTimeout(600);
    const crashText = (await page.getByTestId('harness-crash').count()) ? await page.getByTestId('harness-crash').innerText() : null;
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze();
    const blocking = results.violations.filter((v) => BLOCKING_RULES.includes(v.id));
    const entry = {
      screen,
      project: info.project.name,
      crashed: crashText,
      pageErrors: pageErrors.slice(0, 3),
      blocking: blocking.map((v) => ({ id: v.id, nodes: v.nodes.slice(0, 5).map((n) => n.html.slice(0, 200)) })),
      other: Object.fromEntries(results.violations.filter((v) => !BLOCKING_RULES.includes(v.id)).map((v) => [v.id, v.nodes.length])),
    };
    fs.writeFileSync(info.outputPath('axe-summary.json'), JSON.stringify(entry, null, 2));
    await info.attach('axe-summary', { body: JSON.stringify(entry, null, 2), contentType: 'application/json' });
    expect(crashText, `screen threw while rendering: ${pageErrors[0] ?? crashText}`).toBeNull();
    expect(blocking, JSON.stringify(entry.blocking, null, 2)).toEqual([]);
  });
}
