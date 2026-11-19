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
