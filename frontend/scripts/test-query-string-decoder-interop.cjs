'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');

const root = path.resolve(__dirname, '..');
const queryMetadata = require(path.join(root, 'node_modules/query-string/package.json'));
const decoderMetadata = require(path.join(root, 'node_modules/decode-uri-component/package.json'));
const queryFile = require.resolve('query-string', { paths: [root] });

test('reviewed route decoder versions and interop patch are installed', () => {
  assert.equal(queryMetadata.version, '7.1.3');
  assert.equal(decoderMetadata.version, '0.5.1');
  const source = fs.readFileSync(queryFile, 'utf8');
  const guard = "const decodeComponent = require('decode-uri-component').default; // skeleton decoder ESM interop";
  assert.equal(source.split(guard).length - 1, 1);
  assert.doesNotMatch(source, /const decodeComponent = require\('decode-uri-component'\);/);
});

test('actual query-string route parsing handles valid and malformed input', () => {
  const query = require(queryFile);
  assert.deepEqual(
    { ...query.parse('screen=studio&name=Jeeves%20Dragon') },
    { name: 'Jeeves Dragon', screen: 'studio' },
  );
  assert.equal(query.parse('label=%E0%A4%A').label, '%E0%A4%A');
});
