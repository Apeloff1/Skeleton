import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { decodePackageBytes, hexDigest, validPackageIdentity, validPackageName } from '../src/utils/jeevesDelivery.ts';

test('decoder preserves every byte and rejects forged metadata', () => {
  for (let size = 1; size <= 300; size++) {
    const raw = Buffer.from(Array.from({ length: size }, (_, i) => i % 256));
    const decoded = decodePackageBytes(raw.toString('base64'), size);
    assert.deepEqual(Buffer.from(decoded), raw);
    const digest = createHash('sha256').update(decoded).digest();
    assert.equal(hexDigest(Uint8Array.from(digest).buffer), createHash('sha256').update(raw).digest('hex'));
  }
  for (const malformed of ['YQ=A', 'YR==', 'YQ= ', 'Y!==', 'YQ===']) {
    assert.throws(() => decodePackageBytes(malformed, 1));
  }
  assert.throws(() => decodePackageBytes('YQ==', 0));
  assert.throws(() => decodePackageBytes('YQ==', 2));
  assert.throws(() => decodePackageBytes('YQ==', 9 * 1024 * 1024));
  assert.equal(validPackageIdentity('0'.repeat(32)), true);
  assert.equal(validPackageIdentity('../wrong'), false);
  assert.equal(validPackageName('game.zip'), true);
  assert.equal(validPackageName('../game.zip'), false);
});
