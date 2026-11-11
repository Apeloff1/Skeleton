'use strict';

// Source-level regression: randomized session IDs cannot silently fall back to
// guessable timestamps, counters, or Math.random on React Native devices.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
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
    assert.doesNotMatch(helper, /Math\.random|Date\.now|Sequence|sequence|cryptoObject|getRandomValues/);
  });
}
