// Dynamic Expo config — loads env vars at build time so EAS / Emergent
// deployment pipeline can inject the correct backend URL without editing
// app.json by hand.
//
// This file is automatically picked up by Expo (takes precedence over app.json
// when both exist) and merges with app.json at runtime.

const appJson = require('./app.json');

module.exports = ({ config }) => {
  const base = appJson.expo || {};
  const fromContext = config || {};

  const backendUrl =
    process.env.EXPO_PUBLIC_BACKEND_URL ||
    process.env.EXPO_BACKEND_URL ||
    base?.extra?.EXPO_PUBLIC_BACKEND_URL ||
    '';

  const skeletonUrl =
    process.env.EXPO_PUBLIC_SKELETON_URL ||
    process.env.EXPO_SKELETON_URL ||
    base?.extra?.EXPO_PUBLIC_SKELETON_URL ||
    base?.extra?.EXPO_SKELETON_URL ||
    '';

  // A built APK/AAB cannot reach a host server through the phone's localhost.
  // Reject a disconnected native release before it is distributed.
  const installedBuild = ['preview', 'apk', 'production'].includes(process.env.EAS_BUILD_PROFILE || '');
  if (installedBuild) {
    let endpoint;
    try { endpoint = new URL(backendUrl); } catch { /* validated below */ }
    const hostname = endpoint?.hostname?.toLowerCase() || '';
    const loopback = hostname === 'localhost' || hostname === '0.0.0.0'
      || hostname === '[::1]' || /^127\./.test(hostname) || hostname === '10.0.2.2';
    if (!endpoint || endpoint.protocol !== 'https:' || !hostname || loopback
      || endpoint.username || endpoint.password || endpoint.search || endpoint.hash
      || (endpoint.pathname !== '/' && endpoint.pathname !== '')) {
      throw new Error(
        'Installed Skeleton builds require EXPO_PUBLIC_BACKEND_URL pointing at '
        + 'the HTTPS origin of the real application API. localhost and missing '
        + 'URLs cannot serve chat on a phone. Configure the EAS build environment '
        + 'before compiling; never embed a model provider API key.',
      );
    }
  }

  return {
    ...base,
    ...fromContext,
    // Expo SDK 55+ requires explicit plugin registration for these libs
    // (previously implicit through autolinking).
    plugins: [
      ...(base.plugins || []),
      ...(fromContext.plugins || []),
      'expo-font',
      'expo-web-browser',
    ].filter((v, i, a) => a.indexOf(v) === i),
    extra: {
      ...(base.extra || {}),
      ...(fromContext.extra || {}),
      EXPO_PUBLIC_BACKEND_URL: backendUrl,
      EXPO_BACKEND_URL: backendUrl,
      EXPO_PUBLIC_SKELETON_URL: skeletonUrl,
      EXPO_SKELETON_URL: skeletonUrl,
    },
  };
};
