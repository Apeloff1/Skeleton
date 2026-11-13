"""Review-only exact-head security gate admission contract for Dragon pilot.

The exception permits scanning the *single* internal draft PR; it cannot
claim merge readiness, grant action tokens or skip malware/artifact semantics.
Tests use only tracked workflow text and the standard library.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
BRANCH = "feat/dragon-research-pilot-qualification-20261112"
ADMISSION = (
    "github.event.pull_request.number == 5281"
    " && github.event.pull_request.head.repo.full_name == github.repository"
    f" && github.event.pull_request.head.ref == '{BRANCH}'"
)
ORIGINAL_DRAFT_EXCLUSION = (
    "github.event.action != 'converted_to_draft'"
    " && github.event.action != 'closed'"
)
SOURCE_IDENTITY = "ref: ${{ github.event.pull_request.head.sha || github.sha }}"
EXPECTED_HEAD = "EXPECTED_HEAD: ${{ github.event.pull_request.head.sha || github.sha }}"


class DragonPilotReleaseGateAdmissionTests(unittest.TestCase):
    def test_scans_are_admitted_for_only_the_bound_internal_draft(self):
        for name in ("malware-gate.yml", "artifact-policy.yml"):
            with self.subTest(workflow=name):
                text = (WORKFLOWS / name).read_text(encoding="utf-8")
                self.assertIn(ADMISSION, text)
                self.assertIn("!github.event.pull_request.draft || (", text)
                self.assertIn(ORIGINAL_DRAFT_EXCLUSION, text)
                self.assertIn("github.event_name != 'pull_request'", text)
                self.assertEqual(text.count("github.event.pull_request.number == 5281"), 1)
                self.assertEqual(text.count(BRANCH), 1)

    def test_no_security_scan_writes_or_unbound_source_checkout(self):
        for name in ("malware-gate.yml", "artifact-policy.yml"):
            with self.subTest(workflow=name):
                text = (WORKFLOWS / name).read_text(encoding="utf-8")
                self.assertIn("permissions:\n  contents: read\n", text)
                self.assertNotIn("contents: write", text)
                self.assertNotIn("pull-requests: write", text)
                self.assertNotIn("id-token: write", text)
                self.assertIn("persist-credentials: false", text)
                self.assertIn("fetch-depth: 0", text)
                self.assertIn(SOURCE_IDENTITY, text)
                self.assertIn(EXPECTED_HEAD, text)
                self.assertIn('test "$(git rev-parse HEAD)" = "$EXPECTED_HEAD"', text)
                self.assertNotIn("continue-on-error: true", text)

    def test_malware_proofs_remain_fully_enabled(self):
        text = (WORKFLOWS / "malware-gate.yml").read_text(encoding="utf-8")
        for required in (
            "python scripts/check_package_lifecycle.py",
            "python backend/scripts/check_malware_iocs.py",
            "python scripts/check_malware_policy.py --base",
            "python scripts/check_malware_policy.py --all",
            "test_malware_policy_streaming.py",
            "test_package_lifecycle_policy.py",
            "MALWARE_BASE:",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)

    def test_artifact_provenance_and_base_scan_remain_enabled(self):
        text = (WORKFLOWS / "artifact-policy.yml").read_text(encoding="utf-8")
        for required in (
            "python scripts/artifact_reference.py --check",
            "python scripts/check_artifact_policy.py --base",
            "python scripts/check_artifact_policy.py --all",
            "test_artifact_policy.py",
            "test_artifact_reference.py",
            "ARTIFACT_BASE:",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)

    def test_merging_and_release_are_still_independent(self):
        text = (WORKFLOWS / "merge-readiness.yml").read_text(encoding="utf-8")
        self.assertNotIn(ADMISSION, text)
        self.assertIn(
            "!github.event.pull_request.draft && github.event.action",
            text,
        )
        for name in ("malware-gate.yml", "artifact-policy.yml"):
            source = (WORKFLOWS / name).read_text(encoding="utf-8")
            self.assertNotIn("workflow_dispatch: {", source)
            self.assertNotIn("git push", source)
            self.assertNotIn("gh pr merge", source)


if __name__ == "__main__":
    unittest.main()
