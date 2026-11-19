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
  for (const [selector, current, forged] of [
    ["react-native@0.81.5", "0.81.5", "0.87.1"],
    ["react-native-reanimated@~4.1.1", "4.1.7", "4.7.1"],
    ["expo@~54.0.35", "54.0.37", "55.0.0"],
  ]) {
    const header = selector + ':\n  version "' + current + '"';
    const substitute = selector + ':\n  version "' + forged + '"';
    assert.ok(lock.includes(header), selector + " source lock header");
    const poisoned = lock.replace(header, substitute);
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
