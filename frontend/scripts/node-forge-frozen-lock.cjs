'use strict';
// First-install supply-chain proof: no package execution and no installation writes.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const { EXPECTED_VERSION } = require('./node-forge-rsa-custody.cjs');
const LOCK_LIMIT = 4 * 1024 * 1024;
const ARCHIVE_LIMIT = 16 * 1024 * 1024;
const RSA_LIMIT = 4 * 1024 * 1024;

function sameFile(a, b) {
  return a.dev === b.dev && a.ino === b.ino && a.size === b.size &&
    a.mtimeNs === b.mtimeNs && a.ctimeNs === b.ctimeNs;
}

function readBoundedRegular(filename, limit) {
  assert.ok(Number.isSafeInteger(limit) && limit > 0 && limit <= ARCHIVE_LIMIT);
  const before = fs.lstatSync(filename, { bigint: true });
  assert.ok(before.isFile() && before.size > 0n && before.size <= BigInt(limit),
    'expected a bounded regular file');
  const fd = fs.openSync(filename, fs.constants.O_RDONLY |
    (fs.constants.O_NOFOLLOW || 0) | (fs.constants.O_NONBLOCK || 0));
  try {
    const opened = fs.fstatSync(fd, { bigint: true });
    assert.ok(opened.isFile() && sameFile(before, opened), 'source identity changed before read');
    const bytes = Buffer.alloc(Number(opened.size));
    let offset = 0;
    while (offset < bytes.length) {
      const count = fs.readSync(fd, bytes, offset, bytes.length - offset, offset);
      assert.ok(count > 0, 'source shortened during read');
      offset += count;
    }
    assert.equal(fs.readSync(fd, Buffer.alloc(1), 0, 1, offset), 0, 'source grew during read');
    const after = fs.fstatSync(fd, { bigint: true });
    const pathAfter = fs.lstatSync(filename, { bigint: true });
    assert.ok(pathAfter.isFile() && sameFile(opened, after) && sameFile(after, pathAfter),
      'source changed during read');
    return bytes;
  } finally {
    fs.closeSync(fd);
  }
}

function exactUtf8(bytes) {
  assert.ok(Buffer.isBuffer(bytes), 'expected bytes');
  const text = bytes.toString('utf8');
  assert.ok(bytes.equals(Buffer.from(text, 'utf8')), 'noncanonical UTF-8');
  return text;
}

function parseFrozenForgeLock(bytes) {
  assert.ok(Buffer.isBuffer(bytes) && bytes.length > 0 && bytes.length <= LOCK_LIMIT,
    'invalid lockfile length');
  const text = exactUtf8(bytes);
  assert.ok(!/[\x00\r](?!\n)/.test(text) && !text.includes('\x00'), 'invalid lockfile control bytes');
  const lines = text.split(/\r?\n/);
  const headers = lines.map((line, index) => ({ line, index }))
    .filter(({ line }) => /^(?![ \t#]).*node-forge@/.test(line));
  assert.equal(headers.length, 1, 'expected one unambiguous node-forge selector');
  assert.equal(headers[0].line, 'node-forge@^1.3.3:', 'unreviewed frozen selector');
  const fields = [];
  for (let i = headers[0].index + 1; i < lines.length && /^[ \t]/.test(lines[i]); i++) {
    fields.push(lines[i]);
  }
  assert.equal(fields.length, 3, 'unexpected node-forge lock fields');
  const field = (name, pattern) => {
    const matching = fields.map(line => line.match(new RegExp('^  ' + name + ' ' + pattern + '$')))
      .filter(Boolean);
    assert.equal(matching.length, 1, 'missing or ambiguous frozen ' + name);
    return matching[0][1];
  };
  const version = field('version', '"([^"]+)"');
  assert.equal(version, EXPECTED_VERSION, 'unreviewed node-forge version');
  const resolved = field('resolved', '"([^"]+)"');
  const url = 'https://registry.yarnpkg.com/node-forge/-/node-forge-' + version + '.tgz';
  assert.ok(resolved.startsWith(url + '#'), 'unreviewed archive origin or path');
  const sha1 = resolved.slice(url.length + 1);
  assert.match(sha1, /^[a-f0-9]{40}$/, 'invalid resolved hash');
  const integrity = field('integrity', 'sha512-([A-Za-z0-9+/]+={0,2})');
  const digest = Buffer.from(integrity, 'base64');
  assert.ok(digest.length === 64 && digest.toString('base64') === integrity,
    'invalid canonical SHA-512 integrity');
  return Object.freeze({ version, url, sha1, integrity: 'sha512-' + integrity });
}

function verifyArchiveIdentity(bytes, lock) {
  assert.ok(Buffer.isBuffer(bytes) && bytes.length > 0 && bytes.length <= ARCHIVE_LIMIT,
    'invalid archive length');
  assert.equal('sha512-' + crypto.createHash('sha512').update(bytes).digest('base64'),
    lock.integrity, 'frozen archive integrity mismatch; independent review required');
  assert.equal(crypto.createHash('sha1').update(bytes).digest('hex'),
    lock.sha1, 'frozen resolved archive identity mismatch');
}

module.exports = { LOCK_LIMIT, ARCHIVE_LIMIT, RSA_LIMIT, readBoundedRegular,
  exactUtf8, parseFrozenForgeLock, verifyArchiveIdentity };
