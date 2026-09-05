// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ['dist/*', 'node_modules/*', '.expo/*'],
  },
  {
    files: ['**/*.ts', '**/*.tsx'],
    languageOptions: {
      parserOptions: {
        ecmaVersion: 'latest',
        sourceType: 'module',
        ecmaFeatures: {
          jsx: true,
        },
      },
    },
    rules: {
      // Disable rules that conflict with TypeScript
      'no-unused-vars': 'off',
      'no-undef': 'off',
      // Allow any types during development
      '@typescript-eslint/no-explicit-any': 'off',
      // Unused-vars kept as a signal; ignore JSX-runtime React import and _-prefixed.
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^(_|React$)' },
      ],
      // expo flat + eslint-config-expo currently flags hundreds of pre-existing
      // patterns across the app; keep #5 scoped (Expo URL wire + lockfile).
      // Re-enable via a dedicated lint-debt PR, not this one.
      'react-hooks/static-components': 'off',
      'react-hooks/refs': 'off',
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/use-memo': 'off',
    },
  },
]);
