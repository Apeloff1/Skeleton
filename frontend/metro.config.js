// metro.config.js
const { getDefaultConfig } = require("expo/metro-config");
const path = require('path');
const { createHash } = require('node:crypto');
const { getConfig } = require('expo/config');
const { FileStore } = require('metro-cache');

const config = getDefaultConfig(__dirname);

// Expo inlines public endpoint values during transformation. Metro's shared
// disk cache must distinguish those build inputs, or a later export can serve
// the previous installation's URLs despite different Docker build arguments.
const publicEndpointKeys = [
  'EXPO_PUBLIC_BACKEND_URL', 'EXPO_BACKEND_URL',
  'EXPO_PUBLIC_SKELETON_URL', 'EXPO_SKELETON_URL',
  'EXPO_PUBLIC_BACKEND_FALLBACK_URL',
];
const configuredExtra = getConfig(__dirname, {
  isPublicConfig: true,
  skipSDKVersionRequirement: true,
}).exp.extra || {};
let overrideExtra = {};
if (process.env.APP_MANIFEST) {
  let manifest;
  try { manifest = JSON.parse(process.env.APP_MANIFEST); }
  catch { throw new Error('APP_MANIFEST must contain valid JSON'); }
  overrideExtra = manifest?.extra || manifest?.expo?.extra || {};
}
const publicEndpoints = source => publicEndpointKeys.map(key => [
  key, typeof source[key] === 'string' ? source[key] : '',
]);
const endpointVersion = createHash('sha256')
  .update(JSON.stringify({
    environment: publicEndpoints(process.env),
    configured: publicEndpoints(configuredExtra),
    manifestOverridePresent: !!process.env.APP_MANIFEST,
    manifestOverride: publicEndpoints(overrideExtra),
  }))
  .digest('hex');
config.cacheVersion = `${config.cacheVersion || '1'}:public-endpoints:${endpointVersion}`;

// Use a stable on-disk store (shared across web/android), with the public
// configuration included in Metro's cache key above.
const root = process.env.METRO_CACHE_ROOT || path.join(__dirname, '.metro-cache');
config.cacheStores = [
  new FileStore({ root: path.join(root, 'cache') }),
];


// // Exclude unnecessary directories from file watching
// config.watchFolders = [__dirname];
// config.resolver.blacklistRE = /(.*)\/(__tests__|android|ios|build|dist|.git|node_modules\/.*\/android|node_modules\/.*\/ios|node_modules\/.*\/windows|node_modules\/.*\/macos)(\/.*)?$/;

// // Alternative: use a more aggressive exclusion pattern
// config.resolver.blacklistRE = /node_modules\/.*\/(android|ios|windows|macos|__tests__|\.git|.*\.android\.js|.*\.ios\.js)$/;

// Reduce the number of workers to decrease resource usage
config.maxWorkers = 2;

module.exports = config;
