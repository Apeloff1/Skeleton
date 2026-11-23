'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const source = fs.readFileSync(path.join(__dirname, '../app/apk-build.tsx'), 'utf8');

test('APK Build screen has no unresolved merge conflict markers', () => {
  for (const line of source.split(String.fromCharCode(10))) {
    assert.equal(line.startsWith('<<<<<<< '), false);
    assert.equal(line.trim() === '=======', false);
    assert.equal(line.startsWith('>>>>>>> '), false);
  }
});

test('APK Build screen retains explicit loading, failure, and retry UI', () => {
  assert.ok(source.includes('<LoadingNotice what="APK artifacts" testID="apk-loading" />'));
  assert.ok(source.includes('<LoadErrorNotice failure={failure} what="APK artifacts"'));
  assert.ok(source.includes('onRetry={() => { setLoading(true); void load(); }}'));
});
