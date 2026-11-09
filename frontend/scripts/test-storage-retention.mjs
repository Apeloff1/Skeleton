import assert from 'node:assert/strict';
import { test } from 'node:test';
import { isPrunableStorageKey } from '../src/utils/storageRetentionPolicy.ts';

test('advisory warm-boot and namespaced telemetry caches can expire', () => {
  assert.equal(isPrunableStorageKey('@boot/last_ok:v1'), true);
  assert.equal(isPrunableStorageKey('@telemetry/cache/requests-01'), true);
});

test('durable project, AI, editor and settings data never enters generic TTL pruning', () => {
  for (const key of [
    '@codedock/project/my-game', '@codedock:project/my-game',
    '@codedock:world:v2', '@codedock/academy/save', '@codedock:jeeves:checkpoint',
    '@codedock:ui:settings', '@feature/experimental_voice',
    '@feature-flags/user-override', '@boot/sessions', '@boot/trace',
    '@boot/crash_count', '@boot/last_clean_boot', '@boot/clean_count',
    '@boot/last_ok:v1/evil', '@telemetry/crash-evidence',
    '@telemetry/cache/', 'tb_cache_project-world',
  ]) assert.equal(isPrunableStorageKey(key), false, key);
});

test('arbitrary user-supplied prefixes cannot expand an explicit deletion allowlist', () => {
  for (const prefix of ['@boot/', '@codedock/', '@feature/', '@telemetry/']) {
    const durable = prefix + 'user-owned-value';
    assert.equal(isPrunableStorageKey(durable), false, prefix);
  }
});
