'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { snapshot, supervise, pinnedExpoInvocation } = require('./guarded-expo-export.cjs');

function root(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'expo-guard-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return dir;
}
function script(mode) {
  const files = 'const fs=require("node:fs");fs.mkdirSync("dist");' +
    'fs.writeFileSync("dist/index.html","<html>home</html>");' +
    (mode === 'missing-setup' ? '' :
      'fs.writeFileSync("dist/setup.html","<html>setup</html>");');
  const marker = mode === 'missing-marker' ? '' : 'console.log("Exported: dist");';
  const end = mode === 'hang' || mode === 'missing-setup' ?
    'setInterval(()=>{},1000);' :
    mode === 'sigterm-143' ?
    'process.on("SIGTERM",()=>process.exit(143));setInterval(()=>{},1000);' :
    mode === 'early-143' ?
    'setTimeout(()=>process.exit(143),100);' :
    mode === 'failure' ? 'process.exit(7);' : '';
  return files + marker + end;
}
function run(dir, mode) {
  return supervise({
    cwd: dir, command: process.execPath, args: ['-e', script(mode)],
    echo: false, maxMs: 6000, graceMs: 350, stableMs: 150,
    pollMs: 20, terminateMs: 1000,
  });
}

test('default production invocation uses the pinned Expo CLI, not a Yarn wrapper', t => {
  const dir = root(t);
  assert.throws(() => pinnedExpoInvocation(dir), /pinned Expo CLI missing/);
  const cli = path.join(dir, 'node_modules', 'expo', 'bin', 'cli');
  fs.mkdirSync(path.dirname(cli), { recursive: true });
  fs.writeFileSync(cli, '#!/usr/bin/env node\n');
  const invocation = pinnedExpoInvocation(dir);
  assert.equal(invocation.command, process.execPath);
  assert.deepEqual(invocation.args, [cli, 'export', '--platform', 'web']);
  assert.equal(invocation.args.includes('export:web'), false);
});

test('a symbolic-link Expo entrypoint is rejected', t => {
  const dir = root(t);
  const bin = path.join(dir, 'node_modules', 'expo', 'bin');
  fs.mkdirSync(bin, { recursive: true });
  fs.writeFileSync(path.join(bin, 'real-cli'), '#!/usr/bin/env node\n');
  fs.symlinkSync('real-cli', path.join(bin, 'cli'));
  assert.throws(() => pinnedExpoInvocation(dir), /unsafe Expo CLI entrypoint/);
});

test('normal 0 exit requires an actual export marker and setup HTML', async t => {
  const r = await run(root(t), 'normal');
  assert.equal(r.mode, 'normal-exit');
  assert.equal(r.files, 2);
  assert.match(r.digest, /^[0-9a-f]{64}$/);
});
test('stalled exporter requires stable output and actual process reaping', async t => {
  const r = await run(root(t), 'hang');
  assert.equal(r.mode, 'supervised-post-export-exit');
});
test('Yarn-style SIGTERM exit 143 is allowed only after verified supervised reaping', async t => {
  const r = await run(root(t), 'sigterm-143');
  assert.equal(r.mode, 'supervised-post-export-exit');
  assert.equal(r.files, 2);
});

test('an unsupervised 143 exit after a marker is not qualifying', async t => {
  await assert.rejects(run(root(t), 'early-143'), /exited unsuccessfully|export failed after completion marker/);
});

test('a nonzero exporter exit cannot be masked by output marker', async t => {
  await assert.rejects(run(root(t), 'failure'), /exited unsuccessfully/);
});
test('no completion marker is an error even after exit 0', async t => {
  await assert.rejects(run(root(t), 'missing-marker'), /completion marker missing/);
});
test('marker without required setup output is never accepted', async t => {
  await assert.rejects(run(root(t), 'missing-setup'), /required setup HTML absent/);
});
test('stale dist is refused', async t => {
  const dir = root(t); fs.mkdirSync(path.join(dir, 'dist'));
  await assert.rejects(run(dir, 'normal'), /stale dist/);
});
test('symlinks and nonregular evidence are rejected', t => {
  const dir = path.join(root(t), 'dist');
  fs.mkdirSync(dir);
  fs.writeFileSync(path.join(dir, 'setup.html'), '<html/>');
  fs.symlinkSync('setup.html', path.join(dir, 'evil.html'));
  assert.throws(() => snapshot(dir), /symlink/);
});
test('changed output cannot pass repeated digest verification', t => {
  const dir = path.join(root(t), 'dist');
  fs.mkdirSync(dir);
  const html = path.join(dir, 'setup.html');
  fs.writeFileSync(html, '<html>a</html>');
  const first = snapshot(dir).digest;
  fs.writeFileSync(html, '<html>changed</html>');
  assert.notEqual(first, snapshot(dir).digest);
});

test('same-size content rewrite with restored timestamp changes evidence digest', t => {
  const dir = path.join(root(t), 'dist');
  fs.mkdirSync(dir);
  const html = path.join(dir, 'setup.html');
  fs.writeFileSync(html, '<html>a</html>');
  const first = snapshot(dir).digest;
  const before = fs.statSync(html);
  fs.writeFileSync(html, '<html>b</html>');
  fs.utimesSync(html, before.atime, before.mtime);
  assert.equal(fs.statSync(html).size, before.size);
  assert.notEqual(snapshot(dir).digest, first);
});

test('hard-linked export members cannot be used as ambiguous evidence', t => {
  const dir = path.join(root(t), 'dist');
  fs.mkdirSync(dir);
  const html = path.join(dir, 'setup.html');
  fs.writeFileSync(html, '<html>setup</html>');
  fs.linkSync(html, path.join(dir, 'alias.html'));
  assert.throws(() => snapshot(dir), /unsafe export member/);
});

test('file contents, not only path metadata, determine export evidence', t => {
  const dir = path.join(root(t), 'dist');
  fs.mkdirSync(dir);
  const html = path.join(dir, 'setup.html');
  fs.writeFileSync(html, 'ABCD');
  const first = snapshot(dir);
  fs.writeFileSync(html, 'WXYZ');
  assert.equal(snapshot(dir).bytes, first.bytes);
  assert.notEqual(snapshot(dir).digest, first.digest);
});
