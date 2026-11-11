'use strict';

// Source-level regression: randomized session IDs cannot silently fall back to
// guessable timestamps, counters, or Math.random on React Native devices.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
// Security checks operate on executable lines, not explanatory comments.
// Keep the negative check fail-closed for all non-comment source lines.
function executableHelperLines(helper) {
  return helper.split('\n').filter((line) => !/^\s*\/\//.test(line)).join('\n');
}

test('secure identity scan ignores full-line comments without ignoring executable fallbacks', () => {
  const commentary = '  // Do not use Math.random(), Date.now(), or getRandomValues()';
  assert.doesNotMatch(executableHelperLines(commentary), /Math\.random|Date\.now|getRandomValues/);
  const executable = '  return Math.random();';
  assert.match(executableHelperLines(executable), /Math\.random/);
  const mixed = '// harmless mention of sequence\n  return Date.now();';
  assert.match(executableHelperLines(mixed), /Date\.now/);
});

const fixtures = [
  ['app/tools-arena.tsx', 'createArenaSessionId'],
  ['src/utils/modalLogger.ts', 'createSessionId'],
  ['src/features/Collaboration/CollaborationManager.ts', 'createCollaborationId'],
];

for (const [relative, functionName] of fixtures) {
  test(`${relative}: identity uses only the secure Expo generator`, () => {
    const source = fs.readFileSync(path.join(root, relative), 'utf8');
    assert.match(source, /import \* as Crypto from ['"]expo-crypto['"]/);
    const begin = source.indexOf(`function ${functionName}(`);
    assert.ok(begin >= 0, 'security-critical helper must exist');
    const end = source.indexOf('\n}', begin);
    assert.ok(end > begin, 'expected complete helper block');
    const helper = source.slice(begin, end);
    assert.match(helper, /Crypto\.randomUUID\(\)/);
    assert.doesNotMatch(executableHelperLines(helper), /Math\.random|Date\.now|Sequence|sequence|cryptoObject|getRandomValues/);
  });
}
