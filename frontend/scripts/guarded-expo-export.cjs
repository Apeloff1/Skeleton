#!/usr/bin/env node
'use strict';
// Detect Expo's post-export process hang without treating a log marker as success.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawn } = require('node:child_process');
const { setTimeout: sleep } = require('node:timers/promises');

function snapshot(dir) {
  const root = path.resolve(dir);
  if (!fs.lstatSync(root).isDirectory() || fs.lstatSync(root).isSymbolicLink()) {
    throw Error('non-directory export output');
  }
  let count = 0, bytes = 0, html = 0, setup = false;
  const entries = [], stack = [{ dir: root, prefix: '', depth: 0 }];
  while (stack.length) {
    const { dir: parent, prefix, depth } = stack.pop();
    if (depth >= 32) throw Error('export depth limit exceeded');
    for (const name of fs.readdirSync(parent)) {
      const rel = prefix ? prefix + '/' + name : name;
      const abs = path.join(parent, name);
      const st = fs.lstatSync(abs);
      if (st.isSymbolicLink()) throw Error('symlink in export');
      if (st.isDirectory()) {
        stack.push({ dir: abs, prefix: rel, depth: depth + 1 });
        continue;
      }
      if (!st.isFile() || st.size > 512 * 1024 * 1024) throw Error('unsafe export member');
      if (++count > 250000 || (bytes += st.size) > 6 * 1024 ** 3) {
        throw Error('export bound exceeded');
      }
      if (rel.endsWith('.html')) {
        if (!st.size) throw Error('empty export HTML');
        html++;
      }
      if (rel === 'setup.html' || rel === 'setup/index.html') setup = true;
      entries.push(rel + ':' + st.size + ':' + st.mtimeMs);
    }
  }
  if (!setup || !html || !count) throw Error('required setup HTML absent');
  return { files: count, bytes, digest: crypto.createHash('sha256')
    .update(entries.sort().join('\n')).digest('hex') };
}

async function supervise(opts = {}) {
  const cwd = path.resolve(opts.cwd || path.join(__dirname, '..'));
  const out = path.join(cwd, 'dist');
  if (fs.existsSync(out)) throw Error('stale dist is not qualifying evidence');
  const child = spawn(opts.command || 'yarn', opts.args || ['export:web'], {
    cwd, stdio: ['ignore', 'pipe', 'pipe'],
    detached: process.platform !== 'win32',
    env: { ...process.env, CI: '1', EXPO_NO_TELEMETRY: '1' },
  });
  let exited = false, code = null, signal = null, spawnError = false;
  let markerTime = null, tail = '';
  const done = new Promise(resolve => child.on('close', (c, s) => {
    exited = true; code = c; signal = s; resolve();
  }));
  child.on('error', () => { spawnError = true; });
  function read(chunk, target) {
    if (opts.echo !== false) target.write(chunk);
    tail = (tail + chunk.toString('utf8')).slice(-8192);
    if (tail.replace(/\x1b\[[0-9;]*m/g, '').split(/\r?\n/)
      .some(line => line.trim() === 'Exported: dist') && markerTime === null) {
      markerTime = Date.now();
    }
  }
  child.stdout.on('data', c => read(c, process.stdout));
  child.stderr.on('data', c => read(c, process.stderr));
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
        if (!supervisedExit) throw Error('unexpected exporter exit');
        return { ...third, mode: 'supervised-post-export-exit' };
      }
      await sleep(opts.pollMs ?? 100);
    }
    throw Error('export hard deadline exceeded');
  } finally {
    if (!exited) { kill('SIGTERM'); await reap(); }
  }
}

module.exports = { snapshot, supervise };

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
