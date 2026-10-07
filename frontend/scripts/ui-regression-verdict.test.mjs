import assert from "node:assert/strict";
import test from "node:test";

import {
  bodyTextPrefix,
  compareUiVerdictJson,
  compareUiVerdicts,
  exitCodeForUiVerdict,
  normalizeBodyText,
  normalizedBodyTextHash,
} from "./ui-regression-verdict.mjs";

function viewport(overrides = {}) {
  return {
    status: 200,
    title: "Skeleton",
    hasCanvas: true,
    horizontalOverflow: false,
    bodyTextLen: 500,
    bodyTextHash: "aaa",
    bodyTextPrefix: "skeleton app",
    consoleErrors: [],
    pageErrors: [],
    ...overrides,
  };
}

function verdict(desktop = {}, mobile = {}) {
  return { viewports: { desktop: viewport(desktop), mobile: viewport(mobile) } };
}

test("normalizes and hashes rendered body identity", () => {
  assert.equal(normalizeBodyText("  a\n\t b  "), "a b");
  assert.equal(normalizedBodyTextHash("a \n b"), normalizedBodyTextHash(" a b "));
  assert.equal(bodyTextPrefix("x".repeat(200)).length, 64);
});

test("identical viewport verdicts pass", () => {
  assert.deepEqual(compareUiVerdicts(verdict(), verdict()), { diverges: false, reasons: [] });
});

test("navigation, canvas and overflow regressions accumulate", () => {
  const result = compareUiVerdicts(
    verdict({ status: 500, hasCanvas: false }, { horizontalOverflow: true }),
    verdict(),
  );
  assert.equal(result.diverges, true);
  assert.match(result.reasons.join(";"), /HTTP status changed 200 -> 500/);
  assert.match(result.reasons.join(";"), /canvas disappeared/);
  assert.match(result.reasons.join(";"), /horizontal overflow appeared/);
});

test("new runtime errors fail the verdict", () => {
  const result = compareUiVerdicts(verdict({}, { consoleErrors: ["boom"] }), verdict());
  assert.equal(result.diverges, true);
  assert.match(result.reasons.join(";"), /console\/page errors appeared/);
});

test("body collapse and identity replacement are detected", () => {
  const collapsed = compareUiVerdicts(
    verdict({ bodyTextLen: 20, bodyTextHash: "bbb", bodyTextPrefix: "error" }),
    verdict(),
  );
  assert.match(collapsed.reasons.join(";"), /body text collapsed/);

  const replaced = compareUiVerdicts(
    verdict({ bodyTextLen: 505, bodyTextHash: "bbb", bodyTextPrefix: "500 internal error" }),
    verdict(),
  );
  assert.match(replaced.reasons.join(";"), /body text replaced/);
});

test("missing current viewport data fails closed", () => {
  assert.deepEqual(compareUiVerdicts({}, verdict()), {
    diverges: true,
    reasons: ["current verdict has no viewport data"],
  });
});

test("malformed baselines fail closed", () => {
  assert.deepEqual(compareUiVerdictJson(verdict(), "{"), {
    diverges: true,
    reasons: ["baseline unreadable: invalid JSON"],
  });
  assert.deepEqual(compareUiVerdictJson(verdict(), "[]"), {
    diverges: true,
    reasons: ["baseline unreadable: not a verdict object"],
  });
});

test("exit codes distinguish transport failure from runtime errors", () => {
  assert.equal(exitCodeForUiVerdict(verdict().viewports), 0);
  assert.equal(exitCodeForUiVerdict(verdict({ status: 503 }).viewports), 1);
  assert.equal(exitCodeForUiVerdict(verdict({}, { pageErrors: ["boom"] }).viewports), 2);
  assert.equal(exitCodeForUiVerdict({}), 1);
});
