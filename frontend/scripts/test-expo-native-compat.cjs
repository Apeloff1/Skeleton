"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {validate, EXPECTED} = require("./check-expo-native-compat.cjs");
const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "package.json"), "utf8"));
const lock = fs.readFileSync(path.join(__dirname, "..", "yarn.lock"), "utf8");

test("reviewed Expo 54 dependency matrix matches committed manifest and lock", () => {
  assert.deepEqual(validate(manifest, lock), []);
});
test("independent RN and React major upgrades fail closed", () => {
  for (const [key, version] of [["react-native", "0.87.1"], ["react", "19.3.0"],
                               ["expo", "~57.0.0"], ["react-native-worklets", "0.13.0"]]) {
    const bad = JSON.parse(JSON.stringify(manifest));
    bad.dependencies[key] = version;
    assert.ok(validate(bad, lock).some(error => error.includes(key)), key);
  }
});
test("a correct selector cannot hide a mismatched resolved native version", () => {
  for (const [selector, forged] of [
    ["react-native@0.81.5", "0.87.1"],
    ["react-native-reanimated@~4.1.1", "4.7.1"],
    ["expo@~54.0.35", "55.0.0"],
  ]) {
    // Read the *current* lockfile resolution, not an obsolete patch release:
    // changing an SDK54-compatible patch should never break the test itself.
    const lines = lock.split("\n");
    const position = lines.findIndex(line => line === selector + ":");
    assert.ok(position >= 0, selector + " source lock selector");
    assert.match(lines[position + 1], /^  version "[^"]+"$/);
    lines[position + 1] = '  version "' + forged + '"';
    const poisoned = lines.join("\n");
    assert.ok(validate(manifest, poisoned).some(error =>
      error.includes("resolved version") && error.includes(selector)), selector);
  }
});

test("missing pinned lockfile selectors cannot claim compatibility", () => {
  for (const key of ["react-native", "expo", "react-native-reanimated"]) {
    const selector = key + "@" + EXPECTED[key];
    const stripped = lock.split("\n").filter(line => !line.includes(selector)).join("\n");
    assert.ok(validate(manifest, stripped).some(error => error.includes(selector)));
  }
});
