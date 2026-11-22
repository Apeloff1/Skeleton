'use strict';
/* global __dirname */
// Contract for the pressable/input accessibility pass. Run: yarn test:a11y-pressables
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { analyse, apply } = require('./pressable-a11y.cjs');

const ROOT = path.resolve(__dirname, '..', '..');
const fix = (src) => apply(src, analyse('/x.tsx', src).edits);

test('adds a button role and keeps text-named pressables untouched otherwise', () => {
  const out = fix('const A = () => <TouchableOpacity onPress={go} style={s.b}><Text>Save</Text></TouchableOpacity>;');
  assert.equal(out, 'const A = () => <TouchableOpacity accessibilityRole="button" onPress={go} style={s.b}><Text>Save</Text></TouchableOpacity>;');
  assert.deepEqual(analyse('/x.tsx', out), { edits: [], findings: [] });
});

test('infers labels for icon-only controls and reports unknown icons', () => {
  const out = fix('<Pressable onPress={x}><Ionicons name="close" size={20} /></Pressable>');
  assert.match(out, /accessibilityRole="button" accessibilityLabel="Close"/);
  const unknown = analyse('/x.tsx', '<Pressable onPress={x}><Ionicons name={dyn} /></Pressable>');
  assert.equal(unknown.findings[0].kind, 'unnamed-pressable');
});

test('respects existing roles, labels, spreads and non-interactive wrappers', () => {
  for (const src of [
    '<Pressable accessibilityRole="link" onPress={x}><Text>Docs</Text></Pressable>',
    '<Pressable role="tab" aria-label="One" onPress={x} />',
    '<Pressable {...props} onPress={x} />',
    '<Pressable style={s}><Text>static</Text></Pressable>',
  ]) assert.deepEqual(analyse('/x.tsx', src), { edits: [], findings: [] }, src);
});

test('nested pressables are reported, and a11y-exempt records a reviewed exception', () => {
  const nested = '<Pressable onPress={a}>\n<TouchableOpacity accessibilityRole="button" onPress={b}><Text>In</Text></TouchableOpacity>\n</Pressable>';
  assert.equal(analyse('/x.tsx', nested).findings[0].kind, 'nested-pressable');
  const exempt = '// a11y-exempt: tap-anywhere backdrop\n' + nested;
  assert.deepEqual(analyse('/x.tsx', exempt).findings, []);
});

test('inputs take the visible label first, then the placeholder', () => {
  const out = fix('<View><Text>Display name</Text><TextInput value={v} placeholder="Ada" /></View>');
  assert.match(out, /<TextInput accessibilityLabel="Display name"/);
  const ph = fix('<View><TextInput value={v} placeholder="Search docs…" /></View>');
  assert.match(ph, /<TextInput accessibilityLabel="Search docs"/);
  assert.equal(analyse('/x.tsx', '<TextInput value={v} />').findings[0].kind, 'unlabelled-input');
});

test('switches take the row label, a parent label prop, or are reported', () => {
  assert.match(fix('<View><Text>✦ Dark mode</Text><Switch value={v} /></View>'), /<Switch accessibilityLabel="Dark mode"/);
  assert.match(fix('<Row><View><Text>Sync</Text><Text>{hint}</Text></View><Switch value={v} /></Row>'), /<Switch accessibilityLabel="Sync"/);
  assert.match(fix('<Row label="Line numbers"><Switch value={v} /></Row>'), /<Switch accessibilityLabel="Line numbers"/);
  assert.equal(analyse('/x.tsx', '<Row><Switch value={v} /></Row>').findings[0].kind, 'unlabelled-switch');
  assert.deepEqual(analyse('/x.tsx', '<Switch aria-label="On" value={v} />'), { edits: [], findings: [] });
});

test('sliders without a name are reported for review, never auto-fixed', () => {
  const r = analyse('/x.tsx', '<Slider value={v} onValueChange={f} />');
  assert.deepEqual(r.edits, []);
  assert.equal(r.findings[0].kind, 'unlabelled-slider');
  assert.deepEqual(analyse('/x.tsx', '<Slider aria-label="Volume" value={v} />').findings, []);
});

test('every reviewed screen stays clean', () => {
  const { files } = JSON.parse(fs.readFileSync(path.join(__dirname, 'reviewed-screens.json'), 'utf8'));
  assert.ok(files.length >= 74);
  const dirty = [];
  for (const rel of files) {
    const abs = path.join(ROOT, rel);
    const { edits, findings } = analyse(abs, fs.readFileSync(abs, 'utf8'));
    if (edits.length || findings.length) dirty.push(`${rel}: ${edits.length} fixable, ${findings.length} review`);
  }
  assert.deepEqual(dirty, []);
});

test('repo-wide debt never grows (ratchet)', () => {
  const baseline = JSON.parse(fs.readFileSync(path.join(__dirname, 'baseline.json'), 'utf8'));
  let files;
  try {
    files = execFileSync('git', ['ls-files', 'app/*.tsx', 'app/**/*.tsx', 'src/**/*.tsx'], { cwd: ROOT, encoding: 'utf8' }).split('\n').filter(Boolean);
  } catch { return; } // not a git checkout (e.g. exported tarball)
  let fixable = 0; let review = 0;
  for (const rel of new Set(files)) {
    const abs = path.join(ROOT, rel);
    if (!fs.existsSync(abs)) continue;
    const r = analyse(abs, fs.readFileSync(abs, 'utf8'));
    fixable += r.edits.length; review += r.findings.length;
  }
  assert.ok(fixable <= baseline.fixable, `fixable ${fixable} > baseline ${baseline.fixable}`);
  assert.ok(review <= baseline.needs_review, `needs review ${review} > baseline ${baseline.needs_review}`);
});
