'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const source = fs.readFileSync(path.join(__dirname, '../app/apk-build.tsx'), 'utf8');

test('APK Build screen has no unresolved merge conflict markers', () => {
  assert.doesNotMatch(source, /^(?:<<<<<<< |=======\\s*$|>>>>>>> )/m);
});

test('APK Build screen retains explicit loading, failure, and retry UI', () => {
  assert.match(source, /<LoadingNotice what="APK artifacts" testID="apk-loading" \\/>/);
  assert.match(source, /<LoadErrorNotice failure=\\{failure\\} what="APK artifacts"/);
  assert.match(source, /onRetry=\\{\\(\\) => \\{ setLoading\\(true\\); void load\\(\\); \\}\\}/);
});
