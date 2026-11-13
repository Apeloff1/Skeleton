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
    'scripts\\test.gd', 'a//x.gd', 'foo:bar', '.git/config', 'scripts/a?.gd']) {
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
