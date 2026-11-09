#!/usr/bin/env node
// Execute the complete bounded frontend contract inventory without a shell.
import { readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const root = dirname(fileURLToPath(import.meta.url));
function discover(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? discover(path)
      : /^(?:test-.*\.(?:mjs|cjs)|.*\.test\.(?:mjs|cjs))$/.test(entry.name) ? [path] : [];
  });
}
const files = discover(root).sort();
if (!files.length) throw new Error('No frontend contract tests were discovered');
console.log(`Frontend contract inventory: ${files.length} files`);
const result = spawnSync(process.execPath, ['--test', ...files], { stdio: 'inherit' });
if (result.error) throw result.error;
process.exitCode = result.status ?? 1;
