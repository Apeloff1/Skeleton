"""Negative checks for live E2E source admission; no network or credentials."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "source_e2e_admission", ROOT / "scripts/check_app_foundation_e2e_admission.py")
assert spec is not None and spec.loader is not None
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
W = (ROOT / ".github/workflows/app-foundation-e2e.yml").read_text(encoding="utf-8")
S = (ROOT / "frontend/scripts/test-app-foundation-flows.mjs").read_text(encoding="utf-8")


class LiveE2ESourceAdmission(unittest.TestCase):
    def test_active_sources_are_closed(self):
        self.assertEqual(guard.validate_text(W, S), [])

    def test_missing_workflow(self):
        self.assertTrue(guard.validate_text("", S))

    def test_missing_suite(self):
        self.assertTrue(guard.validate_text(W, ""))

    def test_unparseable_yaml(self):
        self.assertTrue(guard.validate_text("jobs: [", S))

    def test_source_checkout_must_not_use_synthetic_merge_ref(self):
        self.assertTrue(guard.validate_text(
            W.replace("ref: " + guard.EXACT_REF, "ref: main", 1), S))

    def test_checkout_must_not_persist_credentials(self):
        self.assertTrue(guard.validate_text(
            W.replace("persist-credentials: false", "persist-credentials: true", 1), S))

    def test_exact_commit_assertion_cannot_be_disabled(self):
        self.assertTrue(guard.validate_text(
            W.replace('test "$(git rev-parse HEAD)" = "$EXPECTED_HEAD"',
                      "echo source-unchecked", 1), S))

    def test_absent_suite_is_not_optional(self):
        self.assertTrue(guard.validate_text(
            W.replace('test -s "$suite"', 'test -f "$suite"', 1), S))

    def test_operator_path_must_be_set(self):
        self.assertTrue(guard.validate_text(
            W.replace(guard.OPERATOR_REQUIRED, 'echo no-auth', 1), S))

    def test_operator_file_must_exist_and_be_nonempty(self):
        self.assertTrue(guard.validate_text(
            W.replace('test -s "$SKELETON_E2E_OPERATOR_TOKEN_FILE"',
                      'echo no-token', 1), S))

    def test_no_successful_skip(self):
        self.assertTrue(guard.validate_text(
            W.replace('node --test --test-reporter=spec "$suite"',
                      'exit 0', 1), S))

    def test_node_live_flag_cannot_be_disabled(self):
        self.assertTrue(guard.validate_text(
            W.replace('SKELETON_E2E_REQUIRE_FULL_LIVE: "1"',
                      'SKELETON_E2E_REQUIRE_FULL_LIVE: "0"', 1), S))

    def test_node_requires_real_live_base(self):
        self.assertTrue(guard.validate_text(
            W, S.replace(
                "assert.ok(BASE, 'full live E2E requires SKELETON_E2E_BASE_URL')",
                "assert.ok(true)")))

    def test_node_requires_authorized_operator(self):
        self.assertTrue(guard.validate_text(
            W, S.replace(
                "assert.ok(operatorToken, 'full live E2E requires authorized operator token')",
                "assert.ok(true)")))


if __name__ == "__main__":
    unittest.main()
