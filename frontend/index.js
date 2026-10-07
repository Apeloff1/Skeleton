/* global require */

/**
 * Expo Router entry shim for non-browser static rendering.
 *
 * react-native-worklets schedules work through requestAnimationFrame while
 * Expo Router renders static routes in Node. Browser and native runtimes
 * already provide RAF; only install this timer-backed fallback when absent.
 */
if (typeof globalThis.requestAnimationFrame !== 'function') {
  globalThis.requestAnimationFrame = (callback) =>
    setTimeout(() => callback(Date.now()), 16);
}

if (typeof globalThis.cancelAnimationFrame !== 'function') {
  globalThis.cancelAnimationFrame = (handle) => clearTimeout(handle);
}

// Expo Router must load after global polyfills are installed.
require('expo-router/entry');
