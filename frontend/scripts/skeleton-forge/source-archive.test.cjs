'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { load, h, render, text } = require('./harness.cjs');
const Archive = load('src/skeletonForge/sourceArchive.ts');
const Q = load('src/skeletonForge/questionnaire.ts');
const H = load('src/skeletonForge/creatorBridge.ts');
const Panel = load('src/skeletonForge/components/ForgeRunPanel.tsx').default;

const SHA = s => createHash('sha256').update(s).digest('hex');
function fixture(files = {
  'project.godot': 'config_version=5\nrun/main_scene="res://scenes/levels/run_level.tscn"\n',
  'scenes/levels/run_level.tscn': '[gd_scene load_steps=1 format=3]\n',
  'scripts/creature.gd': 'extends CharacterBody2D\n# still local 😀\n',
}) {
  const hashes = Object.fromEntries(Object.entries(files).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)
    .map(([name, body]) => [name, SHA(body)]));
  const digest = SHA(JSON.stringify(hashes));
  const bytes = Object.values(files).reduce((a, x) => a + Buffer.byteLength(x, 'utf8'), 0);
  return {
    succeeded: true,
    files,
    source_manifest: {
      schema: 'skeleton.forge.source_manifest.v1',
      file_count: Object.keys(files).length, files: hashes, sha256: digest,
    },
    source_export: {
      status: 'ready', bytes, file_count: Object.keys(files).length,
      manifest_sha256: digest,
    },
    run: { run_id: 'fixture', succeeded: true, stages: [] },
    forge: { file_count: Object.keys(files).length },
  };
}

function entriesFromZip(blob) {
  const b = Buffer.from(blob);
  const end = b.length - 22;
  assert.equal(b.readUInt32LE(end), 0x06054b50);
  assert.equal(b.readUInt16LE(end + 8), b.readUInt16LE(end + 10));
  const centralAt = b.readUInt32LE(end + 16), centralSize = b.readUInt32LE(end + 12);
  assert.equal(centralAt + centralSize, end);
  let i = centralAt;
  const rows = [];
  for (let n = 0; n < b.readUInt16LE(end + 10); n++) {
    assert.equal(b.readUInt32LE(i), 0x02014b50);
    assert.equal(b.readUInt16LE(i + 10), 0); // No compression
    const len = b.readUInt16LE(i + 28);
    const name = b.toString('utf8', i + 46, i + 46 + len);
    const local = b.readUInt32LE(i + 42);
    assert.equal(b.readUInt32LE(local), 0x04034b50);
    assert.equal(b.readUInt32LE(i + 16), b.readUInt32LE(local + 14));
    const localLength = b.readUInt16LE(local + 26);
    const dataOffset = local + 30 + localLength;
    const size = b.readUInt32LE(i + 24);
    const body = b.subarray(dataOffset, dataOffset + size);
    assert.equal(b.readUInt32LE(local + 18), body.length);
    rows.push({ name, content: body.toString('utf8') });
    i += 46 + len;
  }
  assert.equal(i, end);
  return rows;
}

test('exact-run source archives are valid deterministic unzip-ready files', () => {
  const p = fixture();
  const archive = Archive.buildGodotSourceArchive(p);
  assert.equal(archive.fileCount, 3);
  assert.equal(archive.sourceBytes, p.source_export.bytes);
  assert.equal(archive.manifestSha256, p.source_manifest.sha256);
  assert.match(archive.filename, /^skeleton-godot-[0-9a-f]{16}\.zip$/);
  const contents = entriesFromZip(archive.bytes);
  assert.deepEqual(Object.fromEntries(contents.map(x => [x.name, x.content])), p.files);
  const reversed = fixture(Object.fromEntries(Object.entries(p.files).reverse()));
  assert.deepEqual(
    Buffer.from(Archive.buildGodotSourceArchive(reversed).bytes),
    Buffer.from(archive.bytes),
  );
});

test('export refuses path traversal, Windows absolute paths and unlisted source files', () => {
  for (const name of ['../world.gd', 'src/../world.gd', '/etc/hosts', 'C:\\boot.ini',
    'scripts\\test.gd', 'a//x.gd', 'foo:bar', '.git/config', 'scripts/.git/config', 'scripts/a?.gd', 'assets/con.txt', 'assets/AUX', 'drivers/lpt1.gd', 'scripts/CON.gd']) {
    assert.throws(() => Archive.buildGodotSourceArchive(fixture({
      'project.godot': 'config_version=5\n', [name]: 'extends Node\n',
    })), /Unsafe or unlisted Godot project source path/, name);
  }
});

test('the ZIP builder refuses unsealed, failed, oversized and mismatched runs', () => {
  const original = fixture();
  const variants = [
    { ...original, succeeded: false },
    { ...original, source_manifest: null },
    { ...original, source_export: { status: 'unavailable' } },
    { ...original, source_export: { ...original.source_export, bytes: 1 } },
    { ...original, source_export: { ...original.source_export, manifest_sha256: 'f'.repeat(64) } },
    { ...original, source_manifest: { ...original.source_manifest, file_count: 4 } },
    { ...original, source_manifest: { ...original.source_manifest, files: {} } },
    { ...original, files: { ...original.files, 'unlisted.txt': 'injection' } },
    fixture({ 'scripts/no-project.gd': 'extends Node\n' }),
    fixture({ 'project.godot': 'x'.repeat(Archive.MAX_EXPORT_SOURCE_BYTES + 1) }),
  ];
  for (const candidate of variants) {
    assert.throws(() => Archive.buildGodotSourceArchive(candidate), Error);
  }
  const many = Object.fromEntries([['project.godot', 'godot'], ...Array.from(
    { length: Archive.MAX_EXPORT_FILES }, (_, i) => ['scenes/file_' + i + '.gd', 'extends Node'],
  )]);
  assert.throws(() => Archive.buildGodotSourceArchive(fixture(many)), /file budget/);
});

test('invalid UTF-16 and case-colliding generated paths cannot become a portable ZIP', () => {
  const invalidUnicode = fixture({ 'project.godot': String.fromCharCode(0xd800) });
  assert.throws(() => Archive.buildGodotSourceArchive(invalidUnicode),
    /invalid UTF-16 surrogate/);
  const collision = fixture({
    'project.godot': 'config_version=5\\n',
    'scripts/Quest.gd': 'extends Node\\n',
    'scripts/quest.gd': 'extends Node\\n',
  });
  assert.throws(() => Archive.buildGodotSourceArchive(collision), /Case-colliding/);
});

test('source bundle preparation is opt-in and remains roundtrippable through Galaxy', () => {
  assert.equal(Q.buildRunRequest(Q.INITIAL_STATE).include_files, undefined);
  const enabled = Q.questionnaireReducer(Q.INITIAL_STATE, { type: 'setSourceExportEnabled', value: true });
  assert.equal(Q.buildRunRequest(enabled).include_files, true);
  const handoff = H.handoffFromForge(enabled, 1700000000000);
  const returnHop = H.handoffFromGalaxy({ title: '', vision: '', genreId: null }, handoff, 1700000000001);
  const restored = H.forgeStateFromHandoff(returnHop, 1700000000002);
  assert.equal(restored.sourceExport.enabled, true);
  assert.equal(Q.buildRunRequest(restored).include_files, true);
  const json = Q.questionnaireReducer(restored, { type: 'setOption', key: 'target', value: 'json' });
  assert.equal(Q.buildRunRequest(json).include_files, undefined);
  assert.equal(json.sourceExport.enabled, true);
});

test('run panel only reveals the local share action for a successful, prepared source run', () => {
  const p = fixture();
  const ready = render(h(Panel, { phase: 'done', payload: p, onExport: () => {} }));
  assert.match(ready, /data-testid="run-export-godot-zip"/);
  assert.match(text(ready), /source-only ZIP that opens in Godot/);
  const forbidden = render(h(Panel, { phase: 'done', payload: {
    ...p, source_export: { status: 'unavailable', reason: 'exceeds 8 MiB' }, files: undefined,
  }, onExport: () => {} }));
  assert.doesNotMatch(forbidden, /data-testid="run-export-godot-zip"/);
  assert.match(text(forbidden), /exceeds 8 MiB/);
  const code = fs.readFileSync(path.resolve(__dirname, '../../src/skeletonForge/shareSourceArchive.ts'), 'utf8');
  assert.match(code, /Crypto\.digestStringAsync/);
  assert.match(code, /Sharing\.shareAsync\(/);
  assert.match(code, /owner|stillCurrent/);
});


test('portable ZIP rejects file-directory and case-aliased parent conflicts', () => {
  for (const [a,b] of [['assets','assets/child.txt'], ['Assets/a.txt','assets/b.txt'],
    ['Assets','assets/nested/file.txt'], ['assets/deep','assets/deep/x.txt']]) {
    assert.throws(() => Archive.buildGodotSourceArchive(fixture({
      'project.godot': 'config_version=5', [a]: 'first', [b]: 'second',
    })), /collision|Case-colliding/);
  }
});
test('share custody snapshots files before async hashing and deletes only owned cache files', () => {
  const code = fs.readFileSync(path.resolve(__dirname, '../../src/skeletonForge/shareSourceArchive.ts'), 'utf8');
  assert.match(code, /Object.freeze\(\{ \.\.\.payload.files!/);
  assert.match(code, /Object.freeze\(\{ \.\.\.payload.source_manifest!.files!/);
  assert.ok(code.indexOf('Object.freeze(') < code.indexOf("await import('expo-crypto')"));
  assert.match(code, /if \(created && file.exists\) file.delete\(\)/);
});


test('export snapshot is the same input used for ZIP construction and hashing', () => {
  const code = fs.readFileSync(path.resolve(__dirname, '../../src/skeletonForge/shareSourceArchive.ts'), 'utf8');
  assert.ok(code.indexOf('const files = Object.freeze') < code.indexOf('buildGodotSourceArchive(snapshot)'));
  assert.match(code, /source_manifest: \{ \.\.\.payload.source_manifest, files: expected \}/);
  assert.match(code, /Crypto.digestStringAsync\(digest, files\[path\]\)/);
});
test('export lifecycle fences unmount, account rotation and stale failure callbacks', () => {
  const code = fs.readFileSync(path.resolve(__dirname, '../../src/skeletonForge/components/ForgeCockpitScreen.tsx'), 'utf8');
  assert.match(code, /subscribeAuthChanges\(\(\) => \{/);
  assert.match(code, /runOwnerEpoch.current = null/);
  assert.match(code, /exportMounted.current = false/);
  assert.match(code, /const current = \(\) => exportMounted.current && ownerEpoch === getAuthEpoch\(\)/);
  assert.match(code, /if \(!current\(\)\) return;\s+const message/);
});


test('portable export exposes its full independently retainable source identity', () => {
  const p = fixture();
  const html = render(h(Panel, { phase: 'done', payload: p }));
  assert.match(html, /data-testid="run-full-source-digest"/);
  assert.ok(text(html).includes(p.source_manifest.sha256));
  assert.match(text(html), /verify or reopen the ZIP later/);
});

test('portable playable source requires the exact new receipt and project startup', () => {
  const mode = 'puzzle';
  const scene = 'scenes/archetypes/puzzle/main.tscn';
  const launcher = 'scripts/autoloads/playable_portal.gd';
  const native = [scene, 'scripts/archetypes/puzzle/player_controller.gd',
    'scripts/archetypes/puzzle/core_loop.gd', launcher, 'project.godot'];
  const p = fixture({
    'project.godot': 'config_version=5\nrun/main_scene="res://scenes/archetypes/puzzle/main.tscn"\n',
    [scene]: '[gd_scene load_steps=1 format=3]\n',
    [native[1]]: 'extends CharacterBody2D\n',
    [native[2]]: 'extends Node2D\n',
    [launcher]: 'extends CanvasLayer\n',
  });
  p.forge.playable_archetype = mode;
  assert.throws(() => Archive.buildGodotSourceArchive(p), /playable source receipt/);
  const subset = Object.fromEntries(native.sort().map(path => [path, p.source_manifest.files[path]]));
  p.playable_source = { schema: 'skeleton.gameforge.playable_source.v2', mode, scene: 'res://' + scene,
    launch_scene: 'res://' + scene, launcher, source_files: subset,
    source_sha256: SHA(JSON.stringify(subset)), native_execution_qualified: false };
  assert.equal(Archive.buildGodotSourceArchive(p).fileCount, 5);
  for (const patch of [{mode: 'racing'}, {native_execution_qualified: true}, {launch_scene: null},
    {source_files: {...subset, 'project.godot': 'f'.repeat(64)}}]) {
    assert.throws(() => Archive.buildGodotSourceArchive({...p, playable_source: {...p.playable_source, ...patch}}), /playable/);
  }
});
