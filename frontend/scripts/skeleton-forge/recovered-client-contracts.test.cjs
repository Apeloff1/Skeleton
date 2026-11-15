'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const read = p => fs.readFileSync(path.join(root, p), 'utf8');

test('recovered frontend clients keep their explicit source-bound contracts', () => {
  const types = read('src/skeletonForge/types.ts');
  const client = read('src/skeletonForge/client.ts');
  const chat = read('src/product/chatSessionClient.ts');
  const view = read('src/skeletonForge/components/ForgeCockpitView.tsx');
  assert.match(types, /export interface GenreControlProfile/);
  assert.match(client, /export function fetchJeevesGameQualityCatalog/);
  assert.match(client, /\/jeeves\/game-quality/);
  assert.equal((chat.match(/import \{[^\n]*nativeBackendConfigurationIssue[^\n]*\} from/g) || []).length, 1);
  assert.equal((view.match(/onReturnToStudio\?: \(\) => void;/g) || []).length, 1);
});
