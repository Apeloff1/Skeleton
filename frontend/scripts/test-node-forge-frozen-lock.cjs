'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { readBoundedRegular, exactUtf8, parseFrozenForgeLock, verifyArchiveIdentity,
  LOCK_LIMIT, ARCHIVE_LIMIT } = require('./node-forge-frozen-lock.cjs');
const { main } = require('./verify-node-forge-frozen-archive.cjs');
const bytes = Buffer.from('example archive bytes; deliberately not a tarball');
const sha1 = crypto.createHash('sha1').update(bytes).digest('hex');
const sha512 = crypto.createHash('sha512').update(bytes).digest('base64');
const stanza = 'node-forge@^1.3.3:\n  version "1.4.3"\n  resolved "https://registry.yarnpkg.com/node-forge/-/node-forge-1.4.3.tgz#' +
  sha1 + '"\n  integrity sha512-' + sha512 + '\n';
const parse = value => parseFrozenForgeLock(Buffer.from(value));

test('exact lockbook and CRLF are admitted with identical frozen identities', () => {
  const lock = parse(stanza);
  assert.deepEqual(parse(stanza.replace(/\n/g, '\r\n')), lock);
  assert.equal(lock.sha1, sha1);
  assert.equal(lock.integrity, 'sha512-' + sha512);
  assert.ok(Object.isFrozen(lock));
  assert.doesNotThrow(() => verifyArchiveIdentity(bytes, lock));
});

test('reject ambiguous/multiple selectors and fields; do not treat semver as custody', () => {
  for (const bad of [
    '', stanza + '\n' + stanza, stanza + '\nnode-forge@other:\n  version "1.4.3"\n',
    stanza.replace('node-forge@^1.3.3:', '"node-forge@^1.3.3":'),
    stanza.replace('  version', '  notVersion'),
    stanza.replace('  version "1.4.3"', '  version "1.4.2"'),
    stanza.replace('  version "1.4.3"', '  version "1.4.3"\n  version "1.4.3"'),
    stanza.replace('  integrity', '  sha'),
    stanza.replace(sha512, 'A'.repeat(86) + '=='),
    stanza.replace(sha512, 'AAAA'),
    stanza.replace(sha1, sha1.toUpperCase()),
    stanza + '  unexpected "field"\n',
    stanza + '\x00',
  ]) {
    // A syntactically valid but different SHA-512 is rejected at byte verification.
    if (bad === stanza.replace(sha512, 'A'.repeat(86) + '==')) {
      assert.throws(() => verifyArchiveIdentity(bytes, parse(bad)), /integrity mismatch/);
    } else assert.throws(() => parse(bad));
  }
  assert.throws(() => parse(Buffer.alloc(LOCK_LIMIT + 1, 65)));
  assert.throws(() => exactUtf8(Buffer.from([0xff])));
});

test('reject unreviewed origin, normalized aliases, search, credentials and extra fragment', () => {
  for (const bad of [
    stanza.replace('https://registry.yarnpkg.com', 'http://registry.yarnpkg.com'),
    stanza.replace('registry.yarnpkg.com', 'registry.yarnpkg.com.evil.test'),
    stanza.replace('registry.yarnpkg.com', 'operator@registry.yarnpkg.com'),
    stanza.replace('/node-forge/-/', '/node-forge/../node-forge/-/'),
    stanza.replace('.tgz#', '.tgz?x=1#'),
    stanza.replace('.tgz#', '.tgz##'),
  ]) assert.throws(() => parse(bad));
});

test('SHA-512, resolved SHA-1 and archive bounds are independent fail-closed checks', () => {
  const lock = parse(stanza);
  assert.throws(() => verifyArchiveIdentity(Buffer.from('tampered'), lock), /integrity mismatch/);
  assert.throws(() => verifyArchiveIdentity(bytes, { ...lock, sha1: '0'.repeat(40) }),
    /resolved archive identity mismatch/);
  assert.throws(() => verifyArchiveIdentity(Buffer.alloc(0), lock), /length/);
  assert.throws(() => verifyArchiveIdentity(Buffer.alloc(ARCHIVE_LIMIT + 1), lock), /length/);
});

test('bounded read rejects empty, oversized, directory and symlink input', (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'forge-lock-test-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const good = path.join(directory, 'good');
  const empty = path.join(directory, 'empty');
  fs.writeFileSync(good, bytes);
  fs.writeFileSync(empty, '');
  assert.deepEqual(readBoundedRegular(good, bytes.length), bytes);
  assert.throws(() => readBoundedRegular(good, bytes.length - 1));
  assert.throws(() => readBoundedRegular(empty, 10));
  assert.throws(() => readBoundedRegular(directory, 10));
  if (process.platform !== 'win32') {
    const alias = path.join(directory, 'alias');
    fs.symlinkSync(good, alias);
    assert.throws(() => readBoundedRegular(alias, bytes.length));
  }
});

test('current committed lock is admitted without a network or installed dependency', () => {
  const lockPath = path.resolve(__dirname, '../yarn.lock');
  const lock = parseFrozenForgeLock(readBoundedRegular(lockPath, LOCK_LIMIT));
  assert.equal(lock.version, '1.4.3');
});

test('unrecognized CLI arguments never reach package acquisition', () => {
  for (const args of [['--archive'], ['--archive', ''], ['--unknown'], ['--archive', 'a', 'b']])
    assert.throws(() => main(args), /usage/);
});
