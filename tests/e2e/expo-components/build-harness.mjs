// Bundle the /new-game harness with react-native-web (esbuild). Usage:
//   node build-harness.mjs <frontend/node_modules> <outdir>
import { build } from 'esbuild';
import path from 'node:path';
import fs from 'node:fs';

const [nodeModules, outdir] = process.argv.slice(2);
if (!nodeModules || !outdir) throw new Error('usage: build-harness.mjs <node_modules> <outdir>');
fs.mkdirSync(outdir, { recursive: true });
await build({
  entryPoints: [path.resolve('new-game.harness.tsx')],
  bundle: true,
  outfile: path.join(outdir, 'app.js'),
  format: 'iife',
  platform: 'browser',
  target: 'es2020',
  minify: false,
  sourcemap: false,
  nodePaths: [nodeModules],
  alias: { 'react-native': 'react-native-web' },
  resolveExtensions: ['.web.tsx', '.web.ts', '.web.js', '.tsx', '.ts', '.js', '.jsx', '.json'],
  loader: { '.js': 'jsx', '.png': 'empty', '.ttf': 'empty' },
  define: {
    __DEV__: 'false',
    'process.env.NODE_ENV': '"production"',
    'process.env.EXPO_OS': '"web"',
    global: 'globalThis',
  },
  banner: { js: "var process = globalThis.process || { env: { NODE_ENV: 'production', EXPO_OS: 'web' } };" },
  logLevel: 'warning',
});
fs.writeFileSync(path.join(outdir, 'index.html'), `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>New game · Skeleton</title>
<style>html,body,#root{height:100%;margin:0;background:#020617}</style></head>
<body><div id="root"></div><script src="/app.js"></script></body></html>`);
console.log('built', outdir);
