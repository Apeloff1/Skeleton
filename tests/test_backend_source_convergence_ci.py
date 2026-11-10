"""Adversarial source guards for draft-safe backend CI admission.

These tests deliberately mutate the workflow source, not production state.
All cases must fail closed before any trust or runtime qualification claim.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/check_backend_source_convergence.py"
spec = importlib.util.spec_from_file_location("backend_source_contract", PATH)
assert spec is not None and spec.loader is not None
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
SOURCE = (ROOT / ".github/workflows/backend-quality.yml").read_text(encoding="utf-8")


def mutate(old: str, new: str) -> list[str]:
    # Other existing workflow jobs use similar action/ref/environment strings.
    # Mutate the actual backend qualification job, never an unrelated lane.
    if old in ("  ruff:", "  backend_source_convergence:"):
        if SOURCE.count(old) != 1:
            raise AssertionError("canonical ruff fixture missing")
        return guard.validate_text(SOURCE.replace(old, new, 1))
    marker = "\n  backend_source_convergence:"
    if SOURCE.count(marker) != 1:
        raise AssertionError("expected exactly one backend source job")
    before, backend = SOURCE.split(marker, 1)
    if backend.count(old) < 1:
        raise AssertionError(f"backend source fixture missing: {old[:64]}")
    return guard.validate_text(before + marker + backend.replace(old, new, 1))


class BackendConvergenceAdmission(unittest.TestCase):
    def test_current_source_has_no_unqualified_admission(self):
        self.assertEqual(guard.validate_text(SOURCE), [])

    def test_empty_workflow_rejected(self):
        self.assertTrue(guard.validate_text(""))

    def test_invalid_yaml_rejected(self):
        self.assertTrue(guard.validate_text("jobs: ["))

    def test_oversized_source_rejected(self):
        self.assertTrue(guard.validate_text("A" * 200_001))

    def test_missing_source_lane_rejected(self):
        self.assertTrue(mutate("  backend_source_convergence:", "  removed_source_lane:"))

    def test_main_only_draft_skip_rejected(self):
        self.assertTrue(mutate(
            "if: github.event_name == 'pull_request' || github.event_name == 'workflow_dispatch'",
            "if: github.event_name == 'workflow_dispatch'"))

    def test_read_permission_must_remain(self):
        self.assertTrue(mutate(
            "    permissions:\n      contents: read",
            "    permissions:\n      contents: write"))

    def test_checkout_ref_can_not_fall_back_to_main(self):
        self.assertTrue(mutate("ref: " + guard.REF, "ref: main"))

    def test_checkout_credentials_not_persisted(self):
        self.assertTrue(mutate(
            "persist-credentials: false", "persist-credentials: true"))

    def test_checkout_revision_comparison_required(self):
        self.assertTrue(mutate(
            'test "$(git rev-parse HEAD)" = "$EXPECTED_HEAD"',
            "echo unverified revision"))

    def test_async_marker_plugin_mandatory(self):
        self.assertTrue(mutate(
            "-p pytest_asyncio.plugin", "-p missing_plugin"))

    def test_no_unapproved_python_test_plugin_autoload(self):
        self.assertTrue(mutate(
            'PYTEST_DISABLE_PLUGIN_AUTOLOAD: "1"',
            'PYTEST_DISABLE_PLUGIN_AUTOLOAD: "0"'))

    def test_jwt_import_cannot_be_dropped(self):
        self.assertTrue(mutate('"PyJWT==2.15.1"', '"PyJWT==0"'))

    def test_zstd_import_cannot_be_dropped(self):
        self.assertTrue(mutate('"zstandard==0.25.0"', '"zstandard==0"'))

    def test_hermetic_live_service_manifest_is_still_checked(self):
        self.assertTrue(mutate(
            "python backend/scripts/check_live_service_test_boundaries.py",
            "echo skipping-live-manifest"))

    def test_dns_pin_regressions_required(self):
        self.assertTrue(mutate(
            "backend/tests/test_free_api_dns_pin.py", "tests/not_dns.py"))

    def test_discourse_admission_redaction_regressions_required(self):
        self.assertTrue(mutate(
            "backend/tests/test_discourse_judge_admission.py",
            "tests/other.py"))

    def test_galaxy_budget_regressions_required(self):
        self.assertTrue(mutate(
            "backend/tests/test_galaxy_file_budget.py",
            "tests/other.py"))

    def test_no_successful_error_bypass(self):
        self.assertTrue(mutate(
            "python backend/scripts/check_live_service_test_boundaries.py",
            "python backend/scripts/check_live_service_test_boundaries.py || true"))

    def test_full_ruff_job_cannot_be_deleted(self):
        self.assertTrue(mutate("  ruff:", "  removed_ruff_job:"))


if __name__ == "__main__":
    unittest.main()
