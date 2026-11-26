// Loading/error-state journeys over the react-native-web screen harness. Build first:
//   node expo-screens/build-screens.mjs <frontend/node_modules> <outdir> expo-screens/load-states-screens.json
//   SKELETON_SCREENS_DIR=<outdir> npx playwright test -c playwright.expo-load-states.config.mjs
import { defineConfig, devices } from '@playwright/test';

const dir = process.env.SKELETON_SCREENS_DIR;
const channel = process.env.SKELETON_E2E_CHANNEL || undefined; // e.g. 'chrome' to use the system browser
const port = Number(process.env.SKELETON_SCREENS_PORT ?? 8724);
export default defineConfig({
  testDir: './expo-screens',
  testMatch: /load-states\.spec\.mjs$/,
  timeout: 120_000,
  workers: 1,
  reporter: [['list'], ['json', { outputFile: 'test-results/expo-load-states.json' }]],
  use: { baseURL: `http://127.0.0.1:${port}`, trace: 'retain-on-failure' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], channel } },
    { name: 'mobile', use: { ...devices['Pixel 7'], channel } },
  ],
  webServer: dir
    ? { command: `python3 -m http.server ${port} --bind 127.0.0.1 --directory ${JSON.stringify(dir)}`, url: `http://127.0.0.1:${port}/index.html`, reuseExistingServer: false, stdout: 'ignore', stderr: 'ignore' }
    : undefined,
});
