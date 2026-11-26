// Playwright config for Expo screen journeys rendered through the
// react-native-web harnesses in ./expo-components against a live backend
// gateway + engine. See expo-components/README.md for the stack.
import { defineConfig, devices } from '@playwright/test';

const CI = !!process.env.CI;
const channel = process.env.SKELETON_E2E_CHANNEL || undefined;

export default defineConfig({
  testDir: './expo-components',
  testMatch: /.*\.spec\.mjs$/,
  timeout: 240_000,
  expect: { timeout: 20_000 },
  workers: 1,
  forbidOnly: CI,
  reporter: CI ? [['list'], ['html', { open: 'never', outputFolder: 'playwright-report-expo-components' }]] : [['list']],
  outputDir: 'test-results-expo-components',
  use: {
    baseURL: process.env.SKELETON_GATEWAY_E2E_URL || 'http://127.0.0.1:8722',
    headless: true,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], channel } },
    { name: 'mobile', use: { ...devices['Pixel 7'], channel } },
  ],
});
