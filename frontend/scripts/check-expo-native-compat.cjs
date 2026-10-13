#!/usr/bin/env node
"use strict";
// Expo 54 bundled-native-module gate. Updating the SDK requires a reviewed
// replacement of this compatibility table, not an isolated RN peer bump.
// Source: https://docs.expo.dev/versions/v54.0.0/
const fs = require("node:fs");
const path = require("node:path");

const EXPECTED = Object.freeze({
  "expo": "~54.0.35",
  "react": "19.1.0",
  "react-dom": "19.1.0",
  "react-native": "0.81.5",
  "@types/react": "~19.1.0",
  "@react-native-community/netinfo": "11.4.1",
  "@react-native-community/slider": "5.0.1",
  "react-native-gesture-handler": "~2.28.0",
  "react-native-reanimated": "~4.1.1",
  "react-native-safe-area-context": "~5.6.0",
  "react-native-screens": "~4.16.0",
  "react-native-svg": "15.12.1",
  "react-native-webview": "13.15.0",
  "react-native-worklets": "0.5.1"
});
function validate(manifest, lockText) {
  if (!manifest || typeof manifest !== "object" || Array.isArray(manifest)) {
    throw new Error("A valid frontend package manifest is required");
  }
  const deps = {...(manifest.dependencies || {}), ...(manifest.devDependencies || {})};
  const errors = [];
  for (const [name, version] of Object.entries(EXPECTED)) {
    if (deps[name] !== version) {
      errors.push(name + " expected " + version + ", found " + String(deps[name]));
    }
  }
  if (typeof lockText !== "string") {
    errors.push("A Yarn classic lockfile is required");
  } else {
    for (const [name, version] of Object.entries(EXPECTED)) {
      // Yarn classic groups aliases on a line; accept a quoted or bare selector.
      const selector = name + "@" + version;
      const found = lockText.split("\n").some(line =>
        !/^\s/.test(line) && line.endsWith(":") &&
        line.slice(0, -1).split(", ").some(part =>
          part.replace(/^"|"$/g, "") === selector));
      if (!found) errors.push("yarn.lock missing selector " + selector);
    }
  }
  return errors;
}
function run() {
  const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "package.json"), "utf8"));
  const lock = fs.readFileSync(path.join(__dirname, "..", "yarn.lock"), "utf8");
  const errors = validate(manifest, lock);
  if (errors.length) {
    console.error("[expo-native-compat] SDK 54 incompatible or lockfile drift:\n" +
                  errors.map(item => "- " + item).join("\n"));
    process.exitCode = 1;
  } else {
    console.log("[expo-native-compat] Expo SDK 54 native dependency and lockfile pins verified");
  }
}
if (require.main === module) run();
module.exports = {validate, EXPECTED};
