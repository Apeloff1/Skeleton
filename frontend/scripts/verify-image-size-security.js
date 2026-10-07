#!/usr/bin/env node
/* eslint-disable */
const path = require('path');
const { spawnSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..');

function runBounded(name, source) {
  const result = spawnSync(process.execPath, ['-e', source], {
    cwd: ROOT,
    encoding: 'utf8',
    timeout: 1200,
  });
  if (result.error && result.error.code === 'ETIMEDOUT') {
    throw new Error(`${name}: parser failed to make forward progress`);
  }
  if (result.error) {
    throw result.error;
  }
}

// GHSA-5p2g-fcmc-qvqq / CVE-2025-71329.
// A zero-sized box must never leave the parser offset unchanged.
runBounded(
  'image-size box walk',
  `
    const { findBox } = require('image-size/dist/types/utils.js');
    const input = Uint8Array.from([0,0,0,0,0x4a,0x58,0x4c,0x20]);
    findBox(input, 'ftyp', 0);
  `,
);

// GHSA-w3rx-r6r6-pgpr / CVE-2025-71330.
// The ICNS entry declares length zero; vulnerable builds loop forever.
runBounded(
  'image-size ICNS walk',
  `
    const { ICNS } = require('image-size/dist/types/icns.js');
    const input = Uint8Array.from([
      0x69,0x63,0x6e,0x73, 0x00,0x00,0x00,0x10,
      0x69,0x63,0x30,0x37, 0x00,0x00,0x00,0x00
    ]);
    ICNS.calculate(input);
  `,
);

console.log('[verify-image-size-security] parser progress guards verified');
