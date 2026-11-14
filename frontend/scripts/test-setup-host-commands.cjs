'use strict';
/** First-install copy: canonical POSIX commands unchanged, explicit Windows
 * equivalents, and honest "use WSL 2" where native Windows is unsupported. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const { compileFunction } = require('node:vm');
const ts = require('typescript');

function loadCommands() {
  const source = fs.readFileSync(path.join(__dirname, '../src/features/Setup/setupCommands.ts'), 'utf8');
  const compiled = ts.transpileModule(source, { reportDiagnostics: true, compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } });
  assert.equal(compiled.diagnostics.length, 0);
  const mod = { exports: {} };
  compileFunction(compiled.outputText, ['require', 'module', 'exports'])((name) => { throw new Error('unexpected dependency ' + name); }, mod, mod.exports);
  return mod.exports;
}

const C = loadCommands();

// Canonical production-assembly commands as shipped before this change.
const CANONICAL_POSIX = [
  'python scripts/launch_jeeves_desktop.py',
  'python scripts/build_jeeves_local_manifest.py --model /ABSOLUTE/OWNED_MODEL.gguf --executable /ABSOLUTE/llama-cli --output /ABSOLUTE/jeeves.json --profile qwen3-completion-chat',
  'python scripts/install_ai_chat.py --deployment /ABSOLUTE/jeeves.json --live-local',
  'python scripts/install_ai_chat.py --deployment /ABSOLUTE/jeeves.json --apply',
  'python scripts/install_ai_chat.py --deployment /ABSOLUTE/jeeves.json --apply --force --start',
  'python scripts/ai_chat_installed_smoke.py --base-url https://YOUR_BACKEND_HOST --login-email owner@example.com --exercise',
  'python scripts/ai_chat_installed_smoke.py --base-url https://YOUR_BACKEND_HOST --login-email owner@example.com --recover-thread THREAD_ID --recover-request REQUEST_ID',
  'cd frontend && EXPO_PUBLIC_BACKEND_URL=https://YOUR_BACKEND_HOST npx eas build --profile apk --platform android',
  'python -m skeleton app doctor --live --studio --json',
  'python scripts/provision_local_ai.py --help',
];

test('macOS / Linux and WSL 2 show the canonical commands byte-for-byte', () => {
  assert.deepEqual(C.commandsFor('posix').map((c) => c.command), CANONICAL_POSIX);
  assert.deepEqual(C.commandsFor('wsl').map((c) => c.command), CANONICAL_POSIX);
  assert.ok(C.commandsFor('posix').every((c) => c.note === null));
});

test('the setup screen no longer embeds its own command list', () => {
  const screen = fs.readFileSync(path.join(__dirname, '../src/features/Setup/AppSetupWorkspace.tsx'), 'utf8');
  assert.doesNotMatch(screen, /const COMMANDS = \[/);
  assert.match(screen, /commandsFor\(shell\)/);
  assert.match(screen, /accessibilityRole="radiogroup"/);
  assert.match(screen, /accessibilityRole="radio"/);
});

test('Windows commands are PowerShell-native: py launcher, Windows paths, $env: assignment', () => {
  const win = C.commandsFor('powershell');
  assert.equal(win.length, CANONICAL_POSIX.length);
  for (const item of win) {
    if (item.command === null) continue;
    assert.doesNotMatch(item.command, /^python\b/, item.title);
    assert.doesNotMatch(item.command, /\/ABSOLUTE\//, item.title);
    assert.doesNotMatch(item.command, /&&/, 'Windows PowerShell 5.1 has no && operator: ' + item.title);
    assert.doesNotMatch(item.command, /(^|\s)[A-Z_]+=\S+\s/, 'no POSIX inline env assignment: ' + item.title);
  }
  const android = win.find((c) => /Android/.test(c.title));
  assert.match(android.command, /\$env:EXPO_PUBLIC_BACKEND_URL = "https:\/\/YOUR_BACKEND_HOST"; npx eas build/);
  const manifest = win.find((c) => /manifest/.test(c.title));
  assert.match(manifest.command, /C:\\ABSOLUTE\\llama-cli\.exe/);
  // Flags and placeholders are carried over exactly.
  win.forEach((item, index) => {
    if (!item.command) return;
    const flags = (s) => (s.match(/--[a-z-]+/g) || []);
    assert.deepEqual(flags(item.command), flags(CANONICAL_POSIX[index]), item.title);
  });
});

test('unsupported native Windows steps say so and point to WSL 2 instead of a failing command', () => {
  const win = C.commandsFor('powershell');
  const provision = win.find((c) => /model acquisition/.test(c.title));
  assert.equal(provision.command, null);
  assert.match(provision.note, /WSL 2/);
  const start = win.find((c) => /^Start Jeeves/.test(c.title));
  assert.match(start.note, /Docker Desktop/);
  assert.match(start.note, /not yet covered by installer qualification/);
  assert.match(C.HOST_SHELL_COPY.powershell, /not fully qualified/);
});

test('host shell detection only trusts the browser, never guesses for a phone', () => {
  assert.equal(C.detectHostShell('web', { platform: 'Win32' }), 'powershell');
  assert.equal(C.detectHostShell('web', { userAgentData: { platform: 'Windows' } }), 'powershell');
  assert.equal(C.detectHostShell('web', { platform: 'MacIntel' }), 'posix');
  assert.equal(C.detectHostShell('web', { userAgent: 'Mozilla/5.0 (X11; Linux x86_64)' }), 'posix');
  assert.equal(C.detectHostShell('android', { platform: 'Win32' }), 'posix');
  assert.equal(C.detectHostShell('web', null), 'posix');
  assert.deepEqual(C.HOST_SHELLS.map((s) => s.id), ['posix', 'powershell', 'wsl']);
});
