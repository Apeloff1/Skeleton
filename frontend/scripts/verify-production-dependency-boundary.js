#!/usr/bin/env node
/* eslint-disable */
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const dockerfilePath = path.join(root, 'Dockerfile');
const source = fs.readFileSync(dockerfilePath, 'utf8');
const productionMarker = /FROM\s+nginx:[^\n]+\s+AS\s+production/i;
const match = productionMarker.exec(source);

function fail(message) {
  console.error('[frontend-runtime-boundary] ' + message);
  process.exit(1);
}

if (!match) {
  fail('production stage must use an nginx-only runtime');
}

const production = source.slice(match.index);
const instructions = production
  .split(/\r?\n/)
  .map((line) => line.trim())
  .filter((line) => line && !line.startsWith('#'))
  .join('\n');

for (const forbidden of [
  /\bnode_modules\b/i,
  /\bpackage\.json\b/i,
  /\byarn\.lock\b/i,
  /\bnpm\b/i,
  /\byarn\b/i,
  /\bnode\s+/i,
]) {
  if (forbidden.test(instructions)) {
    fail('Node/JavaScript dependency payload leaked into production stage');
  }
}

if (!/COPY\s+--from=builder[^\n]*\/app\/dist\s+\/usr\/share\/nginx\/html/i.test(production)) {
  fail('production stage must copy only the built static dist payload');
}
if (!/^USER\s+nginx\s*$/im.test(production)) {
  fail('production stage must drop privileges to nginx');
}
if (!/CMD\s+\["nginx",\s*"-g",\s*"daemon off;"\]/i.test(production)) {
  fail('production stage must execute nginx directly');
}

console.log('[frontend-runtime-boundary] verified static nginx production boundary');
