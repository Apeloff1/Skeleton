// react-native.config.js
// Disable auto-linking for incompatible native modules brought in by isomorphic-webcrypto
// These packages are transitive dependencies of yjs -> lib0 -> isomorphic-webcrypto
// They have native code incompatible with Expo SDK 54's module system
module.exports = {
  dependencies: {
    '@unimodules/core': {
      platforms: {
        android: null,
        ios: null,
      },
    },
    '@unimodules/react-native-adapter': {
      platforms: {
        android: null,
        ios: null,
      },
    },
    'expo-random': {
      platforms: {
        android: null,
        ios: null,
      },
    },
    'react-native-securerandom': {
      platforms: {
        android: null,
        ios: null,
      },
    },
  },
};
