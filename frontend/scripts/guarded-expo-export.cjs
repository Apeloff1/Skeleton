#!/usr/bin/env node
'use strict';
// Detect Expo's post-export process hang without treating a log marker as success.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawn } = require('node:child_process');
const { setTimeout: sleep } = require('node:timers/promises');

function snapshot(dir) {
  // This is build-output evidence, not a filesystem sandbox. Never trust a
  // filename/mtime/size tuple as proof that its bytes remained unchanged.
  const root = path.resolve(dir);
  const rootBefore = fs.lstatSync(root, { bigint: true });
  if (!rootBefore.isDirectory() || rootBefore.isSymbolicLink()) {
    throw Error('non-directory export output');
  }
  if (typeof fs.constants.O_NOFOLLOW !== 'number') {
    throw Error('no-follow export inspection unavailable');
  }
  const sameFile = (a, b) =>
    a.dev === b.dev && a.ino === b.ino && a.mode === b.mode &&
    a.nlink === b.nlink && a.size === b.size &&
    a.mtimeNs === b.mtimeNs && a.ctimeNs === b.ctimeNs;
  let count = 0, bytes = 0, html = 0, setup = false;
  const entries = [], stack = [{ dir: root, prefix: '', depth: 0 }];
  const buffer = Buffer.allocUnsafe(64 * 1024);
  while (stack.length) {
    const { dir: parent, prefix, depth } = stack.pop();
    if (depth >= 32) throw Error('export depth limit exceeded');
    for (const name of fs.readdirSync(parent)) {
      const rel = prefix ? prefix + '/' + name : name;
      const abs = path.join(parent, name);
      const st = fs.lstatSync(abs, { bigint: true });
      if (st.isSymbolicLink()) throw Error('symlink in export');
      if (st.isDirectory()) {
        stack.push({ dir: abs, prefix: rel, depth: depth + 1 });
        continue;
      }
      if (!st.isFile() || st.nlink !== 1n ||
          st.size > 512n * 1024n * 1024n) {
        throw Error('unsafe export member');
      }
      if (++count > 250000 || (bytes += Number(st.size)) > 6 * 1024 ** 3) {
        throw Error('export bound exceeded');
      }
      const fd = fs.openSync(abs, fs.constants.O_RDONLY |
        fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK);
      let digest;
      try {
        const opened = fs.fstatSync(fd, { bigint: true });
        if (!sameFile(st, opened) || !opened.isFile()) {
          throw Error('export member replaced before inspection');
        }
        const hasher = crypto.createHash('sha256');
        let readBytes = 0;
        while (true) {
          const length = fs.readSync(fd, buffer, 0, buffer.length, null);
          if (length === 0) break;
          readBytes += length;
          if (readBytes > 512 * 1024 * 1024) {
            throw Error('export member exceeded byte cap');
          }
          hasher.update(buffer.subarray(0, length));
        }
        if (readBytes !== Number(opened.size) ||
            !sameFile(opened, fs.fstatSync(fd, { bigint: true })) ||
            !sameFile(opened, fs.lstatSync(abs, { bigint: true }))) {
          throw Error('export member changed during inspection');
        }
        digest = hasher.digest('hex');
      } finally {
        fs.closeSync(fd);
      }
      if (rel.endsWith('.html')) {
        if (!st.size) throw Error('empty export HTML');
        html++;
      }
      if (rel === 'setup.html' || rel === 'setup/index.html') setup = true;
      entries.push(JSON.stringify([rel, Number(st.size), digest]));
    }
  }
  const rootAfter = fs.lstatSync(root, { bigint: true });
  if (!rootAfter.isDirectory() || rootAfter.isSymbolicLink() ||
      rootBefore.dev !== rootAfter.dev || rootBefore.ino !== rootAfter.ino) {
    throw Error('export output root replaced during inspection');
  }
  if (!setup || !html || !count) throw Error('required setup HTML absent');
  return { files: count, bytes, digest: crypto.createHash('sha256')
    .update(entries.sort().join('\n')).digest('hex') };
}

function pinnedExpoInvocation(cwd) {
  // Launch the installed, lockfile-resolved CLI directly. Yarn wraps Expo in
  // another process, and its signal handling can misreport an expected,
  // supervisor-issued shutdown as a failed export.
  const cli = path.join(cwd, 'node_modules', 'expo', 'bin', 'cli');
  let stat;
  try { stat = fs.lstatSync(cli); } catch {
    throw Error('pinned Expo CLI missing');
  }
  if (!stat.isFile() || stat.isSymbolicLink()) throw Error('unsafe Expo CLI entrypoint');
  return { command: process.execPath, args: [cli, 'export', '--platform', 'web'] };
}

async function supervise(opts = {}) {
  const cwd = path.resolve(opts.cwd || path.join(__dirname, '..'));
  const out = path.join(cwd, 'dist');
  if (fs.existsSync(out)) throw Error('stale dist is not qualifying evidence');
  const invocation = opts.command
    ? { command: opts.command, args: opts.args || [] }
    : pinnedExpoInvocation(cwd);
  const child = spawn(invocation.command, invocation.args, {
    cwd, stdio: ['ignore', 'pipe', 'pipe'],
    detached: process.platform !== 'win32',
    env: { ...process.env, CI: '1', EXPO_NO_TELEMETRY: '1' },
  });
  let exited = false, code = null, signal = null, spawnError = false;
  let markerTime = null;
  // A completion marker is evidence from one complete exporter log line,
  // never a synthetic concatenation of stdout/stderr or an unfinished line.
  const pendingOutput = { stdout: '', stderr: '' };
  const done = new Promise(resolve => child.on('close', (c, s) => {
    exited = true; code = c; signal = s; resolve();
  }));
  child.on('error', () => { spawnError = true; });
  function read(chunk, target, channel) {
    if (opts.echo !== false) target.write(chunk);
    const lines = (pendingOutput[channel] + chunk.toString('utf8'))
      .split(/\r\n|\r|\n/);
    pendingOutput[channel] = lines.pop().slice(-8192);
    if (markerTime === null && lines.some(line =>
      line.replace(/\x1b\[[0-9;]*m/g, '').trim() === 'Exported: dist')) {
      markerTime = Date.now();
    }
  }
  child.stdout.on('data', c => read(c, process.stdout, 'stdout'));
  child.stderr.on('data', c => read(c, process.stderr, 'stderr'));
  function kill(sig) {
    if (child.pid && process.platform !== 'win32') {
      try { process.kill(-child.pid, sig); return true; } catch {}
    }
    try { return child.kill(sig); } catch { return false; }
  }
  async function reap() {
    await Promise.race([done, sleep(opts.terminateMs ?? 5000)]);
    if (!exited) {
      kill('SIGKILL');
      await Promise.race([done, sleep(opts.terminateMs ?? 5000)]);
    }
    if (!exited) throw Error('unreaped export process');
  }
  const start = Date.now();
  try {
    while (Date.now() - start < (opts.maxMs ?? 15 * 60 * 1000)) {
      if (spawnError) throw Error('export failed to start');
      if (exited) {
        if (code !== 0 || signal) throw Error('export exited unsuccessfully');
        if (markerTime === null) throw Error('completion marker missing');
        return { ...snapshot(out), mode: 'normal-exit' };
      }
      if (markerTime !== null && Date.now() - markerTime >= (opts.graceMs ?? 15000)) {
        const first = snapshot(out);
        await sleep(opts.stableMs ?? 4000);
        if (exited && code !== 0) throw Error('export failed after completion marker');
        const second = snapshot(out);
        if (first.digest !== second.digest) throw Error('export output is not stable');
        // Reject any spontaneous nonzero exit before taking ownership of
        // process shutdown. A Yarn shell converts SIGTERM into exit code 143;
        // this is qualifying ONLY after we sent SIGTERM to a live process.
        if (exited) {
          if (code !== 0 || signal) throw Error('export failed after completion marker');
          return { ...second, mode: 'normal-exit' };
        }
        if (!kill('SIGTERM')) throw Error('export termination was not delivered');
        await reap();
        const third = snapshot(out);
        if (second.digest !== third.digest) throw Error('export changed during cleanup');
        const supervisedExit = (code === 0 && signal === null)
          || (code === null && signal === 'SIGTERM')
          || (code === 143 && signal === null);
        if (!supervisedExit) throw Error('unexpected exporter exit code=' + String(code) + ' signal=' + String(signal));
        return { ...third, mode: 'supervised-post-export-exit' };
      }
      await sleep(opts.pollMs ?? 100);
    }
    throw Error('export hard deadline exceeded');
  } finally {
    if (!exited) { kill('SIGTERM'); await reap(); }
  }
}

module.exports = { snapshot, supervise, pinnedExpoInvocation };

if (require.main === module) {
  supervise().then(r => {
    process.stdout.write('[guarded-export] verified files=' + r.files +
      ' bytes=' + r.bytes + ' digest=' + r.digest + ' mode=' + r.mode + '\n');
    if (r.mode !== 'normal-exit') process.stdout.write(
      '[guarded-export] WARNING: exporter required supervision; browser/device/release checks remain mandatory\n'
    );
  }).catch(e => {
    process.stderr.write('[guarded-export] FAILED: ' + String(e.message).slice(0,200) + '\n');
    process.exitCode = 1;
  });
}
