/**
 * .eslintrc.cjs — TS-aware ESLint config for the Expo frontend.
 *
 * Why a hand-rolled config (no eslint-config-expo)?
 * --------------------------------------------------
 * `eslint-config-expo` runs `expo install --check` during the EAS CI build
 * pipeline, which broke the Android cloud builds in Feb 2026 because it
 * does not respect pinned package versions. This config gives us
 * type-aware lint coverage on the local dev box and in CI without
 * dragging that hook into the EAS build path.
 *
 * Usage
 * -----
 *   npx eslint . --ext .ts,.tsx       # lint everything
 *   npx eslint app/hub.tsx --fix      # lint a single file with autofixes
 *
 * The required peer packages (`eslint`, `@typescript-eslint/parser`,
 * `@typescript-eslint/eslint-plugin`, `eslint-plugin-react-hooks`) are
 * intentionally NOT added to package.json devDependencies — `npx` will
 * fetch them on demand, so EAS Android builds stay isolated from the
 * lint toolchain.
 */
/* eslint-env node */

module.exports = {
  root: true,
  parser: '@typescript-eslint/parser',
  parserOptions: {
    ecmaVersion: 2022,
    sourceType: 'module',
    ecmaFeatures: { jsx: true },
    // NOTE: project-aware lint is OPT-IN via `--parser-options project=...`
    // because turning it on globally makes lint 10-30× slower.
  },
  plugins: ['@typescript-eslint', 'react-hooks'],
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  ignorePatterns: [
    'node_modules/',
    '.expo/',
    'dist/',
    'web-build/',
    'android/',
    'ios/',
    '*.config.js',
    'scripts/',
    'metro.config.js',
    'babel.config.js',
  ],
  rules: {
    // Surface bugs, not style.
    '@typescript-eslint/no-unused-vars': [
      'warn',
      { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
    ],
    '@typescript-eslint/no-explicit-any': 'off',  // pragmatic — too many in this codebase
    '@typescript-eslint/ban-ts-comment': 'off',
    'react-hooks/rules-of-hooks': 'error',
    'react-hooks/exhaustive-deps': 'warn',
    'no-empty': ['warn', { allowEmptyCatch: true }],
    'no-undef': 'off',  // TS already handles this; ESLint trips on RN globals
    'no-console': 'off',
    'no-prototype-builtins': 'off',
  },
  overrides: [
    {
      // JS files (config files, scripts) — relax TS-only rules.
      files: ['*.js', '*.cjs', '*.mjs'],
      rules: {
        '@typescript-eslint/no-var-requires': 'off',
        '@typescript-eslint/no-require-imports': 'off',
      },
    },
  ],
};
