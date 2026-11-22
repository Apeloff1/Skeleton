// Bundle the reviewed Expo routes into a react-native-web screen harness.
//   node build-screens.mjs <frontend/node_modules> <outdir>
import { build } from 'esbuild';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const frontend = path.resolve(here, '../../../frontend');
const [nodeModules, outdir] = process.argv.slice(2);
if (!nodeModules || !outdir) throw new Error('usage: build-screens.mjs <node_modules> <outdir>');
const { files } = JSON.parse(fs.readFileSync(path.join(frontend, 'scripts/a11y/reviewed-screens.json'), 'utf8'));
const routes = files.filter((f) => f.startsWith('app/'));

const virtualScreens = {
  name: 'virtual-screens',
  setup(b) {
    b.onResolve({ filter: /^virtual:screens$/ }, () => ({ path: 'screens', namespace: 'virtual' }));
    b.onLoad({ filter: /.*/, namespace: 'virtual' }, () => ({
      resolveDir: here,
      loader: 'ts',
      contents: 'export const SCREENS = {\n' + routes.map((f) =>
        `  ${JSON.stringify(f.slice(4, -4))}: () => import(${JSON.stringify(path.join(frontend, f))}),`).join('\n') + '\n};\n',
    }));
    // expo-three imports three's examples without the extension its exports map requires.
    b.onResolve({ filter: /^three\/examples\/jsm\/.*[^s]$/ }, (args) =>
      b.resolve(`${args.path}.js`, { kind: args.kind, resolveDir: args.resolveDir }));
    // expo-asset-utils still uses the pre-SDK-54 expo-file-system API.
    b.onResolve({ filter: /^expo-file-system$/ }, (args) =>
      args.importer.includes('expo-asset-utils')
        ? b.resolve('expo-file-system/legacy', { kind: args.kind, resolveDir: args.resolveDir })
        : undefined);
    b.onResolve({ filter: /^expo-router$/ }, () => ({ path: path.join(here, 'expo-router.stub.tsx') }));
  },
};

fs.rmSync(outdir, { recursive: true, force: true });
fs.mkdirSync(outdir, { recursive: true });
const result = await build({
  entryPoints: [path.join(here, 'screens.harness.tsx')],
  bundle: true,
  jsx: 'automatic',
  splitting: true,
  format: 'esm',
  outdir,
  platform: 'browser',
  target: 'es2020',
  nodePaths: [nodeModules],
  plugins: [virtualScreens],
  alias: { 'react-native': 'react-native-web' },
  resolveExtensions: ['.web.tsx', '.web.ts', '.web.js', '.tsx', '.ts', '.js', '.jsx', '.json'],
  loader: { '.js': 'jsx', '.png': 'dataurl', '.jpg': 'dataurl', '.gif': 'dataurl', '.ttf': 'file', '.otf': 'file', '.mp3': 'file', '.wav': 'file', '.glb': 'file', '.lottie': 'file' },
  define: { __DEV__: 'false', 'process.env.NODE_ENV': '"production"', 'process.env.EXPO_OS': '"web"', global: 'globalThis' },
  banner: { js: "var process = globalThis.process || { env: { NODE_ENV: 'production', EXPO_OS: 'web' } };" },
  logLevel: 'error',
  logLimit: 50,
  metafile: true,
});
fs.writeFileSync(path.join(outdir, 'index.html'), `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Screen harness · Skeleton</title>
<style>html,body,#root{height:100%;margin:0;background:#020617}</style></head>
<body><div id="root"></div><script type="module" src="/screens.harness.js"></script></body></html>`);
console.log('built', routes.length, 'screens into', outdir, Object.keys(result.metafile.outputs).length, 'chunks');
