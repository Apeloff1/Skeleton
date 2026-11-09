import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const patcher = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'patch-node-modules.js'), 'utf8');
function fixture({ version = '54.0.27', source } = {}) {
  const root = mkdtempSync(join(tmpdir(), 'expo-static-path-'));
  const script = join(root, 'scripts/patch-node-modules.js');
  const pkg = join(root, 'node_modules/@expo/cli');
  const target = join(pkg, 'build/src/export/exportStaticAsync.js');
  mkdirSync(dirname(script), { recursive: true });
  mkdirSync(dirname(target), { recursive: true });
  writeFileSync(script, patcher);
  writeFileSync(join(pkg, 'package.json'), JSON.stringify({ version }));
  writeFileSync(target, source ?? "module.exports = filePathLocation => ({ pathname: filePathLocation.replace(/(\\/?index)?$/, '') });\n");
  return { root, target, run: () => execFileSync(process.execPath, [script], { stdio: 'pipe' }) };
}

test('Expo static paths preserve names ending in index and trim directory index segments', () => {
  const f = fixture();
  try {
    f.run();
    const normalize = createRequire(import.meta.url)(f.target);
    for (const [path, expected] of [['index', ''], ['settings/index', 'settings'],
      ['story-index', 'story-index'], ['sub/story-index', 'sub/story-index'], ['indexer', 'indexer'], ['', '']]) {
      assert.equal(normalize(path).pathname, expected);
    }
  } finally { rmSync(f.root, { recursive: true, force: true }); }
});

test('Expo static export patch is idempotent after reinstall hooks repeat', () => {
  const f = fixture();
  try {
    f.run();
    const once = readFileSync(f.target, 'utf8');
    f.run();
    assert.equal(readFileSync(f.target, 'utf8'), once);
  } finally { rmSync(f.root, { recursive: true, force: true }); }
});

test('Expo package or source drift fails before rewriting the target', () => {
  for (const options of [{ version: '54.0.28' }, { source: 'module.exports = 1;' }]) {
    const f = fixture(options);
    try {
      const before = readFileSync(f.target, 'utf8');
      assert.throws(f.run);
      assert.equal(readFileSync(f.target, 'utf8'), before);
    } finally { rmSync(f.root, { recursive: true, force: true }); }
  }
});
