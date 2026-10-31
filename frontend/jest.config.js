/**
 * Jest config for the frontend unit suites under __tests__/.
 * Uses jest-expo so the repo's babel.config.js (babel-preset-expo) transforms TS/TSX.
 * node:test-style suites (run via `node --test` scripts) are excluded here.
 */
module.exports = {
  preset: 'jest-expo',
  roots: ['<rootDir>/__tests__'],
  testMatch: ['**/*.test.ts', '**/*.test.tsx'],
  testPathIgnorePatterns: ['/node_modules/', 'dragonWatchTimeline\\.test\\.ts$'],
};
