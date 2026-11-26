// Playwright config for the native Local Studio journey (Windows first install).
// Run from tests/e2e against a running `skeleton.cmd start` / `windows_first_install serve`:
//   SKELETON_STUDIO_URL_FILE=%LOCALAPPDATA%\Skeleton\run\studio.url \
//   npx playwright test --config playwright.local-studio.config.mjs
// SKELETON_E2E_CHANNEL=chrome|msedge uses an installed browser instead of the bundled Chromium.
import { defineConfig, devices } from '@playwright/test';

const CI = !!process.env.CI;
const channel = process.env.SKELETON_E2E_CHANNEL || undefined;

export default defineConfig({
  testDir: './local-studio',
  testMatch: /.*\.spec\.mjs$/,
  timeout: 240_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: CI,
  reporter: CI
    ? [['list'], ['html', { open: 'never', outputFolder: 'playwright-report-local-studio' }]]
    : [['list']],
  outputDir: 'test-results-local-studio',
  use: {
    headless: true,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    acceptDownloads: true,
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], channel } },
    { name: 'mobile', use: { ...devices['Pixel 7'], channel }, grep: /@responsive/ },
  ],
});
