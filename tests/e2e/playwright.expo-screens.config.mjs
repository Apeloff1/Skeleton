// Screen-harness a11y journeys. Build first:
//   node expo-screens/build-screens.mjs <frontend/node_modules> <outdir>
//   SKELETON_SCREENS_DIR=<outdir> npx playwright test -c playwright.expo-screens.config.mjs
import { defineConfig, devices } from '@playwright/test';

const dir = process.env.SKELETON_SCREENS_DIR;
const channel = process.env.SKELETON_E2E_CHANNEL || undefined; // e.g. 'chrome' to use the system browser
const port = Number(process.env.SKELETON_SCREENS_PORT ?? 8723);
export default defineConfig({
  testDir: './expo-screens',
  testMatch: /.*\.spec\.mjs$/,
  timeout: 60_000,
  workers: 2,
  reporter: [['list'], ['json', { outputFile: 'test-results/expo-screens.json' }]],
  use: { baseURL: `http://127.0.0.1:${port}`, trace: 'retain-on-failure' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], channel } },
    { name: 'mobile', use: { ...devices['Pixel 7'], channel } },
  ],
  webServer: dir
    ? { command: `python3 -m http.server ${port} --bind 127.0.0.1 --directory ${JSON.stringify(dir)}`, url: `http://127.0.0.1:${port}/index.html`, reuseExistingServer: false, stdout: 'ignore', stderr: 'ignore' }
    : undefined,
});
