"use strict";
/** Bounded fixture-based security contract for Expo static index patching. */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const script = fs.readFileSync(path.join(__dirname, "patch-node-modules.js"), "utf8");
const start = script.indexOf("function patchExpoStaticIndexPath() {");
const end = script.indexOf("\n}\n\npatchImageSizeDoS();", start);
assert.ok(start >= 0 && end > start, "Expo patch function must retain reviewed boundaries");
const source = script.slice(start, end + 2);
const before = "pathname: filePathLocation.replace(/(\\/?index)?$/, '')";
const after = "pathname: filePathLocation === 'index' ? '' : filePathLocation.replace(/\\/index$/, '')";
const pkgPath = path.join(root, "node_modules/@expo/cli/package.json");
const targetPath = path.join(root, "node_modules/@expo/cli/build/src/export/exportStaticAsync.js");

function run(version, target, includePkg = true) {
  const files = new Map();
  if (includePkg) files.set(pkgPath, JSON.stringify({version}));
  files.set(targetPath, target);
  const ctx = {
    ROOT: root,
    path,
    skipped: 0,
    patched: 0,
    console: {log() {}},
    fs: {
      existsSync: key => files.has(key),
      readFileSync: key => {
        assert.ok(files.has(key), "unknown source read");
        return files.get(key);
      },
      writeFileSync: (key, contents) => {
        assert.equal(key, targetPath, "patch must modify only reviewed target");
        files.set(key, contents);
      },
    },
  };
  try {
    vm.runInNewContext(source + "\npatchExpoStaticIndexPath();", ctx, {timeout: 1000});
    return {result: files.get(targetPath), patched: ctx.patched, skipped: ctx.skipped};
  } catch (error) {
    throw new Error(String(error.message));
  }
}

for (const version of ["54.0.27", "54.0.28"]) {
  test("reviewed Expo CLI " + version + " static-index patch", () => {
    const r = run(version, "const routes = { " + before + " };");
    assert.equal(r.patched, 1);
    assert.equal(r.skipped, 0);
    assert.match(r.result, /filePathLocation === 'index'/);
    assert.equal(r.result.includes(before), false);
    assert.ok(r.result.includes(after));
  });
}

test("idempotent hardened upstream code is accepted", () => {
  const r = run("54.0.28", "const routes = { " + after + " };");
  assert.equal(r.skipped, 1);
  assert.equal(r.patched, 0);
});

test("unknown Expo CLI version is rejected", () => {
  assert.throws(() => run("54.0.29", before), /requires static path review/);
});

test("unexpected upstream source is rejected", () => {
  assert.throws(() => run("54.0.28", "const routes = {};"), /changed shape/);
});

test("ambiguous duplicate match is rejected", () => {
  assert.throws(() => run("54.0.28", before + " " + before), /changed shape/);
});

test("missing optional Expo CLI target remains no-op", () => {
  const r = run("54.0.28", "untouched", false);
  assert.equal(r.result, "untouched");
  assert.equal(r.patched, 0);
});
